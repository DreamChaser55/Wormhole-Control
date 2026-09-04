import pytest
from unittest.mock import MagicMock, patch
import os
import pygame

os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()
pygame.font.init()

from entities import Player, Planet, StarType, PlanetType, HullSize, Position
from galaxy import StarSystem
from game_settings import GameSettings, PlayerConfig, SpawnProfile, PLAYER_COLOR_PALETTE
from player_controller import PlayerController
import game_setup
from galaxy_utils import get_home_systems_mapping
from rendering.galaxy_renderer import GalaxyViewRenderer
from save_manager import serialize_player, deserialize_player, deserialize_game_state
from constants import GRAY, HOVER_HIGHLIGHT_COLOR, SELECTION_HIGHLIGHT_COLOR


class MockGame:
    def __init__(self):
        self.gui = MagicMock()
        self.gui.galaxy_generation_rect = pygame.Rect(0, 0, 800, 600)
        self.galaxy = None
        self.players = []
        self.current_player_index = 0
        self.turn_number = 1
        self.campaign_id = "test_camp"
        self.view_mode = "galaxy"
        self.game_started = False
        self.visibility = None
        self.visibility_dirty = False
        self.selected_objects = []
        self.galaxy_view_mouse_hover_system_name = None
        self.screen = MagicMock()
        self.overlay_surface = MagicMock()

    def recompute_visibility(self):
        pass

    def update_side_bar_content(self):
        pass

    def update_player_turn_display(self):
        pass


def test_home_systems_mapping_normal_profile():
    """In Normal spawn profile, each player has a distinct home system."""
    game = MockGame()
    settings = GameSettings(
        num_systems=5,
        spawn_profile=SpawnProfile.NORMAL,
        player_configs=[
            PlayerConfig("Alice", (30, 120, 255), controller=PlayerController.HUMAN, team_id=1),
            PlayerConfig("Bob", (220, 40, 40), controller=PlayerController.HUMAN, team_id=2),
        ],
    )

    success = game_setup.start_new_game(game, settings=settings)
    assert success is True
    assert len(game.players) == 2

    # Check that homeworld_id is assigned on players
    for player in game.players:
        assert player.homeworld_id is not None
        body = game.galaxy.get_celestial_body_by_id(player.homeworld_id)
        assert body is not None
        assert isinstance(body, Planet)
        assert body.owner == player

    # Check mapping
    mapping = get_home_systems_mapping(game)
    assert len(mapping) == 2
    for player in game.players:
        body = game.galaxy.get_celestial_body_by_id(player.homeworld_id)
        assert player in mapping[body.in_system]
        assert len(mapping[body.in_system]) == 1


def test_home_systems_mapping_testing_profile():
    """In Testing spawn profile, all players share the starting system (Sol)."""
    game = MockGame()
    settings = GameSettings(
        num_systems=4,
        spawn_profile=SpawnProfile.TESTING,
        player_configs=[
            PlayerConfig("Alice", (30, 120, 255), controller=PlayerController.HUMAN, team_id=1),
            PlayerConfig("Bob", (220, 40, 40), controller=PlayerController.HUMAN, team_id=2),
            PlayerConfig("Charlie", (40, 200, 80), controller=PlayerController.HUMAN, team_id=3),
        ],
    )

    success = game_setup.start_new_game(game, settings=settings)
    assert success is True
    assert len(game.players) == 3

    # All players should have homeworld_id in Sol (or first available system)
    sol_name = game.players[0].homeworld_id
    first_body = game.galaxy.get_celestial_body_by_id(sol_name)
    shared_system_name = first_body.in_system

    for player in game.players:
        body = game.galaxy.get_celestial_body_by_id(player.homeworld_id)
        assert body.in_system == shared_system_name

    mapping = get_home_systems_mapping(game)
    assert shared_system_name in mapping
    assert len(mapping[shared_system_name]) == 3
    assert set(mapping[shared_system_name]) == set(game.players)


def test_home_systems_mapping_fallback_resolution():
    """If player.homeworld_id is None, mapping resolves via owned planets in the galaxy."""
    player1 = Player("P1", (30, 120, 255))
    player2 = Player("P2", (220, 40, 40))
    player1.homeworld_id = None
    player2.homeworld_id = None

    planet1 = Planet(in_hex=(0, 0), in_system="Sirius")
    planet1.id = 101
    planet1.owner = player1

    planet2 = Planet(in_hex=(0, 0), in_system="Vega")
    planet2.id = 102
    planet2.owner = player2

    sys1 = MagicMock()
    hex1 = MagicMock()
    hex1.celestial_bodies = [planet1]
    sys1.hexes = {(0, 0): hex1}

    sys2 = MagicMock()
    hex2 = MagicMock()
    hex2.celestial_bodies = [planet2]
    sys2.hexes = {(0, 0): hex2}

    galaxy = MagicMock()
    galaxy.systems = {"Sirius": sys1, "Vega": sys2}
    galaxy.get_celestial_body_by_id.side_effect = lambda bid: (
        planet1 if bid == 101 else (planet2 if bid == 102 else None)
    )

    game = MockGame()
    game.players = [player1, player2]
    game.galaxy = galaxy

    mapping = get_home_systems_mapping(game)
    assert "Sirius" in mapping
    assert mapping["Sirius"] == [player1]
    assert player1.homeworld_id == 101

    assert "Vega" in mapping
    assert mapping["Vega"] == [player2]
    assert player2.homeworld_id == 102


def test_galaxy_renderer_draws_single_player_home_mark():
    """Single-player home system is drawn with player color and radius 7."""
    player = Player("Alice", (30, 120, 255))
    player.homeworld_id = 10

    system = MagicMock()
    system.name = "Vega"
    system.position = Position(100, 100)

    galaxy = MagicMock()
    galaxy.wormholes = {}
    galaxy.systems = {"Vega": system}
    planet = Planet(in_hex=(0, 0), in_system="Vega")
    planet.id = 10
    planet.owner = player
    galaxy.get_celestial_body_by_id.side_effect = lambda bid: planet if bid == 10 else None

    game = MockGame()
    game.players = [player]
    game.galaxy = galaxy

    renderer = GalaxyViewRenderer(game)
    renderer.screen = MagicMock()
    renderer.overlay_surface = MagicMock()

    with patch("rendering.galaxy_renderer.pygame.draw.circle") as mock_draw_circle:
        renderer.draw_galaxy_view()

        # Check that pygame.draw.circle was called with player.color and radius 7
        called_with_player_color = False
        for call in mock_draw_circle.call_args_list:
            args, kwargs = call
            # args: (surface, color, center, radius, [width])
            if len(args) >= 4 and args[1] == (30, 120, 255) and args[3] == 7:
                called_with_player_color = True
                break
        assert called_with_player_color, "Expected single player home system drawn with player.color and radius 7"


def test_galaxy_renderer_draws_concentric_circles_for_multiple_players():
    """Shared home system is drawn with concentric circles for all sharing players."""
    p1 = Player("P1", (30, 120, 255))
    p2 = Player("P2", (220, 40, 40))
    p3 = Player("P3", (40, 200, 80))
    p1.homeworld_id = 1
    p2.homeworld_id = 2
    p3.homeworld_id = 3

    system = MagicMock()
    system.name = "Sol"
    system.position = Position(0, 0)

    b1 = Planet(in_hex=(0, 0), in_system="Sol")
    b1.id = 1
    b2 = Planet(in_hex=(1, 0), in_system="Sol")
    b2.id = 2
    b3 = Planet(in_hex=(2, 0), in_system="Sol")
    b3.id = 3

    galaxy = MagicMock()
    galaxy.wormholes = {}
    galaxy.systems = {"Sol": system}
    galaxy.get_celestial_body_by_id.side_effect = lambda bid: {1: b1, 2: b2, 3: b3}.get(bid)

    game = MockGame()
    game.players = [p1, p2, p3]
    game.galaxy = galaxy

    renderer = GalaxyViewRenderer(game)
    renderer.screen = MagicMock()
    renderer.overlay_surface = MagicMock()

    with patch("rendering.galaxy_renderer.pygame.draw.circle") as mock_draw_circle:
        renderer.draw_galaxy_view()

        # For 3 players:
        # inner_radius = 5, ring_thickness = 3
        # i=2 (p3): radius 11
        # i=1 (p2): radius 8
        # i=0 (p1): radius 5
        radii_by_color = {}
        for call in mock_draw_circle.call_args_list:
            args, kwargs = call
            if len(args) >= 4 and args[0] == renderer.screen:
                radii_by_color[args[1]] = args[3]

        assert (40, 200, 80) in radii_by_color
        assert radii_by_color[(40, 200, 80)] == 11
        assert (220, 40, 40) in radii_by_color
        assert radii_by_color[(220, 40, 40)] == 8
        assert (30, 120, 255) in radii_by_color
        assert radii_by_color[(30, 120, 255)] == 5


def test_galaxy_renderer_unowned_system():
    """Unowned systems are drawn with GRAY and radius 5."""
    system = MagicMock()
    system.name = "Centauri"
    system.position = Position(50, 50)

    galaxy = MagicMock()
    galaxy.wormholes = {}
    galaxy.systems = {"Centauri": system}
    galaxy.get_celestial_body_by_id.return_value = None

    game = MockGame()
    game.galaxy = galaxy

    renderer = GalaxyViewRenderer(game)
    renderer.screen = MagicMock()
    renderer.overlay_surface = MagicMock()

    with patch("rendering.galaxy_renderer.pygame.draw.circle") as mock_draw_circle:
        renderer.draw_galaxy_view()

        unowned_drawn = False
        for call in mock_draw_circle.call_args_list:
            args, kwargs = call
            if len(args) >= 4 and args[1] == GRAY and args[3] == 5:
                unowned_drawn = True
                break
        assert unowned_drawn, "Expected unowned system drawn in GRAY with radius 5"


def test_galaxy_renderer_hover_and_selection_scaling():
    """Hover ring and selection ring are drawn on overlay_surface and scale with max_radius."""
    p1 = Player("P1", (30, 120, 255))
    p2 = Player("P2", (220, 40, 40))
    p1.homeworld_id = 1
    p2.homeworld_id = 2

    system = MagicMock(spec=StarSystem)
    system.name = "Sol"
    system.position = Position(0, 0)

    b1 = Planet(in_hex=(0, 0), in_system="Sol")
    b1.id = 1
    b2 = Planet(in_hex=(1, 0), in_system="Sol")
    b2.id = 2

    galaxy = MagicMock()
    galaxy.wormholes = {}
    galaxy.systems = {"Sol": system}
    galaxy.get_celestial_body_by_id.side_effect = lambda bid: {1: b1, 2: b2}.get(bid)

    game = MockGame()
    game.players = [p1, p2]
    game.galaxy = galaxy
    game.selected_objects = [system]
    game.galaxy_view_mouse_hover_system_name = "Sol"

    renderer = GalaxyViewRenderer(game)
    renderer.screen = MagicMock()
    renderer.overlay_surface = MagicMock()

    with patch("rendering.galaxy_renderer.pygame.draw.circle") as mock_draw_circle:
        renderer.draw_galaxy_view()

        # For 2 players, max_radius = 5 + (2-1)*3 = 8
        # Hover ring: radius max_radius + 2 = 10, on overlay_surface
        # Selection ring: radius max_radius + 4 = 12, on overlay_surface
        hover_ring_drawn = False
        selection_ring_drawn = False

        for call in mock_draw_circle.call_args_list:
            args, kwargs = call
            if len(args) >= 4 and args[0] == renderer.overlay_surface:
                if args[1] == HOVER_HIGHLIGHT_COLOR and args[3] == 10:
                    hover_ring_drawn = True
                elif args[1] == SELECTION_HIGHLIGHT_COLOR and args[3] == 12:
                    selection_ring_drawn = True

        assert hover_ring_drawn, "Expected hover ring with radius 10 on overlay_surface"
        assert selection_ring_drawn, "Expected selection ring with radius 12 on overlay_surface"


def test_save_load_preserves_homeworld_id():
    """Saving and loading preserves player.homeworld_id."""
    player = Player("Alice", (30, 120, 255))
    player.homeworld_id = 42

    serialized = serialize_player(player)
    assert "homeworld_id" in serialized
    assert serialized["homeworld_id"] == 42

    restored = deserialize_player(serialized)
    assert restored.homeworld_id == 42


def test_deserialize_game_state_legacy_fallback():
    """Legacy saves lacking homeworld_id recover it from owned planets."""
    legacy_save_data = {
        "game_state": {
            "turn_number": 3,
            "current_player_index": 0,
            "view_mode": "galaxy",
            "current_system_name": "Sol",
        },
        "players": [
            {
                "id": 1,
                "name": "LegacyPlayer",
                "color": [30, 120, 255],
                "controller": "human",
                # Note: homeworld_id is omitted (simulating legacy save)
            }
        ],
        "galaxy": {
            "systems": [
                {
                    "name": "Sol",
                    "position": [0, 0],
                    "radius": 5,
                    "hexes": [
                        {
                            "q": 0,
                            "r": 0,
                            "in_system": "Sol",
                            "celestial_bodies": [
                                {
                                    "class_name": "Planet",
                                    "id": 99,
                                    "name": "Earth",
                                    "position": [0, 0],
                                    "in_hex": [0, 0],
                                    "in_system": "Sol",
                                    "planet_type": "TERRAN",
                                    "owner_id": 1,
                                    "population": 50.0,
                                    "max_population": 100.0,
                                    "population_growth_rate": 0.02,
                                }
                            ],
                            "units": [],
                        }
                    ],
                }
            ],
            "wormholes": [],
        },
    }

    game = MockGame()
    success = deserialize_game_state(game, legacy_save_data)
    assert success is True
    assert len(game.players) == 1
    assert game.players[0].homeworld_id == 99

    # And verify get_home_systems_mapping correctly resolves it
    mapping = get_home_systems_mapping(game)
    assert "Sol" in mapping
    assert mapping["Sol"] == [game.players[0]]

