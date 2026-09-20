"""Tests for strikecraft wing icon rendering in draw_shape and draw_wireframe_shape."""
from unittest.mock import patch
import pygame
import pytest

from constants import BLUE
from geometry import Position
from rendering.drawing_utils import draw_shape, draw_wireframe_shape


def test_draw_shape_strikecraft_wing_draws_all_three_triangles():
    """Verify draw_shape renders all 3 sub-triangles for strikecraft_wing."""
    surface = pygame.Surface((400, 400), pygame.SRCALPHA)
    center = Position(200, 200)
    radius = 50.0

    with patch("pygame.draw.polygon", wraps=pygame.draw.polygon) as mock_polygon:
        draw_shape(surface, "strikecraft_wing", BLUE, center, radius)

    assert mock_polygon.call_count == 3
    calls = mock_polygon.call_args_list

    # All calls target the same surface and color
    for call in calls:
        assert call.args[0] is surface
        assert call.args[1] == BLUE

    # Verify points of the three triangles
    t1_pts = calls[0].args[2]  # Top triangle
    t2_pts = calls[1].args[2]  # Bottom-left triangle
    t3_pts = calls[2].args[2]  # Bottom-right triangle

    # Top triangle apex should be centered and at cy - radius
    assert t1_pts[0] == (200, 200 - 50)
    # Bottom-left triangle bottom corner
    assert t2_pts[1] == (200 - int(50 * 0.8), 200 + int(50 * 0.6))
    # Bottom-right triangle bottom corner
    assert t3_pts[2] == (200 + int(50 * 0.8), 200 + int(50 * 0.6))


def test_draw_shape_strikecraft_wing_raster_symmetry_and_pixels():
    """Verify raster surface has non-zero pixels for all three triangles including bottom-right."""
    surface = pygame.Surface((400, 400), pygame.SRCALPHA)
    center = Position(200, 200)
    radius = 50.0

    draw_shape(surface, "strikecraft_wing", (0, 0, 255, 255), center, radius)

    bounds = surface.get_bounding_rect()
    assert bounds.width > 0 and bounds.height > 0

    # The shape should be horizontally centered around cx = 200
    assert abs(bounds.centerx - 200) <= 1

    # Bottom-left region (x < 200, y > 200) and bottom-right region (x > 200, y > 200)
    # should both have drawn pixels.
    bl_pixels = 0
    br_pixels = 0
    for x in range(bounds.left, 200):
        for y in range(200, bounds.bottom):
            if surface.get_at((x, y)).a > 0:
                bl_pixels += 1

    for x in range(200, bounds.right):
        for y in range(200, bounds.bottom):
            if surface.get_at((x, y)).a > 0:
                br_pixels += 1

    assert bl_pixels > 0, "Bottom-left triangle should have non-zero pixels"
    assert br_pixels > 0, "Bottom-right triangle should have non-zero pixels"
    # Symmetrical triangle arrangement should have very similar pixel counts on left and right
    assert abs(bl_pixels - br_pixels) <= 5, f"Left ({bl_pixels}) and right ({br_pixels}) pixel counts should be symmetric"


def test_draw_wireframe_shape_strikecraft_wing_draws_all_three_triangles():
    """Verify draw_wireframe_shape renders all 3 sub-triangles with the specified width."""
    surface = pygame.Surface((400, 400), pygame.SRCALPHA)
    center = Position(200, 200)
    radius = 30.0

    with patch("pygame.draw.polygon", wraps=pygame.draw.polygon) as mock_polygon:
        draw_wireframe_shape(surface, "strikecraft_wing", BLUE, center, radius, width=2)

    assert mock_polygon.call_count == 3
    for call in mock_polygon.call_args_list:
        assert call.args[0] is surface
        assert call.args[1] == BLUE
        assert call.args[3] == 2  # width argument
