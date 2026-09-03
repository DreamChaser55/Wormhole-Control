"""Unit tests for strikecraft celestial body effects:
- Immunity to negative field effects (speed reduction and debris abrasion)
- Preservation of positive field tactical cover
- Ban on entering or launching in magnetic storms
- Avoidance routing around magnetic storms
- Turn processor clamping at storm boundaries
- AI rule generation and command preflight rejection
"""

import pytest
import math
from utils import HexCoord
from geometry import Position, Circle, distance
from constants import (
    HullSize, StormType, CELESTIAL_FIELD_RADIUS, STORM_RADIUS,
    ASTEROID_FIELD_SPEED_MOD, ICE_FIELD_SPEED_MOD, DEBRIS_FIELD_SPEED_MOD,
    DEBRIS_FIELD_HAZARD_SPEED_THRESHOLD, DEBRIS_FIELD_HAZARD_DAMAGE
)
from entities import (
    Unit, AsteroidField, IceField, DebrisField, Storm,
    is_position_in_magnetic_storm
)
from unit_components import (
    Engines, Hyperdrive, HyperdriveType, Commander, StrikecraftBayComponent,
    StrikecraftWingComponent, WingType, Defenses, TurretType
)
from unit_orders import (
    OrderStatus, MoveOrder, ReachWaypointOrder, DeployUnitOrder, DeployAllWingsOrder
)
from unit_orders.movement import get_hex_collision_obstacles
from turn_processor import TurnProcessor


class MockPlayer:
    def __init__(self, name="Player 1"):
        self.name = name
        self.id = 1
        self.credits = 1000.0


class MockHex:
    def __init__(self, coord):
        self.coord = coord
        self.celestial_bodies = []
        self.dynamic_inhibition_zones = {}

    def get_all_inhibition_zones(self):
        return list(self.dynamic_inhibition_zones.values())


class MockSystem:
    def __init__(self, name="Alpha"):
        self.name = name
        self.hexes = {HexCoord(0, 0): MockHex(HexCoord(0, 0)), HexCoord(1, 0): MockHex(HexCoord(1, 0))}
        self.units = []
        self.star = None

    def get_all_units(self):
        return [(unit, unit.in_hex) for unit in self.units]

    def add_unit(self, unit):
        if unit not in self.units:
            self.units.append(unit)

    def remove_unit(self, unit):
        if unit in self.units:
            self.units.remove(unit)


class MockGalaxy:
    def __init__(self):
        self.systems = {"Alpha": MockSystem("Alpha")}

    def get_unit_by_id(self, unit_id):
        for system in self.systems.values():
            for unit in system.units:
                if unit.id == unit_id:
                    return unit
        return None

    def get_celestial_body_by_id(self, body_id):
        for system in self.systems.values():
            for hex_obj in system.hexes.values():
                for body in hex_obj.celestial_bodies:
                    if body.id == body_id:
                        return body
        return None


class MockGame:
    def __init__(self):
        self.galaxy = MockGalaxy()
        self.players = [MockPlayer()]
        self.current_player_index = 0
        self.turn_number = 1
        self.sidebar_needs_update = False
        self.gui = None


def create_test_ship(name, hull_size, speed=100.0, owner=None, game=None):
    if owner is None:
        owner = game.players[0] if game and game.players else MockPlayer()
    unit = Unit(
        name=name,
        owner=owner,
        position=Position(0.0, 0.0),
        in_hex=HexCoord(0, 0),
        in_system="Alpha",
        hull_size=hull_size,
        game=game
    )
    unit.current_hit_points = unit.max_hit_points
    if unit.antimatter_component:
        unit.antimatter_component.current_amount = 100.0
    eng = Engines(unit=unit, speed=speed)
    unit.add_component(eng)
    if game:
        system = game.galaxy.systems["Alpha"]
        system.add_unit(unit)
    return unit


def test_strikecraft_ignores_field_speed_penalties():
    """Strikecraft wings ignore speed penalties from Asteroid, Ice, and Debris fields."""
    game = MockGame()
    tp = TurnProcessor(game)
    hex_obj = game.galaxy.systems["Alpha"].hexes[HexCoord(0, 0)]

    # Add an asteroid field (0.75x speed)
    ast_field = AsteroidField(in_hex=HexCoord(0, 0), in_system="Alpha")
    ast_field.position = Position(0.0, 0.0)
    hex_obj.celestial_bodies.append(ast_field)

    strikecraft = create_test_ship("Wing 1", HullSize.STRIKECRAFT_WING, speed=100.0, game=game)
    normal_ship = create_test_ship("Frigate 1", HullSize.SMALL, speed=100.0, game=game)

    strikecraft.position = Position(0.0, 0.0)
    normal_ship.position = Position(0.0, 0.0)

    order1 = ReachWaypointOrder(strikecraft, {
        "destination_system_name": "Alpha",
        "destination_hex_coord": HexCoord(0, 0),
        "destination_position": Position(200.0, 0.0)
    })
    order1.status = OrderStatus.IN_PROGRESS
    strikecraft.commander_component.current_order = order1
    strikecraft.engines_component.set_move_target(Position(200.0, 0.0), order1.order_id)

    order2 = ReachWaypointOrder(normal_ship, {
        "destination_system_name": "Alpha",
        "destination_hex_coord": HexCoord(0, 0),
        "destination_position": Position(200.0, 0.0)
    })
    order2.status = OrderStatus.IN_PROGRESS
    normal_ship.commander_component.current_order = order2
    normal_ship.engines_component.set_move_target(Position(200.0, 0.0), order2.order_id)

    tp._process_movement(game.players[0])

    # Strikecraft should move full 100 distance (ignores 0.75x penalty)
    assert math.isclose(strikecraft.position.x, 100.0, abs_tol=0.1)
    # Normal ship should move 75 distance (0.75 * 100)
    assert math.isclose(normal_ship.position.x, 75.0, abs_tol=0.1)


def test_strikecraft_ignores_debris_abrasion():
    """Strikecraft wings ignore high-speed abrasion hazard in Debris fields."""
    game = MockGame()
    tp = TurnProcessor(game)
    hex_obj = game.galaxy.systems["Alpha"].hexes[HexCoord(0, 0)]

    debris = DebrisField(in_hex=HexCoord(0, 0), in_system="Alpha")
    debris.position = Position(0.0, 0.0)
    hex_obj.celestial_bodies.append(debris)

    strikecraft = create_test_ship("Wing 1", HullSize.STRIKECRAFT_WING, speed=80.0, game=game)
    normal_ship = create_test_ship("Destroyer 1", HullSize.MEDIUM, speed=80.0, game=game)

    strikecraft.position = Position(0.0, 0.0)
    normal_ship.position = Position(0.0, 0.0)

    strikecraft.engines_component.set_move_target(Position(200.0, 0.0), 1)
    normal_ship.engines_component.set_move_target(Position(200.0, 0.0), 2)

    tp._process_environmental_hazards(game.players[0])

    # Strikecraft wing should take 0 damage
    assert strikecraft.current_hit_points == strikecraft.max_hit_points
    # Normal ship should take DEBRIS_FIELD_HAZARD_DAMAGE (2 HP)
    assert normal_ship.current_hit_points == normal_ship.max_hit_points - int(DEBRIS_FIELD_HAZARD_DAMAGE)


def test_strikecraft_retains_positive_field_cover():
    """Strikecraft wings still benefit from tactical cover in Ice and Debris fields."""
    game = MockGame()
    hex_obj = game.galaxy.systems["Alpha"].hexes[HexCoord(0, 0)]

    ice = IceField(in_hex=HexCoord(0, 0), in_system="Alpha")
    ice.position = Position(0.0, 0.0)
    hex_obj.celestial_bodies.append(ice)

    strikecraft = create_test_ship("Wing 1", HullSize.STRIKECRAFT_WING, game=game)
    strikecraft.position = Position(0.0, 0.0)

    # Beam cover in Ice field
    beam_cover = strikecraft.get_environmental_cover_bonus(TurretType.BEAM)
    assert beam_cover > 0.0

    # Kinetic cover in Ice field should be 0
    assert strikecraft.get_environmental_cover_bonus(TurretType.MASS_DRIVER) == 0.0

    debris = DebrisField(in_hex=HexCoord(0, 0), in_system="Alpha")
    debris.position = Position(0.0, 0.0)
    hex_obj.celestial_bodies.append(debris)

    # Kinetic cover in Debris field
    kinetic_cover = strikecraft.get_environmental_cover_bonus(TurretType.MASS_DRIVER)
    assert kinetic_cover > 0.0


def test_strikecraft_banned_from_entering_magnetic_storm_direct_order():
    """MoveOrder and ReachWaypointOrder fail with hazard_blocked when targeting inside a magnetic storm."""
    game = MockGame()
    hex_obj = game.galaxy.systems["Alpha"].hexes[HexCoord(0, 0)]

    storm = Storm(in_hex=HexCoord(0, 0), in_system="Alpha", storm_type=StormType.MAGNETIC)
    storm.position = Position(500.0, 0.0)
    hex_obj.celestial_bodies.append(storm)

    strikecraft = create_test_ship("Wing 1", HullSize.STRIKECRAFT_WING, game=game)
    strikecraft.position = Position(0.0, 0.0)

    # Move order targeting center of magnetic storm
    move_order = MoveOrder(strikecraft, {
        "destination_system_name": "Alpha",
        "destination_hex_coord": HexCoord(0, 0),
        "destination_position": Position(500.0, 0.0)
    })
    move_order.execute(galaxy_ref=game.galaxy)

    assert move_order.status == OrderStatus.FAILED
    assert move_order.failure_reason == "hazard_blocked"

    # ReachWaypointOrder directly targeting inside
    wp_order = ReachWaypointOrder(strikecraft, {
        "destination_system_name": "Alpha",
        "destination_hex_coord": HexCoord(0, 0),
        "destination_position": Position(500.0, 0.0)
    })
    wp_order.execute(galaxy_ref=game.galaxy)

    assert wp_order.status == OrderStatus.FAILED
    assert wp_order.failure_reason == "hazard_blocked"


def test_strikecraft_movement_avoidance_around_magnetic_storm():
    """Strikecraft wings treat magnetic storms as collision obstacles and path around them."""
    game = MockGame()
    hex_obj = game.galaxy.systems["Alpha"].hexes[HexCoord(0, 0)]

    storm = Storm(in_hex=HexCoord(0, 0), in_system="Alpha", storm_type=StormType.MAGNETIC)
    storm.position = Position(2000.0, 0.0)
    hex_obj.celestial_bodies.append(storm)

    strikecraft = create_test_ship("Wing 1", HullSize.STRIKECRAFT_WING, game=game)
    normal_ship = create_test_ship("Frigate 1", HullSize.SMALL, game=game)

    # Obstacles for strikecraft should include magnetic storm
    sc_obstacles = get_hex_collision_obstacles(game.galaxy, "Alpha", HexCoord(0, 0), unit=strikecraft)
    assert len(sc_obstacles) == 1
    assert math.isclose(sc_obstacles[0].radius, STORM_RADIUS)

    # Obstacles for normal ship should NOT include magnetic storm
    norm_obstacles = get_hex_collision_obstacles(game.galaxy, "Alpha", HexCoord(0, 0), unit=normal_ship)
    assert len(norm_obstacles) == 0

    # Strikecraft moving from (0, 0) to (4000, 0) through the storm at (2000, 0) should create avoidance sub-orders
    strikecraft.position = Position(0.0, 0.0)
    move_order = MoveOrder(strikecraft, {
        "destination_system_name": "Alpha",
        "destination_hex_coord": HexCoord(0, 0),
        "destination_position": Position(4000.0, 0.0)
    })
    move_order.execute(galaxy_ref=game.galaxy)

    assert move_order.status == OrderStatus.IN_PROGRESS
    assert len(move_order.sub_orders) > 1


def test_strikecraft_sublight_movement_halts_at_storm_boundary():
    """Turn processor stops strikecraft wings from advancing into a magnetic storm."""
    game = MockGame()
    tp = TurnProcessor(game)
    hex_obj = game.galaxy.systems["Alpha"].hexes[HexCoord(0, 0)]

    storm = Storm(in_hex=HexCoord(0, 0), in_system="Alpha", storm_type=StormType.MAGNETIC)
    storm.position = Position(1000.0, 0.0)
    hex_obj.celestial_bodies.append(storm)

    strikecraft = create_test_ship("Wing 1", HullSize.STRIKECRAFT_WING, speed=100.0, game=game)
    # Position just outside storm radius (1000 - STORM_RADIUS - 10)
    start_x = 1000.0 - STORM_RADIUS - 10.0
    strikecraft.position = Position(start_x, 0.0)

    # Attempting to move into the storm
    order = ReachWaypointOrder(strikecraft, {
        "destination_system_name": "Alpha",
        "destination_hex_coord": HexCoord(0, 0),
        "destination_position": Position(1000.0, 0.0)
    })
    order.status = OrderStatus.IN_PROGRESS
    strikecraft.commander_component.current_order = order
    strikecraft.engines_component.set_move_target(Position(1000.0, 0.0), order.order_id)

    tp._process_movement(game.players[0])

    # Should not be inside the storm, but should have advanced to the boundary
    assert strikecraft.position.x > start_x
    dist_to_center = distance(strikecraft.position, storm.position)
    assert dist_to_center > STORM_RADIUS
    assert strikecraft.engines_component.move_target is None


def test_strikecraft_cannot_launch_in_magnetic_storm():
    """Carriers cannot launch strikecraft wings when inside a magnetic storm."""
    game = MockGame()
    hex_obj = game.galaxy.systems["Alpha"].hexes[HexCoord(0, 0)]

    storm = Storm(in_hex=HexCoord(0, 0), in_system="Alpha", storm_type=StormType.MAGNETIC)
    storm.position = Position(0.0, 0.0)
    hex_obj.celestial_bodies.append(storm)

    carrier = create_test_ship("Carrier 1", HullSize.LARGE, game=game)
    carrier.position = Position(0.0, 0.0)
    bay = StrikecraftBayComponent(carrier)
    carrier.add_component(bay)

    wing = create_test_ship("Fighter Wing Alpha", HullSize.STRIKECRAFT_WING, game=game)
    wing_comp = StrikecraftWingComponent(wing, wing_type=WingType.FIGHTER)
    wing.add_component(wing_comp)

    # Dock wing
    bay.docked_units.append(wing)
    wing.docked_in = carrier

    # can_deploy check
    assert bay.can_deploy(wing, game.galaxy) is False
    assert bay.deploy(wing, game.galaxy) is False

    # DeployUnitOrder check
    deploy_order = DeployUnitOrder(carrier, {"docked_unit_id": wing.id})
    deploy_order.execute(galaxy_ref=game.galaxy)
    assert deploy_order.status == OrderStatus.FAILED
    assert deploy_order.failure_reason == "hazard_blocked"

    # DeployAllWingsOrder check
    deploy_all_order = DeployAllWingsOrder(carrier)
    deploy_all_order.execute(galaxy_ref=game.galaxy)
    assert deploy_all_order.status == OrderStatus.FAILED
    assert deploy_all_order.failure_reason == "hazard_blocked"


def test_ai_rules_and_preflight_rejection():
    """Agentic AI rules omit deploy and CommandGateway preflight rejects hazardous commands."""
    from game_ai.rules import command_guidance
    from game_ai.commands import CommandGateway
    from game_ai.contracts import CommandBatch, Command

    game = MockGame()
    hex_obj = game.galaxy.systems["Alpha"].hexes[HexCoord(0, 0)]

    storm = Storm(in_hex=HexCoord(0, 0), in_system="Alpha", storm_type=StormType.MAGNETIC)
    storm.position = Position(0.0, 0.0)
    hex_obj.celestial_bodies.append(storm)

    carrier = create_test_ship("Carrier 1", HullSize.LARGE, game=game)
    carrier.position = Position(0.0, 0.0)
    bay = StrikecraftBayComponent(carrier)
    carrier.add_component(bay)

    wing = create_test_ship("Fighter Wing Alpha", HullSize.STRIKECRAFT_WING, game=game)
    bay.docked_units.append(wing)
    wing.docked_in = carrier

    # AI rules should NOT list deploy_unit or deploy_all_wings as legal
    legal_commands, options, _ = command_guidance(
        game, game.players[0], carrier, exact_bodies=[storm], visible_units=[carrier]
    )
    assert "deploy_unit" not in legal_commands
    assert "deploy_all_wings" not in legal_commands

    # Preflight gateway check for deploy_unit
    gateway = CommandGateway(game)
    deploy_batch = CommandBatch(
        commands=(
            Command(type="deploy_unit", unit_ids=(carrier.id,), target_id=wing.id),
        )
    )
    result = gateway.apply_batch(game.players[0], deploy_batch)
    assert not result.accepted
    assert result.errors[0].code == "hazard_blocked"

    # Preflight gateway check for move command targeting magnetic storm with strikecraft wing
    strikecraft = create_test_ship("Wing 2", HullSize.STRIKECRAFT_WING, game=game)
    strikecraft.position = Position(3000.0, 0.0)

    move_batch = CommandBatch(
        commands=(
            Command(
                type="move",
                unit_ids=(strikecraft.id,),
                system_name="Alpha",
                hex_coord=(0, 0),
                position=(0.0, 0.0)
            ),
        )
    )
    result_move = gateway.apply_batch(game.players[0], move_batch)
    assert not result_move.accepted
    assert result_move.errors[0].code == "hazard_blocked"
