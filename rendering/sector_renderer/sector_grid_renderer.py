import sys
import math
from constants import (
    SECTOR_CIRCLE_CENTER_IN_PX, SECTOR_CIRCLE_RADIUS_LOGICAL,
    SECTOR_BORDER_COLOR, SECTOR_GRID_COLOR, SECTOR_GRID_SPACING
)
from geometry import Position

MAX_SAFE_CIRCLE_RADIUS_PX = 250_000


def _sr():
    return sys.modules['rendering.sector_renderer']


class SectorGridRenderer:
    """Handles sector hex grid, boundary rendering, coordinate transformations,
    viewport clipping, and low-level surface scaling/blitting calculations.
    """

    def __init__(self, parent):
        self.parent = parent

    @property
    def game(self):
        return self.parent.game

    @property
    def screen(self):
        return self.parent.screen

    @property
    def overlay_surface(self):
        return self.parent.overlay_surface

    def coords_to_pixels(self, sector_pos):
        zoom = self.game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0
        pan_offset = self.game.sector_pan_offset
        if not isinstance(pan_offset, Position):
            pan_offset = Position(0, 0)
        try:
            return _sr().sector_coords_to_pixels(sector_pos, zoom, pan_offset)
        except TypeError:
            return _sr().sector_coords_to_pixels(sector_pos)

    def draw_boundary(self, dynamic_radius):
        boundary_center = (
            int(SECTOR_CIRCLE_CENTER_IN_PX.x + self.game.sector_pan_offset.x),
            int(SECTOR_CIRCLE_CENTER_IN_PX.y + self.game.sector_pan_offset.y)
        )
        _sr().pygame.draw.circle(self.screen, SECTOR_BORDER_COLOR, boundary_center, int(dynamic_radius), 1)

    def draw_tactical_grid(self):
        """Draws a faint grey tactical grid clipped to the circular sector boundary."""
        radius = SECTOR_CIRCLE_RADIUS_LOGICAL
        spacing = SECTOR_GRID_SPACING
        if spacing <= 0:
            return

        step = int(spacing)
        start_val = -int(radius) + step
        end_val = int(radius)

        for val in range(start_val, end_val, step):
            # Vertical grid line at x = val
            y_max_sq = radius * radius - val * val
            if y_max_sq > 0:
                y_max = math.sqrt(y_max_sq)
                p1 = self.coords_to_pixels(Position(val, -y_max))
                p2 = self.coords_to_pixels(Position(val, y_max))
                _sr().pygame.draw.line(self.screen, SECTOR_GRID_COLOR, (p1.x, p1.y), (p2.x, p2.y), 1)

            # Horizontal grid line at y = val
            x_max_sq = radius * radius - val * val
            if x_max_sq > 0:
                x_max = math.sqrt(x_max_sq)
                p1 = self.coords_to_pixels(Position(-x_max, val))
                p2 = self.coords_to_pixels(Position(x_max, val))
                _sr().pygame.draw.line(self.screen, SECTOR_GRID_COLOR, (p1.x, p1.y), (p2.x, p2.y), 1)

    def is_circle_off_screen(self, center_px, radius_px):
        w, h = self.screen.get_size()
        return (center_px[0] + radius_px < 0 or
                center_px[0] - radius_px > w or
                center_px[1] + radius_px < 0 or
                center_px[1] - radius_px > h)

    def get_cached_circle_surface(self, radius, color):
        radius = max(1, (int(radius) + 1) // 2 * 2)
        if radius <= 0:
            return None
        color_key = (color[0], color[1], color[2], color[3] if len(color) > 3 else 255)
        key = (radius, color_key)
        if key in self.parent._circle_surface_cache:
            return self.parent._circle_surface_cache[key]
        
        if len(self.parent._circle_surface_cache) > 2000:
            self.parent._circle_surface_cache.clear()
            
        surface = _sr().pygame.Surface((radius * 2, radius * 2), _sr().pygame.SRCALPHA)
        _sr().pygame.draw.circle(surface, color, (radius, radius), radius)
        self.parent._circle_surface_cache[key] = surface
        return surface

    def effect_zoom_bucket(self, zoom):
        target_zoom = getattr(self.game, 'sector_target_zoom', zoom)
        is_zooming = (isinstance(target_zoom, (int, float)) and
                      abs(target_zoom - zoom) > 1e-4)
        step = 0.10 if is_zooming else 0.05
        return round(zoom / step) * step

    def compute_visible_scaled_region(self, source, source_center, destination_center, scale):
        screen_width, screen_height = self.screen.get_size()
        source_width, source_height = source.get_size()
        dest_left = destination_center[0] - source_center[0] * scale
        dest_top = destination_center[1] - source_center[1] * scale
        dest_right = dest_left + source_width * scale
        dest_bottom = dest_top + source_height * scale

        visible_left = max(0, int(math.floor(dest_left)))
        visible_top = max(0, int(math.floor(dest_top)))
        visible_right = min(screen_width, int(math.ceil(dest_right)))
        visible_bottom = min(screen_height, int(math.ceil(dest_bottom)))
        if visible_left >= visible_right or visible_top >= visible_bottom:
            return None

        source_left = max(0, int(math.floor((visible_left - dest_left) / scale)))
        source_top = max(0, int(math.floor((visible_top - dest_top) / scale)))
        source_right = min(source_width, int(math.ceil((visible_right - dest_left) / scale)))
        source_bottom = min(source_height, int(math.ceil((visible_bottom - dest_top) / scale)))
        if source_left >= source_right or source_top >= source_bottom:
            return None

        scaled_left = int(math.floor(dest_left + source_left * scale))
        scaled_top = int(math.floor(dest_top + source_top * scale))
        scaled_right = int(math.ceil(dest_left + source_right * scale))
        scaled_bottom = int(math.ceil(dest_top + source_bottom * scale))
        scaled_size = (max(1, scaled_right - scaled_left), max(1, scaled_bottom - scaled_top))
        source_rect = (source_left, source_top, source_right - source_left, source_bottom - source_top)

        return source_rect, (scaled_left, scaled_top), scaled_size

    def blit_visible_scaled_surface(self, source, source_center, destination_center,
                                    scale, cache_prefix, smooth=True):
        region = self.compute_visible_scaled_region(source, source_center, destination_center, scale)
        if region is None:
            return False
        source_rect, (scaled_left, scaled_top), scaled_size = region

        cache_key = (*cache_prefix, source_rect, scaled_size, smooth)

        scaled_surface = self.parent._scaled_effect_surfaces.get(cache_key)
        if scaled_surface is None:
            source_width, source_height = source.get_size()
            source_region = source if source_rect == (0, 0, source_width, source_height) else source.subsurface(source_rect)
            transform_fn = _sr().pygame.transform.smoothscale if smooth else _sr().pygame.transform.scale
            scaled_surface = transform_fn(source_region, scaled_size)
            self.parent._scaled_effect_surfaces.put(cache_key, scaled_surface)

        self.overlay_surface.blit(scaled_surface, (scaled_left, scaled_top))
        return True

    def blit_scaled_surface_once(self, source, source_center, destination_center,
                                  scale, smooth=False):
        region = self.compute_visible_scaled_region(source, source_center, destination_center, scale)
        if region is None:
            return False
        source_rect, (scaled_left, scaled_top), scaled_size = region

        source_width, source_height = source.get_size()
        source_region = source if source_rect == (0, 0, source_width, source_height) else source.subsurface(source_rect)
        transform_fn = _sr().pygame.transform.smoothscale if smooth else _sr().pygame.transform.scale
        scaled_surface = transform_fn(source_region, scaled_size)
        self.overlay_surface.blit(scaled_surface, (scaled_left, scaled_top))
        return True

    def circle_covers_rect(self, center_px, radius_px, rect) -> bool:
        cx, cy = center_px
        radius_sq = radius_px * radius_px
        try:
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
            left, top, right, bottom = int(left), int(top), int(right), int(bottom)
        except (AttributeError, TypeError, ValueError):
            try:
                left, top, right, bottom = int(rect[0]), int(rect[1]), int(rect[0] + rect[2]), int(rect[1] + rect[3])
            except (IndexError, TypeError, ValueError):
                return False

        corners = (
            (left, top),
            (right, top),
            (left, bottom),
            (right, bottom),
        )
        for corner_x, corner_y in corners:
            if (corner_x - cx) ** 2 + (corner_y - cy) ** 2 > radius_sq:
                return False
        return True

    def circle_covers_viewport(self, center_px, radius_px):
        try:
            w, h = self.screen.get_size()
            w, h = int(w), int(h)
        except (TypeError, ValueError):
            w, h = 1920, 1080
        return self.circle_covers_rect(center_px, radius_px, _sr().pygame.Rect(0, 0, w, h))

    def fill_circle_on_surface(self, surface, center_px, radius_px, rgba, clip_rect) -> bool:
        cx, cy = center_px
        radius_px = max(1, min(int(radius_px), MAX_SAFE_CIRCLE_RADIUS_PX))

        circle_bbox = _sr().pygame.Rect(cx - radius_px, cy - radius_px, 2 * radius_px, 2 * radius_px)
        vis_rect = circle_bbox.clip(clip_rect)
        if vis_rect.width <= 0 or vis_rect.height <= 0:
            return False

        if self.circle_covers_rect((cx, cy), radius_px, vis_rect):
            surface.fill(rgba, vis_rect)
            return True

        old_clip = surface.get_clip()
        surface.set_clip(vis_rect)
        _sr().pygame.draw.circle(surface, rgba, (cx, cy), radius_px)
        surface.set_clip(old_clip)
        return True

    def fill_circle_clipped(self, center_px, radius_px, rgba):
        screen_width, screen_height = self.screen.get_size()
        cx, cy = center_px
        radius_px = max(1, min(int(radius_px), MAX_SAFE_CIRCLE_RADIUS_PX))

        circle_bbox = _sr().pygame.Rect(cx - radius_px, cy - radius_px, 2 * radius_px, 2 * radius_px)
        rect = circle_bbox.clip(self.screen.get_rect())
        if rect.width <= 0 or rect.height <= 0:
            return

        if (self.parent._range_circle_surface is None or
                self.parent._range_circle_surface.get_size() != (screen_width, screen_height)):
            self.parent._range_circle_surface = _sr().pygame.Surface((screen_width, screen_height), _sr().pygame.SRCALPHA)
        surf = self.parent._range_circle_surface

        surf.fill((0, 0, 0, 0), rect)
        self.fill_circle_on_surface(surf, (cx, cy), radius_px, rgba, rect)

        self.overlay_surface.blit(surf, rect.topleft, area=rect)
        self.parent.zoom_render_stats['range_circle_fills'] += 1

    def blit_uncached_circle(self, circle_pos, radius_px, color):
        self.fill_circle_clipped(circle_pos, radius_px, color)

    def draw_range_ring(self, cx, cy, radius_px, outline_rgb):
        if radius_px <= 1 or self.is_circle_off_screen((cx, cy), radius_px):
            return

        if not self.circle_covers_viewport((cx, cy), radius_px):
            _sr().pygame.draw.circle(self.overlay_surface, outline_rgb, (cx, cy), radius_px, 2)

    def update_zoom_render_stats(self):
        self.parent.zoom_render_stats = {
            'cache_hits': self.parent._scaled_effect_surfaces.hits,
            'cache_misses': self.parent._scaled_effect_surfaces.misses,
            'cache_bytes': self.parent._scaled_effect_surfaces.total_bytes,
            'direct_draw_fallbacks': self.parent.zoom_render_stats.get('direct_draw_fallbacks', 0),
            'range_circle_fills': self.parent.zoom_render_stats.get('range_circle_fills', 0),
            'fog_rebuilds': self.parent.zoom_render_stats.get('fog_rebuilds', 0),
            'fog_cache_hits': self.parent.zoom_render_stats.get('fog_cache_hits', 0),
            'fog_full_reveal': self.parent.zoom_render_stats.get('fog_full_reveal', 0),
        }
