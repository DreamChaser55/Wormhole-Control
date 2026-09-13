"""tests/test_system_context_menu.py

Tests for right-click context menu options in system view:
- Verifies placeholder options ('View Hex Details', 'Scan Hex Contents', 'View Planet', 'View Wormhole Info') are not present.
- Verifies empty hexes and hexes with celestial bodies without hyperdrive selection yield no options.
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


def test_system_context_menu_empty_hex_has_no_placeholder_options(system_setup):
    p1, galaxy, system, game = system_setup
    empty_hex = (1, 0)
    assert empty_hex in system.hexes

    options = build_system_context_menu_options(game, empty_hex)

    labels = [opt[0] for opt in options]
    action_ids = [opt[1] for opt in options]
    assert "View Hex Details" not in labels
    assert "view_hex" not in action_ids
    assert "Scan Hex Contents" not in labels
    assert "scan_hex" not in action_ids
    # An empty hex with nothing selected should yield an empty options list
    assert options == []


def test_system_context_menu_with_planet_has_no_placeholder_options(system_setup):
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
    assert "Scan Hex Contents" not in labels
    assert "scan_hex" not in action_ids
    assert "View Planet" not in labels
    assert "view_planet" not in action_ids
    # Celestial hex with nothing selected should yield an empty options list
    assert options == []


def test_system_context_menu_with_wormhole_has_no_placeholder_options(system_setup):
    p1, galaxy, system, game = system_setup
    hex_coord = (0, 1)
    wormhole = Wormhole(in_hex=hex_coord, in_system=system.name, exit_system_name="Alpha Centauri")
    system.hexes[hex_coord].add_celestial_body(wormhole)

    options = build_system_context_menu_options(game, hex_coord)
    labels = [opt[0] for opt in options]
    action_ids = [opt[1] for opt in options]

    assert "View Hex Details" not in labels
    assert "view_hex" not in action_ids
    assert "Scan Hex Contents" not in labels
    assert "scan_hex" not in action_ids
    assert "View Wormhole Info" not in labels
    assert "view_wormhole" not in action_ids
    # Celestial hex with nothing selected should yield an empty options list
    assert options == []


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
    assert options == [("Jump Into This Sector", "jump_interhex")]


def test_system_context_menu_celestial_hex_with_hyperdrive_unit_offers_only_jump(system_setup):
    p1, galaxy, system, game = system_setup
    origin_hex = (0, 0)
    target_hex = (1, 0)

    # Place a planet and a wormhole in the target hex
    planet = Planet(in_hex=target_hex, in_system=system.name)
    planet.name = "Earth"
    system.hexes[target_hex].add_celestial_body(planet)
    wormhole = Wormhole(in_hex=target_hex, in_system=system.name, exit_system_name="Alpha Centauri")
    system.hexes[target_hex].add_celestial_body(wormhole)

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
    assert "Scan Hex Contents" not in labels
    assert "scan_hex" not in action_ids
    assert "View Planet" not in labels
    assert "view_planet" not in action_ids
    assert "View Wormhole Info" not in labels
    assert "view_wormhole" not in action_ids
    assert options == [("Jump Into This Sector", "jump_interhex")]


def test_system_context_menu_unknown_system(system_setup):
    p1, galaxy, system, game = system_setup
    game.current_system_name = "NonExistentSystem"
    options = build_system_context_menu_options(game, (0, 0))
    assert options == []
