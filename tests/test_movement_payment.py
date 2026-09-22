"""Movement payment and real campaign containment must commit together."""
from unittest.mock import Mock

import pytest

from constants import HullSize, FieldDensity, NebulaType
from custom_unit_templates import get_hyperdrive_hex_jump_cost, get_hyperdrive_system_jump_cost
from domain.celestials import Wormhole, AsteroidField, Nebula
from geometry import Position
from tests.support.campaigns import campaign, ship
from turn_processor import TurnProcessor
from unit_components.antimatter import AntimatterStorage
from unit_components.movement import Engines, Hyperdrive
from unit_components.enums import HyperdriveType, JumpStatus
from unit_orders.base import OrderStatus
from unit_orders.movement import ReachWaypointOrder


MODES = ['sublight', 'hex_jump', 'system_jump']


def moving_campaign(mode, *, hull=HullSize.HUGE):
    game = campaign()
    unit = ship(game, hull=hull)
    unit.add_component(Engines(unit, speed=100))
    unit.add_component(AntimatterStorage(unit, max_capacity=200))
    unit.add_component(Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5))
    system, sector, destination = 'Sol', (0, 0), Position(1000, 0)
    cost = 2.0
    if mode == 'hex_jump':
        sector = (1, 0)
        cost = get_hyperdrive_hex_jump_cost(hull)
    elif mode == 'system_jump':
        system = 'Beta'
        entry = Wormhole(in_hex=(0, 0), in_system='Sol', exit_system_name='Beta', stability=100, diameter=HullSize.HUGE)
        exit_ = Wormhole(in_hex=(0, 0), in_system='Beta', exit_system_name='Sol', stability=100, diameter=HullSize.HUGE)
        entry.position, exit_.position = unit.position, destination
        entry.exit_wormhole_id, exit_.exit_wormhole_id = exit_.id, entry.id
        for wormhole in (entry, exit_):
            game.galaxy.systems[wormhole.in_system].add_celestial_body(wormhole)
            game.galaxy.wormholes[wormhole.id] = wormhole
        cost = get_hyperdrive_system_jump_cost(hull)
    order = ReachWaypointOrder(unit, {'destination_system_name': system,
        'destination_hex_coord': sector, 'destination_position': destination})
    unit.commander_component.add_order(order)
    assert order.status == OrderStatus.IN_PROGRESS
    return game, unit, order, cost


def location(game, unit):
    return (unit.in_system, unit.in_hex, unit.position,
            {(name, coord): tuple(sector.units) for name, system in game.galaxy.systems.items()
             for coord, sector in system.hexes.items()})


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('problem', ['destroyed', 'missing', 'insufficient', 'refused'])
def test_unpaid_movement_preserves_location_and_has_no_success_effects(mode, problem, monkeypatch):
    game, unit, order, cost = moving_campaign(mode)
    storage = unit.antimatter_component
    if problem == 'destroyed':
        unit.take_component_damage(AntimatterStorage, storage.max_hit_points)
    elif problem == 'missing':
        unit.remove_component(AntimatterStorage)
    elif problem == 'insufficient':
        storage.current_amount = cost - 0.5
    else:
        monkeypatch.setattr(storage, 'consume', Mock(return_value=False))
    # An unpaid wormhole crossing must not draw its instability roll.
    for wormhole in game.galaxy.wormholes.values():
        wormhole.stability = 0
    roll = Mock(side_effect=AssertionError('unpaid jump rolled instability'))
    monkeypatch.setattr('turn_processor.random.random', roll)
    before, fuel = location(game, unit), storage.current_amount
    assert TurnProcessor(game)._process_movement(unit.owner) == {}
    assert location(game, unit) == before
    assert storage.current_amount == fuel
    assert unit.hyperdrive_component.recharge_time_remaining == 0
    roll.assert_not_called()
    if mode == 'sublight':
        assert order.status == OrderStatus.IN_PROGRESS
        assert unit.engines_component.move_target == Position(1000, 0)
    else:
        assert unit.hyperdrive_component.jump_status == JumpStatus.ERROR
        order.check_completion_conditions()
        assert order.status == OrderStatus.FAILED


@pytest.mark.parametrize('mode', MODES)
@pytest.mark.parametrize('exact_cost', [False, True])
def test_successful_movement_pays_once_and_starts_only_appropriate_effects(mode, exact_cost, monkeypatch):
    game, unit, _order, cost = moving_campaign(mode)
    storage = unit.antimatter_component
    storage.current_amount = cost if exact_cost else 200
    fuel = storage.current_amount
    debit = Mock(wraps=storage.consume)
    monkeypatch.setattr(storage, 'consume', debit)
    moved = TurnProcessor(game)._process_movement(unit.owner)
    assert storage.current_amount == pytest.approx(fuel - cost)
    debit.assert_called_once_with(cost)
    if mode == 'sublight':
        assert unit.position == Position(200, 0)
        assert moved == {unit.id: 100}
        assert unit.hyperdrive_component.jump_status == JumpStatus.READY
    else:
        assert unit.position == Position(1000, 0)
        assert unit.in_system == ('Beta' if mode == 'system_jump' else 'Sol')
        assert unit.in_hex == ((1, 0) if mode == 'hex_jump' else (0, 0))
        assert unit.hyperdrive_component.jump_status == JumpStatus.CHARGING
        assert moved == {}
    memberships = [sector for system in game.galaxy.systems.values()
                   for sector in system.hexes.values() if unit in sector.units]
    assert len(memberships) == 1


@pytest.mark.parametrize('mode', ['hex_jump', 'system_jump'])
def test_rejected_relocation_refunds_exact_debit_without_recharge_or_damage(mode, monkeypatch):
    game, unit, _order, cost = moving_campaign(mode)
    storage = unit.antimatter_component
    storage.current_amount = 123.456
    before, fuel = location(game, unit), storage.current_amount
    def reject(candidate):
        assert candidate is unit
        assert storage.current_amount == fuel - cost
        return False
    # Exercise the real relocation helper's False path, rather than replacing it.
    relocation = Mock(side_effect=reject)
    monkeypatch.setattr(game.galaxy.systems['Sol'], 'remove_unit', relocation)
    roll = Mock(side_effect=AssertionError('failed relocation rolled instability'))
    monkeypatch.setattr('turn_processor.random.random', roll)
    for wormhole in game.galaxy.wormholes.values():
        wormhole.stability = 0
    assert TurnProcessor(game)._process_movement(unit.owner) == {}
    relocation.assert_called_once()
    roll.assert_not_called()
    assert location(game, unit) == before
    assert storage.current_amount == fuel
    assert unit.hyperdrive_component.jump_status == JumpStatus.ERROR
    assert unit.hyperdrive_component.recharge_time_remaining == 0


@pytest.mark.parametrize('mode', ['hex_jump', 'system_jump'])
def test_invalid_jump_destination_preserves_fuel_and_membership(mode):
    game, unit, _order, _cost = moving_campaign(mode)
    if mode == 'hex_jump':
        del game.galaxy.systems['Sol'].hexes[(1, 0)]
    else:
        exit_id = unit.hyperdrive_component.wormhole_jump_target.exit_wormhole_id
        game.galaxy.wormholes[exit_id].in_hex = (99, 99)
    before, fuel = location(game, unit), unit.antimatter_component.current_amount
    assert TurnProcessor(game)._process_movement(unit.owner) == {}
    assert location(game, unit) == before
    assert unit.antimatter_component.current_amount == fuel


def test_tankless_wing_retains_free_sublight_movement():
    game, unit, _order, _cost = moving_campaign('sublight', hull=HullSize.STRIKECRAFT_WING)
    unit.remove_component(AntimatterStorage)
    unit.remove_component(Hyperdrive)
    assert TurnProcessor(game)._process_movement(unit.owner) == {unit.id: 100}
    assert unit.position == Position(200, 0)


def test_zero_displacement_does_not_charge_fuel():
    game, unit, _order, _cost = moving_campaign('sublight')
    unit.position = Position(1000, 0)
    fuel = unit.antimatter_component.current_amount
    assert TurnProcessor(game)._process_movement(unit.owner) == {}
    assert unit.antimatter_component.current_amount == fuel


@pytest.mark.parametrize('affordable', [False, True])
def test_hazard_clipping_waits_for_payment_before_moving_or_failing_order(affordable):
    game, unit, order, cost = moving_campaign('sublight')
    field = AsteroidField((0, 0), 'Sol', FieldDensity.HIGH)
    field.position, field.radius = Position(400, 0), 250
    game.galaxy.systems['Sol'].add_celestial_body(field)
    storage = unit.antimatter_component
    storage.current_amount = cost if affordable else cost - 0.5
    fuel = storage.current_amount
    moved = TurnProcessor(game)._process_movement(unit.owner)
    if affordable:
        assert unit.position == Position(149, 0)
        assert storage.current_amount == 0
        assert order.status == OrderStatus.FAILED
        assert moved == {unit.id: 100}
    else:
        assert unit.position == Position(100, 0)
        assert storage.current_amount == fuel
        assert order.status == OrderStatus.IN_PROGRESS
        assert moved == {}


def test_hydrogen_sublight_discount_still_applies():
    game, unit, _order, _cost = moving_campaign('sublight')
    cloud = Nebula((0, 0), 'Sol', NebulaType.HYDROGEN)
    cloud.position, cloud.radius = Position(100, 0), 1000
    game.galaxy.systems['Sol'].add_celestial_body(cloud)
    TurnProcessor(game)._process_movement(unit.owner)
    assert unit.position == Position(200, 0)
    assert unit.antimatter_component.current_amount == 199
