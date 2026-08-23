import pygame
import math
from collections import OrderedDict
from constants import (
    SECTOR_CIRCLE_RADIUS_IN_PX, SECTOR_CIRCLE_RADIUS_LOGICAL, WORMHOLE_RADIUS,
    FOG_PRESENCE_COLOR, MOVE_ORDER_LINE_COLOR, WORMHOLE_JUMP_ORDER_COLOR,
    TEXT_SCALE, XP_SPEED_BONUS
)

from sector_utils import sector_coords_to_pixels
from geometry import Position
from entities import Unit, OrderType, OrderStatus, Minefield
from rendering.drawing_utils import draw_shape, draw_dotted_line

from rendering.sector_renderer.sector_grid_renderer import SectorGridRenderer
from rendering.sector_renderer.sector_celestial_renderer import SectorCelestialRenderer
from rendering.sector_renderer.sector_entity_renderer import SectorEntityRenderer
from rendering.sector_renderer.sector_overlay_renderer import SectorOverlayRenderer


MAX_CACHED_STORM_DIAMETER = 512
MAX_SAFE_CIRCLE_RADIUS_PX = 250_000


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
    """Facade orchestrator for sector view rendering. Delegates rendering sub-passes to:
      - SectorGridRenderer (hex grid, boundary, clipping & viewport math)
      - SectorCelestialRenderer (stars, planets, nebulae, storms, particle fields)
      - SectorEntityRenderer (ships, stations, minefields, inhibition zones)
      - SectorOverlayRenderer (selection box/brackets, range circles, order lines, fog of war)
    """

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
        self._fog_of_war_surface = None
        self._fog_cache_key = None
        self._fog_blit_rect = None
        self._storm_scratch_surface = None
        self._range_circle_surface = None
        self.zoom_render_stats = {
            'cache_hits': 0,
            'cache_misses': 0,
            'cache_bytes': 0,
            'direct_draw_fallbacks': 0,
            'range_circle_fills': 0,
            'fog_rebuilds': 0,
            'fog_cache_hits': 0,
            'fog_full_reveal': 0,
        }

        # Instantiate sub-renderers
        self._grid_renderer = SectorGridRenderer(self)
        self._celestial_renderer = SectorCelestialRenderer(self)
        self._entity_renderer = SectorEntityRenderer(self)
        self._overlay_renderer = SectorOverlayRenderer(self)

    # -------------------------------------------------------------------------
    # Lazy property accessors for sub-renderers (supports __new__ without __init__)
    # -------------------------------------------------------------------------

    def _ensure_caches(self):
        if not hasattr(self, '_circle_surface_cache') or self._circle_surface_cache is None:
            self._circle_surface_cache = {}
        if not hasattr(self, '_font_cache') or self._font_cache is None:
            self._font_cache = {}
        if not hasattr(self, '_nebula_master_surfaces') or self._nebula_master_surfaces is None:
            self._nebula_master_surfaces = {}
        if not hasattr(self, '_storm_base_circle_surfaces') or self._storm_base_circle_surfaces is None:
            self._storm_base_circle_surfaces = {}
        if not hasattr(self, '_scaled_effect_surfaces') or self._scaled_effect_surfaces is None:
            self._scaled_effect_surfaces = _BoundedSurfaceCache()
        if not hasattr(self, '_last_cached_sector'):
            self._last_cached_sector = None
        if not hasattr(self, '_inhibition_surface'):
            self._inhibition_surface = None
        if not hasattr(self, '_fog_of_war_surface'):
            self._fog_of_war_surface = None
        if not hasattr(self, '_fog_cache_key'):
            self._fog_cache_key = None
        if not hasattr(self, '_fog_blit_rect'):
            self._fog_blit_rect = None
        if not hasattr(self, '_storm_scratch_surface'):
            self._storm_scratch_surface = None
        if not hasattr(self, '_range_circle_surface'):
            self._range_circle_surface = None
        if not hasattr(self, 'zoom_render_stats') or self.zoom_render_stats is None:
            self.zoom_render_stats = {
                'cache_hits': 0,
                'cache_misses': 0,
                'cache_bytes': 0,
                'direct_draw_fallbacks': 0,
                'range_circle_fills': 0,
                'fog_rebuilds': 0,
                'fog_cache_hits': 0,
                'fog_full_reveal': 0,
            }

    @property
    def grid_renderer(self):
        self._ensure_caches()
        if getattr(self, '_grid_renderer', None) is None:
            self._grid_renderer = SectorGridRenderer(self)
        return self._grid_renderer

    @property
    def celestial_renderer(self):
        self._ensure_caches()
        if getattr(self, '_celestial_renderer', None) is None:
            self._celestial_renderer = SectorCelestialRenderer(self)
        return self._celestial_renderer

    @property
    def entity_renderer(self):
        self._ensure_caches()
        if getattr(self, '_entity_renderer', None) is None:
            self._entity_renderer = SectorEntityRenderer(self)
        return self._entity_renderer

    @property
    def overlay_renderer(self):
        self._ensure_caches()
        if getattr(self, '_overlay_renderer', None) is None:
            self._overlay_renderer = SectorOverlayRenderer(self)
        return self._overlay_renderer

    # -------------------------------------------------------------------------
    # Delegating helper methods for backward compatibility & test monkeypatching
    # -------------------------------------------------------------------------

    def _coords_to_pixels(self, sector_pos):
        return self.grid_renderer.coords_to_pixels(sector_pos)

    def _is_circle_off_screen(self, center_px, radius_px):
        return self.grid_renderer.is_circle_off_screen(center_px, radius_px)

    def _get_cached_circle_surface(self, radius, color):
        return self.grid_renderer.get_cached_circle_surface(radius, color)

    def _effect_zoom_bucket(self, zoom):
        return self.grid_renderer.effect_zoom_bucket(zoom)

    def _compute_visible_scaled_region(self, source, source_center, destination_center, scale):
        return self.grid_renderer.compute_visible_scaled_region(source, source_center, destination_center, scale)

    def _blit_visible_scaled_surface(self, source, source_center, destination_center, scale, cache_prefix, smooth=True):
        return self.grid_renderer.blit_visible_scaled_surface(source, source_center, destination_center, scale, cache_prefix, smooth)

    def _blit_scaled_surface_once(self, source, source_center, destination_center, scale, smooth=False):
        return self.grid_renderer.blit_scaled_surface_once(source, source_center, destination_center, scale, smooth)

    def _circle_covers_rect(self, center_px, radius_px, rect) -> bool:
        return self.grid_renderer.circle_covers_rect(center_px, radius_px, rect)

    def _circle_covers_viewport(self, center_px, radius_px):
        return self.grid_renderer.circle_covers_viewport(center_px, radius_px)

    def _fill_circle_on_surface(self, surface, center_px, radius_px, rgba, clip_rect) -> bool:
        return self.grid_renderer.fill_circle_on_surface(surface, center_px, radius_px, rgba, clip_rect)

    def _fill_circle_clipped(self, center_px, radius_px, rgba):
        return self.grid_renderer.fill_circle_clipped(center_px, radius_px, rgba)

    def _blit_uncached_circle(self, circle_pos, radius_px, color):
        return self.grid_renderer.blit_uncached_circle(circle_pos, radius_px, color)

    def _draw_range_ring(self, cx, cy, radius_px, outline_rgb):
        return self.grid_renderer.draw_range_ring(cx, cy, radius_px, outline_rgb)

    def _update_zoom_render_stats(self):
        return self.grid_renderer.update_zoom_render_stats()

    def _draw_tactical_grid(self):
        return self.grid_renderer.draw_tactical_grid()

    def _draw_fog_of_war(self, hex_obj, dynamic_radius: float) -> None:
        return self.overlay_renderer.draw_fog_of_war(hex_obj, dynamic_radius)

    def _draw_unit_range_circles(self, unit: Unit, pixel_pos, dynamic_radius: float) -> None:
        return self.overlay_renderer.draw_unit_range_circles(unit, pixel_pos, dynamic_radius)

    def _get_waypoint_style(self, waypoint):
        return self.overlay_renderer.get_waypoint_style(waypoint)

    def _draw_single_notch(self, p_start, p_end, p_notch, color, line_width):
        return self.overlay_renderer.draw_single_notch(p_start, p_end, p_notch, color, line_width)

    def _draw_path_turn_notches_for_segment(self, segment, connect_to_unit, start_pos, effective_speed):
        return self.overlay_renderer.draw_path_turn_notches_for_segment(segment, connect_to_unit, start_pos, effective_speed)

    def _order_targets_sector(self, order, system_name, hex_coord):
        return self.overlay_renderer.order_targets_sector(order, system_name, hex_coord)

    def _collect_waypoints_from_order(self, order, unit, all_waypoints_sequence, is_current=False):
        return self.overlay_renderer.collect_waypoints_from_order(order, unit, all_waypoints_sequence, is_current)

    def _collect_all_waypoints(self, unit, is_current_order=False):
        return self.overlay_renderer.collect_all_waypoints(unit, is_current_order)

    def _draw_sector_view_order_lines_from_other_sectors(self, external_units):
        return self.overlay_renderer.draw_sector_view_order_lines_from_other_sectors(external_units)

    def _draw_sector_view_order_lines(self, unit, unit_pixel_x, unit_pixel_y):
        return self.overlay_renderer.draw_sector_view_order_lines(unit, unit_pixel_x, unit_pixel_y)

    def _get_pre_rendered_nebula(self, nebula):
        return self.celestial_renderer.get_pre_rendered_nebula(nebula)

    def _draw_nebula(self, nebula, pos_px):
        return self.celestial_renderer.draw_nebula(nebula, pos_px)

    def _draw_celestial_field(self, field, pos_px, base_color, num_particles=40):
        return self.celestial_renderer.draw_celestial_field(field, pos_px, base_color, num_particles)

    def _get_pre_rendered_storm_circles(self, storm):
        return self.celestial_renderer.get_pre_rendered_storm_circles(storm)

    def _draw_storm(self, storm, pos_px):
        return self.celestial_renderer.draw_storm(storm, pos_px)

    # -------------------------------------------------------------------------
    # Main Render Cycle
    # -------------------------------------------------------------------------

    def draw_sector_view(self):
        """Draws the detailed view of the current sector hex."""
        if not self.game.current_system_name or self.game.current_sector_coord is None:
            return
        system = self.game.galaxy.systems[self.game.current_system_name]
        if not system:
            return

        # Clear cached surfaces if the sector has changed
        current_sector_key = (self.game.current_system_name, self.game.current_sector_coord)
        if current_sector_key != self._last_cached_sector:
            self._nebula_master_surfaces.clear()
            self._storm_base_circle_surfaces.clear()
            self._scaled_effect_surfaces.clear()
            self._fog_of_war_surface = None
            self._fog_cache_key = None
            self._fog_blit_rect = None
            self._last_cached_sector = current_sector_key

        zoom = self.game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0
        dynamic_radius = SECTOR_CIRCLE_RADIUS_IN_PX * zoom

        # 1. Selection Box (if dragging)
        self.overlay_renderer.draw_selection_box()

        # 2. Sector Boundary & Tactical Grid
        self.grid_renderer.draw_boundary(dynamic_radius)
        self._draw_tactical_grid()

        # 3. Fog of War overlay
        hex_obj = system.hexes.get(self.game.current_sector_coord)
        if hex_obj:
            self._draw_fog_of_war(hex_obj, dynamic_radius)

        # 4. Inhibition & Cloaking Fields
        hex_obj = system.hexes.get(self.game.current_sector_coord)
        if hex_obj:
            self.entity_renderer.draw_inhibition_zones(hex_obj, dynamic_radius)
            self.entity_renderer.draw_cloaking_fields(hex_obj, dynamic_radius)

        # 5. Objects in Current Hex
        if not hex_obj:
            return

        bodies_to_draw = hex_obj.celestial_bodies
        units_to_draw = [u for u in hex_obj.units if self.game.is_unit_visible(u)]
        minefields_to_draw = [mf for mf in getattr(hex_obj, 'minefields', []) if self.game.is_minefield_visible(mf)]
        has_hidden = any(not self.game.is_unit_visible(u) for u in hex_obj.units)
        
        if has_hidden and self.game.hex_has_presence(self.game.current_system_name, self.game.current_sector_coord):
            font_size = max(12, int(14 * TEXT_SCALE))
            hud_font = pygame.font.Font(None, font_size)
            text_surface = hud_font.render("WARNING: Enemy presence detected in sector", True, FOG_PRESENCE_COLOR)
            text_rect = text_surface.get_rect(center=(self.screen.get_width() // 2, 60))
            self.screen.blit(text_surface, text_rect)

        all_objects_in_sector = bodies_to_draw + units_to_draw + minefields_to_draw

        for obj in all_objects_in_sector:
            obj_pixel_pos = self._coords_to_pixels(obj.position)

            if isinstance(obj, Unit):
                obj_radius_logical = self.entity_renderer.draw_unit(obj, obj_pixel_pos, dynamic_radius)
            elif isinstance(obj, Minefield):
                obj_radius_logical = self.entity_renderer.draw_minefield(obj, obj_pixel_pos, dynamic_radius)
            else:
                obj_color, obj_radius_logical = self.celestial_renderer.draw_celestial_object(obj, obj_pixel_pos, dynamic_radius)

            # Hover highlight
            self.overlay_renderer.draw_hover_highlight(obj, obj_pixel_pos, dynamic_radius, obj_radius_logical)

            # Selection brackets
            self.overlay_renderer.draw_selection_brackets(obj, obj_pixel_pos, dynamic_radius, obj_radius_logical)

            # Weapon/sensor range circles for single selected friendly unit
            if (isinstance(obj, Unit)
                    and len(self.game.selected_objects) == 1
                    and obj in self.game.selected_objects):
                current_turn_player = self.game.players[self.game.current_player_index] if self.game.players else None
                if current_turn_player and (obj.owner == current_turn_player or (hasattr(obj, 'has_infiltrating_agent_from') and obj.has_infiltrating_agent_from(current_turn_player))):
                    self._draw_unit_range_circles(obj, obj_pixel_pos, dynamic_radius)

            # Move/Jump order lines
            if isinstance(obj, Unit):
                unit_obj: Unit = obj
                is_turn_player_unit = self.game.players and unit_obj.owner == self.game.players[self.game.current_player_index]

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

        # External units targeting this sector
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
        self.overlay_renderer.draw_targeting_mode_overlay()
        self._update_zoom_render_stats()
