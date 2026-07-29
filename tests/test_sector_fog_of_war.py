import pytest
import pygame
from unittest.mock import MagicMock
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
