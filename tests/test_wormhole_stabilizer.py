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
from unit_components.wormhole_destabilizer import WormholeDestabilizerComponent
from unit_components.wormhole_stabilizer import WormholeStabilizerComponent
from unit_components.antimatter import AntimatterStorage
from unit_components.movement import Engines, Hyperdrive
from unit_components.enums import HyperdriveType
from unit_orders.base import Order, OrderType, OrderStatus
from unit_orders.wormhole_destabilizer import DestabilizeWormholeOrder
from unit_orders.wormhole_stabilizer import StabilizeWormholeOrder
from wormhole_stabilization import (
    connection_stability, effective_stability, is_stabilized, operating, process_support,
)


@pytest.fixture(params=(WormholeStabilizerComponent, WormholeDestabilizerComponent), ids=('stabilizer', 'destabilizer'))
def support_component(request):
    return request.param


def add_connection(game, origin, destination, *, origin_hex=(0, 0), stability=50, zero_id=False):
    entry = Wormhole(origin_hex, origin, destination, stability=stability)
    exit_ = Wormhole((0, 0), destination, origin, stability=stability)
    if zero_id:
        entry.id = 0
    entry.exit_wormhole_id, exit_.exit_wormhole_id = exit_.id, entry.id
    for body in (entry, exit_):
        body.position = Position(0, 0)
        game.galaxy.wormholes[body.id] = body
        game.galaxy.systems[body.in_system].add_celestial_body(body)
    game.galaxy._build_system_graph()
    return entry, exit_


def setup(*, zero_id=False, mobile=False, owner=0, system='Sol', support_component=WormholeStabilizerComponent):
    game = campaign()
    entry, exit_ = add_connection(game, 'Sol', 'Beta', zero_id=zero_id)
    unit = ship(game, hull=HullSize.MEDIUM, system=system, owner=owner)
    unit.add_component(support_component(unit))
    unit.antimatter_component.current_amount = 100
    if mobile:
        unit.add_component(Engines(unit, speed=100))
    return game, entry, exit_, unit


def command_name(unit):
    return 'destabilize_wormhole' if unit.wormhole_destabilizer_component else 'stabilize_wormhole'


def issue(game, unit, target, *, queue=False, extra=(), kind=None):
    command = dict(type=kind or command_name(unit), unit_ids=[unit.id], target_id=target.id, queue=queue)
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


def test_deferred_activation_exact_payment_and_once_per_owner_turn(support_component):
    game, entry, _, unit = setup(support_component=support_component)
    unit.antimatter_component.current_amount = 5
    assert issue(game, unit, entry).accepted
    for _ in range(3):
        unit.commander_component.update()
    assert unit.antimatter_component.current_amount == 5
    assert not operating(unit, game.galaxy)
    process_support(game, unit.owner)
    assert unit.antimatter_component.current_amount == 0
    assert operating(unit, game.galaxy)
    process_support(game, unit.owner)
    process_support(game, game.players[1])
    assert operating(unit, game.galaxy)
    game.turn_number += 1
    process_support(game, unit.owner)
    assert not operating(unit, game.galaxy)
    assert unit.commander_component.current_order.phase == 'waiting_for_antimatter'


def test_shortage_waits_and_reports_once_per_interruption(monkeypatch, support_component):
    from antimatter_logistics import service_fuel_horizon
    game, entry, _, unit = setup(support_component=support_component)
    unit.antimatter_component.current_amount = 0
    events = []
    monkeypatch.setattr('turn_briefing.unit_event', lambda *a, **k: events.append(a))
    assert issue(game, unit, entry).accepted
    process_support(game, unit.owner)
    process_support(game, unit.owner)
    game.turn_number += 1
    process_support(game, unit.owner)
    assert len(events) == 1
    assert service_fuel_horizon(unit) == 0
    unit.antimatter_component.add(10)
    process_support(game, unit.owner)
    assert operating(unit, game.galaxy) and unit.antimatter_component.current_amount == 5
    game.turn_number += 1
    process_support(game, unit.owner)
    game.turn_number += 1
    process_support(game, unit.owner)
    assert len(events) == 2


@pytest.mark.parametrize('position,sector,allowed', [(500, (0, 0), True), (500.001, (0, 0), False), (0, (1, 0), False)])
def test_station_range_is_inclusive_and_sector_local(position, sector, allowed, support_component):
    game, entry, _, unit = setup(support_component=support_component)
    if sector != unit.in_hex:
        game.galaxy.systems['Sol'].hexes[unit.in_hex].units.remove(unit)
        game.galaxy.systems['Sol'].hexes[sector].units.append(unit)
        unit.in_hex = sector
    unit.position = Position(position, 0)
    result = issue(game, unit, entry)
    assert result.accepted is allowed
    if not allowed:
        assert result.errors[0].code == 'path_unavailable'


def test_mobile_approach_and_arrival_activation(support_component):
    from turn_processor import TurnProcessor
    game, entry, _, unit = setup(mobile=True, support_component=support_component)
    unit.position = Position(590, 0)
    assert issue(game, unit, entry).accepted
    processor = TurnProcessor(game)
    processor.process_player_turn(unit.owner)
    assert operating(unit, game.galaxy)
    assert unit.position.x <= 500
    assert unit.antimatter_component.current_amount < 95  # movement plus one support payment


def test_pre_movement_activation_and_post_movement_arrival_order(monkeypatch, support_component):
    from turn_processor import TurnProcessor
    game, entry, _, unit = setup(mobile=True, support_component=support_component)
    assert issue(game, unit, entry).accepted
    processor = TurnProcessor(game)
    seen = []
    def movement(player):
        seen.append(operating(unit, game.galaxy))
        return {}
    monkeypatch.setattr(processor, '_process_movement', movement)
    processor.process_player_turn(unit.owner)
    assert seen == [True] and unit.antimatter_component.current_amount == 95
    unit.commander_component.clear_explicit_orders()
    game.turn_number += 1
    unit.position = Position(600, 0)
    assert issue(game, unit, entry).accepted
    def arrival(player):
        seen.append(operating(unit, game.galaxy))
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


@pytest.mark.parametrize('natural', [50, 100])
def test_opposing_devices_cancel_across_endpoints_and_duplicate_devices_do_not_stack(natural):
    game, entry, exit_, destabilizer = setup(support_component=WormholeDestabilizerComponent)
    entry.stability = exit_.stability = natural
    duplicate = ship(game, owner=0, system='Beta', hull=HullSize.MEDIUM)
    duplicate.add_component(WormholeDestabilizerComponent(duplicate))
    stabilizer = ship(game, owner=1, system='Beta', hull=HullSize.MEDIUM)
    stabilizer.add_component(WormholeStabilizerComponent(stabilizer))
    for unit in (duplicate, stabilizer):
        unit.antimatter_component.current_amount = 100

    def assert_route(status, stability):
        for body in (entry, exit_):
            view = connection_stability(game.galaxy, body)
            assert (view.status, view.effective_stability) == (status, stability)
            assert body.stability == natural

    assert_route('natural', natural)
    start(game, destabilizer, entry)
    start(game, duplicate, exit_)
    assert_route('destabilized', natural - 30)
    start(game, stabilizer, exit_)
    assert_route('contested', natural)
    game.turn_number += 1
    for player in game.players:
        process_support(game, player)
        process_support(game, player)
    assert all(unit.antimatter_component.current_amount == 90 for unit in (destabilizer, duplicate, stabilizer))
    duplicate.destroy()
    assert_route('contested', natural)
    destabilizer.commander_component.clear_explicit_orders()
    assert_route('stabilized', 100)
    stabilizer.destroy()
    assert_route('natural', natural)


def test_managing_one_device_does_not_depend_on_the_other_device():
    game, entry, _, unit = setup(support_component=WormholeDestabilizerComponent)
    unit.add_component(WormholeStabilizerComponent(unit))
    root = start(game, unit, entry)
    unit.remove_component(WormholeStabilizerComponent)
    assert unit.commander_component.current_order is root
    assert connection_stability(game.galaxy, entry).status == 'destabilized'
    unit.add_component(WormholeStabilizerComponent(unit))
    assert issue(game, unit, entry, kind='stabilize_wormhole').accepted
    assert root.status == OrderStatus.CANCELLED
    assert connection_stability(game.galaxy, entry).status == 'natural'
    process_support(game, unit.owner)
    assert connection_stability(game.galaxy, entry).status == 'stabilized'
    assert unit.antimatter_component.current_amount == 90


@pytest.mark.parametrize('event', ['remove_device', 'destroy_storage', 'remove_storage', 'destroy_unit', 'cancel', 'capture'])
def test_permanent_interruptions_end_support(event, support_component):
    game, entry, _, unit = setup(support_component=support_component)
    order = start(game, unit, entry)
    if event == 'remove_device':
        unit.remove_component(support_component)
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
    assert effective_stability(game.galaxy, entry) == entry.stability
    assert not order.powered


def test_displacement_and_disablement_stop_protection_without_extra_charges(support_component):
    game, entry, _, unit = setup(mobile=True, support_component=support_component)
    order = start(game, unit, entry)
    unit.is_disabled = True
    assert not operating(unit, game.galaxy)
    process_support(game, unit.owner)
    assert order.phase == 'disabled'
    unit.is_disabled = False
    process_support(game, unit.owner)
    assert operating(unit, game.galaxy) and unit.antimatter_component.current_amount == 95
    unit.position = Position(700, 0)
    assert not operating(unit, game.galaxy)
    process_support(game, unit.owner)
    unit.commander_component.update()
    assert order.phase == 'approach' and order.sub_orders


def test_atomic_invalid_batch_preserves_orders_and_fuel(support_component):
    game, entry, _, unit = setup(support_component=support_component)
    old = Order(unit, OrderType.PATROL)
    unit.commander_component.add_order(old)
    result = issue(game, unit, entry, extra=({'type': command_name(unit), 'unit_ids': [unit.id], 'target_id': 999999},))
    assert not result.accepted
    assert unit.commander_component.current_order is old
    assert unit.antimatter_component.current_amount == 100


def test_zero_target_id_and_continuous_queue_disclosure(support_component):
    game, entry, _, unit = setup(zero_id=True, support_component=support_component)
    assert issue(game, unit, entry).accepted
    root = unit.commander_component.current_order
    assert issue(game, unit, entry, queue=True).accepted
    queued = unit.commander_component.orders_queue[0]
    observed = build_observation(game, unit.owner)
    view = next(u for u in observed['units'] if u['id'] == unit.id)
    assert view['queued_orders'][0]['blocked_by_order_id'] == root.public_id
    assert view['current_order']['target_id'] == 0
    process_support(game, unit.owner)
    assert operating(unit, game.galaxy)
    result = CommandGateway(game).apply_batch(unit.owner, CommandBatch((Command(
        'cancel_order', (unit.id,), order_id=root.public_id),)))
    assert result.accepted
    assert unit.commander_component.current_order is queued
    assert not operating(unit, game.galaxy)


@pytest.mark.parametrize('phase', ['approach', 'maintaining', 'waiting_for_antimatter', 'queued'])
def test_round_trip_does_not_replay_payment_or_activation(phase, support_component):
    from save_manager import serialize_game_state, deserialize_game_state
    game, entry, _, unit = setup(mobile=True, support_component=support_component)
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
    assert [child.public_id for child in loaded.commander_component.current_order.sub_orders] == [
        child.public_id for child in root.sub_orders]
    assert restored.galaxy.wormholes[entry.id].stability == 50
    if phase == 'queued':
        assert loaded.commander_component.orders_queue[0].public_id == unit.commander_component.orders_queue[0].public_id
    if phase == 'maintaining':
        process_support(restored, loaded.owner)
        assert loaded.antimatter_component.current_amount == fuel


def test_template_validation_and_refit_requirements(support_component):
    from custom_unit_templates import ComponentConfig, CustomUnitTemplate, template_from_dict
    from refit_validation import evaluate_refit
    from unit_catalog import describe_template
    from unit_templates import UNIT_TEMPLATES
    destabilizing = support_component is WormholeDestabilizerComponent
    device = 'destabilizer' if destabilizing else 'stabilizer'
    flag = f'has_wormhole_{device}_component'
    assert getattr(template_from_dict('Old design', {'hull_size': 'MEDIUM'}).components, flag) is False
    for hull in HullSize:
        config = ComponentConfig(has_antimatter_storage=True,
                                 antimatter_capacity=1000 if hull == HullSize.TITAN else 400, **{flag: True})
        design = CustomUnitTemplate('Wormhole device test', hull, config)
        assert bool(design.validate()) == (hull in (HullSize.STRIKECRAFT_WING, HullSize.TINY, HullSize.SMALL))
    game, _, _, unit = setup(support_component=support_component)
    assert evaluate_refit(unit, 'REMOVE', 'AntimatterStorage').errors
    assert not evaluate_refit(unit, 'REMOVE', support_component.__name__).errors
    for variant in ('TENDER', 'STATION'):
        key = f'WORMHOLE_{device.upper()}_{variant}'
        description = describe_template(key, UNIT_TEMPLATES[key])
        assert description['hull_used'] <= 50
        assert description['support'][f'wormhole_{device}_component']['antimatter_cost_per_turn'] == 5


@pytest.mark.parametrize('kind', ['stabilize_wormhole', 'destabilize_wormhole'])
def test_command_contract_rejects_groups_and_extra_coordinates(kind):
    for fields in ({'unit_ids': [1, 2]}, {'position': [0, 0]}, {'target_id': True}):
        with pytest.raises(ContractError):
            Command.from_dict(dict(type=kind, target_id=0, unit_ids=[1]) | fields)


def test_public_route_status_hides_source_identity(support_component):
    game, entry, exit_, unit = setup(support_component=support_component)
    destabilizing = support_component is WormholeDestabilizerComponent
    start(game, unit, entry)
    enemy = ship(game, owner=1, system='Beta')
    unit.position = Position(-500, 0)
    enemy.position = Position(4500, 0)
    view = build_observation(game, enemy.owner)
    bodies = [b for s in view['systems'] for b in s.get('celestial_bodies', [])]
    public_endpoint = next(b for b in bodies if b['id'] == exit_.id)
    assert public_endpoint['stability_status'] == ('destabilized' if destabilizing else 'stabilized')
    assert public_endpoint['effective_stability'] == (20 if destabilizing else 100)
    assert public_endpoint['crossing_fuel_loss'] == (20 if destabilizing else 0)
    assert public_endpoint['stabilized'] is not destabilizing
    assert unit.id not in [u['id'] for u in view['units']]
    route = next(b for b in bodies if b['id'] == entry.id)
    assert 'source_id' not in route and 'supporting_units' not in route
    ship(game, owner=1).position = Position(-450, 0)
    visible = next(u for u in build_observation(game, enemy.owner)['units'] if u['id'] == unit.id)
    assert {'current_order', 'wormhole_stabilizer', 'wormhole_destabilizer', 'antimatter'}.isdisjoint(visible)
    enemy.owner.team_id = unit.owner.team_id
    ally_view = next(u for u in build_observation(game, enemy.owner)['units'] if u['id'] == unit.id)
    capability = 'wormhole_destabilizer' if destabilizing else 'wormhole_stabilizer'
    assert ally_view[capability]['phase'] == 'maintaining'
    assert ally_view['current_order']['target_id'] == entry.id


def test_preflight_does_not_roll_or_change_source_state(monkeypatch, support_component):
    game, entry, _, unit = setup(support_component=support_component)
    device = unit.get_component(support_component)
    before = deepcopy(device.to_state())
    monkeypatch.setattr('random.random', lambda: pytest.fail('Unexpected random draw'))
    assert issue(game, unit, entry).accepted
    assert before == device.to_state()


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
    assert traveler.antimatter_component.current_amount == (75 if protected else 62.5)


@pytest.mark.parametrize('owner,allied,reverse', [(0, False, False), (1, True, True), (1, False, True)])
@pytest.mark.parametrize('natural,roll,damage,extra_loss', [(100, .29, True, 7.5), (100, .30, False, 7.5), (20, .99, True, 25)])
def test_crossing_damage_and_fuel_match_destabilized_route(monkeypatch, owner, allied, reverse,
                                                     natural, roll, damage, extra_loss):
    from turn_processor import TurnProcessor
    game, entry, exit_, source = setup(support_component=WormholeDestabilizerComponent)
    entry.stability = exit_.stability = natural
    if allied:
        game.players[1].team_id = source.owner.team_id
    start(game, source, entry)
    entrance, destination = (exit_, entry) if reverse else (entry, exit_)
    traveler = ship(game, owner=owner, system=entrance.in_system, hull=HullSize.MEDIUM)
    traveler.position = entrance.position
    traveler.add_component(Hyperdrive(traveler, drive_type=HyperdriveType.ADVANCED))
    traveler.antimatter_component.current_amount = 100
    root = Order(traveler, OrderType.REACH_WAYPOINT)
    root.status = OrderStatus.IN_PROGRESS
    traveler.commander_component.current_order = root
    traveler.hyperdrive_component.set_wormhole_jump_target(entrance, root.local_order_id)
    rolls = iter((roll, .9))  # Damage chance followed by the hull/component choice.
    monkeypatch.setattr('random.random', lambda: next(rolls))
    monkeypatch.setattr('random.uniform', lambda *args: .2)
    TurnProcessor(game)._process_movement(traveler.owner)
    assert traveler.in_system == destination.in_system
    assert traveler.current_hit_points == traveler.max_hit_points * (.8 if damage else 1)
    assert connection_stability(game.galaxy, entrance).crossing_fuel_loss == extra_loss
    assert traveler.antimatter_component.current_amount == 75 - extra_loss


def test_journey_estimates_include_disclosed_route_hazards_only():
    from types import SimpleNamespace
    from antimatter_logistics import estimate_approach
    from galaxy import Hex, StarSystem

    game, entry, _, traveler = setup(mobile=True)
    traveler.add_component(Hyperdrive(traveler, drive_type=HyperdriveType.ADVANCED))
    for name in ('Gamma', 'Delta'):
        system = StarSystem.__new__(StarSystem)
        system.name, system.position, system.radius = name, Position(10, 20), 1
        system.hexes = {(0, 0): Hex(0, 0, name), (1, 0): Hex(1, 0, name)}
        system.celestial_bodies_by_id = {}
        system.in_galaxy = game.galaxy
        game.galaxy.systems[name] = system
    add_connection(game, 'Beta', 'Gamma', origin_hex=(1, 0))
    _, remote_end = add_connection(game, 'Gamma', 'Delta', origin_hex=(1, 0))
    target = SimpleNamespace(in_system='Delta', in_hex=(0, 0), position=Position(1000, 0))
    baseline = estimate_approach(traveler, game.galaxy, target, known_only=True)
    assert baseline is not None

    remote = ship(game, owner=1, system='Delta', hull=HullSize.MEDIUM)
    remote.add_component(WormholeDestabilizerComponent(remote))
    start(game, remote, remote_end)
    assert estimate_approach(traveler, game.galaxy, target, known_only=True).fuel == baseline.fuel
    assert estimate_approach(traveler, game.galaxy, target).fuel == baseline.fuel + 7.5

    local = ship(game, owner=1, hull=HullSize.MEDIUM)
    local.add_component(WormholeDestabilizerComponent(local))
    start(game, local, entry)
    assert estimate_approach(traveler, game.galaxy, target, known_only=True).fuel == baseline.fuel + 7.5
    assert estimate_approach(traveler, game.galaxy, target).fuel == baseline.fuel + 15


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


def test_human_menus_issue_shared_command_and_shift_queues(monkeypatch, support_component):
    from input_processor.context_menu_builder import build_sector_context_menu_options, build_system_context_menu_options
    from input_processor.context_actions import handle_context_menu_action
    from gui.sidebar.panels_world import build_celestial_body_panel
    game, entry, _, unit = setup(support_component=support_component)
    kind = command_name(unit)
    sabotaging = support_component is WormholeDestabilizerComponent
    order_class = DestabilizeWormholeOrder if sabotaging else StabilizeWormholeOrder
    game.selected_objects = [unit]
    sector, _ = build_sector_context_menu_options(game, entry, entry.position)
    system = build_system_context_menu_options(game, entry.in_hex)
    label = 'Destabilize Wormhole' if sabotaging else 'Stabilize Wormhole'
    assert (label, kind) in sector
    assert any(action == f'{kind}_{entry.id}' for _, action in system)
    monkeypatch.setattr('input_processor.context_actions._get_shift_pressed', lambda: False)
    handle_context_menu_action(game, kind, entry)
    root = unit.commander_component.current_order
    assert isinstance(root, order_class)
    monkeypatch.setattr('input_processor.context_actions._get_shift_pressed', lambda: True)
    handle_context_menu_action(game, f'{kind}_{entry.id}', entry.in_hex)
    assert len(unit.commander_component.orders_queue) == 1
    process_support(game, unit.owner)
    labels = [d.get('text', '') for d in build_celestial_body_panel(game, entry)]
    effective = 20 if sabotaging else 100
    assert any(f'50% natural / {effective}% effective' in text for text in labels)
    if sabotaging:
        assert 'Destabilized' in labels
        assert 'Instability drains up to 20 AM per transit' in labels


def test_hidden_target_and_unknown_target_are_indistinguishable(support_component):
    from galaxy import StarSystem, Hex
    game, entry, _, unit = setup(support_component=support_component)
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


def test_gas_giant_entry_ends_maintain_order(support_component):
    from domain.celestials import Planet
    from constants import PlanetType
    game, entry, _, unit = setup(mobile=True, support_component=support_component)
    giant = Planet((0, 0), 'Sol', PlanetType.GAS_GIANT)
    game.galaxy.systems['Sol'].add_celestial_body(giant)
    order = start(game, unit, entry)
    assert giant.hide_unit(unit, game.galaxy)
    assert order.status == OrderStatus.FAILED
    assert effective_stability(game.galaxy, entry) == entry.stability


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


def test_load_rejects_powered_order_without_payment(support_component):
    from save_manager import serialize_game_state
    from campaign_persistence import prepare_campaign
    game, entry, _, unit = setup(support_component=support_component)
    start(game, unit, entry)
    unit.get_component(support_component).last_paid_round = 0
    with pytest.raises(ValueError, match='no payment'):
        prepare_campaign(serialize_game_state(game))
