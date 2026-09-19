"""Tests for the faint tactical grid in Galaxy View."""
from unittest.mock import MagicMock, patch
import pytest
import pygame

from constants import (
    GALAXY_GRID_COLOR,
    GALAXY_BORDER_COLOR,
    GALAXY_GRID_SPACING,
    LOGICAL_GALAXY_SIZE,
    WORMHOLE_LINE_COLOR,
)
from display_config import DisplayConfig
from geometry import Position
from galaxy_utils import logical_to_screen_galaxy
from rendering.galaxy_renderer import GalaxyViewRenderer, draw_galaxy_preview, draw_galaxy_tactical_grid


def make_mock_game(zoom=1.0, pan=Position(0, 0), viewport_rect=pygame.Rect(40, 30, 800, 500)):
    game = MagicMock()
    game.display_config = DisplayConfig()
    game.screen = pygame.Surface((1000, 600))
    game.overlay_surface = pygame.Surface((1000, 600), pygame.SRCALPHA)
    game.gui.galaxy_generation_rect = viewport_rect
    game.galaxy_zoom = zoom
    game.galaxy_pan_offset = pan
    game.galaxy = MagicMock()
    game.galaxy.systems = {}
    game.galaxy.wormholes = {}
    game.players = []
    game.current_player_index = 0
    game.selected_objects = []
    game.galaxy_view_mouse_hover_system_name = None
    return game


def test_tactical_grid_draws_lines_in_galaxy_view():
    game = make_mock_game()
    renderer = GalaxyViewRenderer(game)

    with patch("pygame.draw.line") as mock_draw_line:
        renderer.draw_galaxy_view()

        # Collect grid and border lines
        grid_calls = [
            call for call in mock_draw_line.call_args_list
            if len(call.args) >= 2 and call.args[1] in (GALAXY_GRID_COLOR, GALAXY_BORDER_COLOR)
        ]

        # 2560 / 160 = 16 steps -> 17 vertical lines
        # 1440 / 160 = 9 steps -> 10 horizontal lines
        # Total = 27 lines
        assert len(grid_calls) == 27

        # Width should always be 1 px
        for call in grid_calls:
            assert call.args[-1] == 1

        border_calls = [c for c in grid_calls if c.args[1] == GALAXY_BORDER_COLOR]
        interior_calls = [c for c in grid_calls if c.args[1] == GALAXY_GRID_COLOR]

        # 4 outer boundary edges (x=0, x=2560, y=0, y=1440)
        assert len(border_calls) == 4
        # 23 interior grid lines
        assert len(interior_calls) == 23


@pytest.mark.parametrize("zoom", [0.8, 1.0, 2.5])
@pytest.mark.parametrize("pan", [Position(0, 0), Position(120, -75)])
def test_tactical_grid_coordinates_with_zoom_and_pan(zoom, pan):
    viewport = pygame.Rect(50, 40, 900, 520)
    game = make_mock_game(zoom=zoom, pan=pan, viewport_rect=viewport)
    renderer = GalaxyViewRenderer(game)

    with patch("pygame.draw.line") as mock_draw_line:
        renderer.draw_galaxy_view()

        grid_calls = [
            call for call in mock_draw_line.call_args_list
            if len(call.args) >= 2 and call.args[1] in (GALAXY_GRID_COLOR, GALAXY_BORDER_COLOR)
        ]
        assert len(grid_calls) == 27

        # Test that vertical line x=0 endpoints match screen projection of (0, 0) and (0, 1440)
        p0_screen = logical_to_screen_galaxy(Position(0, 0), viewport, zoom, pan).to_tuple()
        p_bottom_screen = logical_to_screen_galaxy(Position(0, LOGICAL_GALAXY_SIZE.y), viewport, zoom, pan).to_tuple()

        # Find the line corresponding to x=0
        matching = [
            c for c in grid_calls
            if c.args[2] == pytest.approx(p0_screen) and c.args[3] == pytest.approx(p_bottom_screen)
        ]
        assert len(matching) == 1
        assert matching[0].args[1] == GALAXY_BORDER_COLOR


def test_tactical_grid_drawn_before_wormholes_and_systems():
    game = make_mock_game()
    # Add one system and one wormhole
    sol_system = MagicMock()
    sol_system.name = "Sol"
    sol_system.position = Position(1280, 720)
    beta_system = MagicMock()
    beta_system.name = "Beta"
    beta_system.position = Position(1600, 800)
    game.galaxy.systems = {"Sol": sol_system, "Beta": beta_system}
    game.galaxy.wormholes = {
        1: MagicMock(stability=1, in_system="Sol", exit_wormhole_id=2),
        2: MagicMock(stability=1, in_system="Beta", exit_wormhole_id=1),
    }

    renderer = GalaxyViewRenderer(game)
    with patch("pygame.draw.line") as mock_draw_line, patch("pygame.draw.circle") as mock_draw_circle:
        renderer.draw_galaxy_view()

        all_line_calls = mock_draw_line.call_args_list
        # Grid lines must come first
        grid_line_indices = [
            i for i, c in enumerate(all_line_calls)
            if len(c.args) >= 2 and c.args[1] in (GALAXY_GRID_COLOR, GALAXY_BORDER_COLOR)
        ]
        wh_line_indices = [
            i for i, c in enumerate(all_line_calls)
            if len(c.args) >= 2 and c.args[1] == WORMHOLE_LINE_COLOR
        ]

        assert grid_line_indices
        assert wh_line_indices
        assert max(grid_line_indices) < min(wh_line_indices)


def test_preview_draws_tactical_grid():
    preview_rect = pygame.Rect(10, 10, 400, 300)
    surface = pygame.Surface((420, 320))
    galaxy = MagicMock()
    galaxy.systems = {"Sol": MagicMock(position=Position(1280, 720))}
    galaxy.wormholes = {}

    with patch("pygame.draw.line") as mock_draw_line:
        draw_galaxy_preview(surface, galaxy, preview_rect, show_grid=True)
        grid_lines = [
            c for c in mock_draw_line.call_args_list
            if len(c.args) >= 2 and c.args[1] in (GALAXY_GRID_COLOR, GALAXY_BORDER_COLOR)
        ]
        assert len(grid_lines) == 27

    with patch("pygame.draw.line") as mock_draw_line:
        draw_galaxy_preview(surface, galaxy, preview_rect, show_grid=False)
        grid_lines = [
            c for c in mock_draw_line.call_args_list
            if len(c.args) >= 2 and c.args[1] in (GALAXY_GRID_COLOR, GALAXY_BORDER_COLOR)
        ]
        assert len(grid_lines) == 0


pytestmark = pytest.mark.usefixtures("pygame_context")
