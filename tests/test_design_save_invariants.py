"""Accepted designs and refits must produce reloadable equipment."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from campaign_persistence import prepare_campaign
from constants import HullSize
from custom_unit_templates import ComponentConfig, CustomTemplateManager, CustomUnitTemplate, TurretConfig
from geometry import Position
from save_manager import serialize_game_state
from tests.support.campaigns import campaign, ship
from unit_components.constructor import Constructor
from unit_components.enums import TurretType, TurretVariant
from unit_components.weapons import Turret
from unit_orders.construction import ConstructOrder
from unit_orders.refit import RefitOrder
from unit_template_validation import FIXED_HULL_COST_FIELDS
from unit_templates import PRIVATE_TEMPLATES


@pytest.mark.parametrize('field,value', [
    ('damage', '-1'), ('range', '-1'), ('cooldown', '-1'),
    ('damage', 'nan'), ('range', 'inf'), ('cooldown', '1.5'), ('damage', 'bad'),
])
def test_editor_rejects_invalid_turret_without_changing_design(field, value):
    from gui.unit_editor_gui.turret_editor import do_add_turret
    values = dict(damage='1', range='100', cooldown='0')
    values[field] = value
    def entry(text):
        return SimpleNamespace(get_text=lambda: text)
    existing = TurretConfig('BEAM', 1, 100, 0)
    comp = ComponentConfig(has_weapon_bays=True, turrets=[existing])
    editor = SimpleNamespace(_turret_type_dd=None, _turret_variant_dd=None,
        _turret_dmg_entry=entry(values['damage']), _turret_range_entry=entry(values['range']),
        _turret_cd_entry=entry(values['cooldown']), _turrets=comp.turrets, _comp=comp,
        _set_status=Mock())
    do_add_turret(editor)
    assert comp.turrets == [existing]
    message = editor._set_status.call_args
    assert field in message.args[0] and message.kwargs['error']


@pytest.mark.parametrize('field', ['damage', 'range', 'cooldown', *FIXED_HULL_COST_FIELDS])
def test_invalid_design_save_preserves_library_and_registry(tmp_path, field):
    manager = CustomTemplateManager(data_file=tmp_path / 'designs.json')
    valid = CustomUnitTemplate('Saved', HullSize.MEDIUM,
        ComponentConfig(has_weapon_bays=True, turrets=[TurretConfig('BEAM', 1, 100, 0)]))
    assert manager.save_design(valid) == []
    before = manager.data_file.read_bytes(), deepcopy(PRIVATE_TEMPLATES)
    invalid = deepcopy(valid)
    if field in ('damage', 'range', 'cooldown'):
        setattr(invalid.components.turrets[0], field, -1)
    else:
        setattr(invalid.components, field, -1)
    assert any(field in e for e in manager.save_design(invalid, original_name='Saved'))
    assert manager.designs['Saved'] == valid
    assert (manager.data_file.read_bytes(), PRIVATE_TEMPLATES) == before


@pytest.mark.parametrize('variant', ['STANDARD', 'LONG_RANGE', 'ANTI_STRIKECRAFT'])
@pytest.mark.parametrize('stats', [(0, 0, 0), (1.25, 100.5, 2)])
@pytest.mark.parametrize('route', ['construct', 'refit'])
def test_accepted_equipment_roundtrips_through_campaign(tmp_path, variant, stats, route):
    game = campaign()
    player = game.players[0]
    player.credits = 10000
    actor = ship(game, name='Constructor')
    actor.add_component(Constructor(actor))
    turret = dict(type='BEAM', damage=stats[0], range=stats[1], cooldown=stats[2], variant=variant)
    if route == 'construct':
        design = CustomUnitTemplate('Reloadable', HullSize.MEDIUM,
            ComponentConfig(has_weapon_bays=True, turrets=[TurretConfig('BEAM', *stats, variant=variant)],
                            has_constructor_component=True, constructor_hull_cost=0))
        manager = CustomTemplateManager(data_file=tmp_path / 'designs.json')
        assert manager.save_design(design) == []
        order = ConstructOrder(actor, dict(unit_template_name='Reloadable', target_system_name='Sol',
            target_hex_coord=(0, 0), target_position=Position(100, 0)))
        actor.commander_component.add_order(order)
        assert order.status.name == 'IN_PROGRESS'
        actor.constructor_component.finish_construction(game.galaxy)
        target = next(u for u in game.galaxy.systems['Sol'].hexes[(0, 0)].units if u is not actor)
        assert target.constructor_component.hull_cost == 0
    else:
        target = ship(game, name='Refitted')
        target.antimatter_component.max_capacity = target.antimatter_component.current_amount = 200
        order = RefitOrder(actor, dict(target_unit_id=target.id, component_type='Weapons',
            component_config={'turrets': [turret]}, action='ADD'))
        actor.commander_component.add_order(order)
        assert order.status.name == 'IN_PROGRESS'
        actor.constructor_component.finish_refit(game.galaxy)
    assert player.credits < 10000
    expected = (stats[0], stats[1] * (3 if variant == 'LONG_RANGE' else 1),
                stats[2] * (3 if variant == 'LONG_RANGE' else 1))
    for _ in range(2):
        prepared = prepare_campaign(json.loads(json.dumps(serialize_game_state(game))))
        game = prepared.state
        restored = game.galaxy.get_unit_by_id(target.id).weapons_component.turrets[0]
        assert (restored.damage, restored.range, restored.cooldown) == expected
        assert restored.variant.name == variant
        assert restored.current_cooldown == 0


@pytest.mark.parametrize('field', ['damage', 'range', 'cooldown', 'current_cooldown'])
@pytest.mark.parametrize('value', [-1, True, float('inf')])
def test_turret_restore_keeps_strict_numeric_invariants(field, value):
    unit = ship(campaign())
    state = Turret(TurretType.BEAM, 1, 100, 0, unit, TurretVariant.STANDARD).to_state()
    state[field] = value
    with pytest.raises(ValueError, match=field):
        Turret.from_state(state, unit)
