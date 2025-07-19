import pygame
import math
from typing import TYPE_CHECKING
import pygame
import math
from galaxy import StarSystem
from constants import (
    HOVER_HIGHLIGHT_COLOR, SELECTION_HIGHLIGHT_COLOR, WORMHOLE_JUMP_ORDER_COLOR,
    WORMHOLE_LINE_COLOR, BLUE, GRAY
)
from entities import Unit, OrderType
if TYPE_CHECKING:
    from galaxy import StarSystem

class GalaxyViewRenderer:
    def __init__(self, game_instance):
        self.game = game_instance
        self.screen = game_instance.screen
        self.overlay_surface = game_instance.overlay_surface

    def draw_galaxy_view(self):
        """Draws the galaxy map."""
        if not self.game.galaxy: return

        # 1. Draw Wormhole Connections (draw first so they are behind stars)
        for wh_id, wormhole in self.game.galaxy.wormholes.items():
             if wormhole.stability > 0 and wormhole.exit_wormhole_id:
                  exit_wormhole = self.game.galaxy.wormholes[wormhole.exit_wormhole_id]
                  if exit_wormhole:
                       start_system = self.game.galaxy.systems[wormhole.in_system]
                       end_system = self.game.galaxy.systems[exit_wormhole.in_system]
                       if start_system and end_system:
                            pygame.draw.line(self.screen, WORMHOLE_LINE_COLOR,
                                              start_system.position.to_tuple(), end_system.position.to_tuple(), 1)
    
        # 2. Draw Order Lines
        self.draw_galaxy_view_order_lines()

        # 3. Draw Systems
        for sys_name, system in self.game.galaxy.systems.items():
            pos_tuple = system.position.to_tuple()
            
            if self.game.galaxy_view_mouse_hover_system_name == sys_name:
                 color = HOVER_HIGHLIGHT_COLOR
                 radius = 7
            elif sys_name == "Sol":
                 color = BLUE
                 radius = 7
            else:
                color = GRAY
                radius = 5
            
            pygame.draw.circle(self.screen, color, pos_tuple, radius)

            # Draw system name
            font = pygame.font.Font(None, 14)
            text_surface = font.render(system.name, True, color)
            text_rect = text_surface.get_rect()
            text_rect.midleft = (pos_tuple[0] + radius + 5, pos_tuple[1])
            self.screen.blit(text_surface, text_rect)

            # Highlight selected system
            if any(isinstance(obj, StarSystem) and obj.name == sys_name for obj in self.game.selected_objects):
                 pygame.draw.circle(self.overlay_surface, SELECTION_HIGHLIGHT_COLOR, pos_tuple, radius + 3, 2)

    def collect_all_system_waypoints_recursive(self,
                                               order,
                                               previous_system_for_this_leg,
                                               is_part_of_current_top_level_order,
                                               all_collected_waypoints,
                                               current_waypoint_sequence_counter):
        """
        Recursively traverses a unit's orders and sub-orders to collect
        inter-system travel legs for drawing on the galaxy map.
        """
        system_after_this_specific_order_leg = previous_system_for_this_leg
        updated_sequence_counter = current_waypoint_sequence_counter

        if order.order_type == OrderType.REACH_WAYPOINT:
            dsys = order.parameters["destination_system_name"]
            if dsys and dsys != previous_system_for_this_leg:
                all_collected_waypoints.append({
                    'start_system': previous_system_for_this_leg,
                    'end_system': dsys,
                    'is_current': is_part_of_current_top_level_order,
                    'is_sub_order': order.parent_order is not None,
                    'sequence_index': updated_sequence_counter
                })
                updated_sequence_counter += 1
                system_after_this_specific_order_leg = dsys
        
        current_system_for_sub_order_chain = system_after_this_specific_order_leg
        for sub_order in list(order.sub_orders):
            current_system_for_sub_order_chain, updated_sequence_counter = self.collect_all_system_waypoints_recursive(
                sub_order,
                current_system_for_sub_order_chain, 
                is_part_of_current_top_level_order,
                all_collected_waypoints,
                updated_sequence_counter 
            )
        
        return current_system_for_sub_order_chain, updated_sequence_counter

    def draw_galaxy_view_order_lines(self):
        """
        Draws lines on the galaxy map representing the planned inter-system
        jumps for the currently selected unit.
        """
        system_to_system_jumps = []
        
        for selected_unit in self.game.selected_objects:
            if isinstance(selected_unit, Unit) and selected_unit.commander_component:
                all_collected_waypoints = []
            
                waypoint_global_sequence_counter = 0 

                system_for_next_order_chain = selected_unit.in_system 

                if selected_unit.commander_component.current_order:
                    system_for_next_order_chain, waypoint_global_sequence_counter = self.collect_all_system_waypoints_recursive(
                        selected_unit.commander_component.current_order,
                        system_for_next_order_chain, 
                        True, 
                        all_collected_waypoints, 
                        waypoint_global_sequence_counter
                    )
                
                for queued_order in list(selected_unit.commander_component.orders_queue):
                    system_for_next_order_chain, waypoint_global_sequence_counter = self.collect_all_system_waypoints_recursive(
                        queued_order,
                        system_for_next_order_chain,
                        False, 
                        all_collected_waypoints, 
                        waypoint_global_sequence_counter
                    )
                system_to_system_jumps.extend(all_collected_waypoints)
        
        system_to_system_jumps.sort(key=lambda wp: wp['sequence_index'])

        for jump in system_to_system_jumps:
            start_system = self.game.galaxy.systems[jump['start_system']]
            end_system = self.game.galaxy.systems[jump['end_system']]
            
            if start_system and end_system:
                if jump['is_current']:
                    line_width = 3
                    line_color = WORMHOLE_JUMP_ORDER_COLOR
                else:
                    line_width = 2
                    line_color = (max(WORMHOLE_JUMP_ORDER_COLOR[0] - 40, 0),
                                 max(WORMHOLE_JUMP_ORDER_COLOR[1] - 40, 0),
                                 max(WORMHOLE_JUMP_ORDER_COLOR[2] - 40, 0))
                
                start_pos_tuple = start_system.position.to_tuple()
                end_pos_tuple = end_system.position.to_tuple()
                pygame.draw.line(self.overlay_surface, line_color, start_pos_tuple, end_pos_tuple, line_width)
                
                dx = end_pos_tuple[0] - start_pos_tuple[0]
                dy = end_pos_tuple[1] - start_pos_tuple[1]
                end_angle = math.atan2(dy, dx)
                
                arrow_size = 7
                arrow_angle1 = end_angle + math.pi * 3/4
                arrow_angle2 = end_angle - math.pi * 3/4
                
                arrow_x1 = end_pos_tuple[0] + arrow_size * math.cos(arrow_angle1)
                arrow_y1 = end_pos_tuple[1] + arrow_size * math.sin(arrow_angle1)
                arrow_x2 = end_pos_tuple[0] + arrow_size * math.cos(arrow_angle2)
                arrow_y2 = end_pos_tuple[1] + arrow_size * math.sin(arrow_angle2)
                
                pygame.draw.line(self.overlay_surface, line_color, end_pos_tuple, (arrow_x1, arrow_y1), line_width)
                pygame.draw.line(self.overlay_surface, line_color, end_pos_tuple, (arrow_x2, arrow_y2), line_width)
