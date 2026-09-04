import unittest
import math
from geometry import Position, Circle, distance, segment_intersects_circle, compute_avoidance_waypoints
from constants import STAR_RADIUS, PLANET_RADIUS, MOON_RADIUS, ASTEROID_RADIUS, COMET_RADIUS
from entities import Star, Planet, Moon, ColonizableAsteroid, MetalAsteroid, Comet, Nebula, Storm, Wormhole
from constants import StarType, PlanetType, NebulaType, StormType
from unit_orders import MoveOrder, ReachWaypointOrder, PatrolOrder, OrderStatus, OrderType
from unit_components import Engines, Hyperdrive, HyperdriveType, Commander
from turn_processor import TurnProcessor
from tests.test_unit_components import MockPlayer, MockUnit


class SimpleHex:
    def __init__(self, q, r, in_system):
        self.q = q
        self.r = r
        self.in_system = in_system
        self.units = []
        self.celestial_bodies = []
        self.boundary_circle = Circle(Position(0, 0), 5000.0)
        self.dynamic_inhibition_zones = {}
        self.static_inhibition_zones = []

    def get_all_inhibition_zones(self):
        return self.static_inhibition_zones

    def add_unit(self, unit):
        self.units.append(unit)

    def remove_unit(self, unit):
        if unit in self.units:
            self.units.remove(unit)

    def add_celestial_body(self, body):
        self.celestial_bodies.append(body)

    def coordinates(self):
        return (self.q, self.r)


class SimpleSystem:
    def __init__(self, name):
        self.name = name
        self.hexes = {}
        for q in range(-3, 4):
            r1 = max(-3, -q - 3)
            r2 = min(3, -q + 3)
            for r in range(r1, r2 + 1):
                self.hexes[(q, r)] = SimpleHex(q, r, name)

    def get_all_units(self):
        units = []
        for hex_obj in self.hexes.values():
            for unit in hex_obj.units:
                units.append((unit, (hex_obj.q, hex_obj.r)))
        return units

    def get_all_celestial_bodies(self):
        bodies = []
        for hex_obj in self.hexes.values():
            for body in hex_obj.celestial_bodies:
                bodies.append(((hex_obj.q, hex_obj.r), body))
        return bodies

    def add_unit(self, unit):
        hex_obj = self.hexes.get(unit.in_hex)
        if hex_obj and unit not in hex_obj.units:
            hex_obj.add_unit(unit)

    def remove_unit(self, unit):
        hex_obj = self.hexes.get(unit.in_hex)
        if hex_obj and unit in hex_obj.units:
            hex_obj.remove_unit(unit)
            return True
        return False


class SimpleGalaxy:
    def __init__(self):
        self.systems = {"Sol": SimpleSystem("Sol")}
        self.wormholes = {}
        self.system_graph = {"Sol": {}}

    def get_unit_by_id(self, unit_id):
        for system in self.systems.values():
            for hex_obj in system.hexes.values():
                for unit in hex_obj.units:
                    if unit.id == unit_id:
                        return unit
        return None


class TestCollisionGeometry(unittest.TestCase):
    def test_segment_intersects_circle_crosses(self):
        circle = Circle(Position(0, 0), 100.0)
        p1 = Position(-200, 0)
        p2 = Position(200, 0)
        self.assertTrue(segment_intersects_circle(p1, p2, circle))

    def test_segment_intersects_circle_misses(self):
        circle = Circle(Position(0, 0), 100.0)
        p1 = Position(-200, 150)
        p2 = Position(200, 150)
        self.assertFalse(segment_intersects_circle(p1, p2, circle))

    def test_segment_intersects_circle_starts_inside(self):
        circle = Circle(Position(0, 0), 100.0)
        p1 = Position(50, 0)
        p2 = Position(200, 0)
        self.assertTrue(segment_intersects_circle(p1, p2, circle))

    def test_segment_intersects_circle_ends_inside(self):
        circle = Circle(Position(0, 0), 100.0)
        p1 = Position(-200, 0)
        p2 = Position(-50, 0)
        self.assertTrue(segment_intersects_circle(p1, p2, circle))

    def test_segment_intersects_circle_short_segment_outside(self):
        circle = Circle(Position(0, 0), 100.0)
        p1 = Position(150, 0)
        p2 = Position(200, 0)
        self.assertFalse(segment_intersects_circle(p1, p2, circle))

    def test_compute_avoidance_no_obstacles(self):
        start = Position(-1000, 0)
        end = Position(1000, 0)
        wps = compute_avoidance_waypoints(start, end, [])
        self.assertEqual(wps, [])

    def test_compute_avoidance_clear_path(self):
        start = Position(-1000, 2000)
        end = Position(1000, 2000)
        obstacles = [Circle(Position(0, 0), STAR_RADIUS)]
        wps = compute_avoidance_waypoints(start, end, obstacles, margin=50.0)
        self.assertEqual(wps, [])

    def test_compute_avoidance_single_star_blocked(self):
        start = Position(-1000, 0)
        end = Position(1000, 0)
        obstacles = [Circle(Position(0, 0), STAR_RADIUS)]
        wps = compute_avoidance_waypoints(start, end, obstacles, margin=50.0)
        self.assertTrue(len(wps) >= 1)
        # All avoidance waypoints must be outside the star radius + margin
        for wp in wps:
            self.assertGreaterEqual(distance(wp, Position(0, 0)), STAR_RADIUS + 50.0 - 1e-6)

        # The segments between start -> wps -> end must not intersect the Star obstacle
        full_path = [start] + wps + [end]
        for i in range(len(full_path) - 1):
            self.assertFalse(
                segment_intersects_circle(full_path[i], full_path[i + 1], Circle(Position(0, 0), STAR_RADIUS)),
                f"Sub-segment from {full_path[i]} to {full_path[i+1]} intersects the star!"
            )


class TestEntityCollisionRadii(unittest.TestCase):
    def test_solid_celestial_body_radii(self):
        star = Star(in_system="Sol", star_type=StarType.G_TYPE)
        self.assertEqual(star.collision_radius, STAR_RADIUS)

        planet = Planet(in_hex=(1, 0), in_system="Sol", planet_type=PlanetType.TERRAN)
        self.assertEqual(planet.collision_radius, PLANET_RADIUS)

        moon = Moon(in_hex=(1, 0), in_system="Sol")
        self.assertEqual(moon.collision_radius, MOON_RADIUS)

        c_ast = ColonizableAsteroid(in_hex=(1, 0), in_system="Sol")
        self.assertEqual(c_ast.collision_radius, ASTEROID_RADIUS)

        m_ast = MetalAsteroid(in_hex=(1, 0), in_system="Sol")
        self.assertEqual(m_ast.collision_radius, ASTEROID_RADIUS)

        comet = Comet(in_hex=(1, 0), in_system="Sol")
        self.assertEqual(comet.collision_radius, COMET_RADIUS)

    def test_non_solid_celestial_body_radii(self):
        nebula = Nebula(in_hex=(1, 0), in_system="Sol", nebula_type=NebulaType.HYDROGEN)
        self.assertEqual(nebula.collision_radius, 0.0)

        storm = Storm(in_hex=(1, 0), in_system="Sol", storm_type=StormType.PLASMA)
        self.assertEqual(storm.collision_radius, 0.0)

        wormhole = Wormhole(in_hex=(1, 0), in_system="Sol", exit_system_name="Alpha")
        self.assertEqual(wormhole.collision_radius, 0.0)


class TestMoveOrderCollisionAvoidance(unittest.TestCase):
    def setUp(self):
        from unittest.mock import MagicMock
        self.game = MagicMock()
        self.galaxy = SimpleGalaxy()
        self.game.galaxy = self.galaxy
        self.system = self.galaxy.systems["Sol"]
        self.hex_00 = self.system.hexes[(0, 0)]
        self.star = Star(in_system="Sol", star_type=StarType.G_TYPE)
        self.hex_00.add_celestial_body(self.star)

        self.player = MockPlayer()
        self.game.players = [self.player]
        self.game.current_player_index = 0

        self.unit = MockUnit()
        self.unit.owner = self.player
        self.unit.game = self.game
        self.unit.in_galaxy = self.galaxy
        self.unit.in_system = "Sol"
        self.unit.in_hex = (0, 0)
        self.unit.position = Position(-1500, 0)

        self.engines = Engines(self.unit, speed=100.0)
        self.hyperdrive = Hyperdrive(self.unit, drive_type=HyperdriveType.BASIC)
        self.commander = Commander(self.unit)
        self.unit.add_component(self.engines)
        self.unit.add_component(self.hyperdrive)
        self.unit.add_component(self.commander)
        self.hex_00.add_unit(self.unit)

    def test_move_order_intra_hex_routes_around_star(self):
        # Move across the star at (0, 0) from (-1500, 0) to (1500, 0)
        move_order = MoveOrder(self.unit, {
            "destination_system_name": "Sol",
            "destination_hex_coord": (0, 0),
            "destination_position": Position(1500, 0)
        })
        move_order.execute(self.galaxy)

        # Should have generated avoidance sub-order(s) + the final destination sub-order
        self.assertGreater(len(move_order.sub_orders), 1)

        # All waypoint sub-orders must steer clear of the star
        for sub in move_order.sub_orders:
            pos = sub.parameters["destination_position"]
            if distance(pos, Position(1500, 0)) > 0.01:
                # This is an intermediate avoidance waypoint
                self.assertGreaterEqual(distance(pos, Position(0, 0)), STAR_RADIUS + 50.0 - 1e-6)

    def test_move_order_clear_path_has_single_sub_order(self):
        # Move from (-1500, 2000) to (1500, 2000) - completely above the star
        self.unit.position = Position(-1500, 2000)
        move_order = MoveOrder(self.unit, {
            "destination_system_name": "Sol",
            "destination_hex_coord": (0, 0),
            "destination_position": Position(1500, 2000)
        })
        move_order.execute(self.galaxy)

        # No collision -> exactly 1 ReachWaypointOrder sub-order
        self.assertEqual(len(move_order.sub_orders), 1)
        self.assertEqual(move_order.sub_orders[0].parameters["destination_position"], Position(1500, 2000))

    def test_turn_processor_movement_around_star(self):
        # Order the ship to move from (-1500, 0) to (1500, 0)
        move_order = MoveOrder(self.unit, {
            "destination_system_name": "Sol",
            "destination_hex_coord": (0, 0),
            "destination_position": Position(1500, 0)
        })
        self.commander.add_order(move_order)

        tp = TurnProcessor(self.game)
        
        # Run turns until the ship reaches the destination
        max_turns = 100
        turns = 0
        min_distance_to_star = float('inf')

        while move_order.status != OrderStatus.COMPLETED and turns < max_turns:
            tp.process_turn()
            turns += 1
            dist_to_star = distance(self.unit.position, Position(0, 0))
            if dist_to_star < min_distance_to_star:
                min_distance_to_star = dist_to_star

        self.assertEqual(move_order.status, OrderStatus.COMPLETED)
        self.assertLess(distance(self.unit.position, Position(1500, 0)), 1.0)
        # Ship should never have entered the Star's physical collision radius (STAR_RADIUS = 750.015)
        self.assertGreaterEqual(min_distance_to_star, STAR_RADIUS - 1.0)


class TestPatrolOrderCollisionAvoidance(unittest.TestCase):
    def setUp(self):
        from unittest.mock import MagicMock
        self.game = MagicMock()
        self.galaxy = SimpleGalaxy()
        self.game.galaxy = self.galaxy
        self.system = self.galaxy.systems["Sol"]
        self.hex_00 = self.system.hexes[(0, 0)]
        self.star = Star(in_system="Sol", star_type=StarType.G_TYPE)
        self.hex_00.add_celestial_body(self.star)

        self.player = MockPlayer()
        self.game.players = [self.player]
        self.game.current_player_index = 0

        self.unit = MockUnit()
        self.unit.owner = self.player
        self.unit.game = self.game
        self.unit.in_galaxy = self.galaxy
        self.unit.in_system = "Sol"
        self.unit.in_hex = (0, 0)
        self.unit.position = Position(-1500, 0)

        self.engines = Engines(self.unit, speed=100.0)
        self.hyperdrive = Hyperdrive(self.unit, drive_type=HyperdriveType.BASIC)
        self.commander = Commander(self.unit)
        self.unit.add_component(self.engines)
        self.unit.add_component(self.hyperdrive)
        self.unit.add_component(self.commander)
        self.hex_00.add_unit(self.unit)

    def test_patrol_order_avoids_star(self):
        patrol_order = PatrolOrder(self.unit, {
            "destination_system_name": "Sol",
            "destination_hex_coord": (0, 0),
            "destination_position": Position(1500, 0)
        })
        patrol_order.execute(self.galaxy)

        # PatrolOrder spawns a MoveOrder sub-order
        self.assertEqual(len(patrol_order.sub_orders), 1)
        move_sub = patrol_order.sub_orders[0]
        self.assertEqual(move_sub.order_type, OrderType.MOVE)

        # When the MoveOrder executes, it must have collision avoidance sub-orders
        move_sub.execute(self.galaxy)
        self.assertGreater(len(move_sub.sub_orders), 1)


if __name__ == '__main__':
    unittest.main()
