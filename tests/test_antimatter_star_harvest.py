from player_controller import PlayerController
import pytest
from entities import Star, StarType, Unit, Player
from geometry import Position
from constants import (
    StarType, STAR_HARVEST_MULTIPLIERS, DEFAULT_ANTIMATTER_HARVEST_RATE
)
from unit_components import AntimatterStorage, AntimatterHarvester


class MockPlayer:
    _counter = 1
    def __init__(self, name="TestPlayer", player_id=None, team_id=None):
        if player_id is not None:
            self.id = player_id
        else:
            self.id = MockPlayer._counter
            MockPlayer._counter += 1
        self.name = name
        self.controller = PlayerController.HUMAN
        self.team_id = team_id if team_id is not None else self.id


class FakeHex:
    def __init__(self, celestial_bodies=None):
        self.celestial_bodies = celestial_bodies or []


class FakeSystem:
    def __init__(self, hexes=None):
        self.hexes = hexes or {}


class FakeGalaxy:
    def __init__(self, systems=None):
        self.systems = systems or {}


class FakeGame:
    def __init__(self, galaxy=None):
        self.galaxy = galaxy


from unittest.mock import MagicMock
from constants import HullSize

def make_unit_with_harvester(player, harvest_rate=DEFAULT_ANTIMATTER_HARVEST_RATE, initial_am=0.0, max_am=100.0):
    game = MagicMock()
    unit = Unit(
        name="Harvester Unit",
        hull_size=HullSize.MEDIUM,
        game=game,
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol"
    )
    am_storage = AntimatterStorage(unit, max_capacity=max_am)
    am_storage.current_amount = initial_am
    unit.add_component(am_storage)
    harvester = AntimatterHarvester(unit, harvest_rate=harvest_rate)
    unit.add_component(harvester)
    return unit, harvester, am_storage


def test_star_harvest_multipliers_constants():
    """Verify that all 11 star types have defined harvest multipliers in constants."""
    for star_type in StarType:
        assert star_type in STAR_HARVEST_MULTIPLIERS
        assert STAR_HARVEST_MULTIPLIERS[star_type] > 0.0

    assert STAR_HARVEST_MULTIPLIERS[StarType.PULSAR] == 2.5
    assert STAR_HARVEST_MULTIPLIERS[StarType.BLUE_GIANT] == 2.0
    assert STAR_HARVEST_MULTIPLIERS[StarType.G_TYPE] == 1.0
    assert STAR_HARVEST_MULTIPLIERS[StarType.RED_DWARF] == 0.5
    assert STAR_HARVEST_MULTIPLIERS[StarType.BROWN_DWARF] == 0.3
    assert STAR_HARVEST_MULTIPLIERS[StarType.BLACK_HOLE] == 0.1


def test_star_entity_harvest_multiplier_property():
    """Verify Star entity returns the correct harvest multiplier property."""
    blue_giant = Star(in_system="Sol", star_type=StarType.BLUE_GIANT)
    assert blue_giant.harvest_multiplier == 2.0

    g_star = Star(in_system="Sol", star_type=StarType.G_TYPE)
    assert g_star.harvest_multiplier == 1.0

    black_hole = Star(in_system="Sol", star_type=StarType.BLACK_HOLE)
    assert black_hole.harvest_multiplier == 0.1


@pytest.mark.parametrize("star_type,expected_multiplier", [
    (StarType.PULSAR, 2.5),
    (StarType.BLUE_GIANT, 2.0),
    (StarType.G_TYPE, 1.0),
    (StarType.RED_DWARF, 0.5),
    (StarType.BLACK_HOLE, 0.1),
])
def test_harvester_updates_based_on_star_type(star_type, expected_multiplier):
    """Verify that harvester generates antimatter scaled by the nearby star's multiplier."""
    player = MockPlayer()
    unit, harvester, am_storage = make_unit_with_harvester(player, harvest_rate=10.0, initial_am=0.0)

    star = Star(in_system="Sol", star_type=star_type)
    star.position = Position(0, 0)

    hex_obj = FakeHex(celestial_bodies=[star])
    system = FakeSystem(hexes={(0, 0): hex_obj})
    galaxy = FakeGalaxy(systems={"Sol": system})

    harvester.update(galaxy)

    assert harvester.is_harvesting is True
    expected_gained = 10.0 * expected_multiplier
    assert am_storage.current_amount == pytest.approx(expected_gained)


def test_harvester_sidebar_data_displays_base_and_effective_rates():
    """Verify harvester sidebar data includes both base rate and effective star rate when harvesting."""
    player = MockPlayer()
    unit, harvester, am_storage = make_unit_with_harvester(player, harvest_rate=10.0, initial_am=0.0)

    star = Star(in_system="Sol", star_type=StarType.BLUE_GIANT)
    star.position = Position(0, 0)
    star.name = "Sol Star"

    hex_obj = FakeHex(celestial_bodies=[star])
    system = FakeSystem(hexes={(0, 0): hex_obj})
    galaxy = FakeGalaxy(systems={"Sol": system})
    game = FakeGame(galaxy=galaxy)

    # First update to set is_harvesting = True
    harvester.update(galaxy)

    sidebar_data = harvester.get_sidebar_data(game)
    labels = [item['text'] for item in sidebar_data if item.get('type') == 'label']

    assert any("Base Harvest Rate: 10.0/turn" in label for label in labels)
    assert any("Effective Rate: 20.0/turn (2.0x star mult)" in label for label in labels)
    assert any("Harvesting (near Sol Star)" in label for label in labels)

    basic_sidebar_data = harvester.get_basic_sidebar_data(game)
    basic_labels = [item['text'] for item in basic_sidebar_data if item.get('type') == 'label']
    assert any("20.0/t eff. [10.0 base]" in label for label in basic_labels)
