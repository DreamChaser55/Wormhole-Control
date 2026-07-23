import pytest
import pygame
import math
from unittest.mock import MagicMock, patch

from constants import (
    SECTOR_GRID_COLOR, SECTOR_GRID_SPACING, SECTOR_CIRCLE_RADIUS_LOGICAL
)
from rendering.sector_renderer import SectorViewRenderer
from geometry import Position


@pytest.fixture(autouse=True)
def init_pygame():
    pygame.init()
    yield
    pygame.quit()


def test_sector_tactical_grid_constants():
    assert SECTOR_GRID_COLOR == (30, 35, 45)
    assert SECTOR_GRID_SPACING == 1000.0


def test_draw_tactical_grid_invokes_draw_line():
    mock_game = MagicMock()
    mock_game.screen = pygame.Surface((800, 600))
    mock_game.overlay_surface = pygame.Surface((800, 600), pygame.SRCALPHA)
    mock_game.current_system_name = "TestSystem"
    mock_game.current_sector_coord = (0, 0)
    mock_game.sector_zoom = 1.0
    mock_game.sector_pan_offset = Position(0, 0)
    mock_game.is_dragging_selection_box = False

    mock_hex = MagicMock()
    mock_hex.celestial_bodies = []
    mock_hex.units = []
    mock_hex.get_all_inhibition_zones.return_value = []
    mock_game.galaxy.systems = {"TestSystem": MagicMock(hexes={(0, 0): mock_hex})}

    renderer = SectorViewRenderer(mock_game)

    with patch("rendering.sector_renderer.pygame.draw.line") as mock_draw_line:
        renderer.draw_sector_view()

        # Filter calls that use SECTOR_GRID_COLOR
        grid_line_calls = [
            call for call in mock_draw_line.call_args_list
            if len(call[0]) >= 2 and call[0][1] == SECTOR_GRID_COLOR
        ]

        # For logical radius 5000 and spacing 1000:
        # grid step = 1000 -> -4000, -3000, -2000, -1000, 0, 1000, 2000, 3000, 4000 (9 values)
        # Each step draws 1 vertical line and 1 horizontal line -> 18 lines total
        assert len(grid_line_calls) == 18


def test_tactical_grid_boundary_clipping():
    mock_game = MagicMock()
    mock_game.screen = pygame.Surface((800, 600))
    mock_game.overlay_surface = pygame.Surface((800, 600), pygame.SRCALPHA)
    renderer = SectorViewRenderer(mock_game)

    lines_drawn = []

    def mock_line(surface, color, start_pos, end_pos, width=1):
        lines_drawn.append((start_pos, end_pos))

    with patch("rendering.sector_renderer.pygame.draw.line", side_effect=mock_line):
        renderer._draw_tactical_grid()

    assert len(lines_drawn) == 18
