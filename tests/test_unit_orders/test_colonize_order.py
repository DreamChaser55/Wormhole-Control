from unittest.mock import MagicMock
from geometry import Position
from constants import PLANET_RADIUS, DEFAULT_STANDOFF_DISTANCE
from unit_orders import OrderStatus, OrderType, ColonizeOrder
from unit_components import ColonyComponent
from tests.test_unit_components import MockUnit


def test_colonize_order_in_range():
    unit = MockUnit()
    colony = MagicMock()
    colony.population_cargo = 50
    unit.components[ColonyComponent] = colony

    planet = MagicMock()
    planet.id = 999
    planet.name = "Terra"
    planet.in_system = "Sol"
    planet.in_hex = (0, 0)
    planet.position = Position(0, 0)
    planet.collision_radius = PLANET_RADIUS
    planet.owner = None

    galaxy = MagicMock()
    galaxy.get_celestial_body_by_id.return_value = planet

    order = ColonizeOrder(unit, {"target_id": 999})

    # Unit is within standoff distance (PLANET_RADIUS + DEFAULT_STANDOFF_DISTANCE = 712.5)
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(600, 0)

    colony.unload_population.return_value = True

    order.execute(galaxy)
    assert order.status == OrderStatus.COMPLETED
    colony.unload_population.assert_called_once_with(planet, 50)


def test_colonize_order_same_hex_out_of_range_spawns_celestial_approach():
    unit = MockUnit()
    colony = MagicMock()
    colony.population_cargo = 50
    unit.components[ColonyComponent] = colony

    planet = MagicMock()
    planet.id = 999
    planet.name = "Terra"
    planet.in_system = "Sol"
    planet.in_hex = (0, 0)
    planet.position = Position(0, 0)
    planet.collision_radius = PLANET_RADIUS

    galaxy = MagicMock()
    galaxy.get_celestial_body_by_id.return_value = planet

    order = ColonizeOrder(unit, {"target_id": 999})

    # Unit is in the same hex, but far away from the planet (1000.0 > 712.5)
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(1000, 0)

    order.execute(galaxy)

    assert len(order.sub_orders) == 2
    move_sub = order.sub_orders[0]
    colonize_sub = order.sub_orders[1]

    assert move_sub.order_type == OrderType.MOVE
    assert move_sub.parameters.get("target_celestial_id") == 999
    assert move_sub.parameters.get("standoff_distance") == DEFAULT_STANDOFF_DISTANCE
    assert colonize_sub.order_type == OrderType.COLONIZE


def test_colonize_order_different_sector_spawns_sub_orders():
    unit = MockUnit()
    colony = MagicMock()
    colony.population_cargo = 50
    unit.components[ColonyComponent] = colony

    planet = MagicMock()
    planet.id = 999
    planet.name = "Terra"
    planet.in_system = "Sol"
    planet.in_hex = (0, 0)
    planet.position = Position(0, 0)
    planet.collision_radius = PLANET_RADIUS

    galaxy = MagicMock()
    galaxy.get_celestial_body_by_id.return_value = planet

    order = ColonizeOrder(unit, {"target_id": 999})

    # Unit is in another sector
    unit.in_system = "Sol"
    unit.in_hex = (1, 0)
    unit.position = Position(0, 0)

    order.execute(galaxy)

    assert len(order.sub_orders) == 2
    assert order.sub_orders[0].order_type == OrderType.MOVE
    assert order.sub_orders[0].parameters.get("target_celestial_id") == 999
    assert order.sub_orders[1].order_type == OrderType.COLONIZE


def test_colonize_order_no_cargo_fails():
    unit = MockUnit()
    colony = MagicMock()
    colony.population_cargo = 0
    unit.components[ColonyComponent] = colony

    planet = MagicMock()
    planet.id = 999
    planet.name = "Terra"
    planet.in_system = "Sol"
    planet.in_hex = (0, 0)
    planet.position = Position(0, 0)
    planet.collision_radius = PLANET_RADIUS

    galaxy = MagicMock()
    galaxy.get_celestial_body_by_id.return_value = planet

    order = ColonizeOrder(unit, {"target_id": 999})
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(600, 0)

    order.execute(galaxy)
    assert order.status == OrderStatus.FAILED
