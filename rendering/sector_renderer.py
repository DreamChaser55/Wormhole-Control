import pygame
import math
from collections import OrderedDict
from constants import (
    NEBULA_COLORS, SECTOR_CIRCLE_CENTER_IN_PX, SECTOR_CIRCLE_RADIUS_IN_PX,
    SECTOR_CIRCLE_RADIUS_LOGICAL, SECTOR_BORDER_COLOR,
    STAR_RADIUS, PLANET_RADIUS, WORMHOLE_RADIUS, NEBULA_RADIUS, STORM_RADIUS,
    STORM_LIGHTNING_COLOR, STORM_COMPOSE_MAX_DIAMETER,
    WHITE, YELLOW, CYAN, PURPLE, RED,
    HULL_BASE_ICON_SCALES, HULL_DOT_COUNTS, SECTOR_VIEW_BASE_ICON_SIZE,
    ICON_DOT_RADIUS, ICON_DOT_SPACING,
    HOVER_HIGHLIGHT_COLOR, SELECTION_HIGHLIGHT_COLOR,
    MOVE_ORDER_LINE_COLOR, WORMHOLE_JUMP_ORDER_COLOR, STORM_COLORS,
    TEXT_SCALE, XP_SPEED_BONUS,
    MOON_RADIUS, ASTEROID_RADIUS, COMET_RADIUS, CELESTIAL_FIELD_RADIUS
)

from sector_utils import sector_coords_to_pixels
from geometry import distance, Position
import random
from entities import (
    Star, Planet, Wormhole, Unit, OrderType, OrderStatus, Moon, Asteroid, 
    AsteroidField, IceField, Nebula, Storm, Comet, StarType, PlanetType, DebrisField
)
from rendering.drawing_utils import draw_shape

MAX_CACHED_STORM_DIAMETER = 512


class _BoundedSurfaceCache:
    """An LRU cache that bounds both the number and size of cached textures."""

    def __init__(self, max_bytes=96 * 1024 * 1024, max_item_bytes=16 * 1024 * 1024):
        self.max_bytes = max_bytes
        self.max_item_bytes = max_item_bytes
        self._items = OrderedDict()
        self.total_bytes = 0
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _surface_bytes(surface):
        return surface.get_width() * surface.get_height() * 4

    def get(self, key):
        surface = self._items.pop(key, None)
        if surface is None:
            self.misses += 1
            return None
        self.hits += 1
        self._items[key] = surface
        return surface

    def put(self, key, surface):
        surface_bytes = self._surface_bytes(surface)
        if surface_bytes > self.max_item_bytes:
            return surface

        old_surface = self._items.pop(key, None)
        if old_surface is not None:
            self.total_bytes -= self._surface_bytes(old_surface)

        while self._items and self.total_bytes + surface_bytes > self.max_bytes:
            _, evicted_surface = self._items.popitem(last=False)
            self.total_bytes -= self._surface_bytes(evicted_surface)

        if self.total_bytes + surface_bytes <= self.max_bytes:
            self._items[key] = surface
            self.total_bytes += surface_bytes
        return surface

    def clear(self):
        self._items.clear()
        self.total_bytes = 0


class SectorViewRenderer:
    def __init__(self, game_instance):
        self.game = game_instance
        self.screen = game_instance.screen
        self.overlay_surface = game_instance.overlay_surface
        self._font_cache = {}
        self._circle_surface_cache = {}
        self._nebula_master_surfaces = {}
        self._storm_base_circle_surfaces = {}
        self._last_cached_sector = None
        self._scaled_effect_surfaces = _BoundedSurfaceCache()
        self._inhibition_surface = None
        self._storm_scratch_surface = None
        self.zoom_render_stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'cache_bytes': 0,
            'direct_draw_fallbacks': 0,
        }

    def _is_circle_off_screen(self, center_px, radius_px):
        w, h = self.screen.get_size()
        return (center_px[0] + radius_px < 0 or
                center_px[0] - radius_px > w or
                center_px[1] + radius_px < 0 or
                center_px[1] - radius_px > h)

    def _get_cached_circle_surface(self, radius, color):
        # Round to the nearest 2 pixels so that adjacent zoom-animation steps
        # share the same cache entry instead of generating a new Surface every frame.
        radius = max(1, (int(radius) + 1) // 2 * 2)
        if radius <= 0:
            return None
        # Convert color to tuple to make it hashable if it is a pygame.Color
        color_key = (color[0], color[1], color[2], color[3] if len(color) > 3 else 255)
        key = (radius, color_key)
        if key in self._circle_surface_cache:
            return self._circle_surface_cache[key]
        
        if len(self._circle_surface_cache) > 2000:
            self._circle_surface_cache.clear()
            
        surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(surface, color, (radius, radius), radius)
        self._circle_surface_cache[key] = surface
        return surface


    def _coords_to_pixels(self, sector_pos):
        zoom = self.game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0
        pan_offset = self.game.sector_pan_offset
        if not isinstance(pan_offset, Position):
            pan_offset = Position(0, 0)
        try:
            return sector_coords_to_pixels(sector_pos, zoom, pan_offset)
        except TypeError:
            return sector_coords_to_pixels(sector_pos)

    def _effect_zoom_bucket(self, zoom):
        """Use fewer resampling steps while the camera is actively moving."""
        target_zoom = getattr(self.game, 'sector_target_zoom', zoom)
        is_zooming = (isinstance(target_zoom, (int, float)) and
                      abs(target_zoom - zoom) > 1e-4)
        step = 0.10 if is_zooming else 0.05
        return round(zoom / step) * step

    def _compute_visible_scaled_region(self, source, source_center, destination_center, scale):
        """Shared clipping math used by both the cached and uncached scaling
        paths: computes the on-screen destination rect actually visible, and
        the corresponding source sub-rect, so callers never need to transform
        more of ``source`` than what will actually be blitted.

        Returns ``None`` when nothing is visible, otherwise a tuple of
        ``(source_rect, (scaled_left, scaled_top), scaled_size)``.
        """
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

    def _blit_visible_scaled_surface(self, source, source_center, destination_center,
                                     scale, cache_prefix, smooth=True):
        """Scale and cache only the portion of an effect visible on screen.

        Scaling a full high-zoom nebula can otherwise create a many-hundred-MiB
        intermediate texture even though only a viewport-sized part is visible.

        ``smooth`` selects between ``pygame.transform.smoothscale`` (higher
        quality, slower) and ``pygame.transform.scale`` (nearest-neighbour,
        much faster). It is folded into the cache key so a fast-scaled frame
        is never returned when a smooth one was requested, or vice versa.
        """
        region = self._compute_visible_scaled_region(source, source_center, destination_center, scale)
        if region is None:
            return False
        source_rect, (scaled_left, scaled_top), scaled_size = region

        cache_key = (*cache_prefix, source_rect, scaled_size, smooth)

        scaled_surface = self._scaled_effect_surfaces.get(cache_key)
        if scaled_surface is None:
            source_width, source_height = source.get_size()
            source_region = source if source_rect == (0, 0, source_width, source_height) else source.subsurface(source_rect)
            transform_fn = pygame.transform.smoothscale if smooth else pygame.transform.scale
            scaled_surface = transform_fn(source_region, scaled_size)
            self._scaled_effect_surfaces.put(cache_key, scaled_surface)

        self.overlay_surface.blit(scaled_surface, (scaled_left, scaled_top))
        return True

    def _blit_scaled_surface_once(self, source, source_center, destination_center,
                                   scale, smooth=False):
        """Scale and blit the visible portion of ``source`` exactly once, with
        no caching.

        This is used for content that changes every frame (e.g. a storm's
        composited particle canvas). Caching a scaled result that will never
        be reused again next frame would just add bookkeeping overhead while
        still returning nothing but cache misses.
        """
        region = self._compute_visible_scaled_region(source, source_center, destination_center, scale)
        if region is None:
            return False
        source_rect, (scaled_left, scaled_top), scaled_size = region

        source_width, source_height = source.get_size()
        source_region = source if source_rect == (0, 0, source_width, source_height) else source.subsurface(source_rect)
        transform_fn = pygame.transform.smoothscale if smooth else pygame.transform.scale
        scaled_surface = transform_fn(source_region, scaled_size)
        self.overlay_surface.blit(scaled_surface, (scaled_left, scaled_top))
        return True


    def _blit_uncached_circle(self, circle_pos, radius_px, color):
        """Draw a large semi-transparent circle onto the overlay using the same
        source-over alpha blending as the cached/scaled path, without caching a
        huge texture.

        Drawing directly onto ``overlay_surface`` with ``pygame.draw.circle``
        *replaces* pixels instead of alpha-blending them, which both prevents
        overlapping particles from accumulating alpha with each other and
        erases any alpha already accumulated underneath by other (smaller,
        blitted) particles. That mismatch is what made storm circles lose
        their intended transparency once they grew large enough to hit this
        fallback (i.e. when zoomed in). Rendering into a small temporary
        per-pixel-alpha surface and then blitting it keeps the compositing
        identical to the normal path while still only ever allocating an
        on-screen-sized surface.
        """
        screen_width, screen_height = self.screen.get_size()
        cx, cy = circle_pos

        vis_left = max(0, int(math.floor(cx - radius_px)))
        vis_top = max(0, int(math.floor(cy - radius_px)))
        vis_right = min(screen_width, int(math.ceil(cx + radius_px)))
        vis_bottom = min(screen_height, int(math.ceil(cy + radius_px)))
        if vis_left >= vis_right or vis_top >= vis_bottom:
            return

        temp_surface = pygame.Surface((vis_right - vis_left, vis_bottom - vis_top), pygame.SRCALPHA)
        local_center = (int(cx - vis_left), int(cy - vis_top))
        pygame.draw.circle(temp_surface, color, local_center, radius_px)
        self.overlay_surface.blit(temp_surface, (vis_left, vis_top))

    def _update_zoom_render_stats(self):

        self.zoom_render_stats = {
            'cache_hits': self._scaled_effect_surfaces.hits,
            'cache_misses': self._scaled_effect_surfaces.misses,
            'cache_bytes': self._scaled_effect_surfaces.total_bytes,
            'direct_draw_fallbacks': self.zoom_render_stats['direct_draw_fallbacks'],
        }

    def draw_sector_view(self):
        """Draws the detailed view of the current sector hex."""
        if not self.game.current_system_name or self.game.current_sector_coord is None: return
        system = self.game.galaxy.systems[self.game.current_system_name]
        if not system: return

        # Clear cached surfaces if the sector has changed
        current_sector_key = (self.game.current_system_name, self.game.current_sector_coord)
        if current_sector_key != self._last_cached_sector:
            self._nebula_master_surfaces.clear()
            self._storm_base_circle_surfaces.clear()
            self._scaled_effect_surfaces.clear()
            self._last_cached_sector = current_sector_key

        zoom = self.game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0
        dynamic_radius = SECTOR_CIRCLE_RADIUS_IN_PX * zoom

        # 1. Draw Selection Box (if dragging)
        if self.game.is_dragging_selection_box and self.game.selection_box_start_pos:
            mouse_pos = pygame.mouse.get_pos()
            start_pos = self.game.selection_box_start_pos.to_tuple()
            
            rect_x = min(start_pos[0], mouse_pos[0])
            rect_y = min(start_pos[1], mouse_pos[1])
            rect_w = abs(start_pos[0] - mouse_pos[0])
            rect_h = abs(start_pos[1] - mouse_pos[1])
            selection_rect = pygame.Rect(rect_x, rect_y, rect_w, rect_h)

            selection_surface = pygame.Surface(selection_rect.size, pygame.SRCALPHA)
            selection_surface.fill((0, 100, 255, 64))
            self.overlay_surface.blit(selection_surface, selection_rect.topleft)

            pygame.draw.rect(self.overlay_surface, (0, 150, 255), selection_rect, 1)

        # 1. Draw Sector Boundary
        boundary_center = (
            int(SECTOR_CIRCLE_CENTER_IN_PX.x + self.game.sector_pan_offset.x),
            int(SECTOR_CIRCLE_CENTER_IN_PX.y + self.game.sector_pan_offset.y)
        )
        pygame.draw.circle(self.screen, SECTOR_BORDER_COLOR, boundary_center, int(dynamic_radius), 1)

        # 2. Draw Inhibition Fields. Draw directly into a viewport-sized alpha
        # surface instead of scaling and retaining a massive circle texture.
        hex_obj = system.hexes[self.game.current_sector_coord]
        if hex_obj:
            screen_size = self.screen.get_size()
            if self._inhibition_surface is None or self._inhibition_surface.get_size() != screen_size:
                self._inhibition_surface = pygame.Surface(screen_size, pygame.SRCALPHA)
            self._inhibition_surface.fill((0, 0, 0, 0))
            drew_inhibition_zone = False
            for zone in hex_obj.get_all_inhibition_zones():
                zone_pixel_center = self._coords_to_pixels(zone.center)
                zone_pixel_radius = int(zone.radius * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)

                if zone_pixel_radius <= 0:
                    continue
                if self._is_circle_off_screen((zone_pixel_center.x, zone_pixel_center.y), zone_pixel_radius):
                    continue

                pygame.draw.circle(
                    self._inhibition_surface, (255, 0, 0, 50),
                    (int(zone_pixel_center.x), int(zone_pixel_center.y)), zone_pixel_radius
                )
                drew_inhibition_zone = True
                self.zoom_render_stats['direct_draw_fallbacks'] += 1
            if drew_inhibition_zone:
                self.screen.blit(self._inhibition_surface, (0, 0))

        # 3. Get Objects in the Current Hex
        hex_obj = system.hexes[self.game.current_sector_coord]
        bodies_to_draw = []
        units_to_draw = []
        if hex_obj:
            bodies_to_draw = hex_obj.celestial_bodies
            units_to_draw = hex_obj.units
        
        all_objects_in_sector = bodies_to_draw + units_to_draw

        for obj in all_objects_in_sector:
            obj_pixel_pos = self._coords_to_pixels(obj.position) 
            obj_radius_logical = 13.89 # Default logical radius (equivalent to 5 pixels)
            obj_color = WHITE 

            should_draw_circle = True
            if isinstance(obj, Star):
                star_color_map = {
                    StarType.BLUE_GIANT: (173, 216, 255),
                    StarType.YELLOW_GIANT: YELLOW,
                    StarType.RED_DWARF: (255, 127, 80),
                    StarType.NEUTRON_STAR: WHITE,
                }
                obj_color = star_color_map.get(obj.star_type, YELLOW)
                obj_radius_logical = STAR_RADIUS
            elif isinstance(obj, Planet):
                planet_color_map = {
                    PlanetType.TERRAN: (0, 128, 0),
                    PlanetType.DESERT: (210, 180, 140),
                    PlanetType.VOLCANIC: (255, 69, 0),
                    PlanetType.ICE: (173, 216, 230),
                    PlanetType.BARREN: (128, 128, 128),
                    PlanetType.FERROUS: (165, 42, 42),
                    PlanetType.GREENHOUSE: (0, 255, 0),
                    PlanetType.OCEANIC: (0, 0, 205),
                    PlanetType.GAS_GIANT: (255, 228, 181),
                }
                obj_color = planet_color_map.get(obj.planet_type, CYAN)
                obj_radius_logical = PLANET_RADIUS
                if obj.owner:
                    pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    pygame.draw.circle(self.screen, obj.owner.color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)
            elif isinstance(obj, Moon):
                obj_color = (200, 200, 200)
                obj_radius_logical = MOON_RADIUS
                if obj.owner:
                    pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    pygame.draw.circle(self.screen, obj.owner.color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)
            elif isinstance(obj, Asteroid):
                obj_color = (90, 60, 50)
                obj_radius_logical = ASTEROID_RADIUS
                if obj.owner:
                    pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    pygame.draw.circle(self.screen, obj.owner.color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)
            elif isinstance(obj, AsteroidField):
                self._draw_celestial_field(obj, obj_pixel_pos, (100, 100, 100))
                obj_radius_logical = CELESTIAL_FIELD_RADIUS
                should_draw_circle = False
            elif isinstance(obj, IceField):
                self._draw_celestial_field(obj, obj_pixel_pos, (173, 216, 230), num_particles=20)
                obj_radius_logical = CELESTIAL_FIELD_RADIUS
                should_draw_circle = False
            elif isinstance(obj, DebrisField):
                self._draw_celestial_field(obj, obj_pixel_pos, (112, 128, 144), num_particles=15)
                obj_radius_logical = CELESTIAL_FIELD_RADIUS
                should_draw_circle = False
            elif isinstance(obj, Nebula):
                self._draw_nebula(obj, obj_pixel_pos)
                should_draw_circle = False
            elif isinstance(obj, Storm):
                self._draw_storm(obj, obj_pixel_pos)
                should_draw_circle = False
            elif isinstance(obj, Comet):
                obj_color = CYAN
                obj_radius_logical = COMET_RADIUS
            elif isinstance(obj, Wormhole):
                obj_radius_logical = WORMHOLE_RADIUS
                obj_color = PURPLE
                if obj.stability < 100:
                    pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    pygame.draw.circle(self.screen, RED, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 2, 1)
 
            if should_draw_circle and not isinstance(obj, Unit):
                pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                pygame.draw.circle(self.screen, obj_color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius)
            elif isinstance(obj, Unit):
                unit_obj: Unit = obj
                obj_color = unit_obj.owner.color if unit_obj.owner else WHITE
 
                if unit_obj.hull_size.name == "STRIKECRAFT_WING":
                    shape_type = 'strikecraft_wing'
                else:
                    shape_type = 'triangle' if unit_obj.engines_component else 'square'
                scale_factor = HULL_BASE_ICON_SCALES[unit_obj.hull_size]
                current_icon_base_size_logical = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
                dot_count = HULL_DOT_COUNTS[unit_obj.hull_size]
                
                current_icon_base_size_px = int(current_icon_base_size_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                obj_radius_logical = current_icon_base_size_logical
 
                draw_shape(self.screen, shape_type, obj_color, obj_pixel_pos, current_icon_base_size_px)
 
                if unit_obj in self.game.selected_objects and unit_obj.max_hit_points > 0:
                    health_bar_width = current_icon_base_size_px * 2
                    health_bar_height = 4
                    health_bar_y_offset = current_icon_base_size_px + 10
                    
                    health_percentage = unit_obj.current_hit_points / unit_obj.max_hit_points
                    
                    health_bar_x = obj_pixel_pos.x - health_bar_width / 2
                    health_bar_y = obj_pixel_pos.y + health_bar_y_offset
                    
                    pygame.draw.rect(self.screen, (50, 50, 50), (health_bar_x, health_bar_y, health_bar_width, health_bar_height))
                    
                    health_color = (0, 255, 0) if health_percentage > 0.5 else (255, 255, 0) if health_percentage > 0.2 else (255, 0, 0)
                    pygame.draw.rect(self.screen, health_color, (health_bar_x, health_bar_y, health_bar_width * health_percentage, health_bar_height))
 
                if dot_count > 0:
                    icon_dot_radius_px = int(ICON_DOT_RADIUS * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    icon_dot_spacing_px = int(ICON_DOT_SPACING * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    
                    dot_base_y_offset = current_icon_base_size_px * 0.6
                    if shape_type == 'square':
                        dot_base_y_offset = current_icon_base_size_px
                    
                    dot_base_y = obj_pixel_pos.y + dot_base_y_offset + icon_dot_radius_px + 2

                    if shape_type == 'triangle':
                        base_p2_x = obj_pixel_pos.x - int(current_icon_base_size_px * 0.8)
                        base_p3_x = obj_pixel_pos.x + int(current_icon_base_size_px * 0.8)
                        base_width = base_p3_x - base_p2_x
                        start_x = base_p2_x + (base_width - (dot_count - 1) * icon_dot_spacing_px) / 2
                    else: # Square
                        base_p_left_x = obj_pixel_pos.x - current_icon_base_size_px
                        base_p_right_x = obj_pixel_pos.x + current_icon_base_size_px
                        base_width = base_p_right_x - base_p_left_x
                        start_x = base_p_left_x + (base_width - (dot_count - 1) * icon_dot_spacing_px) / 2

                    for dot_i in range(dot_count):
                        dot_x = start_x + dot_i * icon_dot_spacing_px
                        pygame.draw.circle(self.screen, obj_color, (dot_x, dot_base_y), icon_dot_radius_px)

                # Draw Unit Name
                bottom_y = obj_pixel_pos.y + current_icon_base_size_px
                
                # If health bar is drawn, account for its height and vertical position.
                # To prevent the unit name text from moving when selected, we always reserve space 
                # for the health bar if the unit can have one (i.e. max_hit_points > 0).
                if unit_obj.max_hit_points > 0:
                    health_bar_bottom = obj_pixel_pos.y + current_icon_base_size_px + 14
                    if health_bar_bottom > bottom_y:
                        bottom_y = health_bar_bottom
                        
                # If dots are drawn, account for their radius and vertical position
                if dot_count > 0:
                    icon_dot_radius_px = int(ICON_DOT_RADIUS * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    dot_base_y_offset = current_icon_base_size_px * 0.6 if shape_type == 'triangle' else current_icon_base_size_px
                    dot_bottom = obj_pixel_pos.y + dot_base_y_offset + 2 * icon_dot_radius_px + 2
                    if dot_bottom > bottom_y:
                        bottom_y = dot_bottom
                        
                name_font_size = max(1, int(12 * TEXT_SCALE))
                if name_font_size not in self._font_cache:
                    self._font_cache[name_font_size] = pygame.font.Font(None, name_font_size)
                name_font = self._font_cache[name_font_size]
                name_surface = name_font.render(unit_obj.name, True, obj_color)
                name_rect = name_surface.get_rect()
                name_rect.midtop = (obj_pixel_pos.x, bottom_y + 4)
                self.screen.blit(name_surface, name_rect)


            if obj == self.game.sector_view_mouse_hover_object:
                pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                pygame.draw.circle(self.overlay_surface, HOVER_HIGHLIGHT_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)

            if obj in self.game.selected_objects:
                pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                # Draw four selection brackets in the corners
                r = pixel_radius + 5
                tick_length = 10
                
                left = obj_pixel_pos.x - r
                right = obj_pixel_pos.x + r
                top = obj_pixel_pos.y - r
                bottom = obj_pixel_pos.y + r
                
                # Top-Left corner bracket
                pygame.draw.lines(
                    self.overlay_surface,
                    SELECTION_HIGHLIGHT_COLOR,
                    False,
                    [(left + tick_length, top), (left, top), (left, top + tick_length)],
                    2
                )
                # Top-Right corner bracket
                pygame.draw.lines(
                    self.overlay_surface,
                    SELECTION_HIGHLIGHT_COLOR,
                    False,
                    [(right - tick_length, top), (right, top), (right, top + tick_length)],
                    2
                )
                # Bottom-Left corner bracket
                pygame.draw.lines(
                    self.overlay_surface,
                    SELECTION_HIGHLIGHT_COLOR,
                    False,
                    [(left + tick_length, bottom), (left, bottom), (left, bottom - tick_length)],
                    2
                )
                # Bottom-Right corner bracket
                pygame.draw.lines(
                    self.overlay_surface,
                    SELECTION_HIGHLIGHT_COLOR,
                    False,
                    [(right - tick_length, bottom), (right, bottom), (right, bottom - tick_length)],
                    2
                )

            if isinstance(obj, Unit):
                unit_obj: Unit = obj
                is_turn_player_unit = self.game.players and unit_obj.owner == self.game.players[self.game.current_player_index]
                is_selected_or_hovered = unit_obj in self.game.selected_objects or unit_obj == self.game.sector_view_mouse_hover_object

                if is_turn_player_unit:
                    if unit_obj.engines_component and unit_obj.engines_component.move_target:
                        target_pos_in_sector = unit_obj.engines_component.move_target
                        target_pixel_pos = self._coords_to_pixels(target_pos_in_sector)
                        pygame.draw.line(self.overlay_surface, MOVE_ORDER_LINE_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), (target_pixel_pos.x, target_pixel_pos.y), 1)
                        pygame.draw.circle(self.overlay_surface, MOVE_ORDER_LINE_COLOR, (target_pixel_pos.x, target_pixel_pos.y), 3)
                        
                        mock_wp = {
                            'order_type': OrderType.MOVE,
                            'is_current': True,
                            'position': target_pos_in_sector
                        }
                        effective_speed = unit_obj.engines_component.speed * unit_obj.xp_multiplier(XP_SPEED_BONUS)
                        self._draw_path_turn_notches_for_segment([mock_wp], True, unit_obj.position, effective_speed)
                    elif unit_obj.hyperdrive_component and unit_obj.hyperdrive_component.wormhole_jump_target:
                        target_wh_for_jump = unit_obj.hyperdrive_component.wormhole_jump_target
                        if target_wh_for_jump.in_system == self.game.current_system_name and target_wh_for_jump.in_hex == self.game.current_sector_coord:
                            wh_pixel_pos = self._coords_to_pixels(target_wh_for_jump.position)
                            pygame.draw.line(self.overlay_surface, WORMHOLE_JUMP_ORDER_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), (wh_pixel_pos.x, wh_pixel_pos.y), 2)
                            wh_pixel_radius = int(WORMHOLE_RADIUS * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                            pygame.draw.circle(self.overlay_surface, WORMHOLE_JUMP_ORDER_COLOR, (wh_pixel_pos.x, wh_pixel_pos.y), wh_pixel_radius + 4, 1)
                    elif unit_obj.commander_component and unit_obj.commander_component.current_order:
                        order = unit_obj.commander_component.current_order
                        if order.order_type == OrderType.MOVE and order.status in [OrderStatus.PENDING, OrderStatus.IN_PROGRESS]:
                            dest_sys = order.parameters["destination_system_name"]
                            dest_hex = order.parameters["destination_hex_coord"]
                            dest_pos = order.parameters["destination_position"]

                            if dest_sys == self.game.current_system_name and dest_hex == self.game.current_sector_coord and dest_pos:
                                target_pixel_pos = self._coords_to_pixels(dest_pos)
                                pygame.draw.line(self.overlay_surface, MOVE_ORDER_LINE_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), (target_pixel_pos.x, target_pixel_pos.y), 1)
                                pygame.draw.circle(self.overlay_surface, MOVE_ORDER_LINE_COLOR, (target_pixel_pos.x, target_pixel_pos.y), 3)
                                
                                if unit_obj.engines_component:
                                    mock_wp = {
                                        'order_type': OrderType.MOVE,
                                        'is_current': True,
                                        'position': dest_pos
                                    }
                                    effective_speed = unit_obj.engines_component.speed * unit_obj.xp_multiplier(XP_SPEED_BONUS)
                                    self._draw_path_turn_notches_for_segment([mock_wp], True, unit_obj.position, effective_speed)
                            elif dest_sys != self.game.current_system_name:
                                if unit_obj.in_galaxy:
                                    local_wh_for_jump = order.find_wormhole_to_system(unit_obj.in_system, dest_sys, unit_obj.in_galaxy, unit_obj.hull_size)
                                    if local_wh_for_jump and local_wh_for_jump.in_system == self.game.current_system_name and local_wh_for_jump.in_hex == self.game.current_sector_coord:
                                        wh_pixel_pos = self._coords_to_pixels(local_wh_for_jump.position)
                                        pygame.draw.line(self.overlay_surface, WORMHOLE_JUMP_ORDER_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), (wh_pixel_pos.x, wh_pixel_pos.y), 2)
                                        wh_pixel_radius = int(WORMHOLE_RADIUS * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                                        pygame.draw.circle(self.overlay_surface, WORMHOLE_JUMP_ORDER_COLOR, (wh_pixel_pos.x, wh_pixel_pos.y), wh_pixel_radius + 4, 1)
                    if unit_obj.commander_component:
                        self._draw_sector_view_order_lines(unit_obj, obj_pixel_pos.x, obj_pixel_pos.y)
                                
        # Collect external units targeting this sector:
        # 1. Any selected unit (regardless of owner) that is in another sector but targeting this one
        # 2. Any unit belonging to the current turn player that is in another sector but targeting this one
        current_turn_player = self.game.players[self.game.current_player_index] if self.game.players else None
        candidate_units = set()
        if current_turn_player:
            for obj in self.game.selected_objects:
                if isinstance(obj, Unit) and obj.owner == current_turn_player:
                    candidate_units.add(obj)
            if self.game.galaxy:
                for system in self.game.galaxy.systems.values():
                    for hex_obj in system.hexes.values():
                        for unit in hex_obj.units:
                            if unit.owner == current_turn_player:
                                candidate_units.add(unit)

        external_units_with_orders_to_this_sector = []
        for candidate_unit in candidate_units:
            if isinstance(candidate_unit, Unit):
                is_external_unit = (
                    candidate_unit.in_system != self.game.current_system_name or
                    candidate_unit.in_hex != self.game.current_sector_coord
                )
                if is_external_unit and candidate_unit.commander_component:
                    has_orders_to_current_sector = False
                    if candidate_unit.commander_component.current_order:
                        order = candidate_unit.commander_component.current_order
                        if self._order_targets_sector(order, self.game.current_system_name, self.game.current_sector_coord):
                            has_orders_to_current_sector = True
                        for sub_order in order.sub_orders:
                            if self._order_targets_sector(sub_order, self.game.current_system_name, self.game.current_sector_coord):
                                has_orders_to_current_sector = True
                                break
                    if not has_orders_to_current_sector:
                        for queued_order in candidate_unit.commander_component.orders_queue:
                            if self._order_targets_sector(queued_order, self.game.current_system_name, self.game.current_sector_coord):
                                has_orders_to_current_sector = True
                                break
                            for sub_order in queued_order.sub_orders:
                                if self._order_targets_sector(sub_order, self.game.current_system_name, self.game.current_sector_coord):
                                    has_orders_to_current_sector = True
                                    break
                            if has_orders_to_current_sector:
                                break
                    if has_orders_to_current_sector:
                        external_units_with_orders_to_this_sector.append(candidate_unit)

        self._draw_sector_view_order_lines_from_other_sectors(external_units_with_orders_to_this_sector)
        self._update_zoom_render_stats()

    def _get_waypoint_style(self, waypoint):
        if waypoint['order_type'] == OrderType.ATTACK:
            line_color = RED
            line_width = 2
        elif waypoint['order_type'] == OrderType.PROTECT:
            line_color = (255, 105, 180)
            line_width = 2
        elif waypoint['order_type'] == OrderType.USE_ABILITY:
            line_color = (255, 105, 180)  # Hot Pink
            line_width = 2
        elif waypoint['is_current']:
            line_width = 2
            line_color = MOVE_ORDER_LINE_COLOR
        else:
            line_width = 1
            line_color = (max(MOVE_ORDER_LINE_COLOR[0] - 40, 0), 
                         max(MOVE_ORDER_LINE_COLOR[1] - 40, 0), 
                         max(MOVE_ORDER_LINE_COLOR[2] - 40, 0))
        return line_color, line_width

    def _draw_single_notch(self, p_start, p_end, p_notch, color, line_width):
        start_px = self._coords_to_pixels(p_start)
        end_px = self._coords_to_pixels(p_end)
        notch_px = self._coords_to_pixels(p_notch)
        
        dx = end_px.x - start_px.x
        dy = end_px.y - start_px.y
        dist = math.sqrt(dx*dx + dy*dy)
        if dist > 0:
            nx = -dy / dist
            ny = dx / dist
            
            notch_half_len = 4
            x1 = int(notch_px.x + nx * notch_half_len)
            y1 = int(notch_px.y + ny * notch_half_len)
            x2 = int(notch_px.x - nx * notch_half_len)
            y2 = int(notch_px.y - ny * notch_half_len)
            
            pygame.draw.line(self.overlay_surface, color, (x1, y1), (x2, y2), max(2, line_width))

    def _draw_path_turn_notches_for_segment(self, segment, connect_to_unit, start_pos, effective_speed):
        if effective_speed <= 0 or not segment:
            return
            
        segment_points = []
        segment_wps = []
        
        if connect_to_unit:
            segment_points.append(start_pos)
            for wp in segment:
                segment_points.append(wp['position'])
                segment_wps.append(wp)
        else:
            if len(segment) < 2:
                return
            for wp in segment:
                segment_points.append(wp['position'])
            for wp in segment[1:]:
                segment_wps.append(wp)
                
        current_idx = 0
        p_curr = segment_points[0]
        dist_to_next_notch = effective_speed
        
        while current_idx < len(segment_points) - 1:
            p_next = segment_points[current_idx + 1]
            wp = segment_wps[current_idx]
            segment_len = distance(p_curr, p_next)
            
            if segment_len <= 0:
                current_idx += 1
                p_curr = p_next
                continue
                
            if dist_to_next_notch <= segment_len:
                t = dist_to_next_notch / segment_len
                p_notch = Position(
                    p_curr.x + (p_next.x - p_curr.x) * t,
                    p_curr.y + (p_next.y - p_curr.y) * t
                )
                
                color, width = self._get_waypoint_style(wp)
                self._draw_single_notch(p_curr, p_next, p_notch, color, width)
                
                p_curr = p_notch
                dist_to_next_notch = effective_speed
            else:
                dist_to_next_notch -= segment_len
                current_idx += 1
                p_curr = p_next

    def _order_targets_sector(self, order, system_name, hex_coord):
        """Helper method to check if an order targets the specified system and hex."""
        if order.order_type in [OrderType.MOVE, OrderType.REACH_WAYPOINT]:
            dsys = order.parameters.get("destination_system_name")
            dhex = order.parameters.get("destination_hex_coord")
            return dsys == system_name and dhex == hex_coord
        elif order.order_type == OrderType.USE_ABILITY:
            target_unit_id = order.parameters.get("target_unit_id")
            target_position = order.parameters.get("target_position")
            if target_unit_id:
                target_unit = self.game.galaxy.get_unit_by_id(target_unit_id)
                if target_unit:
                    return target_unit.in_system == system_name and target_unit.in_hex == hex_coord
            elif target_position:
                dsys = order.parameters.get("target_system_name") or order.unit.in_system
                dhex = order.parameters.get("target_hex_coord") or order.unit.in_hex
                return dsys == system_name and dhex == hex_coord
        return False
        
    def _collect_waypoints_from_order(self, order, unit, all_waypoints_sequence, is_current=False):
        """Helper method to collect waypoints from a single order and its sub-orders."""
        if order.order_type in [OrderType.MOVE, OrderType.REACH_WAYPOINT]:
            dsys = order.parameters["destination_system_name"]
            dhex = order.parameters["destination_hex_coord"]
            dpos = order.parameters["destination_position"]
            
            sequence_index = len(all_waypoints_sequence)
            all_waypoints_sequence.append({
                'position': dpos,
                'system': dsys,
                'hex': dhex,
                'is_current': is_current,
                'is_sub_order': order.parent_order is not None,
                'sequence_index': sequence_index,
                'order_type': order.order_type
            })
        elif order.order_type in [OrderType.ATTACK, OrderType.PROTECT]:
            target_unit_id = order.parameters["target_unit_id"]
            target_unit = self.game.galaxy.get_unit_by_id(target_unit_id)
            if target_unit:
                sequence_index = len(all_waypoints_sequence)
                all_waypoints_sequence.append({
                    'position': target_unit.position,
                    'system': target_unit.in_system,
                    'hex': target_unit.in_hex,
                    'is_current': is_current,
                    'is_sub_order': False,
                    'sequence_index': sequence_index,
                    'order_type': order.order_type
                })
        elif order.order_type == OrderType.USE_ABILITY:
            target_unit_id = order.parameters.get("target_unit_id")
            target_position = order.parameters.get("target_position")
            if target_unit_id:
                target_unit = self.game.galaxy.get_unit_by_id(target_unit_id)
                if target_unit:
                    sequence_index = len(all_waypoints_sequence)
                    all_waypoints_sequence.append({
                        'position': target_unit.position,
                        'system': target_unit.in_system,
                        'hex': target_unit.in_hex,
                        'is_current': is_current,
                        'is_sub_order': False,
                        'sequence_index': sequence_index,
                        'order_type': order.order_type
                    })
            elif target_position:
                dsys = order.parameters.get("target_system_name") or order.unit.in_system
                dhex = order.parameters.get("target_hex_coord") or order.unit.in_hex
                sequence_index = len(all_waypoints_sequence)
                all_waypoints_sequence.append({
                    'position': target_position,
                    'system': dsys,
                    'hex': dhex,
                    'is_current': is_current,
                    'is_sub_order': order.parent_order is not None,
                    'sequence_index': sequence_index,
                    'order_type': order.order_type
                })
        elif order.order_type == OrderType.PATROL:
            wps = order.parameters.get("waypoints", [])
            if not wps and "destination_position" in order.parameters:
                wps = [{
                    "system_name": order.parameters.get("destination_system_name"),
                    "hex_coord": order.parameters.get("destination_hex_coord"),
                    "position": order.parameters.get("destination_position")
                }]
            start_pos = getattr(order, "start_position", None)
            start_sys = getattr(order, "start_system_name", None)
            start_hex = getattr(order, "start_hex_coord", None)
            if not start_pos:
                start_pos = unit.position
                start_sys = unit.in_system
                start_hex = unit.in_hex

            # Construct the complete patrol cycle: waypoints list followed by the start position.
            cycle = []
            for wp in wps:
                cycle.append({
                    'position': wp['position'],
                    'system': wp['system_name'],
                    'hex': wp['hex_coord']
                })
            if start_pos:
                cycle.append({
                    'position': start_pos,
                    'system': start_sys,
                    'hex': start_hex
                })

            if cycle:
                # Reorder the cycle to start with the active/current waypoint index.
                # This ensures the path flows from the unit's current position to the current leg target,
                # and then continues in order to close the loop.
                idx = getattr(order, "current_waypoint_index", 0)
                if idx >= len(cycle) or idx < 0:
                    idx = 0

                # Form a closed loop starting at idx, going through the cycle, and ending back at idx.
                reordered_cycle = cycle[idx:] + cycle[:idx] + [cycle[idx]]

                for item in reordered_cycle:
                    sequence_index = len(all_waypoints_sequence)
                    all_waypoints_sequence.append({
                        'position': item['position'],
                        'system': item['system'],
                        'hex': item['hex'],
                        'is_current': is_current,
                        'is_sub_order': True,
                        'sequence_index': sequence_index,
                        'order_type': order.order_type
                    })

        for sub_order in list(order.sub_orders):
            # Skip the MoveOrder sub-order of a PatrolOrder because the patrol path
            # loop rendering already handles drawing the active move path to the current target.
            if order.order_type == OrderType.PATROL and sub_order.order_type == OrderType.MOVE:
                continue
            self._collect_waypoints_from_order(
                sub_order,
                unit,
                all_waypoints_sequence,
                is_current=(is_current and order == unit.commander_component.current_order)
            )
    
    def _collect_all_waypoints(self, unit, is_current_order=False):
        """Helper method to collect all waypoints from a unit's orders and sub-orders with sequence index."""
        all_waypoints_sequence = []
        
        if unit.commander_component.current_order:
            self._collect_waypoints_from_order(unit.commander_component.current_order, unit, all_waypoints_sequence, True)
        
        for queued_order in list(unit.commander_component.orders_queue):
            self._collect_waypoints_from_order(queued_order, unit, all_waypoints_sequence, False)
            
        return all_waypoints_sequence
        
    def _draw_sector_view_order_lines_from_other_sectors(self, external_units):
        """Draw order paths for units in other sectors that have orders targeting this sector."""
        for external_unit in external_units:
            all_waypoints_sequence = self._collect_all_waypoints(external_unit)
            waypoints_in_current_sector = [wp for wp in all_waypoints_sequence 
                                        if wp['system'] == self.game.current_system_name and 
                                           wp['hex'] == self.game.current_sector_coord]
            waypoints_in_current_sector.sort(key=lambda wp: wp['sequence_index'])
            
            path_segments = []
            current_segment = []
            
            for i, waypoint in enumerate(waypoints_in_current_sector):
                if i == 0:
                    current_segment.append(waypoint)
                else:
                    prev_wp = waypoints_in_current_sector[i-1]
                    if waypoint['sequence_index'] == prev_wp['sequence_index'] + 1:
                        current_segment.append(waypoint)
                    else:
                        if current_segment:
                            path_segments.append(current_segment)
                        current_segment = [waypoint]
            if current_segment:
                path_segments.append(current_segment)
            
            for segment_index, segment in enumerate(path_segments):
                if not segment:
                    continue
                    
                for i, waypoint in enumerate(segment):
                    dest_pixel_point = self._coords_to_pixels(waypoint['position'])
                    
                    if waypoint['order_type'] == OrderType.ATTACK:
                        line_color = RED
                        line_width = 2
                    elif waypoint['order_type'] == OrderType.PROTECT:
                        line_color = (255, 105, 180)
                        line_width = 2
                    elif waypoint['is_current']:
                        line_width = 2
                        line_color = MOVE_ORDER_LINE_COLOR
                    else:
                        line_width = 1
                        line_color = (max(MOVE_ORDER_LINE_COLOR[0] - 40, 0), 
                                     max(MOVE_ORDER_LINE_COLOR[1] - 40, 0), 
                                     max(MOVE_ORDER_LINE_COLOR[2] - 40, 0))
                    
                    if i == 0:
                        entry_color = WORMHOLE_JUMP_ORDER_COLOR
                        pygame.draw.circle(self.overlay_surface, entry_color, 
                                           (dest_pixel_point.x, dest_pixel_point.y), 3, 1)
                        last_pixel_x, last_pixel_y = dest_pixel_point.x, dest_pixel_point.y
                    else:
                        pygame.draw.line(self.overlay_surface, line_color, 
                                      (last_pixel_x, last_pixel_y), 
                                      (dest_pixel_point.x, dest_pixel_point.y), line_width)
                        last_pixel_x, last_pixel_y = dest_pixel_point.x, dest_pixel_point.y
                    
                    is_exit_point = (i == len(segment) - 1 and segment_index < len(path_segments) - 1)
                    if is_exit_point:
                        exit_color = WORMHOLE_JUMP_ORDER_COLOR
                        pygame.draw.circle(self.overlay_surface, exit_color, 
                                       (dest_pixel_point.x, dest_pixel_point.y), 3, 1)
                    else:
                        if i > 0 or segment_index == 0:
                            circle_size = 3 if not waypoint['is_sub_order'] else 2
                            pygame.draw.circle(self.overlay_surface, line_color, 
                                      (dest_pixel_point.x, dest_pixel_point.y), circle_size)
                
                # Draw turn notches for the segment
                if external_unit.engines_component:
                    effective_speed = external_unit.engines_component.speed * external_unit.xp_multiplier(XP_SPEED_BONUS)
                    self._draw_path_turn_notches_for_segment(segment, False, None, effective_speed)

    def _draw_sector_view_order_lines(self, unit, unit_pixel_x, unit_pixel_y):
        """Draw order paths for a unit in the sector view."""
        all_waypoints_sequence = self._collect_all_waypoints(unit)
        waypoints_in_current_sector = [wp for wp in all_waypoints_sequence 
                                     if wp['system'] == self.game.current_system_name and 
                                        wp['hex'] == self.game.current_sector_coord]
        waypoints_in_current_sector.sort(key=lambda wp: wp['sequence_index'])
        
        path_segments = []
        current_segment = []
        
        for i, waypoint in enumerate(waypoints_in_current_sector):
            if i == 0:
                current_segment.append(waypoint)
            else:
                prev_wp = waypoints_in_current_sector[i-1]
                if waypoint['sequence_index'] == prev_wp['sequence_index'] + 1:
                    current_segment.append(waypoint)
                else:
                    if current_segment:
                        path_segments.append(current_segment)
                    current_segment = [waypoint]
        if current_segment:
            path_segments.append(current_segment)
        
        if path_segments:
            unit_in_current_sector = (unit.in_system == self.game.current_system_name and 
                                     unit.in_hex == self.game.current_sector_coord)
            
            for segment_index, segment in enumerate(path_segments):
                if not segment:
                    continue
                    
                first_waypoint_in_segment = segment[0]
                is_first_waypoint_overall = (first_waypoint_in_segment['sequence_index'] == 0)
                connect_to_unit = unit_in_current_sector and (
                    first_waypoint_in_segment.get('connect_to_unit', False) or
                    (is_first_waypoint_overall and segment_index == 0)
                )
                
                for i, waypoint in enumerate(segment):
                    dest_pixel_point = self._coords_to_pixels(waypoint['position'])
                    
                    if waypoint['order_type'] == OrderType.ATTACK:
                        line_color = RED
                        line_width = 2
                    elif waypoint['order_type'] == OrderType.PROTECT:
                        line_color = (255, 105, 180)
                        line_width = 2
                    elif waypoint['is_current']:
                        line_width = 2
                        line_color = MOVE_ORDER_LINE_COLOR
                    else:
                        line_width = 1
                        line_color = (max(MOVE_ORDER_LINE_COLOR[0] - 40, 0), 
                                     max(MOVE_ORDER_LINE_COLOR[1] - 40, 0), 
                                     max(MOVE_ORDER_LINE_COLOR[2] - 40, 0))
                    
                    if i == 0:
                        if connect_to_unit:
                            pygame.draw.line(self.overlay_surface, line_color, 
                                          (unit_pixel_x, unit_pixel_y), 
                                          (dest_pixel_point.x, dest_pixel_point.y), line_width)
                        if segment_index > 0:
                            entry_color = WORMHOLE_JUMP_ORDER_COLOR
                            pygame.draw.circle(self.overlay_surface, entry_color, 
                                           (dest_pixel_point.x, dest_pixel_point.y), 3, 1)
                        last_pixel_x, last_pixel_y = dest_pixel_point.x, dest_pixel_point.y
                    else:
                        pygame.draw.line(self.overlay_surface, line_color, 
                                      (last_pixel_x, last_pixel_y), 
                                      (dest_pixel_point.x, dest_pixel_point.y), line_width)
                        last_pixel_x, last_pixel_y = dest_pixel_point.x, dest_pixel_point.y
                    
                    is_last_in_segment = (i == len(segment) - 1)
                    is_final_segment = (segment_index == len(path_segments) - 1)
                    will_exit_sector = False
                    
                    if is_last_in_segment:
                        if not is_final_segment:
                            will_exit_sector = True
                        else:
                            all_waypoints = all_waypoints_sequence
                            current_seq_index = waypoint['sequence_index']
                            for wp in all_waypoints:
                                if wp['sequence_index'] == current_seq_index + 1:
                                    if wp['hex'] != self.game.current_sector_coord or wp['system'] != self.game.current_system_name:
                                        will_exit_sector = True
                                    break
                    
                    if is_last_in_segment and will_exit_sector:
                        exit_color = WORMHOLE_JUMP_ORDER_COLOR
                        pygame.draw.circle(self.overlay_surface, exit_color, 
                                      (dest_pixel_point.x, dest_pixel_point.y), 5, 2)
                    elif not (i == 0 and segment_index > 0):
                        circle_size = 3 if not waypoint['is_sub_order'] else 2
                        pygame.draw.circle(self.overlay_surface, line_color, 
                                      (dest_pixel_point.x, dest_pixel_point.y), circle_size)

                # Draw turn notches for this segment
                if unit.engines_component:
                    effective_speed = unit.engines_component.speed * unit.xp_multiplier(XP_SPEED_BONUS)
                    self._draw_path_turn_notches_for_segment(segment, connect_to_unit, unit.position, effective_speed)

    def _get_pre_rendered_nebula(self, nebula):
        if nebula.id in self._nebula_master_surfaces:
            return self._nebula_master_surfaces[nebula.id]

        ref_zoom = 1.0
        ref_dynamic_radius = SECTOR_CIRCLE_RADIUS_IN_PX * ref_zoom
        num_circles = 15
        max_offset_logical = NEBULA_RADIUS / 2.0
        base_radius_logical = NEBULA_RADIUS

        random.seed(nebula.id)

        circles = []
        min_x, max_x = float('inf'), float('-inf')
        min_y, max_y = float('inf'), float('-inf')

        for _ in range(num_circles):
            offset_x_logical = random.uniform(-max_offset_logical, max_offset_logical)
            offset_y_logical = random.uniform(-max_offset_logical, max_offset_logical)

            offset_x_px = offset_x_logical * ref_dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
            offset_y_px = offset_y_logical * ref_dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL

            radius_variation = random.uniform(0.5, 1.2)
            circle_radius_logical = base_radius_logical * radius_variation
            circle_radius_px = int(circle_radius_logical * ref_dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)

            if circle_radius_px <= 0:
                continue

            alpha = random.randint(20, 50)
            color = NEBULA_COLORS[nebula.nebula_type]
            color_key = (color[0], color[1], color[2], alpha)

            circles.append((offset_x_px, offset_y_px, circle_radius_px, color_key))

            min_x = min(min_x, offset_x_px - circle_radius_px)
            max_x = max(max_x, offset_x_px + circle_radius_px)
            min_y = min(min_y, offset_y_px - circle_radius_px)
            max_y = max(max_y, offset_y_px + circle_radius_px)

        random.seed()

        if not circles:
            self._nebula_master_surfaces[nebula.id] = None
            return None

        # Add padding to prevent any edge clipping
        width = int(max_x - min_x) + 4
        height = int(max_y - min_y) + 4

        center_x = -min_x + 2
        center_y = -min_y + 2

        master_surface = pygame.Surface((width, height), pygame.SRCALPHA)

        for offset_x, offset_y, radius, color in circles:
            circle_surface = self._get_cached_circle_surface(radius, color)
            if circle_surface:
                cx = center_x + offset_x - radius
                cy = center_y + offset_y - radius
                master_surface.blit(circle_surface, (cx, cy))

        self._nebula_master_surfaces[nebula.id] = {
            'master': master_surface,
            'center_x': center_x,
            'center_y': center_y,
        }
        return self._nebula_master_surfaces[nebula.id]

    def _draw_nebula(self, nebula, pos_px):
        zoom = self.game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0

        pre_rendered = self._get_pre_rendered_nebula(nebula)
        if not pre_rendered:
            return

        target_zoom = getattr(self.game, 'sector_target_zoom', zoom)
        is_zooming = isinstance(target_zoom, (int, float)) and abs(target_zoom - zoom) > 1e-4

        quantized_zoom = self._effect_zoom_bucket(zoom)
        self._blit_visible_scaled_surface(
            pre_rendered['master'],
            (pre_rendered['center_x'], pre_rendered['center_y']),
            (pos_px.x, pos_px.y),
            quantized_zoom,
            ('nebula', nebula.id, quantized_zoom),
            # Nebula content is static, so a smooth (bilinear) scale is worth
            # the cost while the camera is at rest and the result is cached.
            # While actively zooming, fall back to a fast nearest-neighbour
            # scale so cache churn from the changing zoom bucket stays cheap.
            smooth=not is_zooming,
        )


    def _draw_celestial_field(self, field, pos_px, base_color, num_particles=40):
        """Draws a celestial field with random objects (asteroids/ice bodies/debris)"""
        num_objects = num_particles
        field_radius = CELESTIAL_FIELD_RADIUS  # Logical radius of the field
        time_ms = pygame.time.get_ticks()
        zoom = self.game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0
        dynamic_radius = SECTOR_CIRCLE_RADIUS_IN_PX * zoom

        random.seed(field.id)

        for i in range(num_objects):
            # Generate consistent random properties for each object (asteroid/ice body/debris)
            initial_angle = random.uniform(0, 360)
            initial_radius = random.uniform(field_radius * 0.1, field_radius)
            rotation_speed = random.uniform(-1.5, 1.5)  # Faster rotation
            object_size = random.randint(1, 3)
            color_variation = random.randint(-20, 20)
            object_color = (max(0, min(255, base_color[0] + color_variation)),
                              max(0, min(255, base_color[1] + color_variation)),
                              max(0, min(255, base_color[2] + color_variation)))

            # Animate the object's position
            current_angle_rad = math.radians(initial_angle + (time_ms / 500.0) * rotation_speed)
            offset_x = initial_radius * math.cos(current_angle_rad)
            offset_y = initial_radius * math.sin(current_angle_rad)
            
            offset_x_px = offset_x * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
            offset_y_px = offset_y * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
            object_pos = (pos_px.x + offset_x_px, pos_px.y + offset_y_px)

            # Draw the object
            pygame.draw.circle(self.screen, object_color, object_pos, object_size)

        random.seed()

    def _get_pre_rendered_storm_circles(self, storm):
        """Precompute (and cache, per storm.id) the deterministic layout of a
        storm's rotating particles in a small, fixed-resolution local
        "compose" space, independent of screen size or zoom.

        Every frame, ``_draw_storm`` positions these particles (by animating
        their angle) into a shared scratch canvas sized to
        ``STORM_COMPOSE_MAX_DIAMETER``, then scales the ENTIRE composed
        canvas to the screen with a single transform call -- instead of the
        old approach of individually smoothscaling (or, at high zoom,
        rasterizing via an uncached ``pygame.draw.circle``) each of the 25
        particles every frame.
        """
        if storm.id in self._storm_base_circle_surfaces:
            return self._storm_base_circle_surfaces[storm.id]

        num_circles = 25
        base_radius_logical = STORM_RADIUS

        random.seed(storm.id)

        particles = []
        max_bounding_logical = 0.0
        for i in range(num_circles):
            initial_angle = random.uniform(0, 360)
            initial_radius_logical = random.uniform(base_radius_logical * 0.1, base_radius_logical * 0.9)
            rotation_speed = random.uniform(-3.0, 3.0)
            circle_base_radius_logical = base_radius_logical * random.uniform(0.2, 0.5)

            alpha = random.randint(30, 60)
            color = STORM_COLORS[storm.storm_type]
            color_key = (color[0], color[1], color[2], alpha)

            particles.append({
                'initial_angle': initial_angle,
                'initial_radius_logical': initial_radius_logical,
                'rotation_speed': rotation_speed,
                'circle_base_radius_logical': circle_base_radius_logical,
                'color_key': color_key,
            })
            max_bounding_logical = max(max_bounding_logical, initial_radius_logical + circle_base_radius_logical)

        random.seed()

        if max_bounding_logical <= 0:
            max_bounding_logical = base_radius_logical

        canvas_diameter = float(STORM_COMPOSE_MAX_DIAMETER)
        canvas_center_px = canvas_diameter / 2.0
        padding_px = 4.0
        # logical-units -> local-canvas-px conversion factor, chosen so the
        # storm's full bounding radius fits inside the capped canvas.
        s_compose = max(1e-6, (canvas_center_px - padding_px) / max_bounding_logical)

        for particle in particles:
            particle['local_radius_px'] = max(1, round(particle['circle_base_radius_logical'] * s_compose))

        storm_data = {
            'particles': particles,
            'bounding_radius_logical': max_bounding_logical,
            's_compose': s_compose,
            'canvas_diameter': canvas_diameter,
        }
        self._storm_base_circle_surfaces[storm.id] = storm_data
        return storm_data

    def _draw_storm(self, storm, pos_px):
        zoom = self.game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0
        dynamic_radius = SECTOR_CIRCLE_RADIUS_IN_PX * zoom
        time_ms = pygame.time.get_ticks()

        storm_data = self._get_pre_rendered_storm_circles(storm)
        particles = storm_data['particles']
        s_compose = storm_data['s_compose']
        canvas_diameter = storm_data['canvas_diameter']
        bounding_radius_logical = storm_data['bounding_radius_logical']

        bounding_radius_px = bounding_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
        if bounding_radius_px > 0 and not self._is_circle_off_screen((pos_px.x, pos_px.y), bounding_radius_px):
            canvas_size = (int(canvas_diameter), int(canvas_diameter))
            if self._storm_scratch_surface is None or self._storm_scratch_surface.get_size() != canvas_size:
                self._storm_scratch_surface = pygame.Surface(canvas_size, pygame.SRCALPHA)
            scratch = self._storm_scratch_surface
            scratch.fill((0, 0, 0, 0))

            canvas_center_px = canvas_diameter / 2.0
            for particle in particles:
                current_angle_rad = math.radians(particle['initial_angle'] + (time_ms / 100.0) * particle['rotation_speed'])
                offset_x_logical = particle['initial_radius_logical'] * math.cos(current_angle_rad)
                offset_y_logical = particle['initial_radius_logical'] * math.sin(current_angle_rad)

                local_x = canvas_center_px + offset_x_logical * s_compose
                local_y = canvas_center_px + offset_y_logical * s_compose
                local_radius_px = particle['local_radius_px']

                circle_surface = self._get_cached_circle_surface(local_radius_px, particle['color_key'])
                if circle_surface is not None:
                    scratch.blit(circle_surface, (local_x - local_radius_px, local_y - local_radius_px))

            # Scale the ENTIRE composed canvas to the screen in a single
            # transform call. Positions and sizes were both derived from the
            # same s_compose factor, so this one scale reproduces the same
            # on-screen layout the old per-particle scaling produced.
            target_zoom = getattr(self.game, 'sector_target_zoom', zoom)
            is_zooming = isinstance(target_zoom, (int, float)) and abs(target_zoom - zoom) > 1e-4
            final_scale = (dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL) / s_compose

            self._blit_scaled_surface_once(
                scratch,
                (canvas_center_px, canvas_center_px),
                (pos_px.x, pos_px.y),
                final_scale,
                smooth=not is_zooming,
            )

        # Reset seed to keep behavior consistent (matches prior behavior,
        # which reseeded here regardless of cache hit/miss).
        random.seed()

        # Draw lightning flashes on top
        if random.random() < 0.05:
            num_bolts = random.randint(1, 3)
            base_radius_logical = STORM_RADIUS
            base_radius_px = int(base_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            for _ in range(num_bolts):
                angle = random.uniform(0, 2 * math.pi)
                length_px = random.uniform(base_radius_px * 1.0, base_radius_px * 1.5)
                end_pos_x = pos_px.x + length_px * math.cos(angle)
                end_pos_y = pos_px.y + length_px * math.sin(angle)
                pygame.draw.line(self.overlay_surface, STORM_LIGHTNING_COLOR, (pos_px.x, pos_px.y), (end_pos_x, end_pos_y), 2)


