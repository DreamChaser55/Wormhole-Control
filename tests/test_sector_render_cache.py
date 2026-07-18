from unittest.mock import MagicMock, patch

import pygame

from rendering.sector_renderer import _BoundedSurfaceCache, SectorViewRenderer


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
    assert requested_size[0] <= 322
    assert requested_size[1] <= 202


def test_effect_zoom_bucket_is_coarser_while_camera_is_moving():
    game = MagicMock()
    game.sector_target_zoom = 2.0
    renderer = SectorViewRenderer(game)

    assert renderer._effect_zoom_bucket(1.04) == 1.0
    game.sector_target_zoom = 1.04
    assert renderer._effect_zoom_bucket(1.04) == 1.05
