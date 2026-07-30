import pytest
import pygame
from unittest.mock import MagicMock, patch
from geometry import Position
from constants import (
    SECTOR_CIRCLE_CENTER_IN_PX,
    SECTOR_CIRCLE_RADIUS_IN_PX, SECTOR_CIRCLE_RADIUS_LOGICAL,
    FOG_OF_WAR_COLOR, DEFAULT_SENSOR_SHORT_RANGE,
)

# Use a small test surface.  The sector centre (SECTOR_CIRCLE_CENTER_IN_PX) is
# at the real screen centre (e.g. 1920, 1080) which is outside this surface, so
# we apply a pan offset that brings it to (400, 300) -- the centre of our
# test canvas.
SCREEN_W, SCREEN_H = 800, 600
_CX = int(SECTOR_CIRCLE_CENTER_IN_PX.x)
_CY = int(SECTOR_CIRCLE_CENTER_IN_PX.y)
# Pan offset that maps real sector centre to (SCREEN_W//2, SCREEN_H//2)
_PAN_X = SCREEN_W // 2 - _CX
_PAN_Y = SCREEN_H // 2 - _CY
# dynamic_radius small enough to fit inside the test canvas
TEST_DYNAMIC_RADIUS = min(SCREEN_W, SCREEN_H) // 2 - 10  # 290 px


def _make_screen():
    return pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)


def _make_game(screen, player=None, zoom=1.0):
    game = MagicMock()
    game.screen = screen
    game.sector_zoom = zoom
    game.sector_pan_offset = Position(_PAN_X, _PAN_Y)
    game.players = [player] if player else []
    game.current_player_index = 0
    return game


def _make_renderer(game):
    from rendering.sector_renderer import SectorViewRenderer
    r = SectorViewRenderer.__new__(SectorViewRenderer)
    r.game = game
    r.screen = game.screen
    r.overlay_surface = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    r._fog_of_war_surface = None
    r._fog_cache_key = None
    r._fog_blit_rect = None
    r._range_circle_surface = None
    r._circle_surface_cache = {}
    r._font_cache = {}
    r._nebula_master_surfaces = {}
    r._storm_base_circle_surfaces = {}
    r._scaled_effect_surfaces = MagicMock()
    r._last_cached_sector = None
    r._inhibition_surface = None
    r._storm_scratch_surface = None
    r.zoom_render_stats = {k: 0 for k in [
        "cache_hits", "cache_misses", "cache_bytes",
        "direct_draw_fallbacks", "range_circle_fills",
        "fog_rebuilds", "fog_cache_hits", "fog_full_reveal",
    ]}
    return r


def _make_hex(units=None):
    h = MagicMock()
    h.units = units or []
    return h


def _make_unit(player, position, short_range_radius=DEFAULT_SENSOR_SHORT_RANGE):
    u = MagicMock()
    u.owner = player
    u.position = position
    s = MagicMock()
    s.is_destroyed = False
    s.has_short_range = short_range_radius > 0
    s.short_range_radius = short_range_radius
    u.sensors_component = s
    return u


@pytest.fixture(autouse=True)
def init_pygame():
    pygame.init()
    yield
    pygame.quit()


class TestDrawFogOfWar:

    def test_surface_created(self):
        screen = _make_screen()
        p = MagicMock()
        h = _make_hex([_make_unit(p, Position(0, 0))])
        r = _make_renderer(_make_game(screen, player=p))
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        assert r._fog_of_war_surface is not None
        assert r._fog_of_war_surface.get_size() == (SCREEN_W, SCREEN_H)

    def test_surface_reused(self):
        screen = _make_screen()
        p = MagicMock()
        h = _make_hex([_make_unit(p, Position(0, 0))])
        r = _make_renderer(_make_game(screen, player=p))
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        s1 = id(r._fog_of_war_surface)
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        s2 = id(r._fog_of_war_surface)
        assert s1 == s2

    def test_no_units_fog_covers_centre(self):
        screen = _make_screen()
        p = MagicMock()
        h = _make_hex([])
        r = _make_renderer(_make_game(screen, player=p))
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        cx, cy = SCREEN_W // 2, SCREEN_H // 2
        _, _, _, a = r._fog_of_war_surface.get_at((cx, cy))
        assert a > 0, "Fog should cover centre when no friendly units"

    def test_large_sensor_clears_centre(self):
        screen = _make_screen()
        p = MagicMock()
        # Sensor radius large enough that its pixel radius >= TEST_DYNAMIC_RADIUS
        u = _make_unit(p, Position(0, 0), short_range_radius=SECTOR_CIRCLE_RADIUS_LOGICAL)
        h = _make_hex([u])
        r = _make_renderer(_make_game(screen, player=p))
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        cx, cy = SCREEN_W // 2, SCREEN_H // 2
        _, _, _, a = r._fog_of_war_surface.get_at((cx, cy))
        assert a == 0, "Expected alpha=0 at centre with full-sector sensor"

    def test_destroyed_sensor_no_cutout(self):
        screen = _make_screen()
        p = MagicMock()
        u = _make_unit(p, Position(0, 0))
        u.sensors_component.is_destroyed = True
        h = _make_hex([u])
        r = _make_renderer(_make_game(screen, player=p))
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        cx, cy = SCREEN_W // 2, SCREEN_H // 2
        _, _, _, a = r._fog_of_war_surface.get_at((cx, cy))
        assert a == FOG_OF_WAR_COLOR[3], (
            f"Destroyed sensor: expected fog alpha={FOG_OF_WAR_COLOR[3]}, got a={a}"
        )

    def test_enemy_no_cutout(self):
        screen = _make_screen()
        current = MagicMock()
        enemy = MagicMock()
        u = _make_unit(enemy, Position(0, 0), short_range_radius=SECTOR_CIRCLE_RADIUS_LOGICAL)
        h = _make_hex([u])
        r = _make_renderer(_make_game(screen, player=current))
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        cx, cy = SCREEN_W // 2, SCREEN_H // 2
        _, _, _, a = r._fog_of_war_surface.get_at((cx, cy))
        assert a == FOG_OF_WAR_COLOR[3], (
            f"Enemy unit should not create cutout, got a={a}"
        )

    def test_surface_reset_on_sector_change(self):
        screen = _make_screen()
        p = MagicMock()
        h = _make_hex([_make_unit(p, Position(0, 0))])
        r = _make_renderer(_make_game(screen, player=p))
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        assert r._fog_of_war_surface is not None
        r._fog_of_war_surface = None
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        assert r._fog_of_war_surface is not None

    def test_fog_never_uses_python_scanline_lines(self):
        screen = _make_screen()
        p = MagicMock()
        h = _make_hex([_make_unit(p, Position(0, 0))])
        r = _make_renderer(_make_game(screen, player=p))
        with patch("rendering.sector_renderer.pygame.draw.line") as draw_line:
            r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        draw_line.assert_not_called()

    def test_fog_rebuild_uses_clipped_circle(self):
        screen = _make_screen()
        p = MagicMock()
        h = _make_hex([_make_unit(p, Position(0, 0))])
        r = _make_renderer(_make_game(screen, player=p))
        with patch("rendering.sector_renderer.pygame.draw.circle", wraps=pygame.draw.circle) as draw_circle:
            r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        assert draw_circle.call_count >= 1

    def test_fog_cached_across_identical_frames(self):
        screen = _make_screen()
        p = MagicMock()
        h = _make_hex([_make_unit(p, Position(0, 0))])
        r = _make_renderer(_make_game(screen, player=p))
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        rebuilds_before = r.zoom_render_stats['fog_rebuilds']
        hits_before = r.zoom_render_stats['fog_cache_hits']
        with patch("rendering.sector_renderer.pygame.draw.circle") as draw_circle:
            r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        draw_circle.assert_not_called()
        assert r.zoom_render_stats['fog_rebuilds'] == rebuilds_before
        assert r.zoom_render_stats['fog_cache_hits'] == hits_before + 1

    def test_fog_cache_invalidated_by_zoom_pan_and_unit_change(self):
        screen = _make_screen()
        p = MagicMock()
        u = _make_unit(p, Position(0, 0))
        h = _make_hex([u])
        g = _make_game(screen, player=p)
        r = _make_renderer(g)

        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)
        assert r.zoom_render_stats['fog_rebuilds'] == 1

        # Change zoom
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS + 10)
        assert r.zoom_render_stats['fog_rebuilds'] == 2

        # Change pan
        g.sector_pan_offset = Position(_PAN_X + 5, _PAN_Y)
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS + 10)
        assert r.zoom_render_stats['fog_rebuilds'] == 3

        # Move unit position
        u.position = Position(100, 100)
        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS + 10)
        assert r.zoom_render_stats['fog_rebuilds'] == 4

    def test_fog_skipped_when_sensor_covers_viewport(self):
        screen = MagicMock()
        screen.get_size.return_value = (SCREEN_W, SCREEN_H)
        p = MagicMock()
        # Sensor radius huge enough to cover fog_rect completely
        u = _make_unit(p, Position(0, 0), short_range_radius=SECTOR_CIRCLE_RADIUS_LOGICAL * 10)
        h = _make_hex([u])
        r = _make_renderer(_make_game(screen, player=p))

        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)

        screen.blit.assert_not_called()
        assert r.zoom_render_stats['fog_full_reveal'] == 1

    def test_fog_cutout_contained_in_larger_is_skipped(self):
        screen = _make_screen()
        p = MagicMock()
        # Small sensor unit inside large sensor unit at same location
        u1 = _make_unit(p, Position(0, 0), short_range_radius=500.0)
        u2 = _make_unit(p, Position(0, 0), short_range_radius=2000.0)
        h = _make_hex([u1, u2])
        r = _make_renderer(_make_game(screen, player=p))

        with patch("rendering.sector_renderer.pygame.draw.circle", wraps=pygame.draw.circle) as draw_circle:
            r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)

        # 1 call for sector disc + 1 call for larger cutout (u1 is contained in u2, so culled)
        assert draw_circle.call_count == 2

    def test_fog_offscreen_disc_is_culled(self):
        screen = MagicMock()
        screen.get_size.return_value = (SCREEN_W, SCREEN_H)
        p = MagicMock()
        h = _make_hex([_make_unit(p, Position(0, 0))])
        g = _make_game(screen, player=p)
        g.sector_pan_offset = Position(100000, 100000)
        r = _make_renderer(g)

        with patch("rendering.sector_renderer.pygame.draw.circle") as draw_circle:
            r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)

        draw_circle.assert_not_called()
        screen.blit.assert_not_called()

    def test_fog_blit_bounded_to_fog_rect(self):
        screen = MagicMock()
        screen.get_size.return_value = (SCREEN_W, SCREEN_H)
        p = MagicMock()
        h = _make_hex([])
        r = _make_renderer(_make_game(screen, player=p))

        r._draw_fog_of_war(h, TEST_DYNAMIC_RADIUS)

        screen.blit.assert_called_once()
        args, kwargs = screen.blit.call_args
        area = kwargs.get('area')
        assert area is not None
        assert area.width <= SCREEN_W and area.height <= SCREEN_H
