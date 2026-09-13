"""tests/test_system_context_menu.py

Tests for right-click context menu options in system view:
- Verifies 'View Hex Details' is not present in options.
- Verifies empty hexes without hyperdrive selection yield no options.
- Verifies celestial bodies and units populate relevant options ('Scan Hex Contents', 'View Planet', 'View Wormhole Info').
- Verifies selected hyperdrive units can receive 'Jump Into This Sector'.
"""
import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import HullSize
from domain.players import Player
from domain.units import Unit
from domain.celestials import Planet, Wormhole
from galaxy import Galaxy, StarSystem
from unit_components.movement import Hyperdrive
from unit_components.commander import Commander
from input_processor.context_menu_builder import build_system_context_menu_options
from input_processor.context_actions import handle_context_menu_action


@pytest.fixture
def system_setup():
    p1 = Player("Player 1", (0, 0, 255))
    galaxy = Galaxy()
    system = StarSystem(name="Sol", position=Position(0, 0), radius=3)
    galaxy.systems = {"Sol": system}

    game = MagicMock()
    game.galaxy = galaxy
    game.players = [p1]
    game.current_player_index = 0
    game.current_system_name = "Sol"
    game.selected_objects = []
    game.event_bus = MagicMock()
    return p1, galaxy, system, game


def test_system_context_menu_empty_hex_has_no_view_hex_details(system_setup):
    p1, galaxy, system, game = system_setup
    empty_hex = (1, 0)
    assert empty_hex in system.hexes

    options = build_system_context_menu_options(game, empty_hex)

    labels = [opt[0] for opt in options]
    action_ids = [opt[1] for opt in options]
    assert "View Hex Details" not in labels
    assert "view_hex" not in action_ids
    # An empty hex with nothing selected should yield an empty options list
    assert options == []


def test_system_context_menu_with_planet(system_setup):
    p1, galaxy, system, game = system_setup
    hex_coord = (1, 0)
    planet = Planet(in_hex=hex_coord, in_system=system.name)
    planet.name = "Earth"
    system.hexes[hex_coord].add_celestial_body(planet)

    options = build_system_context_menu_options(game, hex_coord)
    labels = [opt[0] for opt in options]
    action_ids = [opt[1] for opt in options]

    assert "View Hex Details" not in labels
    assert "view_hex" not in action_ids
    assert ("Scan Hex Contents", "scan_hex") in options
    assert ("View Planet", "view_planet") in options


def test_system_context_menu_with_wormhole(system_setup):
    p1, galaxy, system, game = system_setup
    hex_coord = (0, 1)
    wormhole = Wormhole(in_hex=hex_coord, in_system=system.name, exit_system_name="Alpha Centauri")
    system.hexes[hex_coord].add_celestial_body(wormhole)

    options = build_system_context_menu_options(game, hex_coord)
    labels = [opt[0] for opt in options]
    action_ids = [opt[1] for opt in options]

    assert "View Hex Details" not in labels
    assert "view_hex" not in action_ids
    assert ("Scan Hex Contents", "scan_hex") in options
    assert ("View Wormhole Info", "view_wormhole") in options


def test_system_context_menu_with_unit_and_jump_option(system_setup):
    p1, galaxy, system, game = system_setup
    origin_hex = (0, 0)
    target_hex = (2, -1)

    unit = Unit(p1, Position(0, 0), origin_hex, "Sol", "Scout", HullSize.SMALL, game)
    unit.add_component(Commander(unit))
    unit.add_component(Hyperdrive(unit))
    system.hexes[origin_hex].add_unit(unit)

    game.selected_objects = [unit]

    options = build_system_context_menu_options(game, target_hex)
    labels = [opt[0] for opt in options]
    action_ids = [opt[1] for opt in options]

    assert "View Hex Details" not in labels
    assert "view_hex" not in action_ids
    assert ("Jump Into This Sector", "jump_interhex") in options


def test_system_context_menu_unknown_system(system_setup):
    p1, galaxy, system, game = system_setup
    game.current_system_name = "NonExistentSystem"
    options = build_system_context_menu_options(game, (0, 0))
    assert options == []


def test_context_action_view_planet_logs_without_error(system_setup):
    p1, galaxy, system, game = system_setup
    planet = Planet(in_hex=(1, 1), in_system="Sol")
    planet.name = "Mars"
    # Test that action dispatching works smoothly without raising an exception
    handle_context_menu_action(game, "view_planet", target=planet)
