"""Stance support follows installed turrets across UI, commands and equipment changes."""
from collections import deque
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from campaign_graph import find_unit
from constants import HullSize
from game_actions.unit_actions import handle_set_stance, handle_cycle_stance
from game_ai.contracts import Command
from game_ai.observation import build_observation
from geometry import Position
from save_manager import serialize_game_state, deserialize_game_state, serialize_unit
from tests.support.campaigns import campaign, ship
from tests.support.combat import create_combat_ship
from tests.support.commands import world, issue, waypoint
from turn_processor import TurnProcessor
from unit_components.constructor import Constructor
from unit_components.enums import UnitStance, TurretType
from unit_components.movement import Engines, Hyperdrive
from unit_components.strikecraft import StrikecraftBayComponent, StrikecraftWingComponent
from unit_components.weapons import Weapons, Turret
from unit_orders.base import Order, OrderType, OrderStatus
from unit_orders.movement import MoveOrder
from unit_orders.refit import RefitOrder


def arm(unit):
    weapons = Weapons(unit)
    weapons.add_turret(Turret(TurretType.MASS_DRIVER, 10, 100, 1, unit))
    unit.add_component(weapons)
    return weapons


@pytest.mark.parametrize('equipment', ['missing', 'empty', 'armed', 'damaged', 'cooling', 'zero_stats'])
def test_equipment_controls_stance_discovery_and_queries_are_read_only(equipment):
    game, player, _, unit = world()
    if equipment == 'missing':
        unit.remove_component(Weapons)
    elif equipment == 'empty':
        unit.add_component(Weapons(unit))
    elif equipment == 'damaged':
        unit.weapons_component.current_hit_points = 0
    elif equipment == 'cooling':
        unit.weapons_component.turrets[0].current_cooldown = 5
    elif equipment == 'zero_stats':
        unit.weapons_component.turrets[0].damage = 0
        unit.weapons_component.turrets[0].range = 0
    armed = equipment not in {'missing', 'empty'}
    before = serialize_unit(unit)
    commander = unit.commander_component
    assert commander.supports_stances is armed
    view = next(u for u in build_observation(game, player)['units'] if u['id'] == unit.id)
    for key in ('supported_commands', 'legal_commands', 'command_options'):
        assert ('set_stance' in view[key]) is armed
    expected = [s.value for s in commander.get_allowed_stances()] if armed else []
    assert view['capability_details']['allowed_stances'] == expected
    assert view['standing_order']['stance'] == 'do_nothing'
    assert view['standing_order']['engagement'] is None
    if not armed:
        assert commander.get_allowed_stances() == [UnitStance.DO_NOTHING]
    assert serialize_unit(unit) == before


def test_stance_scopes_keep_movement_requirements_and_carrier_does_not_inherit_wing_weapons():
    game, _, _, unit = world()
    unit.remove_component(Engines)
    assert unit.commander_component.get_allowed_stances() == [UnitStance.DO_NOTHING, UnitStance.ATTACK_WEAPON_RANGE]
    unit.add_component(Engines(unit, speed=100))
    unit.remove_component(Hyperdrive)
    assert unit.commander_component.get_allowed_stances() == [UnitStance.DO_NOTHING, UnitStance.ATTACK_WEAPON_RANGE, UnitStance.ATTACK_SAME_SECTOR]
    unit.remove_component(Weapons)
    bay = StrikecraftBayComponent(unit, max_slots=1)
    unit.add_component(bay)
    wing = create_combat_ship(game.galaxy, unit.owner, 'Wing', (0, 0))
    wing.hull_size = HullSize.STRIKECRAFT_WING
    wing.remove_component(Hyperdrive)
    wing.add_component(StrikecraftWingComponent(wing))
    assert wing.commander_component.supports_stances
    assert bay.dock(wing, game.galaxy)
    assert not unit.commander_component.supports_stances
    assert wing.commander_component.supports_stances


@pytest.mark.parametrize('change', ['remove', 'empty_replacement', 'empty_inventory'])
def test_losing_last_turret_releases_pursuit_before_movement(change):
    game, player, enemy, unit = world()
    create_combat_ship(game.galaxy, enemy, 'Target', (0, 0), pos=(1000, 0))
    commander = unit.commander_component
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    commander.update()
    attack = commander.standing_order.active_attack
    assert attack is not None and unit.engines_component.move_target is not None
    position, fuel = deepcopy(unit.position), unit.antimatter_component.current_amount
    if change == 'remove':
        unit.remove_component(Weapons)
    elif change == 'empty_replacement':
        unit.add_component(Weapons(unit))
    else:
        unit.weapons_component.turrets.clear()
    TurnProcessor(game)._process_movement(player)
    assert commander.stance == UnitStance.DO_NOTHING
    assert attack.status == OrderStatus.CANCELLED
    assert commander.standing_order.active_attack is None
    assert unit.engines_component.move_target is None
    assert unit.hyperdrive_component.hex_jump_target is None
    assert unit.position == position and unit.antimatter_component.current_amount == fuel


def test_weapon_damage_and_repair_preserve_policy_and_resume_acquisition():
    game, player, enemy, unit = world()
    target = create_combat_ship(game.galaxy, enemy, 'Target', (0, 0), pos=(1000, 0))
    commander = unit.commander_component
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    commander.update()
    weapons = unit.weapons_component
    weapons.current_hit_points = 0
    commander.prepare_for_movement()
    commander.update()
    assert commander.stance == UnitStance.ATTACK_SAME_SECTOR
    assert commander.standing_order.active_attack is None
    assert unit.engines_component.move_target is None
    assert all(t.target is None for t in weapons.turrets)
    assert issue(game, player, Command('set_stance', (unit.id,), stance='attack_same_sector')).accepted
    weapons.current_hit_points = 1
    commander.update()
    assert commander.standing_order.active_attack.parameters['target_unit_id'] == target.id


def test_refit_removal_preserves_explicit_work_and_rearming_starts_passive():
    game, player, _, unit = world()
    player.credits = 5000
    builder = create_combat_ship(game.galaxy, player, 'Constructor', (0, 0), pos=(50, 0))
    builder.add_component(Constructor(builder))
    commander = unit.commander_component
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    current = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0), 'destination_position': Position(900, 0)})
    queued = Order(unit, OrderType.TOGGLE_INHIBITOR)
    commander.add_order(current)
    commander.add_order(queued)
    movement = unit.engines_component.move_target
    refit = RefitOrder(builder, {'target_unit_id': unit.id, 'action': 'REMOVE', 'component_type': 'Weapons'})
    builder.commander_component.add_order(refit)
    game.sidebar_needs_update = False
    builder.constructor_component.update(game.galaxy)
    refit.check_completion_conditions()
    assert refit.status == OrderStatus.COMPLETED
    assert unit.weapons_component is None and game.sidebar_needs_update
    assert commander.stance == UnitStance.DO_NOTHING
    assert commander.current_order is current and list(commander.orders_queue) == [queued]
    assert unit.engines_component.move_target == movement
    arm(unit)
    assert commander.supports_stances and commander.stance == UnitStance.DO_NOTHING
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    arm(unit)
    assert commander.stance == UnitStance.ATTACK_SAME_SECTOR
    assert commander.current_order is current and list(commander.orders_queue) == [queued]


@pytest.mark.parametrize('stance', list(UnitStance))
def test_unarmed_stance_rejection_is_atomic_in_mixed_group(stance):
    game, player, _, armed = world()
    unarmed = create_combat_ship(game.galaxy, player, 'Unarmed', (0, 0))
    unarmed.remove_component(Weapons)
    for unit in (armed, unarmed):
        assert issue(game, player, Command('move', (unit.id,), **waypoint())).accepted
    before = [serialize_unit(u) for u in (armed, unarmed)]
    result = issue(game, player, Command('cancel_orders', (armed.id,)),
                   Command('set_stance', (armed.id, unarmed.id), stance=stance.value))
    assert not result.accepted and result.failure_stage == 'preflight'
    assert result.applied_count == 0 and result.errors[0].code == 'capability_unavailable'
    assert [serialize_unit(u) for u in (armed, unarmed)] == before
    assert issue(game, player, Command('clear_explicit_orders', (unarmed.id,))).accepted
    assert issue(game, player, Command('cancel_orders', (unarmed.id,))).accepted


def test_stance_commit_rechecks_equipment_and_reports_partial_failure(monkeypatch):
    game, player, _, unit = world()
    original = unit.commander_component.clear_explicit_orders

    def clear_and_lose_weapons():
        original()
        unit.remove_component(Weapons)

    monkeypatch.setattr(unit.commander_component, 'clear_explicit_orders', clear_and_lose_weapons)
    result = issue(game, player, Command('clear_explicit_orders', (unit.id,)),
                   Command('set_stance', (unit.id,), stance='attack_same_sector'),
                   Command('rename_unit', (unit.id,), new_name='Unattempted'))
    assert not result.accepted and result.failure_stage == 'commit'
    assert result.applied_count == 1 and result.requires_observation
    assert [op['status'] for op in result.operation_results] == ['applied', 'failed', 'unattempted']
    assert unit.name != 'Unattempted'
    assert unit.commander_component.stance == UnitStance.DO_NOTHING


@pytest.mark.parametrize('handler', [handle_set_stance, handle_cycle_stance])
def test_human_handlers_validate_stale_controls_and_accept_armed_policy(handler):
    game, player, _, unit = world()
    game.current_player_index = 0
    game.gui = Mock()
    assert issue(game, player, Command('move', (unit.id,), **waypoint())).accepted
    action = {'unit_id': unit.id, 'stance_display_name': UnitStance.ATTACK_SAME_SECTOR.display_name}
    handler(game, action)
    assert unit.commander_component.stance != UnitStance.DO_NOTHING
    game.gui.show_warning_dialog.assert_not_called()
    unit.remove_component(Weapons)
    before = serialize_unit(unit)
    handler(game, action)
    assert serialize_unit(unit) == before
    assert game.gui.show_warning_dialog.call_args.kwargs['title'] == 'Invalid Stance'


@pytest.mark.parametrize('armed', [False, True])
@pytest.mark.parametrize('viewer', ['owner', 'ally', 'enemy'])
def test_sidebar_hides_only_inapplicable_stance_sections(armed, viewer):
    game, player, enemy, unit = world()
    if not armed:
        unit.remove_component(Weapons)
    if viewer == 'ally':
        enemy.team_id = player.team_id
    game.current_player_index = 0 if viewer == 'owner' else 1
    game.gui = SimpleNamespace(is_section_expanded=lambda key: False)
    game._generate_order_data_recursive = lambda order, indent: order.order_type.name
    unit.commander_component.add_order(Order(unit, OrderType.TOGGLE_INHIBITOR))
    before = serialize_unit(unit)
    basic = unit.commander_component.get_basic_sidebar_data(game)
    expanded = unit.commander_component.get_sidebar_data(game)
    assert any('Stance:' in row.get('text', '') for row in basic) is (armed and viewer != 'enemy')
    assert any(row.get('text') == 'Stance Order:' for row in expanded) is (armed and viewer != 'enemy')
    assert any(row.get('action_id') == 'set_stance' for row in expanded) is (armed and viewer == 'owner')
    if viewer != 'enemy':
        assert any(row.get('text') == 'Current Order:' for row in expanded)
        assert any(row.get('text') == 'Queued Orders' for row in expanded)
    if viewer == 'owner':
        assert any(row.get('action_id') == 'stop_unit' for row in basic)
        assert any(row.get('action_id') == 'stop_unit' for row in expanded)
    assert serialize_unit(unit) == before


@pytest.mark.parametrize('equipment', ['missing', 'empty', 'armed', 'damaged'])
@pytest.mark.parametrize('weapons_first', [False, True])
@pytest.mark.parametrize('docked', [False, True])
def test_load_reconciles_stance_after_equipment_without_replaying_orders(equipment, weapons_first, docked):
    game = campaign()
    unit = ship(game, hull=HullSize.STRIKECRAFT_WING if docked else HullSize.HUGE)
    if equipment != 'missing':
        weapons = arm(unit)
        if equipment == 'empty':
            weapons.turrets.clear()
        elif equipment == 'damaged':
            weapons.current_hit_points = 0
    if docked:
        carrier = ship(game, 'Carrier')
        carrier.add_component(StrikecraftBayComponent(carrier, max_slots=1))
        unit.add_component(StrikecraftWingComponent(unit))
        assert carrier.strikecraft_bay_component.dock(unit, game.galaxy)
    # A current-format save may contain a pre-restriction unarmed stance.
    unit.commander_component.set_stance(UnitStance.ATTACK_WEAPON_RANGE)
    current = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0), 'destination_position': Position(400, 0)})
    queued = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0), 'destination_position': Position(600, 0)})
    unit.commander_component.current_order = current
    unit.commander_component.orders_queue = deque([queued])
    # Serialization preserves component insertion order, in either arrangement.
    unit.components = dict(sorted(unit.components.items(), key=lambda item: (item[0] is Weapons) != weapons_first))
    payload = serialize_game_state(game)
    fuel, credits = unit.antimatter_component.current_amount, unit.owner.credits
    history = deepcopy(unit.owner.order_history)
    assert deserialize_game_state(game, payload)
    restored = find_unit(game.galaxy, unit.id)
    commander = restored.commander_component
    expected = UnitStance.ATTACK_WEAPON_RANGE if equipment in {'armed', 'damaged'} else UnitStance.DO_NOTHING
    assert commander.stance == expected
    assert commander.standing_order.active_attack is None
    assert commander.current_order.public_id == current.public_id
    assert commander.current_order.status == OrderStatus.PENDING
    assert [o.public_id for o in commander.orders_queue] == [queued.public_id]
    assert restored.antimatter_component.current_amount == fuel
    assert restored.owner.credits == credits and restored.owner.order_history == history
    if docked:
        assert not find_unit(game.galaxy, carrier.id).commander_component.supports_stances
