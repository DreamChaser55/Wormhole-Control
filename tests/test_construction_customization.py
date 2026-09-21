"""Construction overrides preserve budgets, survive jobs, and enable fair counters."""
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import replace
from itertools import product
import json
from types import SimpleNamespace

import pytest

from campaign_graph import find_unit, iter_units
from construction_customization import customize_template, TURRET_TYPES, DEFENSE_TYPES
from constants import HullSize
from game_ai.contracts import Command, ContractError
from game_ai.observation import build_observation
from game_ai.order_view import order_layers
from geometry import Position
from player_controller import PlayerController
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from unit_catalog import describe_template
from unit_components.constructor import Constructor, assemble_unit_from_template, instantiate_unit_from_template
from unit_components.movement import Engines
from unit_components.defenses import Defenses
from unit_orders.base import OrderStatus
from unit_templates import UNIT_TEMPLATES


def world():
    game = campaign()
    game.gui = None
    game.players[0].credits = 100000
    game.players[0].controller = PlayerController.CODEX
    builder = ship(game, 'Builder')
    builder.add_component(Constructor(builder))
    builder.add_component(Engines(builder, speed=1000))
    return game, builder


def command(builder, **changes):
    return replace(Command('construct', (builder.id,), template_name='ARTILLERY_DREADNOUGHT',
                           system_name='Sol', hex_coord=(0, 0), position=(200, 0),
                           turret_type_override='beam', defense_type_override='shields'), **changes)


def finish(game, builder):
    from turn_processor import TurnProcessor
    for _ in range(150):
        TurnProcessor(game)._process_movement(builder.owner)
        builder.update()
        if builder.commander_component.current_order is None:
            break
    assert builder.commander_component.current_order is None


BUILDABLE = {key: value for key, value in UNIT_TEMPLATES.items()
             if value['hull_size'] != HullSize.STRIKECRAFT_WING}


@pytest.mark.parametrize('key', BUILDABLE)
def test_catalog_customizations_preserve_design_and_runtime_budgets(key):
    original = deepcopy(UNIT_TEMPLATES[key])
    game = campaign()
    base = assemble_unit_from_template(key, original, game.players[0], 'Sol', (0, 0), Position(0, 0), game)
    weapons = [None, *TURRET_TYPES] if original.get('has_weapon_bays') and original.get('turrets') else [None]
    defenses = [None, *DEFENSE_TYPES] if original.get('has_defenses') and sum(original.get(k, 0) for k in DEFENSE_TYPES) else [None]
    for weapon, defense in product(weapons, defenses):
        result = customize_template(original, weapon, defense)
        for field, value in original.items():
            if field not in {'turrets', *DEFENSE_TYPES}:
                assert result[field] == value
        description = describe_template(key, result)
        baseline = describe_template(key, original)
        for field in ('hull_used', 'credit_cost', 'turns', 'upkeep', 'hit_points'):
            assert description[field] == baseline[field]
        unit = assemble_unit_from_template(key, result, game.players[0], 'Sol', (0, 0), Position(0, 0), game)
        assert unit.current_hull_usage == base.current_hull_usage
        assert unit.name == base.name and unit.template_name == base.template_name
        assert [(type(c), c.hull_cost, c.max_hit_points) for c in unit.components.values()] == [
            (type(c), c.hull_cost, c.max_hit_points) for c in base.components.values()]
        if base.weapons_component:
            for actual, preset in zip(unit.weapons_component.turrets, base.weapons_component.turrets, strict=True):
                assert (actual.damage, actual.range, actual.cooldown, actual.variant) == (
                    preset.damage, preset.range, preset.cooldown, preset.variant)
                assert actual.turret_type.value == (weapon or preset.turret_type.value)
        if base.get_component(Defenses):
            strengths = {k: getattr(unit.get_component(Defenses), k) for k in DEFENSE_TYPES}
            expected = {k: getattr(base.get_component(Defenses), k) for k in DEFENSE_TYPES}
            if defense:
                expected = {k: sum(expected.values()) if k == defense else 0 for k in DEFENSE_TYPES}
            assert strengths == expected
    assert original == UNIT_TEMPLATES[key]


def test_copy_and_mixed_defense_consolidation():
    template = dict(has_defenses=True, armor=10, shields=20, point_defense=5,
                    has_weapon_bays=True, turrets=[dict(type='BEAM'), dict(type='MISSILE')])
    result = customize_template(template, 'mass_driver', 'shields')
    assert [result[k] for k in DEFENSE_TYPES] == [0, 35, 0]
    assert [t['type'] for t in result['turrets']] == ['MASS_DRIVER', 'MASS_DRIVER']
    assert [t['type'] for t in template['turrets']] == ['BEAM', 'MISSILE']
    assert customize_template(template) == template
    result['turrets'][0]['type'] = 'MISSILE'
    assert template['turrets'][0]['type'] == 'BEAM'


@pytest.mark.parametrize('field,value', [
    ('turret_type_override', 'BEAM'), ('turret_type_override', True), ('turret_type_override', []),
    ('defense_type_override', 'shield'), ('defense_type_override', 1), ('defense_type_override', ''),
])
def test_invalid_values_are_atomic_even_after_cancellation(field, value):
    game, builder = world()
    assert issue(game, builder.owner, command(builder)).accepted
    root = builder.commander_component.current_order
    credits = builder.owner.credits
    invalid = replace(command(builder), **{field: value})
    with pytest.raises(ContractError):
        Command.from_dict(invalid.to_dict())
    result = issue(game, builder.owner, Command('cancel_orders', (builder.id,)), invalid)
    assert not result.accepted
    assert builder.owner.credits == credits and builder.commander_component.current_order is root


@pytest.mark.parametrize('kind', ['move', 'rename_unit'])
def test_overrides_reject_unrelated_commands(kind):
    raw = dict(type=kind, unit_ids=[1], turret_type_override='beam',
               new_name='Ship' if kind == 'rename_unit' else None)
    if kind == 'move':
        raw.update(system_name='Sol', hex_coord=[0, 0], position=[0, 0])
    with pytest.raises(ContractError):
        Command.from_dict(raw)


@pytest.mark.parametrize('field', ['turret_type_override', 'defense_type_override'])
def test_missing_equipment_rejects_without_replacing_existing_job(field, monkeypatch):
    game, builder = world()
    assert issue(game, builder.owner, command(builder)).accepted
    root, credits = builder.commander_component.current_order, builder.owner.credits
    template = deepcopy(UNIT_TEMPLATES['PATROL_ESCORT'])
    if field == 'turret_type_override':
        template.update(has_weapon_bays=False, turrets=[])
    else:
        template.update(has_defenses=True, armor=0, shields=0, point_defense=0)
    monkeypatch.setitem(UNIT_TEMPLATES, 'NO_EQUIPMENT', template)
    result = issue(game, builder.owner, Command('cancel_orders', (builder.id,)),
                   command(builder, template_name='NO_EQUIPMENT'))
    assert not result.accepted and field in result.errors[0].message
    assert builder.commander_component.current_order is root and builder.owner.credits == credits


@pytest.mark.parametrize('phase', ['active', 'approaching', 'pending'])
def test_customized_build_roundtrip_and_completion(phase):
    game, builder = world()
    before = builder.owner.credits
    if phase == 'pending':
        assert issue(game, builder.owner, command(builder, template_name='PATROL_ESCORT',
                     turret_type_override='missile', defense_type_override='armor')).accepted
    build = command(builder, position=(2500, 0) if phase == 'approaching' else (200, 0), queue=phase == 'pending')
    assert issue(game, builder.owner, build).accepted
    paid = builder.owner.credits
    assert deserialize_game_state(game, serialize_game_state(game))
    builder = find_unit(game.galaxy, builder.id)
    assert builder.owner.credits == paid
    view = order_layers(builder, 'self', {builder.id}, set())
    shown = view['queued_orders'][0] if phase == 'pending' else view['current_order']
    assert shown['parameters']['turret_type_override'] == 'beam'
    assert shown['parameters']['defense_type_override'] == 'shields'
    allied = order_layers(builder, 'ally', {builder.id}, set())
    allied_order = allied['queued_orders'][0] if phase == 'pending' else allied['current_order']
    assert allied_order['parameters'] == shown['parameters']
    assert order_layers(builder, 'enemy', {builder.id}, set()) == {}
    finish(game, builder)
    units = [u for u, _ in iter_units(game.galaxy) if u.id != builder.id]
    assert len(units) == (2 if phase == 'pending' else 1)
    built = next(u for u in units if u.template_name == UNIT_TEMPLATES['ARTILLERY_DREADNOUGHT']['name'])
    assert all(t.turret_type.value == 'beam' for t in built.weapons_component.turrets)
    assert built.get_component(Defenses).armor == built.get_component(Defenses).point_defense == 0
    assert built.get_component(Defenses).shields == sum(UNIT_TEMPLATES['ARTILLERY_DREADNOUGHT'][k] for k in DEFENSE_TYPES)
    expected = UNIT_TEMPLATES['ARTILLERY_DREADNOUGHT']['build_cost']
    if phase == 'pending':
        first = next(u for u in units if u is not built)
        assert all(t.turret_type.value == 'missile' for t in first.weapons_component.turrets)
        assert first.get_component(Defenses).shields == first.get_component(Defenses).point_defense == 0
        expected += UNIT_TEMPLATES['PATROL_ESCORT']['build_cost']
    assert builder.owner.credits == before - expected
    assert deserialize_game_state(game, serialize_game_state(game))
    saved = find_unit(game.galaxy, built.id)
    assert saved.weapons_component.to_state() == built.weapons_component.to_state()
    assert saved.get_component(Defenses).to_state() == built.get_component(Defenses).to_state()


def test_group_builds_and_cancellation_refund_only_own_job():
    game, builder = world()
    other = ship(game, 'Other builder')
    other.add_component(Constructor(other))
    before = builder.owner.credits
    assert issue(game, builder.owner, command(builder, unit_ids=(builder.id, other.id))).accepted
    cost = UNIT_TEMPLATES['ARTILLERY_DREADNOUGHT']['build_cost']
    assert builder.owner.credits == before - 2 * cost
    assert issue(game, builder.owner, command(builder, queue=True, turret_type_override='missile')).accepted
    pending = builder.commander_component.orders_queue[0]
    assert issue(game, builder.owner, Command('cancel_order', (builder.id,), order_id=pending.public_id)).accepted
    assert builder.owner.credits == before - 2 * cost
    assert issue(game, builder.owner, Command('clear_explicit_orders', (builder.id,))).accepted
    assert builder.owner.credits == before - cost
    finish(game, other)
    built = [u for u, _ in iter_units(game.galaxy) if u.id not in {builder.id, other.id}]
    assert len(built) == 1 and all(t.turret_type.value == 'beam' for t in built[0].weapons_component.turrets)


@pytest.mark.parametrize('corruption', ['order', 'job', 'mismatch', 'missing', 'old_version'])
def test_saved_override_validation_is_transactional(corruption):
    game, builder = world()
    assert issue(game, builder.owner, command(builder)).accepted
    original = serialize_game_state(game)
    changed = deepcopy(original)
    def visit(value):
        if isinstance(value, dict):
            if value.get('order_type') == 'CONSTRUCT':
                if corruption == 'order':
                    value['parameters']['turret_type_override'] = 'laser'
                if corruption == 'missing':
                    value['parameters'].pop('turret_type_override')
            job = value.get('current_construction_target')
            if job and corruption in {'job', 'mismatch'}:
                job['turret_type_override'] = 'laser' if corruption == 'job' else 'missile'
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(changed)
    if corruption == 'old_version':
        changed['version'] = '4.11'
    assert not deserialize_game_state(game, changed)
    after = serialize_game_state(game)
    after.pop('timestamp')
    original.pop('timestamp')
    assert after == original


def test_lost_template_equipment_at_completion_fails_and_refunds_once(monkeypatch):
    game, builder = world()
    before = builder.owner.credits
    assert issue(game, builder.owner, command(builder)).accepted
    order = builder.commander_component.current_order
    template = deepcopy(UNIT_TEMPLATES['ARTILLERY_DREADNOUGHT'])
    template.update(has_weapon_bays=False, turrets=[])
    monkeypatch.setitem(UNIT_TEMPLATES, 'ARTILLERY_DREADNOUGHT', template)
    builder.constructor_component.finish_construction(game.galaxy)
    assert order.status == OrderStatus.FAILED and builder.owner.credits == before
    builder.constructor_component.finish_construction(game.galaxy)
    order.cancel()
    assert builder.owner.credits == before and len(list(iter_units(game.galaxy))) == 1


def test_queued_override_revalidates_before_payment(monkeypatch):
    game, builder = world()
    first = command(builder, template_name='PATROL_ESCORT')
    assert issue(game, builder.owner, first, command(builder, queue=True)).accepted
    pending = builder.commander_component.orders_queue[0]
    template = deepcopy(UNIT_TEMPLATES['ARTILLERY_DREADNOUGHT'])
    template.update(has_defenses=False)
    monkeypatch.setitem(UNIT_TEMPLATES, 'ARTILLERY_DREADNOUGHT', template)
    paid = builder.owner.credits
    finish(game, builder)
    assert pending.status == OrderStatus.FAILED and pending.failure_reason == 'invalid_parameters'
    assert builder.owner.credits == paid
    assert len(list(iter_units(game.galaxy))) == 2


def test_direct_start_rejects_invalid_override_before_payment():
    game, builder = world()
    before = builder.owner.credits
    assert not builder.constructor_component.start_construction(
        'PATROL_ESCORT', Position(200, 0), game.galaxy, system_name='Sol', hex_coord=(0, 0),
        turret_type_override='laser')
    assert builder.owner.credits == before
    assert builder.constructor_component.current_construction_target is None


def test_combat_observation_discloses_actual_equipment_only_in_detailed_view(monkeypatch):
    game, builder = world()
    enemy = instantiate_unit_from_template('COVERT_INTELLIGENCE_SHIP', game.players[1], 'Sol', (0, 0),
                                           Position(300, 0), game.galaxy, game,
                                           turret_type_override='missile', defense_type_override='point_defense')
    from visibility import VisibilityService
    monkeypatch.setattr(VisibilityService, 'compute', lambda *_, **__: SimpleNamespace(
        visible_enemy_unit_ids={enemy.id}, presence_hexes=set()))
    observed = build_observation(game, builder.owner)
    view = next(u for u in observed['units'] if u['id'] == enemy.id)
    assert set(view['capability_details']) == {'weapons', 'defenses'}
    weapon = view['capability_details']['weapons']['turrets'][0]
    assert weapon['type'] == 'missile' and weapon['damage'] == enemy.weapons_component.turrets[0].damage
    assert view['capability_details']['defenses']['point_defense'] == enemy.get_component(Defenses).point_defense
    for private in ('template_name', 'upkeep', 'current_order', 'queued_orders', 'standing_order'):
        assert private not in view
    assert 'IntelligenceComponent' not in view['components']
    assert 'target' not in weapon
    monkeypatch.setattr(VisibilityService, 'compute', lambda *_, **__: SimpleNamespace(
        visible_enemy_unit_ids=set(), presence_hexes={('Sol', (0, 0))}))
    hidden = build_observation(game, builder.owner)
    assert enemy.id not in {u['id'] for u in hidden['units']}


def test_socket_and_strict_provider_share_override_contract():
    from game_control_protocol import ControlService
    from game_ai.adapters.openai_responses import OpenAIResponsesProvider
    from game_ai.adapters.base import PlanningRequest
    from game_ai.runtime import get_runtime_config
    from tests.support.ai import EMPTY_PATCH
    game, builder = world()
    game.current_player = builder.owner
    service = ControlService(game, port=0)
    observed = service._dispatch_or_wait(dict(protocol_version=3, action='observe'), Future())
    raw = command(builder).to_dict()
    # Socket omissions and null are both supported.
    raw.pop('defense_type_override')
    reply = service._dispatch_or_wait(dict(protocol_version=3, action='command', request_id='override',
        turn_token=observed['data']['turn_token'], commands=[raw]), Future())
    assert reply['ok'] and reply['data']['accepted']
    assert builder.constructor_component.current_construction_target['defense_type_override'] is None
    output = dict(plan=[], commands=[command(builder).to_dict()], memory_patch=EMPTY_PATCH, end_turn=True)
    def create(**kwargs):
        schema = kwargs['text']['format']
        assert schema['strict'] and schema['name'] == 'wormhole_control_turn_v14'
        fields = schema['schema']['properties']['commands']['items']
        assert 'defense_type_override' in fields['required']
        assert fields['properties']['turret_type_override']['enum'] == [None, *TURRET_TYPES]
        return SimpleNamespace(id='fake', output_text=json.dumps(output), usage=None)
    provider = OpenAIResponsesProvider(client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    result = provider.plan_turn(PlanningRequest('campaign', 'agent', 'AI', 1, {}, {}), get_runtime_config('low'))
    assert result.plan.batch.commands[0] == command(builder)
    assert issue(game, builder.owner, *result.plan.batch.commands).accepted
    assert builder.constructor_component.current_construction_target['defense_type_override'] == 'shields'
