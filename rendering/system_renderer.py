import pygame
import random
import math
from constants import (
    DARK_GRAY, NEBULA_COLORS, STORM_COLORS, YELLOW, CYAN, PURPLE, RED, WHITE,
    SELECTION_HIGHLIGHT_COLOR, HOVER_HIGHLIGHT_COLOR, GRAY,
    HEX_JUMP_ORDER_LINE_COLOR, StarType, PlanetType, NEBULA_RADIUS, STORM_RADIUS,
    STORM_LIGHTNING_COLOR
)
from hexgrid_utils import get_hex_vertices, hex_to_pixel
from entities import (
    Star, Planet, Wormhole, Unit, CelestialBody, OrderType, Moon, Asteroid, 
    AsteroidField, IceField, Nebula, Storm, Comet, DebrisField
)
from galaxy import Hex

class SystemViewRenderer:
    def __init__(self, game_instance):
        self.game = game_instance
        self.screen = game_instance.screen
        self.overlay_surface = game_instance.overlay_surface

    def draw_system_view(self):
        """Draws the hex grid for the current system."""
        if not self.game.current_system_name: return
        system = self.game.galaxy.systems[self.game.current_system_name]

        # 1. Draw Hex Grid Lines
        for hex_coord, hex_obj in system.hexes.items():
             q, r = hex_coord
             hex_points_objects = get_hex_vertices(q, r)
             hex_points_tuples = [p.to_tuple() for p in hex_points_objects]
             pygame.draw.polygon(self.screen, DARK_GRAY, hex_points_tuples, 1)

        # 2. Draw Contents of Hexes (Stars, Planets, Units)
        for hex_coord, hex_obj in system.hexes.items():
            q, r = hex_coord
            hex_center_pixel = hex_to_pixel(q, r)

            # Draw celestial bodies
            for body in hex_obj.celestial_bodies:
                body_color = DARK_GRAY
                body_radius = 3
                should_draw_circle = True

                if isinstance(body, Star):
                    star_color_map = {
                        StarType.BLUE_GIANT: (173, 216, 255),
                        StarType.YELLOW_GIANT: YELLOW,
                        StarType.RED_DWARF: (255, 127, 80),
                        StarType.NEUTRON_STAR: WHITE,
                    }
                    body_color = star_color_map.get(body.star_type, YELLOW)
                    body_radius = 8
                elif isinstance(body, Planet):
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
                    body_color = planet_color_map.get(body.planet_type, CYAN)
                    body_radius = 4
                    if body.owner:
                        pygame.draw.circle(self.screen, body.owner.color, (hex_center_pixel.x, hex_center_pixel.y), body_radius + 3, 1)
                elif isinstance(body, Moon):
                    body_color = (200, 200, 200)
                    body_radius = 2
                    if body.owner:
                        pygame.draw.circle(self.screen, body.owner.color, (hex_center_pixel.x, hex_center_pixel.y), body_radius + 3, 1)
                elif isinstance(body, Asteroid):
                    body_color = (90, 60, 50)
                    body_radius = 2
                    if body.owner:
                        pygame.draw.circle(self.screen, body.owner.color, (hex_center_pixel.x, hex_center_pixel.y), body_radius + 3, 1)
                elif isinstance(body, AsteroidField):
                    self._draw_celestial_field(body, hex_center_pixel, (100, 100, 100))
                    should_draw_circle = False
                elif isinstance(body, IceField):
                    self._draw_celestial_field(body, hex_center_pixel, (173, 216, 230), num_particles=7)
                    should_draw_circle = False
                elif isinstance(body, DebrisField):
                    self._draw_celestial_field(body, hex_center_pixel, (112, 128, 144), num_particles=5)
                    should_draw_circle = False
                elif isinstance(body, Nebula):
                    self._draw_nebula(body, hex_center_pixel)
                    should_draw_circle = False
                elif isinstance(body, Storm):
                    self._draw_storm(body, hex_center_pixel)
                    should_draw_circle = False
                elif isinstance(body, Comet):
                    body_color = (240, 248, 255)
                    body_radius = 2
                elif isinstance(body, Wormhole):
                    body_color = PURPLE
                    body_radius = 4
                    if body.stability < 100:
                        pygame.draw.circle(self.screen, RED, (hex_center_pixel.x, hex_center_pixel.y), body_radius + 2, 1)

                if should_draw_circle:
                    pygame.draw.circle(self.screen, body_color, (hex_center_pixel.x, hex_center_pixel.y), body_radius)

                if body in self.game.selected_objects:
                    pygame.draw.circle(self.overlay_surface, SELECTION_HIGHLIGHT_COLOR, (hex_center_pixel.x, hex_center_pixel.y), body_radius + 2, 2)

            # Draw units
            unit_list = hex_obj.units
            num_units_in_hex = len(unit_list)

            if num_units_in_hex > 0:
                new_system_view_icon_base_size = 3.0
                icon_draw_width = new_system_view_icon_base_size * 2 
                icon_draw_height = new_system_view_icon_base_size * 2 
                icon_padding_x = 3
                icon_padding_y = 3 
                icon_slot_width = icon_draw_width + icon_padding_x
                icon_slot_height = icon_draw_height + icon_padding_y
                icons_per_row = 3

                num_total_rows = (num_units_in_hex + icons_per_row - 1) // icons_per_row
                total_block_visual_height = (num_total_rows * icon_draw_height) + ((num_total_rows - 1) * icon_padding_y if num_total_rows > 0 else 0)
                
                block_start_y = hex_center_pixel.y - (total_block_visual_height / 2.0)

                for i, unit in enumerate(unit_list):
                    row_index = i // icons_per_row
                    col_index = i % icons_per_row

                    num_icons_in_this_row = min(icons_per_row, num_units_in_hex - (row_index * icons_per_row))
                    current_row_visual_width = (num_icons_in_this_row * icon_draw_width) + ((num_icons_in_this_row - 1) * icon_padding_x if num_icons_in_this_row > 0 else 0)
                    
                    row_start_x = hex_center_pixel.x - (current_row_visual_width / 2.0)

                    icon_center_x = row_start_x + (col_index * icon_slot_width) + (icon_draw_width / 2.0)
                    icon_center_y = block_start_y + (row_index * icon_slot_height) + (icon_draw_height / 2.0)

                    unit_screen_x = icon_center_x
                    
                    shape_type = 'triangle' if unit.engines_component else 'square'
                    current_icon_base_size = new_system_view_icon_base_size 

                    if shape_type == 'triangle':
                        unit_screen_y = icon_center_y + current_icon_base_size * 0.2 
                    else: # square
                        unit_screen_y = icon_center_y
                    
                    unit_color = unit.owner.color if unit.owner else WHITE
                
                    if shape_type == 'triangle':
                        p1 = (unit_screen_x, unit_screen_y - current_icon_base_size)
                        p2 = (unit_screen_x - int(current_icon_base_size * 0.8), unit_screen_y + int(current_icon_base_size * 0.6))
                        p3 = (unit_screen_x + int(current_icon_base_size * 0.8), unit_screen_y + int(current_icon_base_size * 0.6))
                        main_shape_points = [p1, p2, p3]
                        pygame.draw.polygon(self.screen, unit_color, main_shape_points)
                        if unit in self.game.selected_objects:
                            pygame.draw.polygon(self.overlay_surface, SELECTION_HIGHLIGHT_COLOR, main_shape_points, 2)
                        
                    else: # 'square'
                        half_size = int(current_icon_base_size)
                        p1 = (unit_screen_x - half_size, unit_screen_y - half_size)
                        p2 = (unit_screen_x + half_size, unit_screen_y - half_size)
                        p3 = (unit_screen_x + half_size, unit_screen_y + half_size)
                        p4 = (unit_screen_x - half_size, unit_screen_y + half_size)
                        main_shape_points = [p1, p2, p3, p4]
                        pygame.draw.polygon(self.screen, unit_color, main_shape_points)
                        if unit in self.game.selected_objects:
                            pygame.draw.polygon(self.overlay_surface, SELECTION_HIGHLIGHT_COLOR, main_shape_points, 2)

        # 3. Highlight Hovered Hex
        if self.game.system_view_mouse_hover_hex:
            q, r = self.game.system_view_mouse_hover_hex
            hex_points_objects = get_hex_vertices(q, r)
            hex_points_tuples = [p.to_tuple() for p in hex_points_objects]
            pygame.draw.polygon(self.overlay_surface, HOVER_HIGHLIGHT_COLOR, hex_points_tuples, 2)

        # 4. Highlight Selected Hex
        for obj in self.game.selected_objects:
            if isinstance(obj, Hex):
                if obj.in_system == self.game.current_system_name:
                     hex_points_objects = get_hex_vertices(obj.q, obj.r)
                     hex_points_tuples = [p.to_tuple() for p in hex_points_objects]
                     pygame.draw.polygon(self.overlay_surface, SELECTION_HIGHLIGHT_COLOR, hex_points_tuples, 2)

        # 5. Highlight Hex Containing the Selected Unit/Body
        for obj in self.game.selected_objects:
            selected_object_hex = None
            if isinstance(obj, Unit):
                unit: Unit = obj
                if unit.in_system == self.game.current_system_name:
                    selected_object_hex = unit.in_hex
            elif isinstance(obj, CelestialBody):
                body: CelestialBody = obj
                if body.in_system == self.game.current_system_name:
                    selected_object_hex = body.in_hex

            if selected_object_hex:
                q, r = selected_object_hex
                hex_points_objects = get_hex_vertices(q, r)
                hex_points_tuples = [p.to_tuple() for p in hex_points_objects]
                pygame.draw.polygon(self.overlay_surface, GRAY, hex_points_tuples, 2)

        # 6. Draw Order Lines (Hex Jumps)
        self._draw_system_view_order_lines(system)

    def _draw_system_view_order_lines(self, system):
        units_to_process = []
        
        for obj in self.game.selected_objects:
            if isinstance(obj, Unit):
                if obj.commander_component:
                    units_to_process.append((obj, obj.in_hex))
        
        if self.game.system_view_mouse_hover_hex:
            units_in_hovered_hex = system.get_units_in_hex(self.game.system_view_mouse_hover_hex)
            for unit in units_in_hovered_hex:
                if unit.commander_component and unit not in [u for u, _ in units_to_process]:
                    units_to_process.append((unit, self.game.system_view_mouse_hover_hex))
        
        if not units_to_process:
            return
            
        for unit, current_hex in units_to_process:
            all_hex_waypoints = []
            
            def collect_all_hex_waypoints(order, start_hex, start_system, sequence_index, is_current=False):
                end_of_sub_orders_pos = start_hex
                end_of_sub_orders_sys = start_system
                
                for sub_order in list(order.sub_orders):
                    end_of_sub_orders_pos, end_of_sub_orders_sys, sequence_index = collect_all_hex_waypoints(
                        sub_order,
                        end_of_sub_orders_pos,
                        end_of_sub_orders_sys,
                        sequence_index,
                        is_current
                    )

                if order.order_type == OrderType.REACH_WAYPOINT:
                    dsys = order.parameters["destination_system_name"]
                    dhex = order.parameters["destination_hex_coord"]

                    if dsys and dhex and (dhex != start_hex or dsys != start_system):
                        is_wormhole_jump = start_system != dsys
                        all_hex_waypoints.append({
                            'start_hex': start_hex,
                            'start_system': start_system,
                            'end_hex': dhex,
                            'end_system': dsys,
                            'is_current': is_current,
                            'is_sub_order': order.parent_order is not None,
                            'sequence_index': sequence_index,
                            'is_wormhole_jump': is_wormhole_jump,
                            'order_type': order.order_type
                        })
                        final_pos = dhex
                        final_sys = dsys
                        sequence_index += 1
                    else:
                        final_pos = start_hex
                        final_sys = start_system
                
                elif order.order_type == OrderType.MOVE:
                    dsys = order.parameters["destination_system_name"]
                    dhex = order.parameters["destination_hex_coord"]

                    start_of_final_leg_pos = end_of_sub_orders_pos
                    start_of_final_leg_sys = end_of_sub_orders_sys

                    if dsys and dhex and (dhex != start_of_final_leg_pos or dsys != start_of_final_leg_sys):
                        is_wormhole_jump = start_of_final_leg_sys != dsys
                        all_hex_waypoints.append({
                            'start_hex': start_of_final_leg_pos,
                            'start_system': start_of_final_leg_sys,
                            'end_hex': dhex,
                            'end_system': dsys,
                            'is_current': is_current,
                            'is_sub_order': False,
                            'sequence_index': sequence_index,
                            'is_wormhole_jump': is_wormhole_jump,
                            'order_type': order.order_type
                        })
                        final_pos = dhex
                        final_sys = dsys
                        sequence_index += 1
                    else:
                        final_pos = end_of_sub_orders_pos
                        final_sys = end_of_sub_orders_sys
                elif order.order_type == OrderType.ATTACK:
                    target_unit_id = order.parameters["target_unit_id"]
                    target_unit = self.game.galaxy.get_unit_by_id(target_unit_id)
                    if target_unit:
                        all_hex_waypoints.append({
                            'start_hex': start_hex,
                            'start_system': start_system,
                            'end_hex': target_unit.in_hex,
                            'end_system': target_unit.in_system,
                            'is_current': is_current,
                            'is_sub_order': False,
                            'sequence_index': sequence_index,
                            'is_wormhole_jump': False,
                            'order_type': order.order_type
                        })
                        final_pos = target_unit.in_hex
                        final_sys = target_unit.in_system
                        sequence_index += 1
                    else:
                        final_pos = end_of_sub_orders_pos
                        final_sys = end_of_sub_orders_sys
                else:
                    final_pos = end_of_sub_orders_pos
                    final_sys = end_of_sub_orders_sys

                return final_pos, final_sys, sequence_index
                
            current_position = current_hex
            current_system_name = unit.in_system
            sequence_counter = 0
            
            if unit.commander_component.current_order:
                current_position, current_system_name, sequence_counter = collect_all_hex_waypoints(
                    unit.commander_component.current_order, 
                    current_position,
                    current_system_name,
                    sequence_counter, 
                    True
                )
            
            for queued_order in list(unit.commander_component.orders_queue):
                current_position, current_system_name, sequence_counter = collect_all_hex_waypoints(
                    queued_order, 
                    current_position,
                    current_system_name,
                    sequence_counter, 
                    False
                )
            
            if unit.hyperdrive_component and unit.hyperdrive_component.hex_jump_target:
                target_hex = unit.hyperdrive_component.hex_jump_target[0] if isinstance(unit.hyperdrive_component.hex_jump_target, tuple) else unit.hyperdrive_component.hex_jump_target
                if target_hex != current_hex:
                    if not any(wp['end_hex'] == target_hex and wp['start_hex'] == current_hex for wp in all_hex_waypoints):
                        all_hex_waypoints.insert(0, {
                            'start_hex': current_hex,
                            'start_system': system.name,
                            'end_hex': target_hex,
                            'end_system': system.name,
                            'is_current': True,
                            'is_sub_order': False,
                            'is_wormhole_jump': False,
                            'sequence_index': -1
                        })
            
            filtered_waypoints = []
            
            for wp in all_hex_waypoints:
                if wp['start_hex'] == unit.in_hex:
                    wp['start_system'] = unit.in_system
            
            wormhole_jumps = []
            internal_waypoints = []
            
            for waypoint in all_hex_waypoints:
                if waypoint['start_system'] == system.name and waypoint['end_system'] == system.name:
                    internal_waypoints.append(waypoint)
                elif waypoint['is_wormhole_jump'] and (waypoint['start_system'] == system.name or waypoint['end_system'] == system.name):
                    wormhole_jumps.append(waypoint)
            
            filtered_waypoints.extend(internal_waypoints)
            
            corrected_waypoints = []
            for wp in all_hex_waypoints:
                if wp['start_hex'] == unit.in_hex and wp['start_system'] != unit.in_system:
                    continue
                if not wp['is_wormhole_jump'] and wp['start_system'] != unit.in_system and wp['start_hex'] == unit.in_hex:
                    continue
                corrected_waypoints.append(wp)
                
            all_hex_waypoints = corrected_waypoints
            
            for jump in wormhole_jumps:
                if jump['start_system'] == system.name:
                    wormhole_hex = None
                    for hex_coord, hex_obj in system.hexes.items():
                        for body in hex_obj.celestial_bodies:
                            if isinstance(body, Wormhole) and body.exit_system_name == jump['end_system']:
                                wormhole_hex = hex_coord
                                break
                        if wormhole_hex:
                            break
                    
                    if wormhole_hex:
                        filtered_waypoints.append({
                            'start_hex': jump['start_hex'],
                            'start_system': system.name,
                            'end_hex': wormhole_hex,
                            'end_system': system.name,
                            'is_current': jump['is_current'],
                            'is_sub_order': jump['is_sub_order'],
                            'sequence_index': jump['sequence_index'],
                            'is_wormhole_jump': False
                        })
                elif jump['end_system'] == system.name:
                    wormhole_hex = None
                    for hex_coord, hex_obj in system.hexes.items():
                        for body in hex_obj.celestial_bodies:
                            if isinstance(body, Wormhole) and body.exit_system_name == jump['start_system']:
                                wormhole_hex = hex_coord
                                break
                        if wormhole_hex:
                            break
                    
                    if wormhole_hex:
                        filtered_waypoints.append({
                            'start_hex': wormhole_hex,
                            'start_system': system.name,
                            'end_hex': jump['end_hex'],
                            'end_system': system.name,
                            'is_current': jump['is_current'],
                            'is_sub_order': jump['is_sub_order'],
                            'sequence_index': jump['sequence_index'],
                            'is_wormhole_jump': False
                        })
                
            assert all(wp['start_system'] == system.name and wp['end_system'] == system.name for wp in filtered_waypoints), "Filtering error: some waypoints are outside current system!"

            filtered_waypoints.sort(key=lambda wp: wp['sequence_index'])
            
            path_segments = []
            current_segment = []
            
            for i, waypoint in enumerate(filtered_waypoints):
                if i == 0:
                    current_segment.append(waypoint)
                else:
                    prev_wp = filtered_waypoints[i-1]
                    if waypoint['sequence_index'] == prev_wp['sequence_index'] + 1:
                        current_segment.append(waypoint)
                    else:
                        if current_segment:
                            path_segments.append(current_segment)
                        current_segment = [waypoint]
            
            if current_segment:
                path_segments.append(current_segment)
                
            for segment_index, segment in enumerate(path_segments):
                for i, jump in enumerate(segment):
                    start_q, start_r = jump['start_hex']
                    end_q, end_r = jump['end_hex']
                        
                    if jump['is_wormhole_jump']:
                        if jump['start_system'] == system.name:
                            wormhole_hex = None
                            for hex_coord, hex_obj in system.hexes.items():
                                for body in hex_obj.celestial_bodies:
                                    if isinstance(body, Wormhole) and body.exit_system_name == jump['end_system']:
                                        wormhole_hex = hex_coord
                                        break
                                if wormhole_hex:
                                    break
                            
                            if wormhole_hex:
                                start_pixel_point = hex_to_pixel(start_q, start_r)
                                end_pixel_point = hex_to_pixel(wormhole_hex[0], wormhole_hex[1])
                                start_x, start_y = start_pixel_point.x, start_pixel_point.y
                                end_x, end_y = end_pixel_point.x, end_pixel_point.y
                            else:
                                continue
                        elif jump['end_system'] == system.name:
                            wormhole_hex = None
                            for hex_coord, hex_obj in system.hexes.items():
                                for body in hex_obj.celestial_bodies:
                                    if isinstance(body, Wormhole) and body.exit_system_name == jump['start_system']:
                                        wormhole_hex = hex_coord
                                        break
                                if wormhole_hex:
                                    break
                            
                            if wormhole_hex:
                                start_pixel_point = hex_to_pixel(wormhole_hex[0], wormhole_hex[1])
                                end_pixel_point = hex_to_pixel(end_q, end_r)
                                start_x, start_y = start_pixel_point.x, start_pixel_point.y
                                end_x, end_y = end_pixel_point.x, end_pixel_point.y
                            else:
                                continue
                    else:
                        start_pixel_point = hex_to_pixel(start_q, start_r)
                        end_pixel_point = hex_to_pixel(end_q, end_r)
                        start_x, start_y = start_pixel_point.x, start_pixel_point.y
                        end_x, end_y = end_pixel_point.x, end_pixel_point.y
                    
                    if jump.get('order_type') == OrderType.ATTACK:
                        line_color = RED
                        line_width = 2
                    elif jump['is_current']:
                        line_width = 2
                        line_color = HEX_JUMP_ORDER_LINE_COLOR
                    else:
                        line_width = 1
                        line_color = (max(HEX_JUMP_ORDER_LINE_COLOR[0] - 40, 0),
                                    max(HEX_JUMP_ORDER_LINE_COLOR[1] - 40, 0),
                                    max(HEX_JUMP_ORDER_LINE_COLOR[2] - 40, 0))
                    
                    pygame.draw.line(self.overlay_surface, line_color, (start_x, start_y), (end_x, end_y), line_width)
                    
                    circle_size = 5 if jump['is_current'] else 3
                    pygame.draw.circle(self.overlay_surface, line_color, (end_x, end_y), circle_size, 1)

    def _draw_nebula(self, nebula, pos_px):
        num_circles = 15
        # Use a smaller radius for system view
        base_radius = NEBULA_RADIUS / 20.0
        max_offset = base_radius * 0.6

        # Seed the random number generator for consistent nebula appearance
        random.seed(nebula.id)

        for _ in range(num_circles):
            offset_x = random.uniform(-max_offset, max_offset)
            offset_y = random.uniform(-max_offset, max_offset)
            circle_pos = (pos_px.x + offset_x, pos_px.y + offset_y)

            radius_variation = random.uniform(0.5, 1.2)
            circle_radius = int(base_radius * radius_variation)

            alpha = random.randint(20, 50)
            color = NEBULA_COLORS[nebula.nebula_type]
            color = (color[0], color[1], color[2], alpha)

            # Create a separate surface for each circle to handle alpha blending correctly
            circle_surface = pygame.Surface((circle_radius * 2, circle_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(circle_surface, color, (circle_radius, circle_radius), circle_radius)
            self.overlay_surface.blit(circle_surface, (circle_pos[0] - circle_radius, circle_pos[1] - circle_radius))
        
        # Reset seed
        random.seed()

    def _draw_celestial_field(self, field, pos_px, base_color, num_particles=15):
        num_asteroids = num_particles
        field_radius = 10
        time_ms = pygame.time.get_ticks()

        random.seed(field.id)

        for i in range(num_asteroids):
            initial_angle = random.uniform(0, 360)
            initial_radius = random.uniform(field_radius * 0.2, field_radius)
            rotation_speed = random.uniform(-3.0, 3.0)
            asteroid_size = 1
            color_variation = random.randint(-20, 20)
            asteroid_color = (max(0, min(255, base_color[0] + color_variation)),
                              max(0, min(255, base_color[1] + color_variation)),
                              max(0, min(255, base_color[2] + color_variation)))

            current_angle_rad = math.radians(initial_angle + (time_ms / 500.0) * rotation_speed)
            offset_x = initial_radius * math.cos(current_angle_rad)
            offset_y = initial_radius * math.sin(current_angle_rad)
            asteroid_pos = (pos_px.x + offset_x, pos_px.y + offset_y)

            pygame.draw.circle(self.screen, asteroid_color, asteroid_pos, asteroid_size)

        random.seed()

    def _draw_storm(self, storm, pos_px):
        num_circles = 25
        base_radius = STORM_RADIUS / 20.0
        time_ms = pygame.time.get_ticks()

        random.seed(storm.id)

        for i in range(num_circles):
            initial_angle = random.uniform(0, 360)
            initial_radius = random.uniform(base_radius * 0.1, base_radius * 0.9)
            rotation_speed = random.uniform(-3.0, 3.0)
            circle_base_radius = int(base_radius * random.uniform(0.2, 0.5))
            alpha = random.randint(30, 60)
            color = STORM_COLORS[storm.storm_type]
            color = (color[0], color[1], color[2], alpha)

            current_angle_rad = math.radians(initial_angle + (time_ms / 100.0) * rotation_speed)
            offset_x = initial_radius * math.cos(current_angle_rad)
            offset_y = initial_radius * math.sin(current_angle_rad)
            circle_pos = (pos_px.x + offset_x, pos_px.y + offset_y)

            if circle_base_radius < 1: continue

            circle_surface = pygame.Surface((circle_base_radius * 2, circle_base_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(circle_surface, color, (circle_base_radius, circle_base_radius), circle_base_radius)
            self.overlay_surface.blit(circle_surface, (circle_pos[0] - circle_base_radius, circle_pos[1] - circle_base_radius))

        random.seed()

        if random.random() < 0.05:
            num_bolts = random.randint(1, 3)
            for _ in range(num_bolts):
                angle = random.uniform(0, 2 * math.pi)
                length = random.uniform(base_radius * 1.0, base_radius * 1.5)
                end_pos_x = pos_px.x + length * math.cos(angle)
                end_pos_y = pos_px.y + length * math.sin(angle)
                pygame.draw.line(self.overlay_surface, STORM_LIGHTNING_COLOR, (pos_px.x, pos_px.y), (end_pos_x, end_pos_y), 1)
