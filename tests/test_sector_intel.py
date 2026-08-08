import pytest
from unittest.mock import MagicMock
from entities import Player, Unit, Position
from constants import HullSize
from galaxy import StarSystem, Galaxy
from unit_components import Sensors
from visibility import VisibilityService
from gui.sidebar.panels_world import build_hex_panel
from save_manager import serialize_player, deserialize_player


class MockGame:
    def __init__(self, galaxy, players):
        self.galaxy = galaxy
        self.players = players
        self.current_player_index = 0
        self.turn_number = 1
        self.visibility = None
        self.visibility_dirty = False

    def is_unit_visible(self, unit):
        return True

    def hex_has_presence(self, system_name, hex_coord):
        return False


def test_player_sector_intel_initial_state():
    p1 = Player(name="Player 1", color=(255, 0, 0))
    assert p1.get_sector_last_intel_turn("Sol", (0, 0)) is None


def test_long_range_sensor_updates_sector_intel():
    p1 = Player(name="Player 1", color=(255, 0, 0))
    p2 = Player(name="Player 2", color=(0, 255, 0))

    galaxy = Galaxy()
    sys = StarSystem(name="Sol", position=Position(0, 0))
    galaxy.systems[sys.name] = sys

    h00 = sys.hexes[(0, 0)]
    h10 = sys.hexes[(1, 0)]

    mock_game = MagicMock()
    mock_game.galaxy = galaxy

    # Unit with long-range sensors (range = 2)
    u_scout = Unit(
        owner=p1, position=Position(0, 0), in_hex=(0, 0), in_system="Sol",
        name="Scout", hull_size=HullSize.SMALL, game=mock_game
    )
    u_scout.remove_component(Sensors)
    u_scout.add_component(Sensors(unit=u_scout, short_range_radius=0, long_range_hexes=2))
    h00.add_unit(u_scout)

    # Compute visibility for P1 on turn 1
    VisibilityService.compute(galaxy, p1, turn_number=1)

    assert p1.get_sector_last_intel_turn("Sol", (0, 0)) == 1
    assert p1.get_sector_last_intel_turn("Sol", (1, 0)) == 1

    # P2 should have no intel
    assert p2.get_sector_last_intel_turn("Sol", (0, 0)) is None
    assert p2.get_sector_last_intel_turn("Sol", (1, 0)) is None


def test_short_range_only_sensor_does_not_update_intel():
    p1 = Player(name="Player 1", color=(255, 0, 0))
    galaxy = Galaxy()
    sys = StarSystem(name="Sol", position=Position(0, 0))
    galaxy.systems[sys.name] = sys
    h00 = sys.hexes[(0, 0)]

    mock_game = MagicMock()
    mock_game.galaxy = galaxy

    # Unit with ONLY short-range sensors
    u_short = Unit(
        owner=p1, position=Position(0, 0), in_hex=(0, 0), in_system="Sol",
        name="ShortScout", hull_size=HullSize.SMALL, game=mock_game
    )
    u_short.remove_component(Sensors)
    u_short.add_component(Sensors(unit=u_short, short_range_radius=500, long_range_hexes=0))
    h00.add_unit(u_short)

    VisibilityService.compute(galaxy, p1, turn_number=1)

    assert p1.get_sector_last_intel_turn("Sol", (0, 0)) is None


def test_sector_intel_sidebar_panel_display():
    p1 = Player(name="Player 1", color=(255, 0, 0))
    p2 = Player(name="Player 2", color=(0, 255, 0))
    galaxy = Galaxy()
    sys = StarSystem(name="Sol", position=Position(0, 0))
    galaxy.systems[sys.name] = sys
    h00 = sys.hexes[(0, 0)]

    game = MockGame(galaxy, [p1, p2])

    # Case 1: Never seen
    panel = build_hex_panel(game, h00)
    intel_labels = [item for item in panel if item.get('text', '').startswith("Last Intel:")]
    assert len(intel_labels) == 1
    assert intel_labels[0]['text'] == "Last Intel: Never"

    # Case 2: Current turn
    p1.record_sector_intel("Sol", (0, 0), turn=1)
    panel = build_hex_panel(game, h00)
    intel_labels = [item for item in panel if item.get('text', '').startswith("Last Intel:")]
    assert intel_labels[0]['text'] == "Last Intel: Current turn"

    # Case 3: 1 turn ago
    game.turn_number = 2
    panel = build_hex_panel(game, h00)
    intel_labels = [item for item in panel if item.get('text', '').startswith("Last Intel:")]
    assert intel_labels[0]['text'] == "Last Intel: 1 turn ago"

    # Case 4: 5 turns ago
    game.turn_number = 6
    panel = build_hex_panel(game, h00)
    intel_labels = [item for item in panel if item.get('text', '').startswith("Last Intel:")]
    assert intel_labels[0]['text'] == "Last Intel: 5 turns ago"


def test_sector_intel_save_load_serialization():
    p1 = Player(name="Player 1", color=(255, 0, 0))
    p1.record_sector_intel("Sol", (0, 0), turn=3)
    p1.record_sector_intel("Alpha Centauri", (2, -1), turn=7)

    serialized = serialize_player(p1)
    assert "sector_intel" in serialized
    assert serialized["sector_intel"]["Sol:0:0"] == 3
    assert serialized["sector_intel"]["Alpha Centauri:2:-1"] == 7

    p1_loaded = deserialize_player(serialized)
    assert p1_loaded.get_sector_last_intel_turn("Sol", (0, 0)) == 3
    assert p1_loaded.get_sector_last_intel_turn("Alpha Centauri", (2, -1)) == 7
    assert p1_loaded.get_sector_last_intel_turn("Sol", (1, 1)) is None
