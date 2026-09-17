"""Wormhole support timing, public commands, route safety and persistence."""
import json
from copy import deepcopy

import pytest

from constants import HullSize
from domain.celestials import Wormhole
from geometry import Position
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch, ContractError
from game_ai.observation import build_observation
from tests.support.campaigns import campaign, ship
from unit_components.wormhole_stabilizer import WormholeStabilizerComponent
from unit_components.antimatter import AntimatterStorage
from unit_components.movement import Engines, Hyperdrive
from unit_components.enums import HyperdriveType
from unit_orders.base import Order, OrderType, OrderStatus
from unit_orders.wormhole_stabilizer import StabilizeWormholeOrder
from wormhole_stabilization import (
    blocker, effective_stability, is_stabilized, operating, process_support,
)


def setup(*, zero_id=False, mobile=False, owner=0, system='Sol'):
    game = campaign()
    entry, exit_ = Wormhole((0, 0), 'Sol', 'Beta', stability=50), Wormhole((0, 0), 'Beta', 'Sol', stability=50)
    if zero_id:
        entry.id = 0
    entry.exit_wormhole_id, exit_.exit_wormhole_id = exit_.id, entry.id
    for body in (entry, exit_):
        body.position = Position(0, 0)
        game.galaxy.wormholes[body.id] = body
        game.galaxy.systems[body.in_system].add_celestial_body(body)
    game.galaxy._build_system_graph()
    unit = ship(game, hull=HullSize.MEDIUM, system=system, owner=owner)
    unit.add_component(WormholeStabilizerComponent(unit))
    unit.antimatter_component.current_amount = 100
    if mobile:
        unit.add_component(Engines(unit, speed=100))
    return game, entry, exit_, unit


def issue(game, unit, target, *, queue=False, extra=()):
    command = dict(type='stabilize_wormhole', unit_ids=[unit.id], target_id=target.id, queue=queue)
    return CommandGateway(game).apply_batch(unit.owner, CommandBatch(tuple(Command.from_dict(c) for c in (command, *extra))))


def start(game, unit, target):
    assert issue(game, unit, target).accepted
    process_support(game, unit.owner)
    return unit.commander_component.current_order


@pytest.mark.parametrize('system,owner', [('Sol', 0), ('Beta', 0), ('Sol', 1), ('Beta', 1)])
def test_one_source_protects_both_directions_without_allegiance_filter(system, owner):
    game, entry, exit_, unit = setup(system=system, owner=owner)
    start(game, unit, entry if system == 'Sol' else exit_)
    assert effective_stability(game.galaxy, entry) == effective_stability(game.galaxy, exit_) == 100
    assert entry.stability == exit_.stability == 50
    unit.commander_component.clear_explicit_orders()
    assert effective_stability(game.galaxy, entry) == effective_stability(game.galaxy, exit_) == 50


def test_deferred_activation_exact_payment_and_once_per_owner_turn():
    game, entry, _, unit = setup()
    unit.antimatter_component.current_amount = 5
    assert issue(game, unit, entry).accepted
    for _ in range(3):
        unit.commander_component.update()
    assert unit.antimatter_component.current_amount == 5
    assert not is_stabilized(game.galaxy, entry)
    process_support(game, unit.owner)
    assert unit.antimatter_component.current_amount == 0
    assert is_stabilized(game.galaxy, entry)
    process_support(game, unit.owner)
    process_support(game, game.players[1])
    assert is_stabilized(game.galaxy, entry)
    game.turn_number += 1
    process_support(game, unit.owner)
    assert not is_stabilized(game.galaxy, entry)
    assert unit.commander_component.current_order.phase == 'waiting_for_antimatter'


def test_shortage_waits_and_reports_once_per_interruption(monkeypatch):
    game, entry, _, unit = setup()
    unit.antimatter_component.current_amount = 0
    events = []
    monkeypatch.setattr('turn_briefing.unit_event', lambda *a, **k: events.append(a))
    assert issue(game, unit, entry).accepted
    process_support(game, unit.owner)
    process_support(game, unit.owner)
    game.turn_number += 1
    process_support(game, unit.owner)
    assert len(events) == 1
    unit.antimatter_component.add(10)
    process_support(game, unit.owner)
    assert operating(unit, game.galaxy) and unit.antimatter_component.current_amount == 5
    game.turn_number += 1
    process_support(game, unit.owner)
    game.turn_number += 1
    process_support(game, unit.owner)
    assert len(events) == 2


@pytest.mark.parametrize('position,sector,allowed', [(500, (0, 0), True), (500.001, (0, 0), False), (0, (1, 0), False)])
def test_station_range_is_inclusive_and_sector_local(position, sector, allowed):
    game, entry, _, unit = setup()
    if sector != unit.in_hex:
        game.galaxy.systems['Sol'].hexes[unit.in_hex].units.remove(unit)
        game.galaxy.systems['Sol'].hexes[sector].units.append(unit)
        unit.in_hex = sector
    unit.position = Position(position, 0)
    assert (blocker(game, unit.owner, unit, entry) is None) is allowed


def test_mobile_approach_and_arrival_activation():
    from turn_processor import TurnProcessor
    game, entry, _, unit = setup(mobile=True)
    unit.position = Position(590, 0)
    assert issue(game, unit, entry).accepted
    processor = TurnProcessor(game)
    processor.process_player_turn(unit.owner)
    assert operating(unit, game.galaxy)
    assert unit.position.x <= 500
    assert unit.antimatter_component.current_amount < 95  # movement plus one support payment


def test_pre_movement_activation_and_post_movement_arrival_order(monkeypatch):
    from turn_processor import TurnProcessor
    game, entry, _, unit = setup(mobile=True)
    assert issue(game, unit, entry).accepted
    processor = TurnProcessor(game)
    seen = []
    def movement(player):
        seen.append(is_stabilized(game.galaxy, entry))
        return {}
    monkeypatch.setattr(processor, '_process_movement', movement)
    processor.process_player_turn(unit.owner)
    assert seen == [True] and unit.antimatter_component.current_amount == 95
    unit.commander_component.clear_explicit_orders()
    game.turn_number += 1
    unit.position = Position(600, 0)
    assert issue(game, unit, entry).accepted
    def arrival(player):
        seen.append(is_stabilized(game.galaxy, entry))
        unit.position = Position(495, 0)
        return {}
    monkeypatch.setattr(processor, '_process_movement', arrival)
    processor.process_player_turn(unit.owner)
    assert seen == [True, False]
    assert operating(unit, game.galaxy) and unit.antimatter_component.current_amount == 90


def test_redundant_sources_pay_individually_and_survive_one_loss():
    game, entry, exit_, unit = setup()
    other = ship(game, owner=1, system='Beta', hull=HullSize.MEDIUM)
    other.add_component(WormholeStabilizerComponent(other))
    other.antimatter_component.current_amount = 20
    start(game, unit, entry)
    start(game, other, exit_)
    assert unit.antimatter_component.current_amount == 95
    assert other.antimatter_component.current_amount == 15
    unit.destroy()
    assert is_stabilized(game.galaxy, entry)
    other.destroy()
    assert not is_stabilized(game.galaxy, entry)


@pytest.mark.parametrize('event', ['remove_stabilizer', 'destroy_storage', 'remove_storage', 'destroy_unit', 'cancel', 'capture'])
def test_permanent_interruptions_end_support(event):
    game, entry, _, unit = setup()
    order = start(game, unit, entry)
    if event == 'remove_stabilizer':
        unit.remove_component(WormholeStabilizerComponent)
    elif event == 'destroy_storage':
        unit.take_component_damage(AntimatterStorage, 100000)
        unit.antimatter_component.current_hit_points = unit.antimatter_component.max_hit_points
    elif event == 'remove_storage':
        unit.remove_component(AntimatterStorage)
    elif event == 'destroy_unit':
        unit.destroy()
    elif event == 'capture':
        unit.owner = game.players[1]
        unit.commander_component.stop_and_idle()
    else:
        unit.commander_component.clear_explicit_orders()
    assert not is_stabilized(game.galaxy, entry)
    assert not order.powered


def test_displacement_and_disablement_stop_protection_without_extra_charges():
    game, entry, _, unit = setup(mobile=True)
    order = start(game, unit, entry)
    unit.is_disabled = True
    assert not is_stabilized(game.galaxy, entry)
    process_support(game, unit.owner)
    assert order.phase == 'disabled'
    unit.is_disabled = False
    process_support(game, unit.owner)
    assert operating(unit, game.galaxy) and unit.antimatter_component.current_amount == 95
    unit.position = Position(700, 0)
    assert not is_stabilized(game.galaxy, entry)
    process_support(game, unit.owner)
    unit.commander_component.update()
    assert order.phase == 'approach' and order.sub_orders


def test_atomic_invalid_batch_preserves_orders_and_fuel():
    game, entry, _, unit = setup()
    old = Order(unit, OrderType.PATROL)
    unit.commander_component.add_order(old)
    result = issue(game, unit, entry, extra=({'type': 'stabilize_wormhole', 'unit_ids': [unit.id], 'target_id': 999999},))
    assert not result.accepted
    assert unit.commander_component.current_order is old
    assert unit.antimatter_component.current_amount == 100


def test_zero_target_id_and_continuous_queue_disclosure():
    game, entry, _, unit = setup(zero_id=True)
    assert issue(game, unit, entry).accepted
    root = unit.commander_component.current_order
    assert issue(game, unit, entry, queue=True).accepted
    observed = build_observation(game, unit.owner)
    view = next(u for u in observed['units'] if u['id'] == unit.id)
    assert view['queued_orders'][0]['blocked_by_order_id'] == root.public_id
    assert view['current_order']['target_id'] == 0
    process_support(game, unit.owner)
    assert is_stabilized(game.galaxy, entry)


@pytest.mark.parametrize('phase', ['approach', 'maintaining', 'waiting_for_antimatter', 'queued'])
def test_round_trip_does_not_replay_payment_or_activation(phase):
    from save_manager import serialize_game_state, deserialize_game_state
    game, entry, _, unit = setup(mobile=True)
    if phase == 'approach':
        unit.position = Position(1500, 0)
    if phase == 'waiting_for_antimatter':
        unit.antimatter_component.current_amount = 0
    assert issue(game, unit, entry).accepted
    if phase in ('maintaining', 'waiting_for_antimatter'):
        process_support(game, unit.owner)
    if phase == 'queued':
        assert issue(game, unit, entry, queue=True).accepted
    fuel = unit.antimatter_component.current_amount
    root = unit.commander_component.current_order
    state = json.loads(json.dumps(serialize_game_state(game)))
    restored = campaign()
    assert deserialize_game_state(restored, state)
    loaded = restored.galaxy.get_unit_by_id(unit.id)
    assert loaded.antimatter_component.current_amount == fuel
    assert loaded.commander_component.current_order.public_id == root.public_id
    assert loaded.commander_component.current_order.phase == root.phase
    assert loaded.commander_component.current_order.powered == root.powered
    assert restored.galaxy.wormholes[entry.id].stability == 50
    if phase == 'maintaining':
        process_support(restored, loaded.owner)
        assert loaded.antimatter_component.current_amount == fuel


def test_template_validation_and_refit_requirements():
    from custom_unit_templates import ComponentConfig, CustomUnitTemplate
    from refit_validation import evaluate_refit
    from unit_catalog import describe_template
    from unit_templates import UNIT_TEMPLATES
    for hull in HullSize:
        config = ComponentConfig(has_wormhole_stabilizer_component=True, has_antimatter_storage=True, antimatter_capacity=400)
        design = CustomUnitTemplate('Stabilizer test', hull, config)
        assert bool(design.validate()) == (hull in (HullSize.STRIKECRAFT_WING, HullSize.TINY, HullSize.SMALL))
    game, _, _, unit = setup()
    assert evaluate_refit(unit, 'REMOVE', 'AntimatterStorage').errors
    assert not evaluate_refit(unit, 'REMOVE', 'WormholeStabilizerComponent').errors
    for key in ('WORMHOLE_STABILIZER_TENDER', 'WORMHOLE_STABILIZER_STATION'):
        description = describe_template(key, UNIT_TEMPLATES[key])
        assert description['hull_used'] <= 50
        assert description['support']['wormhole_stabilizer_component']['antimatter_cost_per_turn'] == 5


def test_command_contract_rejects_groups_and_extra_coordinates():
    for fields in ({'unit_ids': [1, 2]}, {'position': [0, 0]}, {'target_id': True}):
        with pytest.raises(ContractError):
            Command.from_dict(dict(type='stabilize_wormhole', target_id=0, unit_ids=[1]) | fields)


def test_public_route_status_hides_source_identity():
    game, entry, exit_, unit = setup()
    start(game, unit, entry)
    enemy = ship(game, owner=1, system='Beta')
    unit.position = Position(-500, 0)
    enemy.position = Position(4500, 0)
    view = build_observation(game, enemy.owner)
    bodies = [b for s in view['systems'] for b in s.get('celestial_bodies', [])]
    assert next(b for b in bodies if b['id'] == exit_.id)['effective_stability'] == 100
    assert unit.id not in [u['id'] for u in view['units']]
    route = next(b for b in bodies if b['id'] == entry.id)
    assert 'source_id' not in route and 'supporting_units' not in route


def test_preflight_does_not_roll_or_change_source_state(monkeypatch):
    game, entry, _, unit = setup()
    before = deepcopy(unit.wormhole_stabilizer_component.to_state())
    monkeypatch.setattr('random.random', lambda: pytest.fail('Unexpected random draw'))
    assert issue(game, unit, entry).accepted
    assert before == unit.wormhole_stabilizer_component.to_state()


@pytest.mark.parametrize('protected,reverse', [(True, False), (True, True), (False, False)])
def test_actual_enemy_crossing_uses_live_stability(monkeypatch, protected, reverse):
    from turn_processor import TurnProcessor
    game, entry, exit_, source = setup()
    start(game, source, entry)
    if not protected:
        source.commander_component.clear_explicit_orders()
    traveler = ship(game, owner=1, system='Beta' if reverse else 'Sol', hull=HullSize.MEDIUM)
    traveler.position = Position(0, 0)
    traveler.add_component(Hyperdrive(traveler, drive_type=HyperdriveType.ADVANCED))
    traveler.antimatter_component.current_amount = 100
    root = Order(traveler, OrderType.REACH_WAYPOINT)
    root.status = OrderStatus.IN_PROGRESS
    traveler.commander_component.current_order = root
    traveler.hyperdrive_component.set_wormhole_jump_target(exit_ if reverse else entry, root.local_order_id)
    draws = []
    def roll():
        draws.append(True)
        return 0.1 if len(draws) == 1 else 0.9  # instability then hull damage
    monkeypatch.setattr('random.random', roll)
    monkeypatch.setattr('random.uniform', lambda *args: .2)
    TurnProcessor(game)._process_movement(traveler.owner)
    assert traveler.in_system == ('Sol' if reverse else 'Beta')
    assert traveler.current_hit_points == traveler.max_hit_points * (1 if protected else .8)
    assert bool(draws) is not protected
    assert traveler.antimatter_component.current_amount == 75


def test_refit_installs_real_component_with_fixed_cost():
    from refit_validation import evaluate_refit
    from unit_components.constructor import instantiate_component_for_unit
    game, entry, _, unit = setup()
    unit.remove_component(WormholeStabilizerComponent)
    evaluation = evaluate_refit(unit, 'ADD', 'WormholeStabilizerComponent')
    assert not evaluation.errors
    component = instantiate_component_for_unit('WormholeStabilizerComponent', unit, evaluation.configuration)
    assert isinstance(component, WormholeStabilizerComponent) and component.hull_cost == 15
    unit.add_component(component)
    start(game, unit, entry)
    assert operating(unit, game.galaxy)


def test_human_menus_issue_shared_command_and_shift_queues(monkeypatch):
    from input_processor.context_menu_builder import build_sector_context_menu_options, build_system_context_menu_options
    from input_processor.context_actions import handle_context_menu_action
    from gui.sidebar.panels_world import build_celestial_body_panel
    game, entry, _, unit = setup()
    game.selected_objects = [unit]
    sector, _ = build_sector_context_menu_options(game, entry, entry.position)
    system = build_system_context_menu_options(game, entry.in_hex)
    assert ('Stabilize Wormhole', 'stabilize_wormhole') in sector
    assert any(action == f'stabilize_wormhole_{entry.id}' for _, action in system)
    monkeypatch.setattr('input_processor.context_actions._get_shift_pressed', lambda: False)
    handle_context_menu_action(game, 'stabilize_wormhole', entry)
    root = unit.commander_component.current_order
    assert isinstance(root, StabilizeWormholeOrder)
    monkeypatch.setattr('input_processor.context_actions._get_shift_pressed', lambda: True)
    handle_context_menu_action(game, f'stabilize_wormhole_{entry.id}', entry.in_hex)
    assert len(unit.commander_component.orders_queue) == 1
    process_support(game, unit.owner)
    labels = [d.get('text', '') for d in build_celestial_body_panel(game, entry)]
    assert any('50% natural / 100% effective' in text for text in labels)


def test_hidden_target_and_unknown_target_are_indistinguishable():
    from galaxy import StarSystem, Hex
    game, entry, _, unit = setup()
    hidden_system = StarSystem.__new__(StarSystem)
    hidden_system.name, hidden_system.position, hidden_system.radius = 'Hidden', Position(0, 0), 1
    hidden_system.hexes = {(0, 0): Hex(0, 0, 'Hidden')}
    hidden_system.celestial_bodies_by_id = {}
    hidden_system.in_galaxy = game.galaxy
    game.galaxy.systems['Hidden'] = hidden_system
    hidden = Wormhole((0, 0), 'Hidden', 'Beta')
    hidden_system.add_celestial_body(hidden)
    game.galaxy.wormholes[hidden.id] = hidden
    a = issue(game, unit, hidden)
    hidden.id = 999999
    b = issue(game, unit, hidden)
    assert not a.accepted and not b.accepted
    assert a.errors[0].code == b.errors[0].code == 'target_unavailable'


@pytest.mark.parametrize('bad_value', [-1, True, 100000])
def test_invalid_saved_payment_rejects_without_mutating_live_game(bad_value):
    from save_manager import serialize_game_state
    from campaign_persistence import prepare_campaign
    game, entry, _, unit = setup()
    start(game, unit, entry)
    before = unit.antimatter_component.current_amount
    state = serialize_game_state(game)
    raw = next(u for s in state['galaxy']['systems'] for h in s['hexes'] for u in h['units'] if u['id'] == unit.id)
    raw['components']['WormholeStabilizerComponent']['runtime']['last_paid_round'] = bad_value
    with pytest.raises(ValueError):
        prepare_campaign(state)
    assert unit.antimatter_component.current_amount == before
    assert is_stabilized(game.galaxy, entry)


def test_capture_requires_new_owner_payment_even_in_same_round():
    game, entry, _, unit = setup()
    start(game, unit, entry)
    unit.owner = game.players[1]
    assert not operating(unit, game.galaxy)
    unit.commander_component.stop_and_idle()
    start(game, unit, entry)
    assert unit.antimatter_component.current_amount == 90
    assert unit.wormhole_stabilizer_component.last_paid_owner_id == unit.owner.id


def test_naturally_stable_route_and_insufficient_fuel_guidance():
    game, entry, _, unit = setup()
    entry.stability = 100
    unit.antimatter_component.current_amount = 0
    view = next(u for u in build_observation(game, unit.owner)['units'] if u['id'] == unit.id)
    assert 'stabilize_wormhole' in view['legal_commands']
    options = view['command_options']['stabilize_wormhole']
    assert options['enough_fuel_for_upkeep'] is False
    assert next(t for t in options['targets'] if t['target_id'] == entry.id)['already_stable']
    start(game, unit, entry)
    assert unit.commander_component.current_order.phase == 'waiting_for_antimatter'
    assert effective_stability(game.galaxy, entry) == 100


def test_gas_giant_entry_ends_maintain_order():
    from domain.celestials import Planet
    from constants import PlanetType
    game, entry, _, unit = setup(mobile=True)
    giant = Planet((0, 0), 'Sol', PlanetType.GAS_GIANT)
    game.galaxy.systems['Sol'].add_celestial_body(giant)
    order = start(game, unit, entry)
    assert giant.hide_unit(unit, game.galaxy)
    assert order.status == OrderStatus.FAILED
    assert not is_stabilized(game.galaxy, entry)


def test_load_reconciles_displaced_source_after_orders_restore():
    from save_manager import serialize_game_state, deserialize_game_state
    game, entry, _, unit = setup(mobile=True)
    start(game, unit, entry)
    unit.position = Position(800, 0)
    # A displacement stops coverage immediately, before the next support phase.
    assert unit.commander_component.current_order.powered
    assert not operating(unit, game.galaxy)
    fuel = unit.antimatter_component.current_amount
    restored = campaign()
    assert deserialize_game_state(restored, serialize_game_state(game))
    loaded = restored.galaxy.get_unit_by_id(unit.id)
    assert not loaded.commander_component.current_order.powered
    assert loaded.commander_component.current_order.phase == 'approach'
    assert loaded.antimatter_component.current_amount == fuel


def test_load_rejects_powered_order_without_payment():
    from save_manager import serialize_game_state
    from campaign_persistence import prepare_campaign
    game, entry, _, unit = setup()
    start(game, unit, entry)
    unit.wormhole_stabilizer_component.last_paid_round = 0
    with pytest.raises(ValueError, match='no payment'):
        prepare_campaign(serialize_game_state(game))
