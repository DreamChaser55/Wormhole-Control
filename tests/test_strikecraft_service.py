"""Endurance is authoritative, owner-turn based, and independent of controllers."""
from copy import deepcopy
import json
import random

import pytest

from campaign_graph import is_deployed
from campaign_persistence import prepare_campaign
from domain.players import Player
from events import CancelOrdersEvent
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch
from game_ai.observation import build_observation
from geometry import Position
from order_system import OrderSystem
from save_manager import serialize_game_state, deserialize_game_state
from strikecraft_service import process, required
from tests.test_carrier_abilities import scenario, issue
from turn_processor import TurnProcessor
from unit_components.enums import UnitStance
from unit_orders.base import OrderType, OrderStatus, Order
from unit_orders.combat import AttackOrder
from unit_orders.movement import MoveOrder


def world():
    game, carrier, wing, fighter, target, enemy_wing = scenario()
    wing.position = Position(1200, 0)
    return game, carrier, wing


def apply(game, *commands):
    return CommandGateway(game).apply_batch(game.players[0], CommandBatch(commands))


def next_resolution(game, wing):
    game.turn_number += 1
    process(game, wing.owner, advance=True)


@pytest.mark.parametrize('players', [2, 3, 4, 5, 6])
def test_endurance_counts_only_owner_resolutions_once_per_round(players):
    game, carrier, wing = world()
    game.players.extend(Player(f'Extra {i}', (20, 30, 40)) for i in range(players - 2))
    comp = wing.strikecraft_wing_component
    for _ in range(79):
        for player in game.players:
            process(game, player, advance=True)
        process(game, wing.owner, advance=True)
        game.turn_number += 1
    assert comp.turns_outside == 79 and not required(wing)
    process(game, wing.owner, advance=True)
    assert comp.turns_outside == 80 and required(wing)
    assert wing.commander_component.current_order.order_type == OrderType.RETURN_FOR_SERVICE
    next_resolution(game, wing)
    assert comp.turns_outside == 80 and is_deployed(wing, game.galaxy)


def test_return_replaces_orders_and_moves_before_combat():
    game, carrier, wing = world()
    target = next(u for u, _ in game.galaxy.systems['Sol'].get_all_units() if u.name == 'Enemy ship')
    target.position = Position(1250, 0)
    commander = wing.commander_component
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    attack = AttackOrder(wing, {'target_unit_id': target.id})
    commander.add_order(attack)
    queued = MoveOrder(wing, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
                             'destination_position': Position(2000, 0)})
    commander.add_order(queued)
    wing.strikecraft_wing_component.turns_outside = 79
    hp = target.current_hit_points
    TurnProcessor(game).process_player_turn(wing.owner)
    assert wing.position.x < 1200
    assert target.current_hit_points == hp
    assert attack.status == queued.status == OrderStatus.CANCELLED
    assert not commander.orders_queue and commander.stance == UnitStance.ATTACK_SAME_SECTOR
    assert commander.get_active_attack_order() is None


@pytest.mark.parametrize('kind', ['cancel_orders', 'clear_explicit_orders', 'cancel_order', 'set_stance', 'move', 'dock_in_strikecraft_bay'])
def test_gateway_cannot_override_return_and_rejects_batch_atomically(kind):
    game, carrier, wing = world()
    wing.strikecraft_wing_component.turns_outside = 79
    process(game, wing.owner, advance=True)
    root = wing.commander_component.current_order
    kwargs = {'order_id': root.public_id} if kind == 'cancel_order' else {'stance': 'do_nothing'} if kind == 'set_stance' else (
        {'system_name': 'Sol', 'hex_coord': (0, 0), 'position': (2000, 0)} if kind == 'move' else
        {'target_id': carrier.id} if kind == 'dock_in_strikecraft_bay' else {})
    result = apply(game, Command('rename_unit', (carrier.id,), new_name='Changed'), Command(kind, (wing.id,), **kwargs))
    assert not result.accepted and result.errors[0].code == 'wing_service_required'
    assert carrier.name == 'Carrier' and wing.commander_component.current_order is root
    assert apply(game, Command('rename_unit', (wing.id,), new_name='Returning wing')).accepted


def test_commander_and_human_mixed_selection_cannot_override_return():
    from unittest.mock import Mock
    game, carrier, wing = world()
    wing.commander_component.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    wing.strikecraft_wing_component.turns_outside = 79
    process(game, wing.owner, advance=True)
    commander = wing.commander_component
    root = commander.current_order
    target = wing.engines_component.move_target
    commander.stop_and_idle()
    commander.clear_explicit_orders()
    commander.set_stance(UnitStance.DO_NOTHING)
    assert not commander.cancel_order(root.local_order_id)
    rejected = MoveOrder(wing, {})
    commander.add_order(rejected)
    assert rejected.failure_reason == 'wing_service_required'
    system = OrderSystem(game, Mock())
    carrier.commander_component.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    system.handle_cancel_orders(CancelOrdersEvent([wing, carrier]))
    assert commander.current_order is root and wing.engines_component.move_target == target
    assert commander.stance == UnitStance.ATTACK_SAME_SECTOR
    assert carrier.commander_component.stance == UnitStance.DO_NOTHING


@pytest.mark.parametrize('loss', ['orphan', 'destroyed', 'captured', 'sector', 'bay', 'disabled_carrier', 'disabled_wing', 'engines', 'path'])
def test_expiration_at_limit_without_new_orphan_timer(loss, monkeypatch):
    game, carrier, wing = world()
    wing.strikecraft_wing_component.turns_outside = 78
    process(game, wing.owner, advance=True)
    if loss == 'orphan':
        carrier.strikecraft_bay_component.release_wing(wing)
    elif loss == 'destroyed':
        carrier.destroy()
    elif loss == 'captured':
        carrier.owner = game.players[1]
    elif loss == 'sector':
        game.galaxy.systems['Sol'].remove_unit(carrier)
        carrier.in_hex = (1, 0)
        game.galaxy.systems['Sol'].add_unit(carrier)
    elif loss == 'bay':
        carrier.strikecraft_bay_component.current_hit_points = 0
    elif loss == 'disabled_carrier':
        carrier.is_disabled = True
    elif loss == 'disabled_wing':
        wing.is_disabled = True
    elif loss == 'engines':
        wing.engines_component.current_hit_points = 0
    else:
        monkeypatch.setattr('antimatter_logistics.estimate_approach', lambda *a, **k: None)
    assert is_deployed(wing, game.galaxy) and wing.strikecraft_wing_component.turns_outside == 79
    next_resolution(game, wing)
    assert not is_deployed(wing, game.galaxy) and wing._destroyed
    assert carrier.strikecraft_bay_component.slot_for_wing(wing) is None


def test_return_follows_carrier_and_docking_resets_endurance_and_locks_launch():
    game, carrier, wing = world()
    bay = carrier.strikecraft_bay_component
    slot = bay.slot_for_wing(wing)
    wing.strikecraft_wing_component.turns_outside = 79
    process(game, wing.owner, advance=True)
    root = wing.commander_component.current_order
    old_child = root.sub_orders[0]
    carrier.position = Position(100, 200)
    process(game, wing.owner)
    assert root.sub_orders[0] is not old_child
    assert old_child.status == OrderStatus.CANCELLED
    wing.position = Position(200, 200)  # Inclusive docking boundary.
    credits = wing.owner.credits
    cooldown = wing.weapons_component.turrets[0].current_cooldown
    process(game, wing.owner)
    assert wing in bay.docked_units and bay.slot_for_wing(wing) == slot
    assert wing.strikecraft_wing_component.turns_outside == 0 and not required(wing)
    assert wing.owner.credits == credits and wing.weapons_component.turrets[0].current_cooldown == cooldown
    assert not bay.deploy(wing, game.galaxy)
    process(game, wing.owner, advance=True)
    assert wing.strikecraft_wing_component.turns_outside == 0
    game.turn_number += 1
    assert bay.deploy(wing, game.galaxy)
    process(game, wing.owner, advance=True)
    assert wing.strikecraft_wing_component.turns_outside == 1


@pytest.mark.parametrize('bulk', [False, True])
def test_dock_then_relaunch_batch_is_atomic(bulk):
    game, carrier, wing = world()
    wing.position = Position(150, 0)
    command = Command('deploy_all_wings', (carrier.id,)) if bulk else Command('deploy_unit', (carrier.id,), target_id=wing.id)
    result = apply(game, Command('dock_in_strikecraft_bay', (wing.id,), target_id=carrier.id), command)
    assert not result.accepted
    assert result.errors[0].code == 'wing_service_required'
    assert is_deployed(wing, game.galaxy)


def test_early_adoption_and_carrier_recovery_do_not_grant_extra_endurance():
    game, carrier, wing = world()
    wing.strikecraft_wing_component.turns_outside = 78
    carrier.is_disabled = True
    process(game, wing.owner, advance=True)
    assert wing.strikecraft_wing_component.turns_outside == 79
    carrier.is_disabled = False
    next_resolution(game, wing)
    assert required(wing)
    game2, carrier2, orphan = world()
    carrier2.strikecraft_bay_component.release_wing(orphan)
    orphan.strikecraft_wing_component.turns_outside = 79
    orphan.position = carrier2.position
    assert apply(game2, Command('dock_in_strikecraft_bay', (orphan.id,), target_id=carrier2.id)).accepted
    assert orphan.strikecraft_wing_component.turns_outside == 0


def test_carrier_orders_cannot_replace_mandatory_return():
    game, carrier, wing = world()
    wing.position = Position(400, 0)
    wing.strikecraft_wing_component.turns_outside = 79
    process(game, wing.owner, advance=True)
    target = next(u for u, _ in game.galaxy.systems['Sol'].get_all_units() if u.name == 'Enemy ship')
    assert not issue(game, carrier, 'attack_run', target).accepted
    assert not issue(game, carrier, 'emergency_recovery', wing).accepted
    assert wing.commander_component.current_order.order_type == OrderType.RETURN_FOR_SERVICE
    assert wing.engines_component.effective_speed == 40


def test_observations_are_pure_and_enemy_private():
    game, carrier, wing = world()
    # Keep the returning wing in detailed enemy sensor view for this privacy check.
    observer = next(u for u, _ in game.galaxy.systems['Sol'].get_all_units()
                    if u.name == 'Enemy ship')
    observer.sensors_component.short_range_radius = 2000
    wing.strikecraft_wing_component.turns_outside = 79
    process(game, wing.owner, advance=True)
    before = serialize_game_state(game)
    rng, counter = random.getstate(), Order.order_counter
    own = next(v for v in build_observation(game, wing.owner)['units'] if v['id'] == wing.id)
    assert own['wing_service']['return_required'] and own['wing_service']['turns_remaining'] == 0
    assert own['current_order']['origin'] == 'system' and not own['current_order']['cancellable']
    assert own['legal_commands'] == ['rename_unit'] and own['wing_tactical_state']['weapons_suppressed']
    enemy = next(v for v in build_observation(game, game.players[1])['units'] if v['id'] == wing.id)
    assert 'wing_service' not in enemy and 'current_order' not in enemy
    after = serialize_game_state(game)
    # Observations refresh visibility intel, but never the service/order state or RNG.
    assert own['wing_service']['turns_outside'] == wing.strikecraft_wing_component.turns_outside == 80
    assert rng == random.getstate() and counter == Order.order_counter
    assert before['version'] == after['version'] == '4.17'


@pytest.mark.parametrize('phase', ['deployed', 'returning', 'orphan', 'docked'])
def test_save_load_preserves_endurance_without_execution(phase):
    game, carrier, wing = world()
    comp = wing.strikecraft_wing_component
    wing.commander_component.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    comp.turns_outside = 79
    if phase == 'returning':
        process(game, wing.owner, advance=True)
    elif phase == 'orphan':
        carrier.strikecraft_bay_component.release_wing(wing)
    elif phase == 'docked':
        carrier.strikecraft_bay_component.dock(wing, game.galaxy)
    before = (comp.turns_outside, comp.last_endurance_round, comp.recovery_ready_round)
    state = json.loads(json.dumps(serialize_game_state(game)))
    loaded = prepare_campaign(state).state
    from campaign_graph import find_unit
    restored = find_unit(loaded.galaxy, wing.id)
    comp = restored.strikecraft_wing_component
    assert (comp.turns_outside, comp.last_endurance_round, comp.recovery_ready_round) == before
    assert restored.commander_component.stance == UnitStance.ATTACK_SAME_SECTOR
    if phase == 'returning':
        assert restored.commander_component.current_order.public_id == wing.commander_component.current_order.public_id
        process(loaded, restored.owner, advance=True)
        assert comp.turns_outside == 80


@pytest.mark.parametrize('field,value', [('turns_outside', -1), ('turns_outside', 81), ('turns_outside', True),
                                       ('turns_outside', 1.5), ('last_endurance_round', 1000)])
def test_invalid_endurance_save_rejects_transactionally(field, value):
    game, carrier, wing = world()
    state = serialize_game_state(game)
    raw = next(u for u in state['galaxy']['systems'][0]['hexes'][0]['units'] if u['id'] == wing.id)
    raw['components']['StrikecraftWingComponent']['runtime'][field] = value
    original = deepcopy(state)
    galaxy = game.galaxy
    assert not deserialize_game_state(game, state)
    assert state == original and game.galaxy is galaxy


def test_service_order_on_non_wing_rejects_transactionally():
    from unit_orders.strikecraft import ReturnForServiceOrder
    game, carrier, wing = world()
    carrier.commander_component.add_order(ReturnForServiceOrder(carrier, {'target_carrier_id': carrier.id}))
    state = serialize_game_state(game)
    original = deepcopy(state)
    galaxy = game.galaxy
    assert not deserialize_game_state(game, state)
    assert state == original and game.galaxy is galaxy


def test_full_resolution_returns_over_multiple_turns_and_reports_once():
    from turn_briefing import initialize_campaign, begin_window, finish_window, summary_view
    game, carrier, wing = world()
    wing.position = Position(400, 0)
    initialize_campaign(game)
    begin_window(game, wing.owner)
    wing.strikecraft_wing_component.turns_outside = 79
    processor = TurnProcessor(game)
    for _ in range(10):
        processor.process_player_turn(wing.owner)
        if not is_deployed(wing, game.galaxy):
            break
        game.turn_number += 1
    assert wing in carrier.strikecraft_bay_component.docked_units
    finish_window(game, wing.owner)
    entries = summary_view(wing.owner)['entries']
    assert sum(e['count'] for e in entries if e['detail'] == 'Returning to refuel and rearm') == 1
    view = next(u for u in build_observation(game, wing.owner)['units'] if u['id'] == carrier.id)
    docked = next(u for u in view['capability_details']['strikecraft_bay']['docked_units'] if u['id'] == wing.id)
    assert docked['wing_service']['status'] == 'servicing' and docked['wing_service']['turns_outside'] == 0


def test_endurance_loss_cleans_selection_orders_and_reports_without_salvage():
    from turn_briefing import initialize_campaign, begin_window, finish_window, summary_view
    game, carrier, wing = world()
    wing.strikecraft_wing_component.turns_outside = 79
    initialize_campaign(game)
    begin_window(game, wing.owner)
    process(game, wing.owner, advance=True)
    carrier.is_disabled = True
    game.selected_objects = [wing]
    game.deselect_object = lambda unit: game.selected_objects.remove(unit)
    game.hovered_object = wing
    credits, xp = wing.owner.credits, carrier.experience_points
    process(game, wing.owner)
    assert game.selected_objects == [] and game.hovered_object is None
    assert wing.owner.credits == credits and carrier.experience_points == xp
    assert wing.strikecraft_wing_component.mother_carrier is None
    process(game, wing.owner)
    finish_window(game, wing.owner)
    losses = [e for e in summary_view(wing.owner)['entries'] if e['category'] == 'loss' and e['subject_id'] == wing.id]
    assert len(losses) == 1 and losses[0]['count'] == 1
    assert any(e['reason'] == 'wing_endurance_expired' for e in wing.owner.order_history)


def test_capture_preserves_elapsed_time_and_prevents_second_tick_in_same_round():
    game, carrier, wing = world()
    wing.strikecraft_wing_component.turns_outside = 20
    process(game, wing.owner, advance=True)
    wing.owner = game.players[1]
    process(game, wing.owner, advance=True)
    assert wing.strikecraft_wing_component.turns_outside == 21
    next_resolution(game, wing)
    assert wing.strikecraft_wing_component.turns_outside == 22


def test_actual_obstacles_detour_and_unreachable_carrier_expires():
    from domain.celestials import Storm
    from constants import StormType
    game, carrier, wing = world()
    wing.position = Position(1500, 0)
    storm = Storm((0, 0), 'Sol', StormType.MAGNETIC)
    storm.position = Position(800, 0)
    storm.radius = 180
    game.galaxy.systems['Sol'].add_celestial_body(storm)
    wing.strikecraft_wing_component.turns_outside = 79
    process(game, wing.owner, advance=True)
    assert required(wing) and abs(wing.engines_component.move_target.y) > 0
    carrier.position = storm.position
    process(game, wing.owner)
    assert not is_deployed(wing, game.galaxy)


def test_mandatory_return_replaces_existing_attack_run_and_cannot_adopt_elsewhere():
    from tests.test_carrier_abilities import make_wing
    from unit_components.strikecraft import StrikecraftBayComponent
    from tests.support.campaigns import ship
    game, carrier, wing = world()
    wing.position = Position(400, 0)
    target = next(u for u, _ in game.galaxy.systems['Sol'].get_all_units() if u.name == 'Enemy ship')
    assert issue(game, carrier, 'attack_run', target).accepted
    attack = wing.commander_component.current_order
    wing.strikecraft_wing_component.turns_outside = 79
    process(game, wing.owner, advance=True)
    assert attack.status == OrderStatus.CANCELLED
    other = ship(game, 'Other carrier')
    other.add_component(StrikecraftBayComponent(other, max_slots=2))
    assert not other.strikecraft_bay_component.dock(wing, game.galaxy)
    eligible = make_wing(game, carrier)
    from tactical_abilities import start_owner_turn
    game.turn_number += 8
    start_owner_turn(game.galaxy, wing.owner, game.turn_number)
    assert issue(game, carrier, 'attack_run', target).accepted
    assert eligible.commander_component.current_order.order_type == OrderType.ATTACK_RUN
    assert wing.commander_component.current_order.order_type == OrderType.RETURN_FOR_SERVICE


def test_wing_and_carrier_sidebars_show_service_and_hide_conflicting_controls():
    from types import SimpleNamespace
    from tests.support.campaigns import ship
    from unit_components.strikecraft import StrikecraftBayComponent
    game, carrier, wing = world()
    game.gui = SimpleNamespace(is_section_expanded=lambda key: False)
    game._generate_order_data_recursive = lambda *args: 'Order'
    wing.strikecraft_wing_component.turns_outside = 79
    process(game, wing.owner, advance=True)
    rows = wing.strikecraft_wing_component.get_sidebar_data(game)
    assert any('Returning to refuel and rearm' in r.get('text', '') for r in rows)
    commander_rows = wing.commander_component.get_sidebar_data(game)
    assert not any(r.get('action_id') in {'set_stance', 'stop_unit'} for r in commander_rows)
    rows = carrier.strikecraft_bay_component.get_sidebar_data(game)
    assert not any(r.get('action_id') == 'recall_ship' and r['target_data'][1] == wing.id for r in rows)
    # A separate bay isolates the launch-all lock from other ready wings.
    other = ship(game, 'Other')
    other.add_component(StrikecraftBayComponent(other, max_slots=1))
    wing.strikecraft_wing_component.turns_outside = 79
    assert other.strikecraft_bay_component.dock(wing, game.galaxy)
    rows = other.strikecraft_bay_component.get_sidebar_data(game)
    assert any(r.get('text') == 'Ready next owner turn' for r in rows)
    assert not any(r.get('action_id') in {'deploy_ship', 'launch_all_wings'} for r in rows)
