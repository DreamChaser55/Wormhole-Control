import pytest
from unittest.mock import MagicMock
from geometry import Position
from unit_components import AntimatterStorage, AntimatterHarvester, Commander
from tests.test_unit_components import MockUnit, MockPlayer
from unit_orders import OrderStatus, OrderType, ContinuousResupplyOrder, TransferAntimatterOrder
from entities import Star
from constants import HullSize, StarType, DEFAULT_ANTIMATTER_CAPACITY


def _make_star(in_system="Sol", in_hex=(0, 0), position=None):
    star = Star(in_system=in_system, star_type=StarType.G_TYPE)
    star.position = position or Position(0, 0)
    star.in_hex = in_hex
    star.id = 42
    star.name = "Sol Star"
    return star


def _make_harvester_unit(player, position=None, in_hex=(0, 0), in_system="Sol",
                         am_capacity=100.0, am_current=None):
    unit = MockUnit()
    unit.owner = player
    unit.in_system = in_system
    unit.in_hex = in_hex
    unit.position = position or Position(0, 0)
    unit.hull_size = HullSize.MEDIUM
    commander = Commander(unit)
    unit.add_component(commander)
    am = unit.antimatter_component
    am.max_capacity = am_capacity
    am.current_amount = am_current if am_current is not None else am_capacity
    harvester = AntimatterHarvester(unit)
    unit.add_component(harvester)
    return unit


def _make_needy_unit(player, position=None, in_hex=(0, 0), in_system="Sol",
                     am_capacity=100.0, am_current=0.0):
    unit = MockUnit()
    unit.id = id(unit)
    unit.owner = player
    unit.in_system = in_system
    unit.in_hex = in_hex
    unit.position = position or Position(500, 0)
    unit.hull_size = HullSize.SMALL
    commander = Commander(unit)
    unit.add_component(commander)
    am = unit.antimatter_component
    am.max_capacity = am_capacity
    am.current_amount = am_current
    return unit


def _make_galaxy(units_in_hex, star=None):
    star = star or _make_star()
    galaxy = MagicMock()
    all_units = list(units_in_hex)
    mock_hex = MagicMock()
    mock_hex.units = all_units
    mock_hex.celestial_bodies = [star]
    mock_system = MagicMock()
    mock_system.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_system}
    galaxy.get_celestial_body_by_id.side_effect = lambda bid: star if bid == star.id else None
    galaxy.get_unit_by_id.side_effect = lambda uid: next((u for u in all_units if u.id == uid), None)
    galaxy.system_graph = {}
    return galaxy


def test_continuous_resupply_flow():
    player = MockPlayer()
    harvester = _make_harvester_unit(player, am_current=0.0)
    needy = _make_needy_unit(player)
    star = _make_star()
    galaxy = _make_galaxy([harvester, needy], star=star)
    harvester.game.galaxy = galaxy

    order = ContinuousResupplyOrder(harvester, {"target_id": star.id, "target_name": star.name})
    order.execute(galaxy)
    assert order.status == OrderStatus.IN_PROGRESS

    # Simulate passive harvesting filling the storage
    harvester.antimatter_component.current_amount = harvester.antimatter_component.max_capacity
    order.check_completion_conditions()

    assert len(order.sub_orders) == 1
    assert order.sub_orders[0].order_type == OrderType.TRANSFER_ANTIMATTER
    assert order.sub_orders[0].parameters["target_unit_id"] == needy.id

    # Simulate transfer completing
    needy.antimatter_component.current_amount = needy.antimatter_component.max_capacity
    harvester.antimatter_component.current_amount = 0.0
    order.sub_orders[0].status = OrderStatus.COMPLETED
    order.update(galaxy)

    assert order.status == OrderStatus.IN_PROGRESS


def test_continuous_resupply_no_needy_units():
    player = MockPlayer()
    harvester = _make_harvester_unit(player, am_current=100.0)
    star = _make_star()
    galaxy = _make_galaxy([harvester], star=star)
    harvester.game.galaxy = galaxy

    order = ContinuousResupplyOrder(harvester, {"target_id": star.id, "target_name": star.name})
    order.execute(galaxy)

    assert order.status == OrderStatus.IN_PROGRESS
    assert len(order.sub_orders) == 0


def test_continuous_resupply_returns_to_star_when_reserve_hits_60():
    player = MockPlayer()
    star = _make_star(in_hex=(0, 0))
    # Harvester is away from star hex (e.g. in hex (2, 2)) after completing transfer, reserve = 60.0
    harvester = _make_harvester_unit(player, in_hex=(2, 2), am_current=60.0)
    galaxy = _make_galaxy([harvester], star=star)
    harvester.game.galaxy = galaxy

    order = ContinuousResupplyOrder(harvester, {"target_id": star.id, "target_name": star.name})
    order.execute(galaxy)

    assert order.status == OrderStatus.IN_PROGRESS
    assert len(order.sub_orders) == 1
    assert order.sub_orders[0].order_type == OrderType.MOVE



def test_continuous_resupply_requires_harvester():
    player = MockPlayer()
    unit = MockUnit()
    unit.owner = player
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    unit.hull_size = HullSize.MEDIUM
    commander = Commander(unit)
    unit.add_component(commander)
    # No AntimatterHarvester added

    star = _make_star()
    galaxy = _make_galaxy([unit], star=star)
    unit.game.galaxy = galaxy

    order = ContinuousResupplyOrder(unit, {"target_id": star.id})
    order.execute(galaxy)

    assert order.status == OrderStatus.FAILED


def test_continuous_resupply_picks_closest_needy_unit():
    player = MockPlayer()
    harvester = _make_harvester_unit(player, position=Position(0, 0), am_current=100.0)
    needy_close = _make_needy_unit(player, position=Position(100, 0), am_current=0.0)
    needy_far = _make_needy_unit(player, position=Position(2000, 0), am_current=0.0)
    star = _make_star()

    mock_hex = MagicMock()
    mock_hex.units = [harvester, needy_close, needy_far]
    mock_hex.celestial_bodies = [star]
    mock_system = MagicMock()
    mock_system.hexes = {(0, 0): mock_hex}
    galaxy = MagicMock()
    galaxy.systems = {"Sol": mock_system}
    galaxy.get_celestial_body_by_id.side_effect = lambda bid: star if bid == star.id else None
    all_units = [harvester, needy_close, needy_far]
    galaxy.get_unit_by_id.side_effect = lambda uid: next((u for u in all_units if u.id == uid), None)
    galaxy.system_graph = {}
    harvester.game.galaxy = galaxy

    order = ContinuousResupplyOrder(harvester, {"target_id": star.id, "target_name": star.name})
    order.execute(galaxy)

    assert order.status == OrderStatus.IN_PROGRESS
    assert len(order.sub_orders) == 1
    sub = order.sub_orders[0]
    assert sub.order_type == OrderType.TRANSFER_ANTIMATTER
    assert sub.parameters["target_unit_id"] == needy_close.id


def test_continuous_resupply_fails_with_unknown_star():
    player = MockPlayer()
    harvester = _make_harvester_unit(player, am_current=100.0)
    galaxy = MagicMock()
    galaxy.get_celestial_body_by_id.return_value = None
    galaxy.systems = {}
    harvester.game.galaxy = galaxy

    order = ContinuousResupplyOrder(harvester, {"target_id": 9999})
    order.execute(galaxy)

    assert order.status == OrderStatus.FAILED
