"""Tests for strikecraft wing icon rendering in draw_shape and draw_wireframe_shape."""
from unittest.mock import patch
import pygame

from constants import BLUE
from geometry import Position
from rendering.drawing_utils import darken_color, draw_shape, draw_wireframe_shape


def test_draw_shape_strikecraft_wing_draws_all_three_triangles():
    """Verify draw_shape renders all 3 sub-triangles with a darker fill and full-color outline."""
    surface = pygame.Surface((400, 400), pygame.SRCALPHA)
    center = Position(200, 200)
    radius = 50.0
    expected_interior = darken_color(BLUE)

    with patch("pygame.draw.polygon", wraps=pygame.draw.polygon) as mock_polygon:
        draw_shape(surface, "strikecraft_wing", BLUE, center, radius)

    assert mock_polygon.call_count == 6
    fill_calls = mock_polygon.call_args_list[:3]
    outline_calls = mock_polygon.call_args_list[3:]

    for call in fill_calls:
        assert call.args[0] is surface
        assert call.args[1] == expected_interior
        assert len(call.args) == 3

    for call in outline_calls:
        assert call.args[0] is surface
        assert call.args[1] == BLUE
        assert call.args[3] == 1

    # Verify points of the three triangles match between fill and outline
    t1_pts = fill_calls[0].args[2]  # Top triangle
    t2_pts = fill_calls[1].args[2]  # Bottom-left triangle
    t3_pts = fill_calls[2].args[2]  # Bottom-right triangle
    assert [c.args[2] for c in outline_calls] == [t1_pts, t2_pts, t3_pts]

    # Top triangle apex should be centered and at cy - radius
    assert t1_pts[0] == (200, 200 - 50)
    # Bottom-left triangle bottom corner
    assert t2_pts[1] == (200 - int(50 * 0.8), 200 + int(50 * 0.6))
    # Bottom-right triangle bottom corner
    assert t3_pts[2] == (200 + int(50 * 0.8), 200 + int(50 * 0.6))


def test_draw_shape_renders_darker_interior_and_full_color_outline():
    """Verify rendered unit shapes have darkened interior pixels and full-color outline pixels."""
    color = (40, 180, 255)
    interior = darken_color(color)
    center = Position(100, 100)
    radius = 40.0

    for shape, interior_probe, outline_probe in (
        ("square", (100, 100), (100 - 32, 100)),
        ("triangle", (100, 100), (100, 100 - 40)),
        ("strikecraft_wing", (100, 100 - 20), (100, 100 - 40)),
        ("circle", (100, 100), (100 - 40, 100)),
    ):
        surface = pygame.Surface((200, 200), pygame.SRCALPHA)
        draw_shape(surface, shape, color, center, radius)
        assert surface.get_at(interior_probe)[:3] == interior
        assert surface.get_at(outline_probe)[:3] == color


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
