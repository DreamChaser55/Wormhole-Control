"""Comprehensive tests for celestial body traits, environmental hazards, and tactical cover."""

import pytest
from entities import (
    Unit, Star, Planet, Moon, ColonizableAsteroid, MetalAsteroid, Comet,
    AsteroidField, IceField, DebrisField, Nebula, Storm, Player
)
from constants import (
    PlanetType, StarType, NebulaType, StormType, HullSize,
    PLANET_TRAITS, CELESTIAL_FIELD_RADIUS, STORM_RADIUS,
    ICE_FIELD_BEAM_DEFENSE_BONUS, DEBRIS_FIELD_DEFENSE_BONUS,
    BLACK_HOLE_EVENT_HORIZON_RADIUS, BLACK_HOLE_EVENT_HORIZON_DAMAGE,
    BLACK_HOLE_INHIBITION_RADIUS, PULSAR_SHIELD_DRAIN_PERCENT,
    STORM_PLASMA_DAMAGE_PER_TURN, STORM_MAGNETIC_AM_DRAIN_PER_TURN,
    STORM_RADIATION_COMPONENT_DAMAGE_PER_TURN,
    DUST_NEBULA_SENSOR_MOD, HYDROGEN_NEBULA_HARVEST_MULTIPLIER
)
from geometry import Position
from utils import HexCoord
from unit_components import (
    ColonyComponent, MiningComponent, AntimatterHarvester, AntimatterStorage,
    Engines, Sensors
)
from unit_orders import ColonizeOrder, LoadColonistsOrder
from visibility import VisibilityService, is_unit_in_asteroid_field


class MockGalaxy:
    def __init__(self):
        self.systems = {}
        self.turn_number = 1

    def get_celestial_body_by_id(self, body_id):
        for system in self.systems.values():
            for _, body in system.get_all_celestial_bodies():
                if body.id == body_id:
                    return body
        return None


class MockSystem:
    def __init__(self, name="Sol"):
        self.name = name
        self.hexes = {}
        self.star = None

    def get_all_units(self):
        units = []
        for hex_coord, hex_obj in self.hexes.items():
            for unit in hex_obj.units:
                units.append((unit, hex_coord))
        return units

    def get_all_celestial_bodies(self):
        bodies = []
        for hex_coord, hex_obj in self.hexes.items():
            for body in hex_obj.celestial_bodies:
                bodies.append((hex_coord, body))
        return bodies


class MockHex:
    def __init__(self, coord=(0, 0)):
        self.coord = coord
        self.units = []
        self.celestial_bodies = []
        self.dynamic_inhibition_zones = {}


class MockGame:
    def __init__(self):
        self.galaxy = MockGalaxy()
        self.players = []
        self.current_player_index = 0
        self.turn_number = 1
        self.selected_objects = []


def create_test_unit(owner, name="Scout", in_system="Sol", in_hex=(0, 0), pos=Position(0, 0), game=None):
    if game is None:
        game = MockGame()
    u = Unit(owner=owner, position=pos, in_hex=in_hex, in_system=in_system, name=name, hull_size=HullSize.SMALL, game=game)
    return u


def test_planet_traits_initialization():
    """Verify planetary types correctly initialize traits from PLANET_TRAITS."""
    earth = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.TERRAN)
    assert earth.is_colonizable is True
    assert earth.growth_rate == 0.02
    assert earth.passive_metal == 0.0

    volcanic = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.VOLCANIC)
    assert volcanic.is_colonizable is True
    assert volcanic.passive_metal == 5.0
    assert volcanic.growth_rate == 0.008

    ice = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.ICE)
    assert ice.is_colonizable is True
    assert ice.passive_crystal == 2.0

    jupiter = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.GAS_GIANT)
    assert jupiter.is_colonizable is False
    assert jupiter.harvest_multiplier == 0.5
    assert jupiter.inhibition_field_radius == 2800.0
    assert jupiter.collision_radius == 450.0


def test_star_types_initialization():
    """Verify extreme star parameters."""
    black_hole = Star(in_system="Core", star_type=StarType.BLACK_HOLE)
    assert black_hole.inhibition_field_radius == BLACK_HOLE_INHIBITION_RADIUS

    blue_giant = Star(in_system="Orion", star_type=StarType.BLUE_GIANT)
    assert blue_giant.inhibition_field_radius == 3000.0
    assert blue_giant.collision_radius == 600.0


def test_gas_giant_uncolonizable_orders():
    """Verify Colonize and LoadColonists orders reject Gas Giants."""
    p1 = Player("Player 1", (0, 100, 255))
    unit = create_test_unit(p1)
    colony_comp = ColonyComponent(unit)
    colony_comp.population_cargo = 50
    unit.add_component(colony_comp)

    gas_giant = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.GAS_GIANT)
    gas_giant.position = Position(0, 0)

    galaxy = MockGalaxy()
    system = MockSystem("Sol")
    hex_obj = MockHex((0, 0))
    hex_obj.units.append(unit)
    hex_obj.celestial_bodies.append(gas_giant)
    system.hexes[(0, 0)] = hex_obj
    galaxy.systems["Sol"] = system

    # Direct ColonyComponent load and unload
    assert colony_comp.unload_population(gas_giant, 10) is False
    assert colony_comp.load_population(gas_giant, 10) is False

    # ColonizeOrder preflight / execution
    colonize_order = ColonizeOrder(unit, {"target_id": gas_giant.id})
    colonize_order.execute(galaxy)
    assert colonize_order.status.name == "FAILED"
    assert colonize_order.failure_reason == "target_not_colonizable"

    # LoadColonistsOrder execution
    load_order = LoadColonistsOrder(unit, {"target_id": gas_giant.id, "amount": 10})
    load_order.execute(galaxy)
    assert load_order.status.name == "FAILED"
    assert load_order.failure_reason == "target_not_colonizable"


def test_asteroid_field_non_mineable_and_metal_asteroid_mineable():
    """Verify AsteroidField cannot be mined for metal, but MetalAsteroid can."""
    p1 = Player("Player 1", (0, 100, 255))
    unit = create_test_unit(p1)
    mining = MiningComponent(unit)
    unit.add_component(mining)

    galaxy = MockGalaxy()
    system = MockSystem("Sol")
    hex_obj = MockHex((0, 0))
    hex_obj.units.append(unit)

    asteroid_field = AsteroidField(in_hex=(0, 0), in_system="Sol")
    asteroid_field.position = Position(0, 0)
    hex_obj.celestial_bodies.append(asteroid_field)

    metal_asteroid = MetalAsteroid(in_hex=(0, 0), in_system="Sol")
    metal_asteroid.position = Position(0, 0)
    hex_obj.celestial_bodies.append(metal_asteroid)

    system.hexes[(0, 0)] = hex_obj
    galaxy.systems["Sol"] = system

    # Target AsteroidField -> no raw metal mined
    mining.set_target(asteroid_field)
    mining.update(galaxy)
    assert mining.raw_metal_cargo == 0.0

    # Target MetalAsteroid -> successfully mined
    mining.set_target(metal_asteroid)
    mining.update(galaxy)
    assert mining.raw_metal_cargo == 10.0


def test_ice_field_and_debris_field_tactical_cover():
    """Verify tactical cover defense bonus against beam (IceField) and kinetic/missile (DebrisField)."""
    p1 = Player("Player 1", (0, 100, 255))
    game = MockGame()
    galaxy = game.galaxy
    system = MockSystem("Sol")
    hex_obj = MockHex((0, 0))

    unit = create_test_unit(p1, pos=Position(100, 100), game=game)
    hex_obj.units.append(unit)

    ice_field = IceField(in_hex=(0, 0), in_system="Sol")
    ice_field.position = Position(100, 100)
    hex_obj.celestial_bodies.append(ice_field)

    system.hexes[(0, 0)] = hex_obj
    galaxy.systems["Sol"] = system

    # In IceField: beam cover bonus should be 10%
    assert unit.get_environmental_cover_bonus("beam") == pytest.approx(ICE_FIELD_BEAM_DEFENSE_BONUS)
    assert unit.get_environmental_cover_bonus("missile") == 0.0

    # Switch IceField to DebrisField
    hex_obj.celestial_bodies.remove(ice_field)
    debris_field = DebrisField(in_hex=(0, 0), in_system="Sol")
    debris_field.position = Position(100, 100)
    hex_obj.celestial_bodies.append(debris_field)

    # In DebrisField: mass_driver and missile cover bonus should be 10%
    assert unit.get_environmental_cover_bonus("mass_driver") == pytest.approx(DEBRIS_FIELD_DEFENSE_BONUS)
    assert unit.get_environmental_cover_bonus("missile") == pytest.approx(DEBRIS_FIELD_DEFENSE_BONUS)
    assert unit.get_environmental_cover_bonus("beam") == 0.0


def test_antimatter_harvesting_from_gas_giant_and_hydrogen_nebula():
    """Verify AntimatterHarvester can harvest from Gas Giants (0.5x) and Hydrogen Nebulae (0.4x)."""
    p1 = Player("Player 1", (0, 100, 255))
    unit = create_test_unit(p1, pos=Position(0, 0))
    am_comp = unit.antimatter_component
    am_comp.max_capacity = 200.0
    am_comp.current_amount = 50.0

    harvester = AntimatterHarvester(unit, harvest_rate=10.0)
    unit.add_component(harvester)

    galaxy = MockGalaxy()
    system = MockSystem("Sol")
    hex_obj = MockHex((0, 0))
    hex_obj.units.append(unit)

    gas_giant = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.GAS_GIANT)
    gas_giant.position = Position(0, 0)
    hex_obj.celestial_bodies.append(gas_giant)

    system.hexes[(0, 0)] = hex_obj
    galaxy.systems["Sol"] = system

    # Harvest from Gas Giant
    source = harvester.find_nearby_star(galaxy)
    assert source == gas_giant
    harvester.update(galaxy)
    assert harvester.is_harvesting is True
    # 50 + 10 * 0.5 = 55
    assert am_comp.current_amount == pytest.approx(55.0)

    # Swap Gas Giant for Hydrogen Nebula
    hex_obj.celestial_bodies.remove(gas_giant)
    nebula = Nebula(in_hex=(0, 0), in_system="Sol", nebula_type=NebulaType.HYDROGEN)
    nebula.position = Position(0, 0)
    hex_obj.celestial_bodies.append(nebula)

    source = harvester.find_nearby_star(galaxy)
    assert source == nebula
    harvester.update(galaxy)
    # 55 + 10 * 0.4 = 59
    assert am_comp.current_amount == pytest.approx(59.0)


def test_environmental_hazards_in_turn_processor():
    """Verify Plasma Storm damage, Magnetic Storm AM drain, and Black Hole event horizon damage."""
    from turn_processor import TurnProcessor

    p1 = Player("Player 1", (0, 100, 255))
    p1.is_human = False
    game = MockGame()
    game.players.append(p1)
    processor = TurnProcessor(game)

    system = MockSystem("Sol")
    hex_obj = MockHex((0, 0))

    # Unit 1: in Plasma Storm
    u1 = create_test_unit(p1, name="Ship1", pos=Position(100, 100), game=game)
    u1.current_hit_points = 100
    hex_obj.units.append(u1)

    storm_plasma = Storm(in_hex=(0, 0), in_system="Sol", storm_type=StormType.PLASMA)
    storm_plasma.position = Position(100, 100)
    hex_obj.celestial_bodies.append(storm_plasma)

    # Unit 2: in Magnetic Storm
    u2 = create_test_unit(p1, name="Ship2", pos=Position(500, 500), game=game)
    am_comp = u2.antimatter_component
    am_comp.current_amount = 50.0
    hex_obj.units.append(u2)

    storm_mag = Storm(in_hex=(0, 0), in_system="Sol", storm_type=StormType.MAGNETIC)
    storm_mag.position = Position(500, 500)
    hex_obj.celestial_bodies.append(storm_mag)

    system.hexes[(0, 0)] = hex_obj
    game.galaxy.systems["Sol"] = system

    processor._process_environmental_hazards(p1)

    # Plasma storm inflicts STORM_PLASMA_DAMAGE_PER_TURN (8)
    assert u1.current_hit_points == 100 - int(STORM_PLASMA_DAMAGE_PER_TURN)

    # Magnetic storm drains STORM_MAGNETIC_AM_DRAIN_PER_TURN (6)
    assert am_comp.current_amount == pytest.approx(50.0 - STORM_MAGNETIC_AM_DRAIN_PER_TURN)


def test_black_hole_event_horizon_hazard():
    """Verify Black Hole event horizon damages ships within 750 radius."""
    from turn_processor import TurnProcessor

    p1 = Player("Player 1", (0, 100, 255))
    p1.is_human = False
    game = MockGame()
    game.players.append(p1)
    processor = TurnProcessor(game)

    system = MockSystem("Sol")
    system.star = Star(in_system="Sol", star_type=StarType.BLACK_HOLE)
    system.star.position = Position(0, 0)

    hex_obj = MockHex((0, 0))
    u1 = create_test_unit(p1, name="Probe", pos=Position(500, 0), game=game)  # Distance 500 <= 750
    u1.current_hit_points = 100
    hex_obj.units.append(u1)

    system.hexes[(0, 0)] = hex_obj
    game.galaxy.systems["Sol"] = system

    processor._process_environmental_hazards(p1)

    assert u1.current_hit_points == 100 - int(BLACK_HOLE_EVENT_HORIZON_DAMAGE)


def test_passive_resource_generation_from_colonized_planets():
    """Verify colonized planets generate passive metal/crystal for owner."""
    from turn_processor import TurnProcessor

    p1 = Player("Player 1", (0, 100, 255))
    p1.metal = 0.0
    p1.crystal = 0.0
    p1.credits = 0.0

    game = MockGame()
    game.players.append(p1)
    processor = TurnProcessor(game)

    system = MockSystem("Sol")
    hex_obj = MockHex((0, 0))

    volcanic = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.VOLCANIC)
    volcanic.owner = p1
    volcanic.population = 10.0  # Pop > 0
    hex_obj.celestial_bodies.append(volcanic)

    ice = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.ICE)
    ice.owner = p1
    ice.population = 10.0
    hex_obj.celestial_bodies.append(ice)

    system.hexes[(0, 0)] = hex_obj
    game.galaxy.systems["Sol"] = system

    processor._process_resource_generation(p1)

    assert p1.metal == pytest.approx(volcanic.passive_metal)
    assert p1.crystal == pytest.approx(ice.passive_crystal)


def test_asteroid_field_radar_stealth():
    """Verify units inside AsteroidField are concealed from enemy long-range sensor presence."""
    p1 = Player("Viewer", (0, 100, 255))
    p2 = Player("Enemy", (255, 0, 0))

    game = MockGame()
    galaxy = game.galaxy
    system = MockSystem("Sol")

    # Observer unit for P1 with long-range radar in hex (0, 0)
    obs_unit = create_test_unit(p1, name="Observer", in_hex=(0, 0), pos=Position(0, 0), game=game)
    sensors = Sensors(obs_unit, short_range_radius=300.0, long_range_hexes=2, hull_cost=0)
    obs_unit.add_component(sensors)

    # Enemy unit in hex (1, 0) inside an AsteroidField
    enemy_unit = create_test_unit(p2, name="EnemyShip", in_hex=(1, 0), pos=Position(100, 100), game=game)

    hex0 = MockHex((0, 0))
    hex0.units.append(obs_unit)

    hex1 = MockHex((1, 0))
    hex1.units.append(enemy_unit)
    ast_field = AsteroidField(in_hex=(1, 0), in_system="Sol")
    ast_field.position = Position(100, 100)
    hex1.celestial_bodies.append(ast_field)

    system.hexes[(0, 0)] = hex0
    system.hexes[(1, 0)] = hex1
    galaxy.systems["Sol"] = system

    # Check is_unit_in_asteroid_field helper
    assert is_unit_in_asteroid_field(enemy_unit, galaxy) is True
    assert is_unit_in_asteroid_field(obs_unit, galaxy) is False

    # Compute visibility snapshot for Viewer
    snapshot = VisibilityService.compute(galaxy, p1, turn_number=1)

    # Enemy unit should NOT appear in presence_hexes because AsteroidField conceals from long-range radar
    assert ("Sol", (1, 0)) not in snapshot.presence_hexes
    assert enemy_unit.id not in snapshot.visible_enemy_unit_ids


def test_debris_field_speed_hazard():
    """Verify moving at speed > 50 through DebrisField causes abrasion damage."""
    from turn_processor import TurnProcessor

    p1 = Player("Player 1", (0, 100, 255))
    p1.is_human = False
    game = MockGame()
    game.players.append(p1)
    processor = TurnProcessor(game)

    system = MockSystem("Sol")
    hex_obj = MockHex((0, 0))

    u = create_test_unit(p1, name="FastShip", pos=Position(100, 100), game=game)
    u.current_hit_points = 100
    eng = Engines(u, speed=120.0)
    eng.move_target = Position(200, 200)
    u.add_component(eng)
    hex_obj.units.append(u)

    debris = DebrisField(in_hex=(0, 0), in_system="Sol")
    debris.position = Position(100, 100)
    hex_obj.celestial_bodies.append(debris)

    system.hexes[(0, 0)] = hex_obj
    game.galaxy.systems["Sol"] = system

    processor._process_environmental_hazards(p1)

    # FastShip took DEBRIS_FIELD_HAZARD_DAMAGE (2)
    assert u.current_hit_points == 98

