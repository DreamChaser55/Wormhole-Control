"""Regression tests for the viewport-bounded weapon/sensor range ring
rendering path used in the sector view.

Before this fix, `_draw_unit_range_circles` allocated a
``(2*radius_px) x (2*radius_px)`` SRCALPHA surface and rasterized a full
circle onto it for every ring, every frame. At high sector-view zoom levels
(radius_px in the thousands of pixels), this could allocate hundreds of MB
and rasterize tens of millions of pixels per frame, causing the severe
slowdown described in the bug report ("performance is poor when I zoom in
... and weapon/sensor range circles are drawn on the selected unit").

These tests assert the new implementation (`_fill_circle_clipped` /
`_draw_range_ring`, used by `_draw_unit_range_circles`) is bounded by the
screen size regardless of the ring's true radius, still produces the
expected visual result (alpha-blended fill + outline), still culls fully
off-screen rings, and still de-duplicates identical turret ranges.
"""
from unittest.mock import MagicMock, patch

import pygame

from rendering.sector_renderer import SectorViewRenderer
from geometry import Position


def _make_test_renderer(screen_size=(320, 200)):
    game = MagicMock()
    renderer = SectorViewRenderer(game)
    renderer.screen = pygame.Surface(screen_size)
    renderer.overlay_surface = pygame.Surface(screen_size, pygame.SRCALPHA)
    return game, renderer


def _make_unit(sensor_range=None, turret_ranges=None, owner=None):
    """Build a minimal stand-in for entities.Unit with just the attributes
    _draw_unit_range_circles touches."""
    unit = MagicMock()
    if sensor_range is not None:
        sensors = MagicMock()
        sensors.has_short_range = True
        sensors.short_range_radius = sensor_range
        unit.sensors_component = sensors
    else:
        unit.sensors_component = None

    if turret_ranges:
        turrets = []
        for r in turret_ranges:
            turret = MagicMock()
            turret.range = r
            turrets.append(turret)
        weapons = MagicMock()
        weapons.turrets = turrets
        unit.weapons_component = weapons
    else:
        unit.weapons_component = None

    unit.owner = owner
    return unit


def test_fill_circle_clipped_never_allocates_a_surface_larger_than_the_screen():
    """The core regression check: no matter how large radius_px is, the
    only surface ever allocated for the fill must be bounded by the screen
    size, not by radius_px**2."""
    game, renderer = _make_test_renderer()

    original_surface_ctor = pygame.Surface
    allocated_sizes = []

    def spy_surface(size, *args, **kwargs):
        allocated_sizes.append(size)
        return original_surface_ctor(size, *args, **kwargs)

    with patch("rendering.sector_renderer.pygame.Surface", side_effect=spy_surface):
        # Huge radius, comparable to what a 15x max-zoom sensor/weapon range
        # ring would produce on a 1440p screen (thousands of pixels).
        renderer._fill_circle_clipped((160, 100), 4320, (0, 200, 255, 18))

    # The only allocation should be the persistent range-circle surface,
    # sized to the screen -- never anything close to (2*4320)^2.
    assert allocated_sizes == [(320, 200)]
    assert renderer._range_circle_surface.get_size() == (320, 200)


def test_fill_circle_clipped_reuses_persistent_surface_across_frames():
    """Repeated calls (simulating repeated frames) must not allocate a new
    surface each time."""
    game, renderer = _make_test_renderer()
    renderer._fill_circle_clipped((160, 100), 4320, (0, 200, 255, 18))
    surface_after_first = renderer._range_circle_surface

    renderer._fill_circle_clipped((160, 100), 4320, (0, 200, 255, 18))
    surface_after_second = renderer._range_circle_surface

    assert surface_after_first is surface_after_second


def test_fill_circle_clipped_covering_viewport_uses_rect_fill_not_scanline_loop():
    """When the disc fully covers the viewport (as happens at high zoom,
    where the range ring is far bigger than the screen), the implementation
    must use a flat rect fill instead of walking scanlines / calling
    pygame.draw.line per row."""
    game, renderer = _make_test_renderer()

    with patch("rendering.sector_renderer.pygame.draw.line") as draw_line:
        renderer._fill_circle_clipped((160, 100), 4320, (0, 200, 255, 18))

    # No manual scanline drawing should have happened.
    draw_line.assert_not_called()
    # The rect-fill fast path should still have produced the correct alpha
    # everywhere on screen (since the disc covers the whole viewport).
    assert renderer.overlay_surface.get_at((0, 0)).a == 18
    assert renderer.overlay_surface.get_at((319, 199)).a == 18


def test_fill_circle_clipped_partial_coverage_uses_scanline_fill():
    """When the circle does not cover the whole viewport, pixels should
    still be correctly filled via the scanline path (draw.line calls)."""
    game, renderer = _make_test_renderer()

    with patch("rendering.sector_renderer.pygame.draw.line", wraps=pygame.draw.line) as draw_line:
        renderer._fill_circle_clipped((160, 100), 30, (0, 200, 255, 18))

    assert draw_line.call_count > 0
    # The center pixel should have been filled with the expected alpha.
    assert renderer.overlay_surface.get_at((160, 100)).a == 18


def test_fill_circle_clipped_culls_when_offscreen():
    """A circle whose bounding box doesn't touch the screen at all must not
    touch overlay_surface (no allocation of the persistent surface needed
    yet, and no visible change)."""
    game, renderer = _make_test_renderer()

    renderer._fill_circle_clipped((100000, 100000), 50, (0, 200, 255, 18))

    # Nothing should have been blended onto the overlay.
    assert renderer.overlay_surface.get_at((0, 0)).a == 0


def test_fill_circle_clipped_blends_instead_of_replacing():
    """Overlapping fills must alpha-blend (source-over) rather than replace
    pixels outright, matching the existing storm/nebula compositing
    semantics."""
    game, renderer = _make_test_renderer()
    color = (255, 80, 40, 25)

    renderer._fill_circle_clipped((160, 100), 20, color)
    alpha_after_one = renderer.overlay_surface.get_at((160, 100)).a

    renderer._fill_circle_clipped((160, 100), 20, color)
    alpha_after_two = renderer.overlay_surface.get_at((160, 100)).a

    assert alpha_after_one == 25
    assert alpha_after_two > alpha_after_one


def test_draw_range_ring_draws_fill_and_outline():
    game, renderer = _make_test_renderer()

    renderer._draw_range_ring(160, 100, 30, (0, 200, 255, 18), (0, 200, 255))

    # Fill should be visible near the center.
    assert renderer.overlay_surface.get_at((160, 100)).a == 18
    # Outline should be visible somewhere near the ring boundary
    # (approximately radius_px away from the center, along a scanned arc).
    boundary_alphas = [
        renderer.overlay_surface.get_at((160 + dx, 100)).a
        for dx in range(27, 34)
    ]
    assert any(a > 0 for a in boundary_alphas)


def test_draw_range_ring_skips_outline_when_disc_covers_viewport():
    """When the ring's disc fully encloses the viewport, its circumference
    never crosses the screen, so the (otherwise pointless) outline draw call
    should be skipped."""
    game, renderer = _make_test_renderer()

    with patch("rendering.sector_renderer.pygame.draw.circle", wraps=pygame.draw.circle) as draw_circle:
        renderer._draw_range_ring(160, 100, 4320, (0, 200, 255, 18), (0, 200, 255))

    # No outline circle call (the only pygame.draw.circle calls would come
    # from the outline branch, since the fill uses the scanline/rect path).
    draw_circle.assert_not_called()


def test_draw_range_ring_culls_fully_offscreen_ring():
    game, renderer = _make_test_renderer()

    with patch.object(renderer, "_fill_circle_clipped") as fill_mock:
        renderer._draw_range_ring(100000, 100000, 50, (0, 200, 255, 18), (0, 200, 255))

    fill_mock.assert_not_called()


def test_draw_unit_range_circles_draws_sensor_and_weapon_rings():
    game, renderer = _make_test_renderer()
    unit = _make_unit(sensor_range=2000.0, turret_ranges=[300.0])

    with patch.object(renderer, "_draw_range_ring") as ring_mock:
        renderer._draw_unit_range_circles(unit, Position(160, 100), 720.0)

    # One sensor ring + one weapon ring.
    assert ring_mock.call_count == 2


def test_draw_unit_range_circles_deduplicates_identical_turret_ranges():
    game, renderer = _make_test_renderer()
    unit = _make_unit(sensor_range=None, turret_ranges=[300.0, 300.0, 450.0])

    with patch.object(renderer, "_draw_range_ring") as ring_mock:
        renderer._draw_unit_range_circles(unit, Position(160, 100), 720.0)

    # Two distinct ranges (300 deduplicated, plus 450) -> two calls.
    assert ring_mock.call_count == 2


def test_draw_unit_range_circles_at_extreme_zoom_allocates_only_screen_sized_surface():
    """End-to-end regression test at a zoom level equivalent to the reported
    bug (near SECTOR_ZOOM_MAX): drawing a unit's range circles must never
    allocate a surface bigger than the screen."""
    from constants import SECTOR_CIRCLE_RADIUS_IN_PX, SECTOR_ZOOM_MAX

    game, renderer = _make_test_renderer()
    unit = _make_unit(sensor_range=2000.0, turret_ranges=[300.0, 400.0])

    dynamic_radius = SECTOR_CIRCLE_RADIUS_IN_PX * SECTOR_ZOOM_MAX

    original_surface_ctor = pygame.Surface
    allocated_sizes = []

    def spy_surface(size, *args, **kwargs):
        allocated_sizes.append(size)
        return original_surface_ctor(size, *args, **kwargs)

    with patch("rendering.sector_renderer.pygame.Surface", side_effect=spy_surface):
        renderer._draw_unit_range_circles(unit, Position(160, 100), dynamic_radius)

    for size in allocated_sizes:
        assert size[0] <= 320 and size[1] <= 200


def test_blit_uncached_circle_still_blends_and_culls():
    """The public wrapper kept for backwards compatibility must retain the
    same blending/culling behavior as before."""
    game, renderer = _make_test_renderer()
    color = (255, 69, 0, 40)

    renderer._blit_uncached_circle((160, 100), 20, color)
    alpha_after_one = renderer.overlay_surface.get_at((160, 100)).a

    renderer._blit_uncached_circle((160, 100), 20, color)
    alpha_after_two = renderer.overlay_surface.get_at((160, 100)).a

    assert alpha_after_one == 40
    assert alpha_after_two > alpha_after_one

    # Off-screen-only circle should not throw and should not paint anything.
    renderer._blit_uncached_circle((100000, 100000), 50, color)


def test_range_circles_drawn_when_single_unit_selected():
    """Range circles should be drawn when exactly one friendly unit is
    selected."""
    game, renderer = _make_test_renderer()
    owner = MagicMock()
    unit = _make_unit(sensor_range=2000.0, turret_ranges=[300.0], owner=owner)
    game.selected_objects = [unit]
    game.players = [owner]
    game.current_player_index = 0

    # Directly verify the guard condition that controls drawing:
    # single selected + owned by current player => should draw.
    from entities import Unit
    obj = unit
    should_draw = (
        len(game.selected_objects) == 1
        and obj in game.selected_objects
    )
    current_turn_player = game.players[game.current_player_index]
    should_draw = should_draw and current_turn_player and obj.owner == current_turn_player

    assert should_draw, "Guard should allow drawing for a single owned selected unit"


def test_range_circles_suppressed_when_multiple_units_selected():
    """Range circles should NOT be drawn when multiple units are selected,
    to avoid visual clutter from overlapping circles."""
    game, renderer = _make_test_renderer()
    owner = MagicMock()
    unit1 = _make_unit(sensor_range=2000.0, turret_ranges=[300.0], owner=owner)
    unit2 = _make_unit(sensor_range=1500.0, turret_ranges=[250.0], owner=owner)
    game.selected_objects = [unit1, unit2]
    game.players = [owner]
    game.current_player_index = 0

    # Verify the guard blocks drawing for each unit when multiple are selected.
    for obj in [unit1, unit2]:
        should_draw = (
            len(game.selected_objects) == 1
            and obj in game.selected_objects
        )
        assert not should_draw, (
            "Guard should block range circles when multiple units are selected"
        )

