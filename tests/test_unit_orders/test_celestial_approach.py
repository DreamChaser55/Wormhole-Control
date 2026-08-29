import math
import unittest
from unittest.mock import MagicMock

from geometry import Position, Vector, distance, Circle
from constants import (
    PLANET_RADIUS, MOON_RADIUS, ASTEROID_RADIUS,
    DEFAULT_STANDOFF_DISTANCE, SECTOR_CIRCLE_RADIUS_LOGICAL
)
from entities import Planet, Moon, ColonizableAsteroid, Player, Unit
from unit_components import Engines, Hyperdrive, ColonyComponent, AntimatterStorage
from unit_orders import MoveOrder, OrderStatus, ReachWaypointOrder
from hexgrid_utils import hex_to_pixel
from save_manager import serialize_order, deserialize_order
from tests.test_unit_components import MockUnit, MockPlayer


class TestCelestialApproach(unittest.TestCase):
    def setUp(self):
        self.player = MockPlayer()

    def test_same_sector_resolution(self):
        unit = MockUnit()
        unit.in_system = "Sol"
        unit.in_hex = (0, 0)
        unit.position = Position(1000.0, 0.0)

        planet = MagicMock()
        planet.id = 101
        planet.name = "Terra"
        planet.in_system = "Sol"
        planet.in_hex = (0, 0)
        planet.position = Position(0.0, 0.0)
        planet.collision_radius = PLANET_RADIUS

        sector_hex = MagicMock()
        sector_hex.boundary_circle = Circle(Position(0.0, 0.0), SECTOR_CIRCLE_RADIUS_LOGICAL)

        system = MagicMock()
        system.hexes = {(0, 0): sector_hex}

        galaxy = MagicMock()
        galaxy.get_celestial_body_by_id.return_value = planet
        galaxy.systems = {"Sol": system}

        order = MoveOrder.for_celestial_approach(unit, planet, DEFAULT_STANDOFF_DISTANCE)
        self.assertFalse(order.parameters["approach_position_resolved"])

        success = order._resolve_celestial_approach_destination(galaxy)
        self.assertTrue(success)
        self.assertTrue(order.parameters["approach_position_resolved"])

        dest_pos = order.parameters["destination_position"]
        expected_distance = PLANET_RADIUS + DEFAULT_STANDOFF_DISTANCE  # 375.0 + 150.0 = 525.0
        self.assertAlmostEqual(distance(dest_pos, planet.position), expected_distance, places=2)
        # Direction was from (1000, 0) to (0, 0) -> +X direction
        self.assertAlmostEqual(dest_pos.x, expected_distance, places=2)
        self.assertAlmostEqual(dest_pos.y, 0.0, places=2)

    def test_different_sector_intra_system_resolution(self):
        unit = MockUnit()
        unit.in_system = "Sol"
        unit.in_hex = (2, 0)
        unit.position = Position(0.0, 0.0)

        planet = MagicMock()
        planet.id = 101
        planet.name = "Terra"
        planet.in_system = "Sol"
        planet.in_hex = (0, 0)
        planet.position = Position(0.0, 0.0)
        planet.collision_radius = PLANET_RADIUS

        sector_hex = MagicMock()
        sector_hex.boundary_circle = Circle(Position(0.0, 0.0), SECTOR_CIRCLE_RADIUS_LOGICAL)

        system = MagicMock()
        system.hexes = {(0, 0): sector_hex}

        galaxy = MagicMock()
        galaxy.get_celestial_body_by_id.return_value = planet
        galaxy.systems = {"Sol": system}

        order = MoveOrder.for_celestial_approach(unit, planet, DEFAULT_STANDOFF_DISTANCE)
        success = order._resolve_celestial_approach_destination(galaxy)
        self.assertTrue(success)

        dest_pos = order.parameters["destination_position"]
        expected_distance = PLANET_RADIUS + DEFAULT_STANDOFF_DISTANCE  # 525.0
        self.assertAlmostEqual(distance(dest_pos, planet.position), expected_distance, places=2)

        # Vector from (0, 0) to (2, 0) in hex pixel space is strictly positive X
        p_orig = hex_to_pixel(2, 0)
        p_dest = hex_to_pixel(0, 0)
        expected_dir = (p_orig - p_dest).normalize()

        expected_pos = planet.position + (expected_dir * expected_distance)
        self.assertAlmostEqual(dest_pos.x, expected_pos.x, places=2)
        self.assertAlmostEqual(dest_pos.y, expected_pos.y, places=2)

    def test_moon_and_asteroid_standoff_distances(self):
        unit = MockUnit()
        unit.in_system = "Sol"
        unit.in_hex = (0, 0)
        unit.position = Position(0.0, 500.0)

        moon = MagicMock()
        moon.id = 102
        moon.name = "Luna"
        moon.in_system = "Sol"
        moon.in_hex = (0, 0)
        moon.position = Position(0.0, 0.0)
        moon.collision_radius = MOON_RADIUS

        asteroid = MagicMock()
        asteroid.id = 103
        asteroid.name = "Ceres"
        asteroid.in_system = "Sol"
        asteroid.in_hex = (0, 0)
        asteroid.position = Position(0.0, 0.0)
        asteroid.collision_radius = ASTEROID_RADIUS

        sector_hex = MagicMock()
        sector_hex.boundary_circle = Circle(Position(0.0, 0.0), SECTOR_CIRCLE_RADIUS_LOGICAL)
        system = MagicMock()
        system.hexes = {(0, 0): sector_hex}
        galaxy = MagicMock()
        galaxy.systems = {"Sol": system}

        # Test Moon
        galaxy.get_celestial_body_by_id.return_value = moon
        moon_order = MoveOrder.for_celestial_approach(unit, moon)
        moon_order._resolve_celestial_approach_destination(galaxy)
        moon_dest = moon_order.parameters["destination_position"]
        self.assertAlmostEqual(distance(moon_dest, moon.position), MOON_RADIUS + DEFAULT_STANDOFF_DISTANCE, places=2)

        # Test Asteroid
        galaxy.get_celestial_body_by_id.return_value = asteroid
        ast_order = MoveOrder.for_celestial_approach(unit, asteroid)
        ast_order._resolve_celestial_approach_destination(galaxy)
        ast_dest = ast_order.parameters["destination_position"]
        self.assertAlmostEqual(distance(ast_dest, asteroid.position), ASTEROID_RADIUS + DEFAULT_STANDOFF_DISTANCE, places=2)

    def test_serialization_round_trip(self):
        unit = MockUnit()
        planet = MagicMock()
        planet.id = 101
        planet.name = "Terra"
        planet.in_system = "Sol"
        planet.in_hex = (0, 0)
        planet.position = Position(0.0, 0.0)
        planet.collision_radius = PLANET_RADIUS

        order = MoveOrder.for_celestial_approach(unit, planet, 150.0)
        serialized = serialize_order(order)

        self.assertEqual(serialized["parameters"]["target_celestial_id"], 101)
        self.assertEqual(serialized["parameters"]["standoff_distance"], 150.0)
        self.assertFalse(serialized["parameters"]["approach_position_resolved"])

        deserialized = deserialize_order(serialized, unit, None)
        self.assertIsInstance(deserialized, MoveOrder)
        self.assertEqual(deserialized.parameters["target_celestial_id"], 101)
        self.assertEqual(deserialized.parameters["standoff_distance"], 150.0)
        self.assertFalse(deserialized.parameters["approach_position_resolved"])
