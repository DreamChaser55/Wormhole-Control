from display_config import display_config_for
import pygame
import math
from collections import OrderedDict
from constants import SECTOR_CIRCLE_RADIUS_LOGICAL, WORMHOLE_RADIUS, FOG_PRESENCE_COLOR, MOVE_ORDER_LINE_COLOR, WORMHOLE_JUMP_ORDER_COLOR, XP_SPEED_BONUS

from sector_utils import sector_coords_to_pixels
from geometry import Position
from domain.units import Unit
from unit_orders.base import OrderType, OrderStatus
from domain.minefields import Minefield
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
        self.grid_renderer = SectorGridRenderer(self)
        self.celestial_renderer = SectorCelestialRenderer(self)
        self.entity_renderer = SectorEntityRenderer(self)
        self.overlay_renderer = SectorOverlayRenderer(self)

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
        dynamic_radius = display_config_for(self.game).sector_radius * zoom

        # 1. Selection Box (if dragging)
        self.overlay_renderer.draw_selection_box()

        # 2. Sector Boundary & Tactical Grid
        self.grid_renderer.draw_boundary(dynamic_radius)
        self.grid_renderer.draw_tactical_grid()

        # 3. Fog of War overlay
        hex_obj = system.hexes.get(self.game.current_sector_coord)
        if hex_obj:
            self.overlay_renderer.draw_fog_of_war(hex_obj, dynamic_radius)

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
        
        if self.game.hex_has_presence(self.game.current_system_name, self.game.current_sector_coord):
            font_size = max(12, int(14 * display_config_for(self.game).text_scale))
            hud_font = pygame.font.Font(None, font_size)
            text_surface = hud_font.render("WARNING: Enemy presence detected in sector", True, FOG_PRESENCE_COLOR)
            text_rect = text_surface.get_rect(center=(self.screen.get_width() // 2, 60))
            self.screen.blit(text_surface, text_rect)

        from domain.deployables import Deployable
        from tactical_ui import draw, draw_deployable
        draw(self, hex_obj)
        all_objects_in_sector = bodies_to_draw + units_to_draw + minefields_to_draw + [d for d in getattr(hex_obj, 'deployables', ()) if self.game.is_unit_visible(d)]

        for obj in all_objects_in_sector:
            obj_pixel_pos = self.grid_renderer.coords_to_pixels(obj.position)

            if isinstance(obj, Unit):
                obj_radius_logical = self.entity_renderer.draw_unit(obj, obj_pixel_pos, dynamic_radius)
            elif isinstance(obj, Deployable):
                obj_radius_logical = draw_deployable(self, obj, obj_pixel_pos)
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
                    self.overlay_renderer.draw_unit_range_circles(obj, obj_pixel_pos, dynamic_radius)

            # Move/Jump order lines
            if isinstance(obj, Unit):
                unit_obj: Unit = obj
                is_turn_player_unit = self.game.players and unit_obj.owner == self.game.players[self.game.current_player_index]

                if is_turn_player_unit:
                    has_commander_orders = (
                        unit_obj.commander_component
                        and (
                            unit_obj.commander_component.current_order
                            or unit_obj.commander_component.orders_queue
                            or getattr(
                                getattr(unit_obj.commander_component, "standing_order", None),
                                "has_engagement",
                                False,
                            )
                        )
                    )
                    if has_commander_orders:
                        self.overlay_renderer.draw_sector_view_order_lines(unit_obj, obj_pixel_pos.x, obj_pixel_pos.y)
                    else:
                        if unit_obj.engines_component and unit_obj.engines_component.move_target:
                            target_pos_in_sector = unit_obj.engines_component.move_target
                            target_pixel_pos = self.grid_renderer.coords_to_pixels(target_pos_in_sector)
                            pygame.draw.line(self.overlay_surface, MOVE_ORDER_LINE_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), (target_pixel_pos.x, target_pixel_pos.y), 1)
                            pygame.draw.circle(self.overlay_surface, MOVE_ORDER_LINE_COLOR, (target_pixel_pos.x, target_pixel_pos.y), 3)
                            
                            mock_wp = {
                                'order_type': OrderType.MOVE,
                                'is_current': True,
                                'position': target_pos_in_sector
                            }
                            effective_speed = unit_obj.engines_component.speed * unit_obj.xp_multiplier(XP_SPEED_BONUS)
                            self.overlay_renderer.draw_path_turn_notches_for_segment([mock_wp], True, unit_obj.position, effective_speed)
                        elif unit_obj.hyperdrive_component and unit_obj.hyperdrive_component.wormhole_jump_target:
                            target_wh_for_jump = unit_obj.hyperdrive_component.wormhole_jump_target
                            if target_wh_for_jump.in_system == self.game.current_system_name and target_wh_for_jump.in_hex == self.game.current_sector_coord:
                                wh_pixel_pos = self.grid_renderer.coords_to_pixels(target_wh_for_jump.position)
                                pygame.draw.line(self.overlay_surface, WORMHOLE_JUMP_ORDER_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), (wh_pixel_pos.x, wh_pixel_pos.y), 2)
                                wh_pixel_radius = int(WORMHOLE_RADIUS * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                                pygame.draw.circle(self.overlay_surface, WORMHOLE_JUMP_ORDER_COLOR, (wh_pixel_pos.x, wh_pixel_pos.y), wh_pixel_radius + 4, 1)

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
                    order = (
                        candidate_unit.commander_component.current_order
                        or candidate_unit.commander_component.get_active_order_root()
                    )
                    if order:
                        if self.overlay_renderer.order_targets_sector(order, self.game.current_system_name, self.game.current_sector_coord):
                            has_orders_to_current_sector = True
                        for sub_order in order.sub_orders:
                            if self.overlay_renderer.order_targets_sector(sub_order, self.game.current_system_name, self.game.current_sector_coord):
                                has_orders_to_current_sector = True
                                break
                    if not has_orders_to_current_sector:
                        for queued_order in candidate_unit.commander_component.orders_queue:
                            if self.overlay_renderer.order_targets_sector(queued_order, self.game.current_system_name, self.game.current_sector_coord):
                                has_orders_to_current_sector = True
                                break
                            for sub_order in queued_order.sub_orders:
                                if self.overlay_renderer.order_targets_sector(sub_order, self.game.current_system_name, self.game.current_sector_coord):
                                    has_orders_to_current_sector = True
                                    break
                            if has_orders_to_current_sector:
                                break
                    if has_orders_to_current_sector:
                        external_units_with_orders_to_this_sector.append(candidate_unit)

        self.overlay_renderer.draw_sector_view_order_lines_from_other_sectors(external_units_with_orders_to_this_sector)
        self.overlay_renderer.draw_targeting_mode_overlay()
        self.grid_renderer.update_zoom_render_stats()
