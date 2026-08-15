import sys
import math
from constants import (
    SECTOR_CIRCLE_CENTER_IN_PX, SECTOR_CIRCLE_RADIUS_LOGICAL,
    HOVER_HIGHLIGHT_COLOR, SELECTION_HIGHLIGHT_COLOR,
    MOVE_ORDER_LINE_COLOR, WORMHOLE_JUMP_ORDER_COLOR, RED,
    FOG_OF_WAR_COLOR, XP_SPEED_BONUS,
    TOP_BAR_HEIGHT, INFO_BOX_WIDTH, TEXT_SCALE
)
from geometry import distance, Position
from entities import Unit, OrderType

MAX_SAFE_CIRCLE_RADIUS_PX = 250_000


def _sr():
    return sys.modules['rendering.sector_renderer']


class SectorOverlayRenderer:
    """Handles rendering of overlays: selection drag rectangle, selection brackets,
    hover highlights, sensor/weapon range circles, order path lines, turn notches,
    and Fog of War rasterization.
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

    def draw_selection_box(self):
        """Draws the transparent blue drag selection rectangle if active."""
        if self.game.is_dragging_selection_box and self.game.selection_box_start_pos:
            mouse_pos = _sr().pygame.mouse.get_pos()
            start_pos = self.game.selection_box_start_pos.to_tuple()
            
            rect_x = min(start_pos[0], mouse_pos[0])
            rect_y = min(start_pos[1], mouse_pos[1])
            rect_w = abs(start_pos[0] - mouse_pos[0])
            rect_h = abs(start_pos[1] - mouse_pos[1])
            selection_rect = _sr().pygame.Rect(rect_x, rect_y, rect_w, rect_h)

            selection_surface = _sr().pygame.Surface(selection_rect.size, _sr().pygame.SRCALPHA)
            selection_surface.fill((0, 100, 255, 64))
            self.overlay_surface.blit(selection_surface, selection_rect.topleft)

            _sr().pygame.draw.rect(self.overlay_surface, (0, 150, 255), selection_rect, 1)

    def draw_hover_highlight(self, obj, obj_pixel_pos, dynamic_radius, obj_radius_logical):
        """Draws a hover highlight circle around the hovered object."""
        if obj == self.game.sector_view_mouse_hover_object:
            pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            _sr().pygame.draw.circle(self.overlay_surface, HOVER_HIGHLIGHT_COLOR, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)

    def draw_selection_brackets(self, obj, obj_pixel_pos, dynamic_radius, obj_radius_logical):
        """Draws four corner selection brackets around selected objects."""
        if obj in self.game.selected_objects:
            pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            r = pixel_radius + 5
            tick_length = 10
            
            left = obj_pixel_pos.x - r
            right = obj_pixel_pos.x + r
            top = obj_pixel_pos.y - r
            bottom = obj_pixel_pos.y + r
            
            # Top-Left corner bracket
            _sr().pygame.draw.lines(
                self.overlay_surface,
                SELECTION_HIGHLIGHT_COLOR,
                False,
                [(left + tick_length, top), (left, top), (left, top + tick_length)],
                2
            )
            # Top-Right corner bracket
            _sr().pygame.draw.lines(
                self.overlay_surface,
                SELECTION_HIGHLIGHT_COLOR,
                False,
                [(right - tick_length, top), (right, top), (right, top + tick_length)],
                2
            )
            # Bottom-Left corner bracket
            _sr().pygame.draw.lines(
                self.overlay_surface,
                SELECTION_HIGHLIGHT_COLOR,
                False,
                [(left + tick_length, bottom), (left, bottom), (left, bottom - tick_length)],
                2
            )
            # Bottom-Right corner bracket
            _sr().pygame.draw.lines(
                self.overlay_surface,
                SELECTION_HIGHLIGHT_COLOR,
                False,
                [(right - tick_length, bottom), (right, bottom), (right, bottom - tick_length)],
                2
            )

    def draw_fog_of_war(self, hex_obj, dynamic_radius: float) -> None:
        """Draw a C&C-style grey fog of war over the sector view."""
        screen_width, screen_height = self.screen.get_size()
        screen_size = (screen_width, screen_height)
        screen_rect = _sr().pygame.Rect(0, 0, screen_width, screen_height)

        if self.parent._fog_of_war_surface is None or self.parent._fog_of_war_surface.get_size() != screen_size:
            self.parent._fog_of_war_surface = _sr().pygame.Surface(screen_size, _sr().pygame.SRCALPHA)
            self.parent._fog_cache_key = None
            self.parent._fog_blit_rect = None

        sector_center_px = (int(SECTOR_CIRCLE_CENTER_IN_PX.x + self.game.sector_pan_offset.x),
                            int(SECTOR_CIRCLE_CENTER_IN_PX.y + self.game.sector_pan_offset.y))
        sector_radius_px = max(1, min(int(dynamic_radius), MAX_SAFE_CIRCLE_RADIUS_PX))
        cx, cy = sector_center_px
        r = sector_radius_px

        disc_bbox = _sr().pygame.Rect(cx - r, cy - r, 2 * r, 2 * r)
        fog_rect = screen_rect.clip(disc_bbox)

        if fog_rect.width <= 0 or fog_rect.height <= 0:
            self.parent._fog_cache_key = None
            self.parent._fog_blit_rect = None
            return

        cutouts = []
        current_player = (self.game.players[self.game.current_player_index]
                          if self.game.players and 0 <= self.game.current_player_index < len(self.game.players)
                          else None)

        if current_player:
            for unit in hex_obj.units:
                if unit.owner != current_player:
                    continue
                sensors = unit.sensors_component
                if sensors is None or getattr(sensors, 'is_destroyed', False) or not getattr(sensors, 'has_short_range', False):
                    continue

                short_range = getattr(sensors, 'short_range_radius', 0.0)
                if short_range <= 0:
                    continue

                unit_px = self.parent._coords_to_pixels(unit.position)
                sr_px = max(1, min(int(short_range * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL), MAX_SAFE_CIRCLE_RADIUS_PX))
                ucx, ucy = int(unit_px.x), int(unit_px.y)
                unit_bbox = _sr().pygame.Rect(ucx - sr_px, ucy - sr_px, 2 * sr_px, 2 * sr_px)
                if unit_bbox.colliderect(fog_rect):
                    cutouts.append((ucx, ucy, sr_px))

        key = (
            screen_size,
            self.parent._last_cached_sector,
            round(dynamic_radius, 1),
            round(self.game.sector_pan_offset.x, 1),
            round(self.game.sector_pan_offset.y, 1),
            id(current_player),
            tuple((round(ucx, 1), round(ucy, 1), sr_px) for ucx, ucy, sr_px in cutouts)
        )

        if key == self.parent._fog_cache_key:
            self.parent.zoom_render_stats['fog_cache_hits'] += 1
            if self.parent._fog_blit_rect is not None:
                self.screen.blit(self.parent._fog_of_war_surface, self.parent._fog_blit_rect.topleft, area=self.parent._fog_blit_rect)
            return

        clear_rect = fog_rect.union(self.parent._fog_blit_rect) if self.parent._fog_blit_rect else fog_rect
        self.parent._fog_of_war_surface.fill((0, 0, 0, 0), clear_rect.clip(screen_rect))

        for ucx, ucy, sr_px in cutouts:
            if self.parent._circle_covers_rect((ucx, ucy), sr_px, fog_rect):
                self.parent.zoom_render_stats['fog_rebuilds'] += 1
                self.parent.zoom_render_stats['fog_full_reveal'] += 1
                self.parent._fog_cache_key = key
                self.parent._fog_blit_rect = None
                return

        cutouts.sort(key=lambda c: c[2], reverse=True)
        culled_cutouts = []
        for ucx, ucy, sr_px in cutouts:
            contained = False
            for acx, acy, ar_px in culled_cutouts:
                if ar_px >= sr_px:
                    max_dist = ar_px - sr_px
                    if (ucx - acx) ** 2 + (ucy - acy) ** 2 <= max_dist * max_dist:
                        contained = True
                        break
            if not contained:
                culled_cutouts.append((ucx, ucy, sr_px))

        fog_surf = self.parent._fog_of_war_surface

        self.parent._fill_circle_on_surface(fog_surf, (cx, cy), r, FOG_OF_WAR_COLOR, fog_rect)

        for ucx, ucy, sr_px in culled_cutouts:
            self.parent._fill_circle_on_surface(fog_surf, (ucx, ucy), sr_px, (0, 0, 0, 0), fog_rect)

        self.screen.blit(fog_surf, fog_rect.topleft, area=fog_rect)
        self.parent.zoom_render_stats['fog_rebuilds'] += 1
        self.parent._fog_cache_key = key
        self.parent._fog_blit_rect = fog_rect

    def draw_unit_range_circles(self, unit: Unit, pixel_pos, dynamic_radius: float) -> None:
        """Draw sensor and weapon range circles around a selected owned unit."""
        cx, cy = int(pixel_pos.x), int(pixel_pos.y)

        sensors = unit.sensors_component
        if sensors and sensors.has_short_range:
            sr_px = int(sensors.short_range_radius * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            self.parent._draw_range_ring(cx, cy, sr_px, (0, 200, 255))

        weapons = unit.weapons_component
        if weapons and weapons.turrets:
            drawn_ranges: set[int] = set()
            for turret in weapons.turrets:
                rng_px = int(turret.range * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                if rng_px in drawn_ranges:
                    continue
                drawn_ranges.add(rng_px)
                self.parent._draw_range_ring(cx, cy, rng_px, (255, 80, 40))

        orbital_defense = getattr(unit, 'orbital_defense_component', None)
        if orbital_defense and not orbital_defense.is_destroyed:
            od_px = int(orbital_defense.radius * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            from constants import ORBITAL_DEFENSE_RING_COLOR
            self.parent._draw_range_ring(cx, cy, od_px, ORBITAL_DEFENSE_RING_COLOR)

    def get_waypoint_style(self, waypoint):
        if waypoint['order_type'] == OrderType.ATTACK:
            line_color = RED
            line_width = 2
        elif waypoint['order_type'] == OrderType.PROTECT:
            line_color = (255, 105, 180)
            line_width = 2
        elif waypoint['order_type'] == OrderType.USE_ABILITY:
            line_color = (255, 105, 180)
            line_width = 2
        elif waypoint['order_type'] == OrderType.PATROL:
            line_color = (160, 200, 255)
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

    def draw_single_notch(self, p_start, p_end, p_notch, color, line_width):
        start_px = self.parent._coords_to_pixels(p_start)
        end_px = self.parent._coords_to_pixels(p_end)
        notch_px = self.parent._coords_to_pixels(p_notch)
        
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
            
            _sr().pygame.draw.line(self.overlay_surface, color, (x1, y1), (x2, y2), max(2, line_width))

    def draw_path_turn_notches_for_segment(self, segment, connect_to_unit, start_pos, effective_speed):
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
                
                color, width = self.get_waypoint_style(wp)
                self.draw_single_notch(p_curr, p_next, p_notch, color, width)
                
                p_curr = p_notch
                dist_to_next_notch = effective_speed
            else:
                dist_to_next_notch -= segment_len
                current_idx += 1
                p_curr = p_next

    def order_targets_sector(self, order, system_name, hex_coord):
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

    def collect_waypoints_from_order(self, order, unit, all_waypoints_sequence, is_current=False):
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
                idx = getattr(order, "current_waypoint_index", 0)
                if idx >= len(cycle) or idx < 0:
                    idx = 0

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
            if order.order_type == OrderType.PATROL and sub_order.order_type == OrderType.MOVE:
                continue
            self.collect_waypoints_from_order(
                sub_order,
                unit,
                all_waypoints_sequence,
                is_current=(is_current and order == unit.commander_component.current_order)
            )

    def collect_all_waypoints(self, unit, is_current_order=False):
        all_waypoints_sequence = []
        
        if unit.commander_component.current_order:
            self.collect_waypoints_from_order(unit.commander_component.current_order, unit, all_waypoints_sequence, True)
        
        for queued_order in list(unit.commander_component.orders_queue):
            self.collect_waypoints_from_order(queued_order, unit, all_waypoints_sequence, False)
            
        return all_waypoints_sequence

    def draw_sector_view_order_lines_from_other_sectors(self, external_units):
        for external_unit in external_units:
            all_waypoints_sequence = self.collect_all_waypoints(external_unit)
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
                    dest_pixel_point = self.parent._coords_to_pixels(waypoint['position'])
                    
                    if waypoint['order_type'] == OrderType.ATTACK:
                        line_color = RED
                        line_width = 2
                    elif waypoint['order_type'] == OrderType.PROTECT:
                        line_color = (255, 105, 180)
                        line_width = 2
                    elif waypoint['order_type'] == OrderType.PATROL:
                        line_color = (160, 200, 255)
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
                        _sr().pygame.draw.circle(self.overlay_surface, entry_color, 
                                           (dest_pixel_point.x, dest_pixel_point.y), 3, 1)
                        last_pixel_x, last_pixel_y = dest_pixel_point.x, dest_pixel_point.y
                    else:
                        if waypoint['order_type'] == OrderType.PATROL:
                            _sr().draw_dotted_line(self.overlay_surface, line_color,
                                             (last_pixel_x, last_pixel_y),
                                             (dest_pixel_point.x, dest_pixel_point.y), line_width)
                        else:
                            _sr().pygame.draw.line(self.overlay_surface, line_color, 
                                          (last_pixel_x, last_pixel_y), 
                                          (dest_pixel_point.x, dest_pixel_point.y), line_width)
                        last_pixel_x, last_pixel_y = dest_pixel_point.x, dest_pixel_point.y
                    
                    is_exit_point = (i == len(segment) - 1 and segment_index < len(path_segments) - 1)
                    if is_exit_point:
                        exit_color = WORMHOLE_JUMP_ORDER_COLOR
                        _sr().pygame.draw.circle(self.overlay_surface, exit_color, 
                                       (dest_pixel_point.x, dest_pixel_point.y), 3, 1)
                    else:
                        if i > 0 or segment_index == 0:
                            circle_size = 3 if not waypoint['is_sub_order'] else 2
                            _sr().pygame.draw.circle(self.overlay_surface, line_color, 
                                      (dest_pixel_point.x, dest_pixel_point.y), circle_size)
                
                if external_unit.engines_component:
                    effective_speed = external_unit.engines_component.speed * external_unit.xp_multiplier(XP_SPEED_BONUS)
                    self.draw_path_turn_notches_for_segment(segment, False, None, effective_speed)

    def draw_sector_view_order_lines(self, unit, unit_pixel_x, unit_pixel_y):
        all_waypoints_sequence = self.collect_all_waypoints(unit)
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
                    dest_pixel_point = self.parent._coords_to_pixels(waypoint['position'])
                    
                    if waypoint['order_type'] == OrderType.ATTACK:
                        line_color = RED
                        line_width = 2
                    elif waypoint['order_type'] == OrderType.PROTECT:
                        line_color = (255, 105, 180)
                        line_width = 2
                    elif waypoint['order_type'] == OrderType.PATROL:
                        line_color = (160, 200, 255)
                        line_width = 2
                    elif waypoint['is_current']:
                        line_width = 2
                        line_color = MOVE_ORDER_LINE_COLOR
                    else:
                        line_width = 1
                        line_color = (max(MOVE_ORDER_LINE_COLOR[0] - 40, 0), 
                                     max(MOVE_ORDER_LINE_COLOR[1] - 40, 0), 
                                     max(MOVE_ORDER_LINE_COLOR[2] - 40, 0))
                    
                    is_patrol = waypoint['order_type'] == OrderType.PATROL

                    if i == 0:
                        if connect_to_unit:
                            if is_patrol:
                                _sr().draw_dotted_line(self.overlay_surface, line_color,
                                                 (unit_pixel_x, unit_pixel_y),
                                                 (dest_pixel_point.x, dest_pixel_point.y), line_width)
                            else:
                                _sr().pygame.draw.line(self.overlay_surface, line_color, 
                                              (unit_pixel_x, unit_pixel_y), 
                                              (dest_pixel_point.x, dest_pixel_point.y), line_width)
                        if segment_index > 0:
                            entry_color = WORMHOLE_JUMP_ORDER_COLOR
                            _sr().pygame.draw.circle(self.overlay_surface, entry_color, 
                                           (dest_pixel_point.x, dest_pixel_point.y), 3, 1)
                        last_pixel_x, last_pixel_y = dest_pixel_point.x, dest_pixel_point.y
                    else:
                        if is_patrol:
                            _sr().draw_dotted_line(self.overlay_surface, line_color,
                                             (last_pixel_x, last_pixel_y),
                                             (dest_pixel_point.x, dest_pixel_point.y), line_width)
                        else:
                            _sr().pygame.draw.line(self.overlay_surface, line_color, 
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
                        _sr().pygame.draw.circle(self.overlay_surface, exit_color, 
                                      (dest_pixel_point.x, dest_pixel_point.y), 5, 2)
                    elif not (i == 0 and segment_index > 0):
                        circle_size = 3 if not waypoint['is_sub_order'] else 2
                        _sr().pygame.draw.circle(self.overlay_surface, line_color, 
                                      (dest_pixel_point.x, dest_pixel_point.y), circle_size)

                if unit.engines_component:
                    effective_speed = unit.engines_component.speed * unit.xp_multiplier(XP_SPEED_BONUS)
                    self.draw_path_turn_notches_for_segment(segment, connect_to_unit, unit.position, effective_speed)

    def draw_targeting_mode_overlay(self) -> None:
        """Renders on-screen guidance banner and cursor/hover target visual cues
        when an ability targeting mode is active."""
        pending = getattr(self.game, 'pending_ability', None)
        if not pending or not isinstance(pending, (tuple, list)) or len(pending) == 0:
            return

        ability_type_str = pending[0]
        if not isinstance(ability_type_str, str):
            return

        req_unit = pending[1] if len(pending) > 1 else False
        req_pos = pending[2] if len(pending) > 2 else False

        pending_name = ability_type_str.replace('_', ' ').title()
        if req_unit:
            guidance_text = f"TARGETING: {pending_name.upper()}  —  Right-Click target unit to cast (ESC to cancel)"
        elif req_pos:
            guidance_text = f"TARGETING: {pending_name.upper()}  —  Right-Click target location to cast (ESC to cancel)"
        else:
            guidance_text = f"TARGETING: {pending_name.upper()}  —  Right-Click to cast (ESC to cancel)"

        # 0. Draw Range Ring around casting unit(s)
        from unit_components import ABILITY_DEFINITIONS, AbilityType
        try:
            atype_enum = AbilityType(ability_type_str)
            defn = ABILITY_DEFINITIONS.get(atype_enum)
        except (ValueError, KeyError):
            defn = None

        if defn and getattr(defn, 'range', 0) > 0 and hasattr(self.parent, '_draw_range_ring') and hasattr(self.parent, '_coords_to_pixels'):
            dynamic_radius = (
                self.parent.get_dynamic_sector_radius()
                if hasattr(self.parent, 'get_dynamic_sector_radius')
                else SECTOR_CIRCLE_RADIUS_LOGICAL
            )
            selected_units = [u for u in getattr(self.game, 'selected_objects', []) if isinstance(u, Unit)]
            for unit in selected_units:
                if (getattr(unit, 'in_system', None) == getattr(self.game, 'current_system_name', None) and
                        getattr(unit, 'in_hex', None) == getattr(self.game, 'current_sector_coord', None)):
                    unit_px = self.parent._coords_to_pixels(unit.position)
                    rng_px = int(defn.range * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                    if rng_px > 1:
                        self.parent._draw_range_ring(int(unit_px.x), int(unit_px.y), rng_px, (200, 100, 255))

        # 1. Draw top-center HUD targeting banner
        font_size = max(13, int(15 * TEXT_SCALE))
        if font_size not in self.parent._font_cache:
            self.parent._font_cache[font_size] = _sr().pygame.font.Font(None, font_size)
        banner_font = self.parent._font_cache[font_size]

        text_surf = banner_font.render(guidance_text, True, (255, 230, 100))
        text_rect = text_surf.get_rect()

        screen_w = self.screen.get_width()
        if not isinstance(screen_w, (int, float)):
            screen_w = 1280
        screen_h = self.screen.get_height()
        if not isinstance(screen_h, (int, float)):
            screen_h = 720

        banner_w = text_rect.width + 30
        banner_h = text_rect.height + 12
        banner_x = int((screen_w - INFO_BOX_WIDTH - banner_w) // 2)
        banner_y = int(TOP_BAR_HEIGHT + 10)

        banner_rect = _sr().pygame.Rect(banner_x, banner_y, banner_w, banner_h)
        banner_surf = _sr().pygame.Surface((banner_w, banner_h), _sr().pygame.SRCALPHA)
        banner_surf.fill((15, 25, 45, 230))
        _sr().pygame.draw.rect(banner_surf, (255, 200, 50, 255), banner_surf.get_rect(), 2, border_radius=4)

        self.overlay_surface.blit(banner_surf, (banner_x, banner_y))
        text_rect.center = banner_rect.center
        self.overlay_surface.blit(text_surf, text_rect)

        # 2. Draw Hover Guidance / Reticle
        hovered_obj = getattr(self.game, 'sector_view_mouse_hover_object', None)
        mouse_pos = _sr().pygame.mouse.get_pos()
        if not isinstance(mouse_pos, (tuple, list)) or len(mouse_pos) < 2 or not isinstance(mouse_pos[0], (int, float)):
            mouse_pos = (0, 0)

        tip_font_size = max(11, int(13 * TEXT_SCALE))
        if tip_font_size not in self.parent._font_cache:
            self.parent._font_cache[tip_font_size] = _sr().pygame.font.Font(None, tip_font_size)
        tip_font = self.parent._font_cache[tip_font_size]

        if req_unit:
            if isinstance(hovered_obj, Unit):
                unit_px = self.parent._coords_to_pixels(hovered_obj.position)
                _sr().pygame.draw.circle(self.overlay_surface, (255, 80, 80), (int(unit_px.x), int(unit_px.y)), 18, 2)
                _sr().pygame.draw.line(self.overlay_surface, (255, 80, 80), (int(unit_px.x) - 24, int(unit_px.y)), (int(unit_px.x) + 24, int(unit_px.y)), 1)
                _sr().pygame.draw.line(self.overlay_surface, (255, 80, 80), (int(unit_px.x), int(unit_px.y) - 24), (int(unit_px.x), int(unit_px.y) + 24), 1)

                tip_str = f"Right-Click to cast {pending_name} on {hovered_obj.name}"
                tip_color = (120, 255, 120)
            else:
                tip_str = f"Right-Click a unit to cast {pending_name}"
                tip_color = (255, 200, 100)
        elif req_pos:
            tip_str = f"Right-Click to cast {pending_name} at position"
            tip_color = (120, 255, 120)
        else:
            tip_str = f"Right-Click to cast {pending_name}"
            tip_color = (120, 255, 120)

        # Draw tooltip near mouse pointer when inside sector viewport
        if mouse_pos[0] < screen_w - INFO_BOX_WIDTH and mouse_pos[1] > TOP_BAR_HEIGHT:
            tip_surf = tip_font.render(tip_str, True, tip_color)
            tip_bg = _sr().pygame.Surface((tip_surf.get_width() + 10, tip_surf.get_height() + 6), _sr().pygame.SRCALPHA)
            tip_bg.fill((10, 15, 25, 200))
            _sr().pygame.draw.rect(tip_bg, tip_color, tip_bg.get_rect(), 1, border_radius=3)

            tip_x = int(mouse_pos[0] + 15)
            tip_y = int(mouse_pos[1] + 15)
            if tip_x + tip_bg.get_width() > screen_w - INFO_BOX_WIDTH:
                tip_x = int(mouse_pos[0] - tip_bg.get_width() - 10)
            if tip_y + tip_bg.get_height() > screen_h - TOP_BAR_HEIGHT:
                tip_y = int(mouse_pos[1] - tip_bg.get_height() - 10)

            self.overlay_surface.blit(tip_bg, (tip_x, tip_y))
            self.overlay_surface.blit(tip_surf, (tip_x + 5, tip_y + 3))

