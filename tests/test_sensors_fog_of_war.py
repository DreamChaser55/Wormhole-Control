import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import DEFAULT_SENSOR_SHORT_RANGE, HullSize
from entities import Player, Unit, Planet, Star, PlanetType, StarType
from unit_components import Sensors
from visibility import VisibilityService, is_unit_visible, hex_has_presence
from galaxy import Galaxy, StarSystem, Hex


@pytest.fixture
def test_setup():
    p1 = Player("Player 1", (0, 0, 255))
    p2 = Player("Player 2", (255, 0, 0))

    galaxy = Galaxy()
    system = StarSystem(name="Alpha", position=Position(0, 0), radius=3)
    galaxy.systems = {"Alpha": system}

    return p1, p2, galaxy, system


def test_baseline_sensors_on_unit_creation(test_setup):
    p1, p2, galaxy, system = test_setup
    mock_game = MagicMock()
    mock_game.galaxy = galaxy

    unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Alpha",
        name="Scout",
        hull_size=HullSize.SMALL,
        game=mock_game
    )

    sensors = unit.sensors_component
    assert sensors is not None
    assert isinstance(sensors, Sensors)
    assert sensors.short_range_radius == DEFAULT_SENSOR_SHORT_RANGE
    assert sensors.long_range_hexes == 0
    assert sensors.hull_cost == 0


def test_short_range_detailed_visibility(test_setup):
    p1, p2, galaxy, system = test_setup
    mock_game = MagicMock()
    mock_game.galaxy = galaxy

    friendly_unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Alpha",
        name="Friendly Fighter",
        hull_size=HullSize.SMALL,
        game=mock_game
    )

    enemy_in_range = Unit(
        owner=p2,
        position=Position(1000, 0),
        in_hex=(0, 0),
        in_system="Alpha",
        name="Enemy Scout",
        hull_size=HullSize.SMALL,
        game=mock_game
    )

    system.hexes[(0, 0)].units.extend([friendly_unit, enemy_in_range])

    snapshot = VisibilityService.compute(galaxy, p1)

    assert is_unit_visible(snapshot, friendly_unit) is True
    assert is_unit_visible(snapshot, enemy_in_range) is True
    assert enemy_in_range.id in snapshot.visible_enemy_unit_ids
    assert not hex_has_presence(snapshot, "Alpha", (0, 0))


def test_short_range_miss_hidden(test_setup):
    p1, p2, galaxy, system = test_setup
    mock_game = MagicMock()
    mock_game.galaxy = galaxy

    friendly_unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Alpha",
        name="Friendly Ship",
        hull_size=HullSize.SMALL,
        game=mock_game
    )

    enemy_out_of_range = Unit(
        owner=p2,
        position=Position(3500, 0),  # > 2000.0 default short range
        in_hex=(0, 0),
        in_system="Alpha",
        name="Enemy Raider",
        hull_size=HullSize.SMALL,
        game=mock_game
    )

    system.hexes[(0, 0)].units.extend([friendly_unit, enemy_out_of_range])

    snapshot = VisibilityService.compute(galaxy, p1)

    assert is_unit_visible(snapshot, friendly_unit) is True
    assert is_unit_visible(snapshot, enemy_out_of_range) is False
    assert enemy_out_of_range.id not in snapshot.visible_enemy_unit_ids
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is False


def test_long_range_same_hex_presence(test_setup):
    p1, p2, galaxy, system = test_setup
    mock_game = MagicMock()
    mock_game.galaxy = galaxy

    friendly_unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Alpha",
        name="Friendly Sensor Cruiser",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    # Upgrade sensors to long-range hexes = 1
    friendly_unit.remove_component(Sensors)
    friendly_unit.add_component(Sensors(friendly_unit, short_range_radius=2000.0, long_range_hexes=1, hull_cost=5))

    enemy_same_hex_far = Unit(
        owner=p2,
        position=Position(3500, 0),
        in_hex=(0, 0),
        in_system="Alpha",
        name="Enemy Stealth Cruiser",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )

    system.hexes[(0, 0)].units.extend([friendly_unit, enemy_same_hex_far])

    snapshot = VisibilityService.compute(galaxy, p1)

    assert is_unit_visible(snapshot, enemy_same_hex_far) is False
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is True


def test_long_range_neighbor_hex_presence(test_setup):
    p1, p2, galaxy, system = test_setup
    mock_game = MagicMock()
    mock_game.galaxy = galaxy

    friendly_unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Alpha",
        name="Picket Ship",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    friendly_unit.remove_component(Sensors)
    friendly_unit.add_component(Sensors(friendly_unit, short_range_radius=2000.0, long_range_hexes=1, hull_cost=5))

    enemy_neighbor_hex = Unit(
        owner=p2,
        position=Position(0, 0),
        in_hex=(1, 0),
        in_system="Alpha",
        name="Enemy Patrol",
        hull_size=HullSize.SMALL,
        game=mock_game
    )

    system.hexes[(0, 0)].units.append(friendly_unit)
    system.hexes[(1, 0)].units.append(enemy_neighbor_hex)

    snapshot = VisibilityService.compute(galaxy, p1)

    assert is_unit_visible(snapshot, enemy_neighbor_hex) is False
    assert hex_has_presence(snapshot, "Alpha", (1, 0)) is True
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is False


def test_detailed_overrides_presence(test_setup):
    p1, p2, galaxy, system = test_setup
    mock_game = MagicMock()
    mock_game.galaxy = galaxy

    friendly_unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Alpha",
        name="Sensor Station",
        hull_size=HullSize.LARGE,
        game=mock_game
    )
    friendly_unit.remove_component(Sensors)
    friendly_unit.add_component(Sensors(friendly_unit, short_range_radius=2000.0, long_range_hexes=1, hull_cost=5))

    enemy_close = Unit(
        owner=p2,
        position=Position(500, 0),  # inside short range
        in_hex=(0, 0),
        in_system="Alpha",
        name="Enemy Interceptor",
        hull_size=HullSize.SMALL,
        game=mock_game
    )

    system.hexes[(0, 0)].units.extend([friendly_unit, enemy_close])

    snapshot = VisibilityService.compute(galaxy, p1)

    assert is_unit_visible(snapshot, enemy_close) is True
    # Since enemy_close is DETAILED and there are no undetailed enemies in (0, 0), presence_hexes should not list (0, 0)
    assert hex_has_presence(snapshot, "Alpha", (0, 0)) is False


def test_template_sensor_wiring(test_setup):
    p1, p2, galaxy, system = test_setup
    from unit_components import Constructor

    constructor_unit = Unit(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Alpha",
        name="Builder",
        hull_size=HullSize.MEDIUM,
        game=MagicMock()
    )
    constructor_comp = Constructor(constructor_unit)

    # Use template with customized sensors
    template_dict = {
        "name": "Custom Picket",
        "hull_size": "MEDIUM",
        "has_sensors": True,
        "sensor_short_range": 4500.0,
        "sensor_long_range_hexes": 2,
        "sensors_hull_cost": 15
    }

    with pytest.MonkeyPatch.context() as m:
        from unit_templates import UNIT_TEMPLATES
        m.setitem(UNIT_TEMPLATES, "CUSTOM_PICKET", template_dict)

        constructor_comp.create_unit_from_template(
            galaxy=galaxy,
            template_name="CUSTOM_PICKET",
            owner=p1,
            system_name="Alpha",
            hex_coord=(0, 0),
            position=Position(100, 100)
        )

    spawned = [u for u in system.hexes[(0, 0)].units if u.name == "Custom Picket"][0]
    sensors = spawned.sensors_component
    assert sensors is not None
    assert sensors.short_range_radius == 4500.0
    assert sensors.long_range_hexes == 2
    assert sensors.hull_cost == 15
