"""Resistance resolution, lifecycle and shared human/agent command contract."""
import copy
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from constants import HullSize, StarType, StormType, FieldDensity
from domain.celestials import Star, Storm, DebrisField
from environmental_resistance import SPECS, active_kinds, set_enabled, upkeep, retained_fraction
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch
from game_ai.observation import build_observation
from geometry import Position
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from turn_processor import TurnProcessor
from unit_components.abilities import AbilityComponent
from unit_components.abilities.base import AbilityInstance
from unit_components.antimatter import AntimatterStorage
from unit_components.enums import AbilityType, TurretType
from unit_components.movement import Engines


def equipped(game, owner=0, hull=HullSize.HUGE):
    unit = ship(game, owner=owner, hull=hull)
    unit.add_component(AntimatterStorage(unit, max_capacity=200))
    unit.add_component(Engines(unit, speed=100))
    unit.add_component(AbilityComponent(unit, [AbilityType(k) for k in SPECS]))
    return unit


def toggle(unit, kind='hazard_shielding', **kwargs):
    return Command(type='toggle_ability', unit_ids=(unit.id,), ability=kind, **kwargs)


def issue(game, *commands):
    return CommandGateway(game).apply_batch(game.players[0], CommandBatch(commands))


def source(game, kind):
    if kind in ('black_hole', 'pulsar'):
        body = Star('Sol', StarType[kind.upper()])
    elif kind == 'debris':
        body = DebrisField((0, 0), 'Sol', FieldDensity.HIGH)
    else:
        body = Storm((0, 0), 'Sol', StormType[kind.upper()])
    body.position = Position(0, 0)
    game.galaxy.systems['Sol'].add_celestial_body(body)
    return body


def phase(game, unit, speed=100):
    rng = SimpleNamespace(choice=lambda candidates: next((c for c in candidates if c is unit.sensors_component), candidates[0]))
    TurnProcessor(game, rng=rng)._process_environmental_hazards(unit.owner, {unit.id: speed})


@pytest.mark.parametrize('kind,ability,base,protected', [
    ('plasma', 'hazard_shielding', 8, 2),
    ('black_hole', 'hazard_shielding', 15, 3),
    ('debris', 'hazard_shielding', 3, 0),
    ('radiation', 'radiation_hardening', 4, 1),
    ('magnetic', 'antimatter_containment', 6, 1.5),
    ('pulsar', 'antimatter_containment', 10, 199 * .0125),
])
@pytest.mark.parametrize('enabled', [False, True])
def test_each_hazard_at_inclusive_boundary(kind, ability, base, protected, enabled):
    from celestial_descriptions import describe_body
    game = campaign()
    unit = equipped(game)
    body = source(game, kind)
    radius = describe_body(body).hazards[0].radius
    unit.position = Position(radius if radius is not None else 4500, 0)
    if enabled:
        assert issue(game, toggle(unit, ability)).accepted
    hp, component_hp = unit.current_hit_points, unit.sensors_component.current_hit_points
    phase(game, unit)
    expected = protected if enabled else base
    cost = SPECS[ability].upkeep if enabled else 0
    if kind in ('magnetic', 'pulsar'):
        assert unit.antimatter_component.current_amount == pytest.approx(200 - cost - expected)
    elif kind == 'radiation':
        assert component_hp - unit.sensors_component.current_hit_points == expected
        assert unit.current_hit_points == hp
    else:
        assert hp - unit.current_hit_points == expected


@pytest.mark.parametrize('kind', ['plasma', 'black_hole', 'debris', 'radiation', 'magnetic'])
def test_outside_boundary_charges_upkeep_without_damage(kind):
    from celestial_descriptions import describe_body
    game = campaign()
    unit = equipped(game)
    body = source(game, kind)
    unit.position = Position(describe_body(body).hazards[0].radius + .01, 0)
    for ability in SPECS:
        set_enabled(unit, ability, True)
    hp = unit.current_hit_points
    phase(game, unit)
    assert unit.current_hit_points == hp
    assert unit.antimatter_component.current_amount == 196


def test_upkeep_is_atomic_and_owner_specific_in_safe_space():
    game = campaign()
    unit, enemy = equipped(game), equipped(game, owner=1)
    for target in (unit, enemy):
        for kind in SPECS:
            set_enabled(target, kind, True)
    unit.antimatter_component.current_amount = 4
    phase(game, unit)
    assert unit.antimatter_component.current_amount == 0
    assert active_kinds(unit) == set(SPECS)
    assert enemy.antimatter_component.current_amount == 200
    unit.antimatter_component.current_amount = 3
    phase(game, unit)
    assert not active_kinds(unit)
    assert unit.antimatter_component.current_amount == 3


def test_movement_can_exhaust_upkeep_before_hazards_and_harvest_is_too_late():
    game = campaign()
    unit = equipped(game)
    source(game, 'plasma')
    assert issue(game, toggle(unit)).accepted
    unit.antimatter_component.current_amount = 1
    hp = unit.current_hit_points
    phase(game, unit)
    assert unit.current_hit_points == hp - 8
    assert unit.antimatter_component.current_amount == 1
    unit.antimatter_component.add(20)
    assert not active_kinds(unit)


def test_overlapping_hazards_charge_once_and_stack_with_forcefield():
    game = campaign()
    unit = equipped(game)
    source(game, 'plasma')
    source(game, 'plasma')
    set_enabled(unit, 'hazard_shielding', True)
    hp = unit.current_hit_points
    phase(game, unit)
    assert unit.current_hit_points == hp - 4
    assert unit.antimatter_component.current_amount == 198
    unit.damage_reduction = .75
    phase(game, unit)
    assert unit.current_hit_points == hp - 4
    assert unit.antimatter_component.current_amount == 196


def test_fuel_clamping_and_pulsars_use_remaining_fuel():
    game = campaign()
    unit = equipped(game)
    source(game, 'magnetic')
    source(game, 'pulsar')
    set_enabled(unit, 'antimatter_containment', True)
    phase(game, unit)
    assert unit.antimatter_component.current_amount == pytest.approx((199 - 1.5) * .9875)
    unit.antimatter_component.current_amount = 1.25
    phase(game, unit)
    assert unit.antimatter_component.current_amount == 0


def test_radiation_prerequisite_destruction_removes_protection_for_next_source():
    game = campaign()
    unit = equipped(game)
    source(game, 'radiation')
    source(game, 'plasma')
    for kind in SPECS:
        set_enabled(unit, kind, True)
    unit.antimatter_component.current_hit_points = 1
    hp = unit.current_hit_points
    rng = SimpleNamespace(choice=lambda candidates: unit.antimatter_component)
    TurnProcessor(game, rng=rng)._process_environmental_hazards(unit.owner)
    assert unit.antimatter_component.is_destroyed
    assert not active_kinds(unit)
    assert unit.current_hit_points == hp - 8


@pytest.mark.parametrize('action', ['storage_removed', 'abilities_refitted', 'disabled', 'destroyed'])
def test_lifecycle_shutdown_without_automatic_reactivation(action):
    game = campaign()
    unit = equipped(game)
    set_enabled(unit, 'hazard_shielding', True)
    old = unit.ability_component
    if action == 'storage_removed':
        unit.remove_component(AntimatterStorage)
        unit.add_component(AntimatterStorage(unit))
    elif action == 'abilities_refitted':
        unit.add_component(AbilityComponent(unit, [AbilityType.HAZARD_SHIELDING]))
    elif action == 'disabled':
        from timed_effects import add, remove
        add(unit, 900, AbilityType.ION_BOLT, 'disable')
        remove(unit, 900, AbilityType.ION_BOLT)
    else:
        unit.destroy()
    assert not any(i.is_active for i in old.abilities.values())
    assert not active_kinds(unit)


def test_toggle_preserves_orders_and_stance_and_repeated_toggles_project():
    game = campaign()
    unit = equipped(game)
    from unit_orders.movement import MoveOrder
    order = MoveOrder(unit, {'target_position': Position(500, 0)})
    unit.commander_component.orders_queue.append(order)
    stance = unit.commander_component.stance
    assert issue(game, toggle(unit), toggle(unit)).accepted
    assert not active_kinds(unit)
    assert list(unit.commander_component.orders_queue) == [order]
    assert unit.commander_component.stance == stance
    assert unit.antimatter_component.current_amount == 200


def test_combined_affordability_rejection_is_atomic():
    game = campaign()
    unit = equipped(game)
    unit.antimatter_component.current_amount = 2
    result = issue(game, toggle(unit), toggle(unit, 'radiation_hardening'))
    assert not result.accepted
    assert result.errors[0].code == 'insufficient_resources'
    assert not active_kinds(unit)
    assert unit.antimatter_component.current_amount == 2
    assert issue(game, toggle(unit), toggle(unit), toggle(unit, 'radiation_hardening')).accepted
    assert active_kinds(unit) == {'radiation_hardening'}


@pytest.mark.parametrize('change', ['queue', 'target', 'foreign', 'missing', 'cast'])
def test_invalid_toggle_requests_do_not_mutate(change):
    game = campaign()
    unit = equipped(game)
    command = toggle(unit)
    if change == 'queue':
        command = replace(command, queue=True)
    elif change == 'target':
        command = replace(command, target_id=unit.id)
    elif change == 'foreign':
        command = replace(command, unit_ids=(equipped(game, owner=1).id,))
    elif change == 'missing':
        command = replace(command, ability='adaptive_forcefield')
    else:
        command = replace(command, type='use_ability')
    assert not issue(game, command).accepted
    assert not active_kinds(unit)


def test_save_restore_preserves_enabled_state_without_charging_or_expiring():
    game = campaign()
    unit = equipped(game)
    assert issue(game, toggle(unit)).accepted
    unit.ability_component.update(game.galaxy)
    assert active_kinds(unit) == {'hazard_shielding'}
    state = serialize_game_state(game)
    assert state['version'] == '4.14'
    restored = campaign()
    assert deserialize_game_state(restored, json.loads(json.dumps(state)))
    loaded = restored.galaxy.get_unit_by_id(unit.id)
    assert active_kinds(loaded) == {'hazard_shielding'}
    assert loaded.antimatter_component.current_amount == 200


@pytest.mark.parametrize('field,value', [('activation_mode', 'invalid'), ('activation_mode', 'cast'),
                                        ('ongoing_antimatter', -1), ('ongoing_antimatter', True),
                                        ('ongoing_antimatter', float('nan')), ('ongoing_antimatter', 0)])
def test_saved_definition_validation(field, value):
    game = campaign()
    unit = equipped(game)
    state = copy.deepcopy(unit.ability_component.abilities[AbilityType.HAZARD_SHIELDING].to_state())
    state['definition'][field] = value
    with pytest.raises(ValueError):
        AbilityInstance.from_state(state)


@pytest.mark.parametrize('field,value', [('cooldown_remaining', 1), ('duration_remaining', 1),
                                        ('target_unit_id', 0), ('spawned_unit_ids', [0])])
def test_saved_toggle_cannot_have_cast_runtime(field, value):
    game = campaign()
    unit = equipped(game)
    state = unit.ability_component.abilities[AbilityType.HAZARD_SHIELDING].to_state()
    state['runtime'][field] = value
    with pytest.raises(ValueError):
        AbilityInstance.from_state(state)


@pytest.mark.parametrize('field,value', [('duration', 1), ('range', 1), ('antimatter_cost', 1),
                                        ('requires_target_unit', True)])
def test_saved_toggle_cannot_become_a_cast(field, value):
    game = campaign()
    unit = equipped(game)
    state = unit.ability_component.abilities[AbilityType.HAZARD_SHIELDING].to_state()
    state['definition'][field] = value
    with pytest.raises(ValueError):
        AbilityInstance.from_state(state)


def test_ui_observation_and_logistics_share_toggle_rules():
    from antimatter_logistics import equipment_upkeep
    from gui.unit_editor_gui.descriptions import ability_description
    from tactical_ui import handle_action
    game = campaign()
    unit = equipped(game)
    handle_action(game, {'action': 'toggle_resistance_ability',
                        'target_data': {'unit_id': unit.id, 'ability': 'hazard_shielding'}})
    assert upkeep(unit) == equipment_upkeep(unit) == 2
    rows = unit.ability_component.get_sidebar_data(game)
    assert any(row.get('text') == 'Hazard Shielding: Active' for row in rows)
    assert any(row.get('text') == 'Disable (2 AM/turn)' for row in rows)
    assert 'Until disabled' in ability_description('hazard_shielding')[1]
    observation = build_observation(game, unit.owner)
    owned = next(u for u in observation['units'] if u['id'] == unit.id)
    assert 'toggle_ability' in owned['legal_commands']
    assert owned['environmental_resistances']['ongoing_antimatter'] == 2
    assert not set(SPECS) & set(owned['command_options']['use_ability']['values'])


def test_protection_does_not_reduce_combat_or_wormhole_damage():
    game = campaign()
    unit = equipped(game)
    set_enabled(unit, 'hazard_shielding', True)
    hp = unit.current_hit_points
    unit.take_damage(8, TurretType.MASS_DRIVER)
    unit.take_damage(8, cause='wormhole instability')
    assert unit.current_hit_points == hp - 16
    assert retained_fraction(unit, 'wormhole instability') == 1


def test_capture_turns_protection_off():
    from unit_components.abilities.capture_unit import CaptureUnitAbility
    from unit_components.marines import MarinesComponent
    game = campaign()
    caster, target = equipped(game), equipped(game, owner=1)
    caster.add_component(MarinesComponent(caster, marines_count=100))
    set_enabled(target, 'hazard_shielding', True)
    target.engines_component.current_hit_points = 0
    assert CaptureUnitAbility().on_activate(caster.ability_component, game.galaxy, target.id)
    assert target.owner == caster.owner
    assert not active_kinds(target)


def test_hiding_and_docking_clear_enabled_state():
    from constants import PlanetType
    from domain.celestials import Planet
    from unit_components.hangar import HangarComponent
    game = campaign()
    unit = equipped(game)
    body = Planet((0, 0), 'Sol', planet_type=PlanetType.GAS_GIANT)
    body.position = Position(0, 0)
    game.galaxy.systems['Sol'].add_celestial_body(body)
    set_enabled(unit, 'hazard_shielding', True)
    assert body.hide_unit(unit, game.galaxy)
    assert not active_kinds(unit)
    # Docking remains defensive even for a runtime craft outside Designer rules.
    craft = equipped(game, hull=HullSize.TINY)
    carrier = equipped(game)
    carrier.add_component(HangarComponent(carrier, max_slots=2))
    set_enabled(craft, 'hazard_shielding', True)
    assert carrier.hangar_component.dock(craft, game.galaxy)
    assert not active_kinds(craft)


def test_earlier_cast_spending_changes_toggle_affordability_atomically():
    game = campaign()
    unit = equipped(game)
    unit.add_component(AbilityComponent(unit, [AbilityType.HAZARD_SHIELDING, AbilityType.ADAPTIVE_FORCEFIELD]))
    unit.antimatter_component.current_amount = 21
    result = issue(game, Command(type='use_ability', unit_ids=(unit.id,), ability='adaptive_forcefield'), toggle(unit))
    assert not result.accepted
    assert result.errors[-1].code == 'insufficient_resources'
    assert not active_kinds(unit)
    assert unit.antimatter_component.current_amount == 21
    assert unit.damage_reduction == 0


def test_future_resupply_cannot_finance_toggle():
    game = campaign()
    unit, donor = equipped(game), equipped(game)
    unit.antimatter_component.current_amount = 0
    result = issue(game, Command(type='take_antimatter', unit_ids=(unit.id,), target_id=donor.id, queue=True), toggle(unit))
    assert not result.accepted
    assert not active_kinds(unit)
    assert unit.antimatter_component.current_amount == 0


def test_observation_preserves_enemy_boundary_and_exposes_allied_state():
    game = campaign()
    owned, other = equipped(game), equipped(game, owner=1)
    owned.sensors_component.short_range_radius = 5000
    set_enabled(other, 'radiation_hardening', True)
    observed = build_observation(game, owned.owner)
    enemy = next(u for u in observed['units'] if u['id'] == other.id)
    assert 'environmental_resistances' not in enemy
    assert 'ability_states' not in enemy
    other.owner.team_id = owned.owner.team_id = 5
    observed = build_observation(game, owned.owner)
    ally = next(u for u in observed['units'] if u['id'] == other.id)
    assert ally['environmental_resistances']['abilities']['radiation_hardening']['active']


@pytest.mark.parametrize('density', list(FieldDensity))
def test_all_debris_densities_round_to_zero_without_changing_drag(density):
    from environmental_effects import modifiers_for_unit
    game = campaign()
    unit = equipped(game)
    body = DebrisField((0, 0), 'Sol', density)
    body.position = Position(0, 0)
    game.galaxy.systems['Sol'].add_celestial_body(body)
    before = modifiers_for_unit(unit)
    set_enabled(unit, 'hazard_shielding', True)
    hp = unit.current_hit_points
    phase(game, unit)
    assert unit.current_hit_points == hp
    assert modifiers_for_unit(unit) == before


@pytest.mark.parametrize('ability', list(SPECS))
def test_designer_requires_storage_and_valid_hull(ability):
    from custom_unit_templates import CustomUnitTemplate
    design = CustomUnitTemplate('Resistance', HullSize.HUGE)
    design.components.has_ability_component = True
    design.components.abilities = [ability]
    assert any('has_antimatter_storage' in error for error in design.validate())
    design.components.has_antimatter_storage = True
    design.components.antimatter_capacity = 200
    assert not design.validate()
    for hull in (HullSize.TINY, HullSize.STRIKECRAFT_WING):
        design.hull_size = hull
        assert design.validate()


def test_full_owner_turn_charges_once_before_harvesting():
    from unit_components.antimatter import AntimatterHarvester
    game = campaign()
    unit = equipped(game)
    unit.add_component(AntimatterHarvester(unit))
    body = source(game, 'pulsar')
    body.position = Position(0, 0)
    unit.position = Position(1000, 0)
    unit.antimatter_component.current_amount = 1
    set_enabled(unit, 'antimatter_containment', True)
    TurnProcessor(game).process_player_turn(unit.owner)
    # The 1 AM upkeep consumes the seed before the pulsar; harvest happens later.
    expected = unit.harvester_component.harvest_rate * body.harvest_multiplier
    assert unit.antimatter_component.current_amount == expected
    assert active_kinds(unit) == {'antimatter_containment'}


@pytest.mark.parametrize('size', [(1280, 720), (1920, 1080), (2560, 1440)])
def test_toggle_controls_fit_sidebar_and_preserve_payload(pygame_context, size):
    import pygame
    from display_config import DisplayConfig
    from gui.theme_loader import build_ui_manager
    from gui.sidebar.view import _build_button
    from gui.dynamic_actions import build_button_payload
    config = DisplayConfig(*size)
    pygame.display.set_mode(size)
    gui = SimpleNamespace(manager=build_ui_manager(config), dynamic_button_actions={}, side_bar_dynamic_elements=[])
    game = campaign()
    unit = equipped(game)
    for row in unit.ability_component.get_sidebar_data(game):
        if row.get('action_id') != 'toggle_resistance_ability':
            continue
        _build_button(gui, row, 0, 0, config.info_box_width - 40, 28, None, row['object_id'])
        button = gui.side_bar_dynamic_elements[-1]
        assert button.font.get_rect(button.text).width < button.get_relative_rect().width - 10
        payload = build_button_payload(gui, row['action_id'], row['target_data'])
        assert payload['target_data'] == row['target_data']
        assert payload['action'] == 'toggle_resistance_ability'
    assert len(gui.dynamic_button_actions) == 3
