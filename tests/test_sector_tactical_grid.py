import pytest
import pygame
import math
from unittest.mock import MagicMock, patch
from constants import (
    SECTOR_GRID_COLOR, SECTOR_CIRCLE_RADIUS_LOGICAL
)
from rendering.sector_renderer import SectorViewRenderer
from geometry import Position


def test_tactical_grid_draws_lines_clipped_to_sector():
    mock_game = MagicMock()
    mock_game.screen = pygame.Surface((800, 600))
    mock_game.overlay_surface = pygame.Surface((800, 600), pygame.SRCALPHA)
    mock_game.current_system_name = "TestSystem"
    mock_game.current_sector_coord = (0, 0)
    mock_game.sector_zoom = 1.0
    mock_game.sector_pan_offset = Position(0, 0)
    mock_game.is_dragging_selection_box = False
    mock_game.players = []
    mock_game.current_player_index = 0

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

        assert grid_line_calls
        from sector_utils import pixels_to_sector_coords
        for call in grid_line_calls:
            for endpoint in call.args[2:4]:
                point = pixels_to_sector_coords(Position(*endpoint), zoom=mock_game.sector_zoom, pan_offset=mock_game.sector_pan_offset)
                # Pixel rounding permits at most one pixel per axis of overshoot.
                from constants import SECTOR_CIRCLE_RADIUS_IN_PX
                tolerance = math.sqrt(2) * SECTOR_CIRCLE_RADIUS_LOGICAL / SECTOR_CIRCLE_RADIUS_IN_PX
                assert math.hypot(point.x, point.y) <= SECTOR_CIRCLE_RADIUS_LOGICAL + tolerance

pytestmark = pytest.mark.usefixtures("pygame_context")
