from unittest.mock import MagicMock, patch

import pygame

from rendering.sector_renderer import _BoundedSurfaceCache, SectorViewRenderer
from geometry import Position
from entities import Storm, Nebula
from constants import StormType, NebulaType



def test_bounded_surface_cache_evicts_least_recently_used_surface():
    cache = _BoundedSurfaceCache(max_bytes=400, max_item_bytes=400)
    first = pygame.Surface((8, 8), pygame.SRCALPHA)
    second = pygame.Surface((8, 8), pygame.SRCALPHA)

    cache.put("first", first)
    cache.put("second", second)

    assert cache.get("first") is None
    assert cache.get("second") is second
    assert cache.total_bytes == 256


def test_bounded_surface_cache_does_not_retain_oversized_surface():
    cache = _BoundedSurfaceCache(max_bytes=1024, max_item_bytes=128)
    oversized = pygame.Surface((8, 8), pygame.SRCALPHA)

    assert cache.put("oversized", oversized) is oversized
    assert cache.get("oversized") is None
    assert cache.total_bytes == 0


def test_visible_scaling_never_requests_a_full_high_zoom_texture():
    game = MagicMock()
    renderer = SectorViewRenderer(game)
    renderer.screen = pygame.Surface((320, 200))
    renderer.overlay_surface = pygame.Surface((320, 200), pygame.SRCALPHA)
    source = pygame.Surface((1000, 800), pygame.SRCALPHA)

    with patch("rendering.sector_renderer.pygame.transform.smoothscale", wraps=pygame.transform.smoothscale) as smoothscale:
        assert renderer._blit_visible_scaled_surface(
            source, (500, 400), (160, 100), 15.0, ("test",)
        )

    requested_size = smoothscale.call_args.args[1]
    # The shared clipping helper (_compute_visible_scaled_region) snaps the
    # visible region to whole source-pixel boundaries, so the scaled surface
    # can be up to ~2x`scale` px larger than the raw screen size (here, up to
    # 320 + 2*15 = 350 and 200 + 2*15 = 230). This still guarantees we're
    # nowhere near transforming the full 1000x800 source texture, matching
    # the bound used by the equivalent test for `_blit_scaled_surface_once`.
    assert requested_size[0] <= 350
    assert requested_size[1] <= 350


def test_effect_zoom_bucket_is_coarser_while_camera_is_moving():
    game = MagicMock()
    game.sector_target_zoom = 2.0
    renderer = SectorViewRenderer(game)

    assert renderer._effect_zoom_bucket(1.04) == 1.0
    game.sector_target_zoom = 1.04
    assert renderer._effect_zoom_bucket(1.04) == 1.05


def test_blit_uncached_circle_blends_instead_of_replacing():
    """Regression test: large (uncached) storm circles must alpha-blend with
    the overlay (like the cached/scaled path) instead of replacing pixels,
    otherwise overlapping storm particles lose their intended transparency
    once zoomed in far enough to hit this fallback."""
    game = MagicMock()
    renderer = SectorViewRenderer(game)
    renderer.screen = pygame.Surface((320, 200))
    renderer.overlay_surface = pygame.Surface((320, 200), pygame.SRCALPHA)

    color = (255, 69, 0, 40)

    # Draw the same semi-transparent circle twice at the same spot.
    renderer._blit_uncached_circle((160, 100), 20, color)
    alpha_after_one = renderer.overlay_surface.get_at((160, 100)).a

    renderer._blit_uncached_circle((160, 100), 20, color)
    alpha_after_two = renderer.overlay_surface.get_at((160, 100)).a

    # A single draw should reproduce the source alpha...
    assert alpha_after_one == 40
    # ...but overlapping draws must accumulate alpha (source-over blending),
    # not stay flat as pygame.draw.circle's replace semantics would produce.
    assert alpha_after_two > alpha_after_one


def test_blit_uncached_circle_only_allocates_onscreen_region():
    game = MagicMock()
    renderer = SectorViewRenderer(game)
    renderer.screen = pygame.Surface((320, 200))
    renderer.overlay_surface = pygame.Surface((320, 200), pygame.SRCALPHA)

    # Circle centered off the right edge of the screen; only a sliver is visible.
    renderer._blit_uncached_circle((310, 100), 400, (255, 69, 0, 40))

    # Should not have thrown, and should have painted something on-screen.
    assert renderer.overlay_surface.get_at((315, 100)).a > 0


def _make_test_renderer():
    game = MagicMock()
    renderer = SectorViewRenderer(game)
    renderer.screen = pygame.Surface((320, 200))
    renderer.overlay_surface = pygame.Surface((320, 200), pygame.SRCALPHA)
    return game, renderer


def test_blit_scaled_surface_once_never_requests_a_full_high_zoom_texture():
    """The no-cache scaler used for per-frame-changing content (storms) must
    clip to the visible viewport just like the cached scaler, instead of
    transforming a many-hundred-MiB intermediate texture at high zoom."""
    game, renderer = _make_test_renderer()
    source = pygame.Surface((1000, 800), pygame.SRCALPHA)

    with patch("rendering.sector_renderer.pygame.transform.scale", wraps=pygame.transform.scale) as scale:
        assert renderer._blit_scaled_surface_once(
            source, (500, 400), (160, 100), 15.0, smooth=False
        )

    requested_size = scale.call_args.args[1]
    # Bounded close to the screen size, nowhere near the full 15000x12000
    # texture a naive full-surface scale would have requested.
    assert requested_size[0] <= 350
    assert requested_size[1] <= 350


def test_draw_storm_composites_particles_and_scales_the_canvas_exactly_once():
    """Regression test for the compose-then-scale storm rendering: instead of
    individually smoothscaling (or uncached-circle-drawing) each of the 25
    rotating particles every frame, the storm's particles must be composited
    into one local canvas and that canvas scaled to the screen with a single
    transform call."""
    game, renderer = _make_test_renderer()
    game.sector_zoom = 1.0
    game.sector_target_zoom = 1.0  # camera at rest -> smooth scaling path

    storm = Storm(in_hex=(0, 0), in_system="Sol", storm_type=StormType.PLASMA)
    pos_px = Position(160, 100)  # dead center of the 320x200 test screen

    with patch("rendering.sector_renderer.pygame.transform.scale", wraps=pygame.transform.scale) as fast_scale, \
         patch("rendering.sector_renderer.pygame.transform.smoothscale", wraps=pygame.transform.smoothscale) as smooth_scale:
        renderer._draw_storm(storm, pos_px)

    # Exactly one transform call total for the whole storm (all 25 particles
    # composited locally first), and since the camera is at rest it should be
    # the smooth (quality) path.
    assert fast_scale.call_count == 0
    assert smooth_scale.call_count == 1


def test_draw_storm_uses_fast_scale_while_zooming():
    game, renderer = _make_test_renderer()
    game.sector_zoom = 1.0
    game.sector_target_zoom = 2.0  # camera actively zooming

    storm = Storm(in_hex=(0, 0), in_system="Sol", storm_type=StormType.MAGNETIC)
    pos_px = Position(160, 100)

    with patch("rendering.sector_renderer.pygame.transform.scale", wraps=pygame.transform.scale) as fast_scale, \
         patch("rendering.sector_renderer.pygame.transform.smoothscale", wraps=pygame.transform.smoothscale) as smooth_scale:
        renderer._draw_storm(storm, pos_px)

    assert fast_scale.call_count == 1
    assert smooth_scale.call_count == 0


def test_draw_storm_offscreen_is_culled_with_no_transform_calls():
    """A storm whose bounding circle doesn't touch the screen at all should
    skip compositing and scaling entirely."""
    game, renderer = _make_test_renderer()
    game.sector_zoom = 1.0
    game.sector_target_zoom = 1.0

    storm = Storm(in_hex=(0, 0), in_system="Sol", storm_type=StormType.RADIATION)
    far_away_pos = Position(1_000_000, 1_000_000)

    with patch("rendering.sector_renderer.pygame.transform.scale", wraps=pygame.transform.scale) as fast_scale, \
         patch("rendering.sector_renderer.pygame.transform.smoothscale", wraps=pygame.transform.smoothscale) as smooth_scale:
        renderer._draw_storm(storm, far_away_pos)

    assert fast_scale.call_count == 0
    assert smooth_scale.call_count == 0


def test_storm_local_canvas_particles_accumulate_alpha():
    """The compose-then-scale storm path blits each particle (obtained from
    the shared circle-surface cache) onto a local canvas using normal
    per-pixel-alpha blitting. Overlapping particles must therefore still
    accumulate alpha (source-over) exactly like the old per-particle
    rendering did, preserving the intended denser look where storm
    particles overlap."""
    game, renderer = _make_test_renderer()

    color_key = (255, 69, 0, 40)
    circle_surface = renderer._get_cached_circle_surface(10, color_key)

    canvas = pygame.Surface((40, 40), pygame.SRCALPHA)
    canvas.blit(circle_surface, (10, 10))
    alpha_after_one = canvas.get_at((20, 20)).a

    canvas.blit(circle_surface, (10, 10))
    alpha_after_two = canvas.get_at((20, 20)).a

    assert alpha_after_one > 0
    assert alpha_after_two > alpha_after_one


def test_draw_nebula_uses_smoothscale_at_rest_and_fast_scale_while_zooming():
    game, renderer = _make_test_renderer()
    nebula = Nebula(in_hex=(0, 0), in_system="Sol", nebula_type=NebulaType.HYDROGEN)
    pos_px = Position(160, 100)

    # Camera at rest: zoom == target_zoom -> smooth (quality) path, cached.
    game.sector_zoom = 1.0
    game.sector_target_zoom = 1.0
    with patch("rendering.sector_renderer.pygame.transform.scale", wraps=pygame.transform.scale) as fast_scale, \
         patch("rendering.sector_renderer.pygame.transform.smoothscale", wraps=pygame.transform.smoothscale) as smooth_scale:
        renderer._draw_nebula(nebula, pos_px)
    assert smooth_scale.call_count == 1
    assert fast_scale.call_count == 0

    # Camera actively zooming: target differs from current zoom -> fast path.
    game.sector_zoom = 1.0
    game.sector_target_zoom = 2.0
    with patch("rendering.sector_renderer.pygame.transform.scale", wraps=pygame.transform.scale) as fast_scale, \
         patch("rendering.sector_renderer.pygame.transform.smoothscale", wraps=pygame.transform.smoothscale) as smooth_scale:
        renderer._draw_nebula(nebula, pos_px)
    assert fast_scale.call_count == 1
    assert smooth_scale.call_count == 0



