import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import HullSize, NebulaType, NEBULA_RADIUS
from entities import Player, Unit, Nebula
from unit_components import Sensors
from visibility import VisibilityService, is_unit_visible, hex_has_presence, is_unit_in_nebula
from galaxy import Galaxy, StarSystem


@pytest.fixture
def galaxy_setup():
    p1 = Player("Player 1", (0, 0, 255), team_id=1)
    p2 = Player("Player 2", (255, 0, 0), team_id=2)
    p3 = Player("Player 3", (0, 255, 0), team_id=1)  # Ally of P1

    galaxy = Galaxy()
    system = StarSystem(name="Alpha", position=Position(0, 0), radius=3)
    galaxy.systems = {"Alpha": system}

    mock_game = MagicMock()
    mock_game.galaxy = galaxy
    mock_game.turn_number = 1

    return p1, p2, p3, galaxy, system, mock_game


def test_unit_inside_nebula_hidden_from_long_range_sensors(galaxy_setup):
    p1, p2, p3, galaxy, system, mock_game = galaxy_setup

    # Hex (0, 0) contains a Nebula
    nebula = Nebula(in_hex=(0, 0), in_system="Alpha", nebula_type=NebulaType.HYDROGEN)
    system.hexes[(0, 0)].add_celestial_body(nebula)

    # P1 sensor ship with long-range sensor coverage stationed far from center (Position 3500, 0)
    sensor_ship = Unit(p1, Position(3500, 0), in_hex=(0, 0), in_system="Alpha", name="RadarBase", hull_size=HullSize.MEDIUM, game=mock_game)
    sensor_ship.remove_component(Sensors)
    sensor_ship.add_component(Sensors(sensor_ship, short_range_radius=1000.0, long_range_hexes=1, hull_cost=5))

    # P2 enemy ship inside the nebula cloud (Position 500, 0 <= NEBULA_RADIUS 1666.68)
    # Distance from sensor_ship is 3000 > 1000 (outside short-range visual radius)
    enemy_ship = Unit(p2, Position(500, 0), in_hex=(0, 0), in_system="Alpha", name="EnemyLurker", hull_size=HullSize.SMALL, game=mock_game)

    system.hexes[(0, 0)].units.extend([sensor_ship, enemy_ship])

    assert is_unit_in_nebula(enemy_ship, galaxy) is True

    snapshot = VisibilityService.compute(galaxy, p1)

    # Long-range sensors cover (0, 0), but the enemy ship is concealed by the nebula!
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is False
    assert is_unit_visible(snapshot, enemy_ship) is False
    assert enemy_ship.id not in snapshot.visible_enemy_unit_ids


def test_unit_outside_nebula_radius_detected_by_long_range_sensors(galaxy_setup):
    p1, p2, p3, galaxy, system, mock_game = galaxy_setup

    # Hex (0, 0) contains a Nebula at (0, 0) with radius NEBULA_RADIUS = 3600.0
    nebula = Nebula(in_hex=(0, 0), in_system="Alpha", nebula_type=NebulaType.OXYGEN)
    system.hexes[(0, 0)].add_celestial_body(nebula)

    # P1 sensor ship stationed at (-4500, 0)
    sensor_ship = Unit(p1, Position(-4500, 0), in_hex=(0, 0), in_system="Alpha", name="RadarBase", hull_size=HullSize.MEDIUM, game=mock_game)
    sensor_ship.remove_component(Sensors)
    sensor_ship.add_component(Sensors(sensor_ship, short_range_radius=1000.0, long_range_hexes=1, hull_cost=5))

    # P2 enemy ship stationed at Position(4000, 0) — inside the same hex, but OUTSIDE the nebula radius!
    # Distance to sensor_ship is 8500 > 1000 (outside short-range visual radius)
    enemy_ship = Unit(p2, Position(4000, 0), in_hex=(0, 0), in_system="Alpha", name="EnemyCruiser", hull_size=HullSize.MEDIUM, game=mock_game)

    system.hexes[(0, 0)].units.extend([sensor_ship, enemy_ship])

    assert is_unit_in_nebula(enemy_ship, galaxy) is False

    snapshot = VisibilityService.compute(galaxy, p1)

    # Long-range sensors detect enemy presence because the ship is in open space
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is True
    assert is_unit_visible(snapshot, enemy_ship) is False  # Undetailed presence


def test_short_range_sensors_reveal_unit_inside_nebula(galaxy_setup):
    p1, p2, p3, galaxy, system, mock_game = galaxy_setup

    # Hex (0, 0) contains a Nebula
    nebula = Nebula(in_hex=(0, 0), in_system="Alpha", nebula_type=NebulaType.DUST)
    system.hexes[(0, 0)].add_celestial_body(nebula)

    # P2 enemy ship inside nebula at (0, 0)
    enemy_ship = Unit(p2, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="HiddenEnemy", hull_size=HullSize.SMALL, game=mock_game)

    # P1 sensor ship moves within short-range visual radius (Position 500, 0 <= 1000.0)
    sensor_ship = Unit(p1, Position(500, 0), in_hex=(0, 0), in_system="Alpha", name="Scout", hull_size=HullSize.SMALL, game=mock_game)
    sensor_ship.remove_component(Sensors)
    sensor_ship.add_component(Sensors(sensor_ship, short_range_radius=1000.0, long_range_hexes=1, hull_cost=5))

    system.hexes[(0, 0)].units.extend([sensor_ship, enemy_ship])

    snapshot = VisibilityService.compute(galaxy, p1)

    # Detailed short-range visual sensors penetrate the nebula!
    assert is_unit_visible(snapshot, enemy_ship) is True
    assert enemy_ship.id in snapshot.visible_enemy_unit_ids


def test_mixed_units_in_nebula_hex(galaxy_setup):
    p1, p2, p3, galaxy, system, mock_game = galaxy_setup

    nebula = Nebula(in_hex=(0, 0), in_system="Alpha", nebula_type=NebulaType.NITROGEN)
    system.hexes[(0, 0)].add_celestial_body(nebula)

    # P1 sensor ship at (-4500, 0) with 1000 short-range radius
    sensor_ship = Unit(p1, Position(-4500, 0), in_hex=(0, 0), in_system="Alpha", name="Watcher", hull_size=HullSize.MEDIUM, game=mock_game)
    sensor_ship.remove_component(Sensors)
    sensor_ship.add_component(Sensors(sensor_ship, short_range_radius=1000.0, long_range_hexes=1, hull_cost=5))

    # Enemy A is hidden inside the nebula (Position 200, 0)
    enemy_a = Unit(p2, Position(200, 0), in_hex=(0, 0), in_system="Alpha", name="EnemyA", hull_size=HullSize.SMALL, game=mock_game)
    # Enemy B is in open space outside nebula (Position 4000, 0)
    enemy_b = Unit(p2, Position(4000, 0), in_hex=(0, 0), in_system="Alpha", name="EnemyB", hull_size=HullSize.SMALL, game=mock_game)

    system.hexes[(0, 0)].units.extend([sensor_ship, enemy_a, enemy_b])

    # Case 1: Enemy B is outside nebula -> hex presence is reported
    snapshot = VisibilityService.compute(galaxy, p1)
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is True

    # Case 2: Enemy B also flies into the nebula (Position 800, 0) -> all enemies hidden!
    enemy_b.position = Position(800, 0)
    snapshot = VisibilityService.compute(galaxy, p1)
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is False


def test_friendly_and_allied_units_in_nebula_always_visible(galaxy_setup):
    p1, p2, p3, galaxy, system, mock_game = galaxy_setup

    nebula = Nebula(in_hex=(0, 0), in_system="Alpha", nebula_type=NebulaType.HYDROGEN)
    system.hexes[(0, 0)].add_celestial_body(nebula)

    p1_unit = Unit(p1, Position(0, 0), in_hex=(0, 0), in_system="Alpha", name="P1Ship", hull_size=HullSize.SMALL, game=mock_game)
    p3_ally_unit = Unit(p3, Position(100, 0), in_hex=(0, 0), in_system="Alpha", name="P3AllyShip", hull_size=HullSize.SMALL, game=mock_game)

    system.hexes[(0, 0)].units.extend([p1_unit, p3_ally_unit])

    snapshot = VisibilityService.compute(galaxy, p1)

    assert is_unit_visible(snapshot, p1_unit) is True
    assert is_unit_visible(snapshot, p3_ally_unit) is True


def test_is_unit_in_nebula_helper_functions(galaxy_setup):
    p1, p2, p3, galaxy, system, mock_game = galaxy_setup

    assert is_unit_in_nebula(None) is False

    nebula = Nebula(in_hex=(1, 0), in_system="Alpha", nebula_type=NebulaType.HYDROGEN)
    system.hexes[(1, 0)].add_celestial_body(nebula)

    unit = Unit(p1, Position(0, 0), in_hex=(1, 0), in_system="Alpha", name="TestShip", hull_size=HullSize.SMALL, game=mock_game)
    assert is_unit_in_nebula(unit, galaxy) is True

    # Move outside radius
    unit.position = Position(NEBULA_RADIUS + 500, 0)
    assert is_unit_in_nebula(unit, galaxy) is False

    # In hex without nebula
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    assert is_unit_in_nebula(unit, galaxy) is False
