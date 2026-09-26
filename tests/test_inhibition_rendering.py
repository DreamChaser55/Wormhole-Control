"""Unit tests for hyperspace inhibition zone rendering in Sector View."""
from unittest.mock import MagicMock, patch
import pygame
import pytest

from geometry import Position, Circle
from constants import (
    SECTOR_CIRCLE_RADIUS_LOGICAL,
    INHIBITION_FIELD_COLOR,
    INHIBITION_FIELD_LINE_WIDTH,
)
from rendering.sector_renderer.sector_entity_renderer import SectorEntityRenderer
from rendering.sector_renderer.sector_grid_renderer import SectorGridRenderer


@pytest.fixture
def mock_parent():
    parent = MagicMock()
    parent.game = MagicMock()
    parent.screen = MagicMock()
    parent.screen.get_size.return_value = (800, 600)
    parent.overlay_surface = pygame.Surface((800, 600), pygame.SRCALPHA)
    parent.grid_renderer = SectorGridRenderer(parent)
    parent.grid_renderer.coords_to_pixels = MagicMock(
        side_effect=lambda pos: Position(pos.x + 400, pos.y + 300)
    )
    return parent


def test_draw_inhibition_zones_draws_outlined_circle(mock_parent):
    """Verify inhibition zones are drawn as outlined circles with configured color and line width."""
    renderer = SectorEntityRenderer(mock_parent)

    mock_hex = MagicMock()
    mock_hex.get_all_inhibition_zones.return_value = [
        Circle(center=Position(0, 0), radius=1500.0)
    ]

    dynamic_radius = 300.0
    expected_pixel_radius = int(1500.0 * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)

    with patch("pygame.draw.circle", wraps=pygame.draw.circle) as mock_draw_circle:
        renderer.draw_inhibition_zones(mock_hex, dynamic_radius)

        assert mock_draw_circle.call_count == 1
        call_args, call_kwargs = mock_draw_circle.call_args

        # Verify surface, color, center, and radius
        assert call_args[0] == mock_parent.overlay_surface
        assert call_args[1] == INHIBITION_FIELD_COLOR
        assert call_args[2] == (400, 300)
        assert call_args[3] == expected_pixel_radius

        # Verify outlined circle style (width >= 1, specifically INHIBITION_FIELD_LINE_WIDTH)
        width_arg = call_kwargs.get("width", call_args[4] if len(call_args) > 4 else 0)
        assert width_arg == INHIBITION_FIELD_LINE_WIDTH
        assert width_arg == 4

    # Only the opaque boundary is painted; the main renderer composites it later.
    assert mock_parent.overlay_surface.get_at((400, 300)).a == 0
    assert mock_parent.overlay_surface.get_at((400 + expected_pixel_radius - 1, 300)) == (100, 150, 255, 255)
    assert mock_parent.overlay_surface.get_at((400 + expected_pixel_radius - 5, 300)).a == 0
    mock_parent.screen.blit.assert_not_called()


def test_draw_inhibition_zones_multiple_zones(mock_parent):
    """Verify multiple inhibition zones (static and dynamic) are all drawn with outlined style."""
    renderer = SectorEntityRenderer(mock_parent)

    mock_hex = MagicMock()
    mock_hex.get_all_inhibition_zones.return_value = [
        Circle(center=Position(-100, -100), radius=1000.0),
        Circle(center=Position(200, 200), radius=2000.0),
    ]

    dynamic_radius = 300.0

    with patch("pygame.draw.circle") as mock_draw_circle:
        renderer.draw_inhibition_zones(mock_hex, dynamic_radius)

        assert mock_draw_circle.call_count == 2
        for c in mock_draw_circle.call_args_list:
            args, kwargs = c
            assert args[1] == INHIBITION_FIELD_COLOR
            width_arg = kwargs.get("width", args[4] if len(args) > 4 else 0)
            assert width_arg == INHIBITION_FIELD_LINE_WIDTH

    mock_parent.screen.blit.assert_not_called()


def test_draw_inhibition_zones_skips_culled_rings(mock_parent):
    """Skip off-screen, tiny and viewport-enclosing rings via the shared helper."""
    renderer = SectorEntityRenderer(mock_parent)

    mock_hex = MagicMock()
    mock_hex.get_all_inhibition_zones.return_value = [
        Circle(center=Position(0, 0), radius=0.0),  # zero radius
        Circle(center=Position(0, 0), radius=-100.0),  # negative radius
        Circle(center=Position(0, 0), radius=25.0),  # one pixel at this zoom
        Circle(center=Position(0, 0), radius=10000.0),  # encloses viewport
        Circle(center=Position(5000, 5000), radius=500.0),  # off screen
    ]

    with patch("pygame.draw.circle") as mock_draw_circle:
        renderer.draw_inhibition_zones(mock_hex, 300.0)
        assert mock_draw_circle.call_count == 0

    mock_parent.screen.blit.assert_not_called()


def test_draw_inhibition_zones_empty_hex(mock_parent):
    """Verify empty hex does not draw or blit anything."""
    renderer = SectorEntityRenderer(mock_parent)

    mock_hex = MagicMock()
    mock_hex.get_all_inhibition_zones.return_value = []

    with patch("pygame.draw.circle") as mock_draw_circle:
        renderer.draw_inhibition_zones(mock_hex, 300.0)
        assert mock_draw_circle.call_count == 0

    mock_parent.screen.blit.assert_not_called()


def test_draw_inhibition_zones_none_hex(mock_parent):
    """Verify None hex safely returns without error."""
    renderer = SectorEntityRenderer(mock_parent)
    renderer.draw_inhibition_zones(None, 300.0)
    mock_parent.screen.blit.assert_not_called()
