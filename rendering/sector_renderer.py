import pygame
import math
from constants import (
    NEBULA_COLORS, SECTOR_CIRCLE_CENTER_IN_PX, SECTOR_CIRCLE_RADIUS_IN_PX,
    SECTOR_CIRCLE_RADIUS_LOGICAL, SECTOR_BORDER_COLOR,
    STAR_RADIUS, PLANET_RADIUS, WORMHOLE_RADIUS, NEBULA_RADIUS, STORM_RADIUS,
    STORM_LIGHTNING_COLOR,
    WHITE, YELLOW, CYAN, PURPLE, RED,
    HULL_BASE_ICON_SCALES, HULL_DOT_COUNTS, SECTOR_VIEW_BASE_ICON_SIZE,
    ICON_DOT_RADIUS, ICON_DOT_SPACING,
    HOVER_HIGHLIGHT_COLOR, SELECTION_HIGHLIGHT_COLOR,
    MOVE_ORDER_LINE_COLOR, WORMHOLE_JUMP_ORDER_COLOR, STORM_COLORS,
    TEXT_SCALE
)
from sector_utils import sector_coords_to_pixels
import random
from entities import (
    Star, Planet, Wormhole, Unit, OrderType, OrderStatus, Moon, Asteroid, 
    AsteroidField, IceField, Nebula, Storm, Comet, StarType, PlanetType, DebrisField
)
from rendering.drawing_utils import draw_shape

class SectorViewRenderer:
    def __init__(self, game_instance):
        self.game = game_instance
        self.screen = game_instance.screen
        self.overlay_surface = game_instance.overlay_surface

    def draw_sector_view(self):
        """Draws the detailed view of the current sector hex."""
        if not self.game.current_system_name or self.game.current_sector_coord is None: return
        system = self.game.galaxy.systems[self.game.current_system_name]
        if not system: return

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
        pygame.draw.circle(self.screen, SECTOR_BORDER_COLOR, SECTOR_CIRCLE_CENTER_IN_PX.to_tuple(), SECTOR_CIRCLE_RADIUS_IN_PX, 1)

        # 2. Draw Inhibition Fields
        hex_obj = system.hexes[self.game.current_sector_coord]
        if hex_obj:
            for zone in hex_obj.get_all_inhibition_zones():
                zone_pixel_center = sector_coords_to_pixels(zone.center)
                zone_pixel_radius = int(zone.radius * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                
                circle_surface = pygame.Surface((zone_pixel_radius * 2, zone_pixel_radius * 2), pygame.SRCALPHA)
                pygame.draw.circle(circle_surface, (255, 0, 0, 50), (zone_pixel_radius, zone_pixel_radius), zone_pixel_radius)
                
                self.screen.blit(circle_surface, (zone_pixel_center.x - zone_pixel_radius, zone_pixel_center.y - zone_pixel_radius))

        # 3. Get Objects in the Current Hex
        hex_obj = system.hexes[self.game.current_sector_coord]
        bodies_to_draw = []
        units_to_draw = []
        if hex_obj:
            bodies_to_draw = hex_obj.celestial_bodies
            units_to_draw = hex_obj.units
        
        all_objects_in_sector = bodies_to_draw + units_to_draw

        for obj in all_objects_in_sector:
            obj_pixel_pos = sector_coords_to_pixels(obj.position) 
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
                    pixel_radius = int(obj_radius_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    pygame.draw.circle(self.screen, obj.owner.color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)
            elif isinstance(obj, Moon):
                obj_color = (200, 200, 200)
                obj_radius_logical = 27.78
                if obj.owner:
                    pixel_radius = int(obj_radius_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    pygame.draw.circle(self.screen, obj.owner.color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)
            elif isinstance(obj, Asteroid):
                obj_color = (90, 60, 50)
                obj_radius_logical = 16.67
                if obj.owner:
                    pixel_radius = int(obj_radius_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    pygame.draw.circle(self.screen, obj.owner.color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)
            elif isinstance(obj, AsteroidField):
                self._draw_celestial_field(obj, obj_pixel_pos, (100, 100, 100))
                obj_radius_logical = 100.0
                should_draw_circle = False
            elif isinstance(obj, IceField):
                self._draw_celestial_field(obj, obj_pixel_pos, (173, 216, 230), num_particles=20)
                obj_radius_logical = 100.0
                should_draw_circle = False
            elif isinstance(obj, DebrisField):
                self._draw_celestial_field(obj, obj_pixel_pos, (112, 128, 144), num_particles=15)
                obj_radius_logical = 100.0
                should_draw_circle = False
            elif isinstance(obj, Nebula):
                self._draw_nebula(obj, obj_pixel_pos)
                should_draw_circle = False
            elif isinstance(obj, Storm):
                self._draw_storm(obj, obj_pixel_pos)
                should_draw_circle = False
            elif isinstance(obj, Comet):
                obj_color = (240, 248, 255)
                obj_radius_logical = 16.67
            elif isinstance(obj, Wormhole):
                obj_radius_logical = WORMHOLE_RADIUS
                obj_color = PURPLE
                if obj.stability < 100:
                    pixel_radius = int(obj_radius_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    pygame.draw.circle(self.screen, RED, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 2, 1)

            if should_draw_circle and not isinstance(obj, Unit):
                pixel_radius = int(obj_radius_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                pygame.draw.circle(self.screen, obj_color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius)
            elif isinstance(obj, Unit):
                unit_obj: Unit = obj
                obj_color = unit_obj.owner.color if unit_obj.owner else WHITE

                shape_type = 'triangle' if unit_obj.engines_component else 'square'
                scale_factor = HULL_BASE_ICON_SCALES[unit_obj.hull_size]
                current_icon_base_size_logical = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
                dot_count = HULL_DOT_COUNTS[unit_obj.hull_size]
                
                current_icon_base_size_px = int(current_icon_base_size_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
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
                    icon_dot_radius_px = int(ICON_DOT_RADIUS * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    icon_dot_spacing_px = int(ICON_DOT_SPACING * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    
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
                
                # If health bar is drawn, account for its height and vertical position
                if unit_obj in self.game.selected_objects and unit_obj.max_hit_points > 0:
                    health_bar_bottom = obj_pixel_pos.y + current_icon_base_size_px + 14
                    if health_bar_bottom > bottom_y:
                        bottom_y = health_bar_bottom
                        
                # If dots are drawn, account for their radius and vertical position
                if dot_count > 0:
                    icon_dot_radius_px = int(ICON_DOT_RADIUS * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    dot_base_y_offset = current_icon_base_size_px * 0.6 if shape_type == 'triangle' else current_icon_base_size_px
                    dot_bottom = obj_pixel_pos.y + dot_base_y_offset + 2 * icon_dot_radius_px + 2
                    if dot_bottom > bottom_y:
                        bottom_y = dot_bottom
                        
                name_font_size = max(1, int(12 * TEXT_SCALE))
                name_font = pygame.font.Font(None, name_font_size)
                name_surface = name_font.render(unit_obj.name, True, obj_color)
                name_rect = name_surface.get_rect()
                name_rect.midtop = (obj_pixel_pos.x, bottom_y + 4)
                self.screen.blit(name_surface, name_rect)


            if obj == self.game.sector_view_mouse_hover_object:
                pixel_radius = int(obj_radius_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                pygame.draw.circle(self.overlay_surface, HOVER_HIGHLIGHT_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)

            if obj in self.game.selected_objects:
                pixel_radius = int(obj_radius_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                pygame.draw.circle(self.overlay_surface, SELECTION_HIGHLIGHT_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 5, 2)

            if isinstance(obj, Unit) and (obj in self.game.selected_objects or obj == self.game.sector_view_mouse_hover_object):
                unit_obj: Unit = obj
                if unit_obj.engines_component and unit_obj.engines_component.move_target:
                    target_pos_in_sector = unit_obj.engines_component.move_target
                    target_pixel_pos = sector_coords_to_pixels(target_pos_in_sector)
                    pygame.draw.line(self.overlay_surface, MOVE_ORDER_LINE_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), (target_pixel_pos.x, target_pixel_pos.y), 1)
                    pygame.draw.circle(self.overlay_surface, MOVE_ORDER_LINE_COLOR, (target_pixel_pos.x, target_pixel_pos.y), 3)
                elif unit_obj.hyperdrive_component and unit_obj.hyperdrive_component.wormhole_jump_target:
                    target_wh_for_jump = unit_obj.hyperdrive_component.wormhole_jump_target
                    if target_wh_for_jump.in_system == self.game.current_system_name and target_wh_for_jump.in_hex == self.game.current_sector_coord:
                        wh_pixel_pos = sector_coords_to_pixels(target_wh_for_jump.position)
                        pygame.draw.line(self.overlay_surface, WORMHOLE_JUMP_ORDER_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), (wh_pixel_pos.x, wh_pixel_pos.y), 2)
                        wh_pixel_radius = int(WORMHOLE_RADIUS * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                        pygame.draw.circle(self.overlay_surface, WORMHOLE_JUMP_ORDER_COLOR, (wh_pixel_pos.x, wh_pixel_pos.y), wh_pixel_radius + 4, 1)
                elif unit_obj.commander_component and unit_obj.commander_component.current_order:
                    order = unit_obj.commander_component.current_order
                    if order.order_type == OrderType.MOVE and order.status in [OrderStatus.PENDING, OrderStatus.IN_PROGRESS]:
                        dest_sys = order.parameters["destination_system_name"]
                        dest_hex = order.parameters["destination_hex_coord"]
                        dest_pos = order.parameters["destination_position"]

                        if dest_sys == self.game.current_system_name and dest_hex == self.game.current_sector_coord and dest_pos:
                            target_pixel_pos = sector_coords_to_pixels(dest_pos)
                            pygame.draw.line(self.overlay_surface, MOVE_ORDER_LINE_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), (target_pixel_pos.x, target_pixel_pos.y), 1)
                            pygame.draw.circle(self.overlay_surface, MOVE_ORDER_LINE_COLOR, (target_pixel_pos.x, target_pixel_pos.y), 3)
                        elif dest_sys != self.game.current_system_name:
                            if unit_obj.in_galaxy:
                                local_wh_for_jump = order.find_wormhole_to_system(unit_obj.in_system, dest_sys, unit_obj.in_galaxy, unit_obj.hull_size)
                                if local_wh_for_jump and local_wh_for_jump.in_system == self.game.current_system_name and local_wh_for_jump.in_hex == self.game.current_sector_coord:
                                    wh_pixel_pos = sector_coords_to_pixels(local_wh_for_jump.position)
                                    pygame.draw.line(self.overlay_surface, WORMHOLE_JUMP_ORDER_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), (wh_pixel_pos.x, wh_pixel_pos.y), 2)
                                    wh_pixel_radius = int(WORMHOLE_RADIUS * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
                                    pygame.draw.circle(self.overlay_surface, WORMHOLE_JUMP_ORDER_COLOR, (wh_pixel_pos.x, wh_pixel_pos.y), wh_pixel_radius + 4, 1)
                if unit_obj.commander_component and (unit_obj in self.game.selected_objects or unit_obj == self.game.sector_view_mouse_hover_object):
                    self._draw_sector_view_order_lines(unit_obj, obj_pixel_pos.x, obj_pixel_pos.y)
                                
        external_units_with_orders_to_this_sector = []
        for selected_unit in self.game.selected_objects:
            if isinstance(selected_unit, Unit):
                is_external_unit = (
                    selected_unit.in_system != self.game.current_system_name or
                    selected_unit.in_hex != self.game.current_sector_coord
                )
                if is_external_unit and selected_unit.commander_component:
                    has_orders_to_current_sector = False
                    if selected_unit.commander_component.current_order:
                        order = selected_unit.commander_component.current_order
                        if self._order_targets_sector(order, self.game.current_system_name, self.game.current_sector_coord):
                            has_orders_to_current_sector = True
                        for sub_order in order.sub_orders:
                            if self._order_targets_sector(sub_order, self.game.current_system_name, self.game.current_sector_coord):
                                has_orders_to_current_sector = True
                                break
                    if not has_orders_to_current_sector:
                        for queued_order in selected_unit.commander_component.orders_queue:
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
                        external_units_with_orders_to_this_sector.append(selected_unit)

        self._draw_sector_view_order_lines_from_other_sectors(external_units_with_orders_to_this_sector)

    def _order_targets_sector(self, order, system_name, hex_coord):
        """Helper method to check if an order targets the specified system and hex."""
        if order.order_type not in [OrderType.MOVE, OrderType.REACH_WAYPOINT]:
            return False
            
        dsys = order.parameters["destination_system_name"]
        dhex = order.parameters["destination_hex_coord"]
        
        return dsys == system_name and dhex == hex_coord
        
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
        elif order.order_type == OrderType.ATTACK:
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

        for sub_order in list(order.sub_orders):
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
                    dest_pixel_point = sector_coords_to_pixels(waypoint['position'])
                    
                    if waypoint['order_type'] == OrderType.ATTACK:
                        line_color = RED
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
                connect_to_unit = unit_in_current_sector and is_first_waypoint_overall and segment_index == 0
                
                for i, waypoint in enumerate(segment):
                    dest_pixel_point = sector_coords_to_pixels(waypoint['position'])
                    
                    if waypoint['order_type'] == OrderType.ATTACK:
                        line_color = RED
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
                            all_waypoints = self._collect_all_waypoints(unit)
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

    def _draw_nebula(self, nebula, pos_px):
        num_circles = 15
        max_offset_logical = NEBULA_RADIUS / 2.0
        base_radius_logical = NEBULA_RADIUS

        # Seed the random number generator for consistent nebula appearance
        random.seed(nebula.id)

        for _ in range(num_circles):
            offset_x_logical = random.uniform(-max_offset_logical, max_offset_logical)
            offset_y_logical = random.uniform(-max_offset_logical, max_offset_logical)
            
            offset_x_px = offset_x_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL
            offset_y_px = offset_y_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL
            circle_pos = (pos_px.x + offset_x_px, pos_px.y + offset_y_px)

            radius_variation = random.uniform(0.5, 1.2)
            circle_radius_logical = base_radius_logical * radius_variation
            circle_radius_px = int(circle_radius_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)

            alpha = random.randint(20, 50)
            color = NEBULA_COLORS[nebula.nebula_type]
            color = (color[0], color[1], color[2], alpha)

            # Create a separate surface for each circle to handle alpha blending correctly
            circle_surface = pygame.Surface((circle_radius_px * 2, circle_radius_px * 2), pygame.SRCALPHA)
            pygame.draw.circle(circle_surface, color, (circle_radius_px, circle_radius_px), circle_radius_px)
            self.overlay_surface.blit(circle_surface, (circle_pos[0] - circle_radius_px, circle_pos[1] - circle_radius_px))
        
        # Reset seed
        random.seed()

    def _draw_celestial_field(self, field, pos_px, base_color, num_particles=40):
        """Draws a celestial field with random objects (asteroids/ice bodies/debris)"""
        num_objects = num_particles
        field_radius = 100  # Logical radius of the field
        time_ms = pygame.time.get_ticks()

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
            
            offset_x_px = offset_x * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL
            offset_y_px = offset_y * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL
            object_pos = (pos_px.x + offset_x_px, pos_px.y + offset_y_px)

            # Draw the object
            pygame.draw.circle(self.screen, object_color, object_pos, object_size)

        random.seed()

    def _draw_storm(self, storm, pos_px):
        num_circles = 25
        base_radius_logical = STORM_RADIUS
        time_ms = pygame.time.get_ticks()

        # Seed the random number generator for consistent storm appearance
        random.seed(storm.id)

        for i in range(num_circles):
            # Generate consistent random properties for each circle
            initial_angle = random.uniform(0, 360)
            initial_radius_logical = random.uniform(base_radius_logical * 0.1, base_radius_logical * 0.9)
            rotation_speed = random.uniform(-3.0, 3.0)  # degrees per 100ms
            circle_base_radius_logical = base_radius_logical * random.uniform(0.2, 0.5)
            
            circle_base_radius_px = int(circle_base_radius_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
            
            alpha = random.randint(30, 60)
            color = STORM_COLORS[storm.storm_type]
            color = (color[0], color[1], color[2], alpha)

            # Animate the circle's position
            current_angle_rad = math.radians(initial_angle + (time_ms / 100.0) * rotation_speed)
            offset_x_logical = initial_radius_logical * math.cos(current_angle_rad)
            offset_y_logical = initial_radius_logical * math.sin(current_angle_rad)
            
            offset_x_px = offset_x_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL
            offset_y_px = offset_y_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL
            circle_pos = (pos_px.x + offset_x_px, pos_px.y + offset_y_px)

            # Draw the circle
            circle_surface = pygame.Surface((circle_base_radius_px * 2, circle_base_radius_px * 2), pygame.SRCALPHA)
            pygame.draw.circle(circle_surface, color, (circle_base_radius_px, circle_base_radius_px), circle_base_radius_px)
            self.overlay_surface.blit(circle_surface, (circle_pos[0] - circle_base_radius_px, circle_pos[1] - circle_base_radius_px))

        # Reset seed
        random.seed()

        # Draw lightning flashes on top
        if random.random() < 0.05:
            num_bolts = random.randint(1, 3)
            base_radius_px = int(base_radius_logical * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
            for _ in range(num_bolts):
                angle = random.uniform(0, 2 * math.pi)
                length_px = random.uniform(base_radius_px * 1.0, base_radius_px * 1.5)
                end_pos_x = pos_px.x + length_px * math.cos(angle)
                end_pos_y = pos_px.y + length_px * math.sin(angle)
                pygame.draw.line(self.overlay_surface, STORM_LIGHTNING_COLOR, (pos_px.x, pos_px.y), (end_pos_x, end_pos_y), 2)
