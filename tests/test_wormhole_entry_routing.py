"""Wormhole entry approaches must not acquire an unrelated departure escape."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from constants import HullSize
from custom_unit_templates import (
    get_hyperdrive_system_jump_cost,
    get_sublight_antimatter_cost_per_turn,
)
from domain.celestials import Wormhole
from galaxy import Hex, StarSystem
from game_ai.contracts import Command
from geometry import Circle, Position, distance, is_point_in_circle
from save_manager import load_game_from_file, save_game_to_file
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from turn_processor import TurnProcessor
from unit_components.antimatter import AntimatterStorage
from unit_components.enums import HyperdriveType, JumpStatus, TurretType, TurretVariant
from unit_components.inhibitor import HyperspaceInhibitionFieldEmitter
from unit_components.movement import Engines, Hyperdrive
from unit_components.weapons import Turret, Weapons
from unit_orders.base import OrderStatus
from unit_orders.movement import MoveOrder


def _add_system(game, name):
    # Keep the fixture independent of procedural celestial generation.
    system = StarSystem.__new__(StarSystem)
    system.name, system.position, system.radius = name, Position(500, 500), 1
    system.hexes = {(0, 0): Hex(0, 0, name), (1, 0): Hex(1, 0, name)}
    system.celestial_bodies_by_id = {}
    system.in_galaxy = game.galaxy
    game.galaxy.systems[name] = system


def _connect(game, origin, destination, entry_hex=(0, 0)):
    entry = Wormhole(entry_hex, origin, destination, diameter=HullSize.HUGE)
    exit_ = Wormhole((0, 0), destination, origin, diameter=HullSize.HUGE)
    entry.exit_wormhole_id, exit_.exit_wormhole_id = exit_.id, entry.id
    for body in (entry, exit_):
        system = game.galaxy.systems[body.in_system]
        system.add_celestial_body(body)
        system.hexes[body.in_hex].update_static_inhibition_zones()
        game.galaxy.wormholes[body.id] = body
        game.galaxy.system_graph.setdefault(body.in_system, {})[body.exit_system_name] = body.diameter
    return entry


def _world(*, multihop=False, entry_hex=(0, 0)):
    game = campaign()
    game.galaxy.game = game
    game.gui = None
    entry = _connect(game, 'Sol', 'Beta', entry_hex)
    destination = 'Beta'
    if multihop:
        _add_system(game, 'Gamma')
        _connect(game, 'Beta', 'Gamma', (1, 0))
        destination = 'Gamma'

    unit = ship(game, 'Artillery', hull=HullSize.MEDIUM)
    unit.position = Position(175.19, 0)
    unit.add_component(Engines(unit, speed=100))
    unit.add_component(Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=3))
    unit.add_component(AntimatterStorage(unit, max_capacity=500))
    weapons = Weapons(unit)
    for variant in (TurretVariant.STANDARD, TurretVariant.LONG_RANGE):
        weapons.add_turret(Turret(TurretType.MISSILE, damage=20, range=400,
                                 cooldown=1, parent_unit=unit, variant=variant))
    unit.add_component(weapons)
    target = ship(game, 'Shipyard', owner=1, system=destination, sector=(1, 0))
    target.position = Position(0, -3000)
    observer = ship(game, 'Forward observer', system=destination, sector=(1, 0))
    observer.position = Position(100, -3000)
    return SimpleNamespace(game=game, unit=unit, target=target, entry=entry)


def _move_to_target(world, *, queue=False):
    target = world.target
    return Command('move', (world.unit.id,), system_name=target.in_system,
                   hex_coord=target.in_hex, position=(target.position.x, target.position.y), queue=queue)


def _advance(world):
    moved = TurnProcessor(world.game)._process_movement(world.unit.owner)
    world.unit.commander_component.update()
    return moved


def _replace_advancing_move(world, command_type):
    unit = world.unit
    unit.position = Position(2075.19, 0)
    assert issue(world.game, unit.owner, _move_to_target(world)).accepted
    original = unit.commander_component.current_order
    for _ in range(19):
        _advance(world)
    assert unit.position.x == pytest.approx(175.19)
    assert unit.engines_component.move_target == world.entry.position
    assert issue(world.game, unit.owner, Command(command_type, (unit.id,), target_id=world.target.id)).accepted
    assert original.status == OrderStatus.CANCELLED
    outcomes = [event for event in unit.owner.order_history if event['order_id'] == original.public_id]
    assert len(outcomes) == 1 and outcomes[0]['outcome'] == 'cancelled'
    return unit.commander_component.current_order


@pytest.mark.parametrize('multihop', [False, True])
@pytest.mark.parametrize('command_type', ['attack', 'attack_long_range'])
def test_replacing_move_at_entry_approaches_inward_then_pays_for_transit(multihop, command_type):
    world = _world(multihop=multihop)
    root = _replace_advancing_move(world, command_type)
    unit = world.unit
    approach = root.sub_orders[0]
    local, transit = list(approach.sub_orders)[:2]
    assert local.parameters['destination_position'] == world.entry.position
    assert local.parameters['destination_system_name'] == 'Sol'
    assert transit.parameters['destination_system_name'] == 'Beta'

    fuel = unit.antimatter_component.current_amount
    step_cost = get_sublight_antimatter_cost_per_turn(unit.hull_size, unit.engines_component.effective_speed)
    assert _advance(world) == {unit.id: 100}
    assert unit.position.x == pytest.approx(75.19)
    assert unit.antimatter_component.current_amount == pytest.approx(fuel - step_cost)
    _advance(world)
    assert unit.position == world.entry.position
    assert unit.hyperdrive_component.wormhole_jump_target is world.entry
    _advance(world)
    assert (unit.in_system, unit.in_hex) == ('Beta', (0, 0))
    assert unit.antimatter_component.current_amount == pytest.approx(
        fuel - 2 * step_cost - get_hyperdrive_system_jump_cost(unit.hull_size))
    assert unit.hyperdrive_component.jump_status == JumpStatus.CHARGING
    assert unit.hyperdrive_component.recharge_time_remaining == unit.hyperdrive_component.RECHARGE_DURATION
    assert root.status == OrderStatus.IN_PROGRESS


@pytest.mark.parametrize('multihop', [False, True])
def test_starting_at_entry_center_transits_without_sublight_escape(multihop):
    world = _world(multihop=multihop)
    unit = world.unit
    unit.position = world.entry.position
    assert issue(world.game, unit.owner, _move_to_target(world)).accepted
    assert unit.engines_component.move_target is None
    assert unit.hyperdrive_component.wormhole_jump_target is world.entry
    fuel = unit.antimatter_component.current_amount
    _advance(world)
    assert unit.in_system == 'Beta'
    assert unit.antimatter_component.current_amount == fuel - get_hyperdrive_system_jump_cost(unit.hull_size)


def _origin_zone(world, body, kind):
    sector = world.game.galaxy.systems['Sol'].hexes[(0, 0)]
    if kind == 'natural':
        return Circle(body.position, body.inhibition_field_radius)
    body.inhibition_field_radius = 0
    sector.update_static_inhibition_zones()
    emitter = ship(world.game, 'Inhibitor', sector=(0, 0))
    emitter.position = Position(0, 0)
    component = HyperspaceInhibitionFieldEmitter(emitter, radius=1000)
    emitter.add_component(component)
    component.is_active = True
    zone = Circle(emitter.position, component.radius)
    sector.dynamic_inhibition_zones[emitter.id] = zone
    return zone


def _assert_outward_escape(world, zone):
    unit = world.unit
    root = unit.commander_component.current_order
    escape, jump = list(root.sub_orders)[:2]
    point = escape.parameters['destination_position']
    assert escape.parameters['destination_system_name'] == 'Sol'
    assert escape.parameters['destination_hex_coord'] == (0, 0)
    assert not is_point_in_circle(point, zone)
    assert jump.parameters['destination_system_name'] == 'Sol'
    assert jump.parameters['destination_hex_coord'] == (1, 0)
    before = distance(unit.position, zone.center)
    _advance(world)
    assert distance(unit.position, zone.center) > before


@pytest.mark.parametrize('multihop', [False, True])
@pytest.mark.parametrize('kind', ['natural', 'dynamic'])
def test_selected_entry_in_another_sector_still_requires_escape(multihop, kind):
    world = _world(multihop=multihop, entry_hex=(1, 0))
    _add_system(world.game, 'Unrelated')
    unrelated = _connect(world.game, 'Sol', 'Unrelated')
    zone = _origin_zone(world, unrelated, kind)
    assert issue(world.game, world.unit.owner, _move_to_target(world)).accepted
    _assert_outward_escape(world, zone)


@pytest.mark.parametrize('kind', ['natural', 'dynamic'])
def test_ordinary_sector_jump_still_requires_escape(kind):
    world = _world()
    zone = _origin_zone(world, world.entry, kind)
    command = Command('move', (world.unit.id,), system_name='Sol', hex_coord=(1, 0), position=(3000, 0))
    assert issue(world.game, world.unit.owner, command).accepted
    _assert_outward_escape(world, zone)


@pytest.mark.parametrize('multihop', [False, True])
@pytest.mark.parametrize('blocker', ['drive', 'diameter', 'disconnected'])
def test_unavailable_route_preserves_existing_work_and_leaves_no_children(multihop, blocker):
    world = _world(multihop=multihop)
    unit, galaxy = world.unit, world.game.galaxy
    assert issue(world.game, unit.owner, Command('move', (unit.id,), system_name='Sol',
                                               hex_coord=(0, 0), position=(500, 0))).accepted
    original = unit.commander_component.current_order
    if blocker == 'drive':
        unit.remove_component(Hyperdrive)
    elif blocker == 'diameter':
        world.entry.diameter = HullSize.TINY
        galaxy.system_graph['Sol']['Beta'] = HullSize.TINY
    else:
        del galaxy.wormholes[world.entry.id]
        galaxy.system_graph['Sol'].clear()
    history = deepcopy(unit.owner.order_history)
    result = issue(world.game, unit.owner, Command('attack_long_range', (unit.id,), target_id=world.target.id))
    assert not result.accepted and result.applied_count == 0
    assert unit.commander_component.current_order is original
    assert unit.owner.order_history == history

    order = MoveOrder.for_unit_approach(unit, world.target, 300)
    order.execute(galaxy)
    assert order.status == OrderStatus.FAILED
    assert not order.sub_orders
    assert unit.engines_component.move_target == Position(500, 0)


def test_later_unavailable_leg_clears_prepared_departure_and_jump_children():
    world = _world(multihop=True, entry_hex=(1, 0))
    sector = world.game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.static_inhibition_zones = [Circle(Position(0, 0), 1000)]
    galaxy = world.game.galaxy
    for identity, body in list(galaxy.wormholes.items()):
        if body.in_system == 'Beta' and body.exit_system_name == 'Gamma':
            del galaxy.wormholes[identity]
    order = MoveOrder.for_unit_approach(world.unit, world.target, 300)
    order.execute(galaxy)
    assert order.status == OrderStatus.FAILED
    assert not order.sub_orders
    assert world.unit.engines_component.move_target is None
    assert world.unit.hyperdrive_component.hex_jump_target is None
    assert world.unit.hyperdrive_component.wormhole_jump_target is None


@pytest.mark.parametrize('multihop', [False, True])
def test_save_load_preserves_inward_approach_identity_progress_and_queue(multihop, tmp_path):
    world = _world(multihop=multihop)
    root = _replace_advancing_move(world, 'attack_long_range')
    unit = world.unit
    _advance(world)
    assert unit.position.x == pytest.approx(75.19)
    assert issue(world.game, unit.owner, _move_to_target(world, queue=True)).accepted
    approach = root.sub_orders[0]
    leg = approach.sub_orders[0]
    queued = unit.commander_component.orders_queue[0]
    history = deepcopy(unit.owner.order_history)
    fuel = unit.antimatter_component.current_amount
    path = tmp_path / 'inward_approach.json'
    save_game_to_file(world.game, str(path))
    restored_game = campaign()
    assert load_game_from_file(restored_game, str(path))
    restored = restored_game.galaxy.get_unit_by_id(unit.id)
    active = restored.commander_component.current_order
    assert active.public_id == root.public_id
    assert active.sub_orders[0].public_id == approach.public_id
    assert active.sub_orders[0].sub_orders[0].public_id == leg.public_id
    assert active.status == OrderStatus.IN_PROGRESS
    assert restored.position.x == pytest.approx(75.19)
    assert restored.antimatter_component.current_amount == fuel
    assert restored.engines_component.move_target == Position(0, 0)
    assert restored.commander_component.orders_queue[0].public_id == queued.public_id
    assert restored.commander_component.orders_queue[0].status == OrderStatus.PENDING
    assert restored.owner.order_history == history
    continuation = SimpleNamespace(game=restored_game, unit=restored)
    _advance(continuation)
    assert restored.position == Position(0, 0)
    _advance(continuation)
    assert restored.in_system == 'Beta'
