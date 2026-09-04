import pygame
import math
from typing import TYPE_CHECKING
from galaxy import StarSystem
from constants import (
    HOVER_HIGHLIGHT_COLOR, SELECTION_HIGHLIGHT_COLOR, WORMHOLE_JUMP_ORDER_COLOR,
    WORMHOLE_LINE_COLOR, GRAY, TEXT_SCALE
)
from entities import Unit, OrderType
from galaxy_utils import logical_to_screen_galaxy, get_home_systems_mapping
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
                            start_screen_pos = logical_to_screen_galaxy(start_system.position, self.game.gui.galaxy_generation_rect)
                            end_screen_pos = logical_to_screen_galaxy(end_system.position, self.game.gui.galaxy_generation_rect)
                            pygame.draw.line(self.screen, WORMHOLE_LINE_COLOR,
                                              start_screen_pos.to_tuple(), end_screen_pos.to_tuple(), 1)
    
        # 2. Draw Order Lines
        self.draw_galaxy_view_order_lines()

        # 3. Draw Systems
        home_systems_map = get_home_systems_mapping(self.game)

        for sys_name, system in self.game.galaxy.systems.items():
            screen_pos = logical_to_screen_galaxy(system.position, self.game.gui.galaxy_generation_rect)
            pos_tuple = screen_pos.to_tuple()
            is_hovered = (self.game.galaxy_view_mouse_hover_system_name == sys_name)
            home_players = home_systems_map.get(sys_name, [])

            if not home_players:
                # Standard unowned star system
                if is_hovered:
                    color = HOVER_HIGHLIGHT_COLOR
                    radius = 7
                else:
                    color = GRAY
                    radius = 5
                max_radius = radius
                pygame.draw.circle(self.screen, color, pos_tuple, radius)
                label_color = color

            elif len(home_players) == 1:
                # Single player home system: highlighted by that player's color
                player = home_players[0]
                player_color = player.color
                max_radius = 7
                pygame.draw.circle(self.screen, player_color, pos_tuple, max_radius)
                label_color = HOVER_HIGHLIGHT_COLOR if is_hovered else player_color
                if is_hovered:
                    pygame.draw.circle(self.overlay_surface, HOVER_HIGHLIGHT_COLOR, pos_tuple, max_radius + 2, 2)

            else:
                # Multiple players have homeworld in the same system:
                # Highlight with concentric circles of player colors.
                # Draw filled concentric circles from outermost player down to innermost player
                num_players = len(home_players)
                inner_radius = 5
                ring_thickness = 3
                max_radius = inner_radius + (num_players - 1) * ring_thickness

                for i in range(num_players - 1, -1, -1):
                    r = inner_radius + i * ring_thickness
                    pygame.draw.circle(self.screen, home_players[i].color, pos_tuple, r)

                label_color = HOVER_HIGHLIGHT_COLOR if is_hovered else (230, 230, 230)
                if is_hovered:
                    pygame.draw.circle(self.overlay_surface, HOVER_HIGHLIGHT_COLOR, pos_tuple, max_radius + 2, 2)

            # Draw system name
            if not pygame.font.get_init():
                pygame.font.init()
            font_size = max(1, int(12 * TEXT_SCALE))
            font = pygame.font.Font(None, font_size)
            text_surface = font.render(system.name, True, label_color)
            text_rect = text_surface.get_rect()
            text_rect.midleft = (pos_tuple[0] + max_radius + 5, pos_tuple[1])
            self.screen.blit(text_surface, text_rect)

            # Highlight selected system
            if any(isinstance(obj, StarSystem) and obj.name == sys_name for obj in self.game.selected_objects):
                 pygame.draw.circle(self.overlay_surface, SELECTION_HIGHLIGHT_COLOR, pos_tuple, max_radius + 4, 2)

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
        current_turn_player = self.game.players[self.game.current_player_index] if self.game.players else None
        if not current_turn_player:
            return
        
        for selected_unit in self.game.selected_objects:
            if isinstance(selected_unit, Unit) and selected_unit.owner == current_turn_player and selected_unit.commander_component:
                all_collected_waypoints = []
            
                waypoint_global_sequence_counter = 0 

                system_for_next_order_chain = selected_unit.in_system 

                active_root = (
                    selected_unit.commander_component.current_order
                    or selected_unit.commander_component.get_active_order_root()
                )
                if active_root:
                    system_for_next_order_chain, waypoint_global_sequence_counter = self.collect_all_system_waypoints_recursive(
                        active_root,
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
                
                start_screen_pos = logical_to_screen_galaxy(start_system.position, self.game.gui.galaxy_generation_rect)
                end_screen_pos = logical_to_screen_galaxy(end_system.position, self.game.gui.galaxy_generation_rect)
                start_pos_tuple = start_screen_pos.to_tuple()
                end_pos_tuple = end_screen_pos.to_tuple()
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


# ---------------------------------------------------------------------------
# Standalone Galaxy Preview Rendering (for New Game Wizard & Dialogs)
# ---------------------------------------------------------------------------

def draw_galaxy_preview(
    surface: pygame.Surface,
    galaxy: typing.Any,
    preview_rect: pygame.Rect,
    home_systems_map: typing.Optional[typing.Dict[str, typing.List[typing.Any]]] = None,
    hovered_system_name: typing.Optional[str] = None,
    selected_system_name: typing.Optional[str] = None,
    scale: float = 1.0,
) -> None:
    """Renders a visual preview of a Galaxy into a target preview rectangle.

    Args:
        surface: Target pygame surface to draw into.
        galaxy: Galaxy instance to preview (or None).
        preview_rect: Bounding rectangle on surface for the map preview.
        home_systems_map: Mapping of system_name -> list of player objects (or dicts/tuples with .color).
        hovered_system_name: Optional system name currently hovered by mouse cursor.
        selected_system_name: Optional system name currently focused/selected.
        scale: Resolution scale factor.
    """
    if preview_rect.width <= 0 or preview_rect.height <= 0:
        return

    # Background fill
    bg_color = (12, 18, 32)
    border_color = (58, 109, 140)
    surface.fill(bg_color, preview_rect)
    pygame.draw.rect(surface, border_color, preview_rect, 1)

    if not pygame.font.get_init():
        pygame.font.init()

    if not galaxy or not getattr(galaxy, "systems", None):
        font_size = max(12, int(14 * scale))
        font = pygame.font.Font(None, font_size)
        msg_surf = font.render("Click 'Generate Map' to create galaxy preview", True, (140, 160, 180))
        msg_rect = msg_surf.get_rect(center=preview_rect.center)
        surface.blit(msg_surf, msg_rect)
        return

    # 1. Draw Wormhole Connections
    for wh_id, wormhole in getattr(galaxy, "wormholes", {}).items():
        if getattr(wormhole, "stability", 0) > 0 and getattr(wormhole, "exit_wormhole_id", None):
            exit_wh = galaxy.wormholes.get(wormhole.exit_wormhole_id)
            if exit_wh:
                start_system = galaxy.systems.get(wormhole.in_system)
                end_system = galaxy.systems.get(exit_wh.in_system)
                if start_system and end_system:
                    start_screen_pos = logical_to_screen_galaxy(start_system.position, preview_rect)
                    end_screen_pos = logical_to_screen_galaxy(end_system.position, preview_rect)
                    pygame.draw.line(
                        surface,
                        WORMHOLE_LINE_COLOR,
                        start_screen_pos.to_tuple(),
                        end_screen_pos.to_tuple(),
                        1,
                    )

    # 2. Draw Systems
    font_size = max(10, int(11 * scale))
    font = pygame.font.Font(None, font_size)
    home_map = home_systems_map or {}

    for sys_name, system in galaxy.systems.items():
        screen_pos = logical_to_screen_galaxy(system.position, preview_rect)
        pos_tuple = (int(screen_pos.x), int(screen_pos.y))
        is_hovered = (hovered_system_name == sys_name)
        is_selected = (selected_system_name == sys_name)
        home_players = home_map.get(sys_name, [])

        if not home_players:
            # Unowned star system
            if is_hovered:
                color = HOVER_HIGHLIGHT_COLOR
                radius = 6
            else:
                color = (130, 150, 175)
                radius = 4
            max_radius = radius
            pygame.draw.circle(surface, color, pos_tuple, radius)
            label_color = color
        elif len(home_players) == 1:
            # Single player home system
            player = home_players[0]
            player_color = getattr(player, "color", (255, 255, 255))
            max_radius = 6
            pygame.draw.circle(surface, player_color, pos_tuple, max_radius)
            label_color = HOVER_HIGHLIGHT_COLOR if is_hovered else player_color
            if is_hovered:
                pygame.draw.circle(surface, HOVER_HIGHLIGHT_COLOR, pos_tuple, max_radius + 2, 2)
        else:
            # Multiple players in the same home system: concentric rings
            num_players = len(home_players)
            inner_radius = 4
            ring_thickness = 2
            max_radius = inner_radius + (num_players - 1) * ring_thickness

            for i in range(num_players - 1, -1, -1):
                r = inner_radius + i * ring_thickness
                p_color = getattr(home_players[i], "color", (255, 255, 255))
                pygame.draw.circle(surface, p_color, pos_tuple, r)

            label_color = HOVER_HIGHLIGHT_COLOR if is_hovered else (240, 240, 240)
            if is_hovered:
                pygame.draw.circle(surface, HOVER_HIGHLIGHT_COLOR, pos_tuple, max_radius + 2, 2)

        if is_selected:
            pygame.draw.circle(surface, SELECTION_HIGHLIGHT_COLOR, pos_tuple, max_radius + 4, 2)

        # Draw system name
        text_surface = font.render(sys_name, True, label_color)
        text_rect = text_surface.get_rect()
        text_rect.midleft = (pos_tuple[0] + max_radius + 4, pos_tuple[1])
        surface.blit(text_surface, text_rect)


def get_system_at_preview_point(
    screen_pos: typing.Tuple[int, int],
    galaxy: typing.Any,
    preview_rect: pygame.Rect,
    hit_radius: float = 20.0,
    scale: float = 1.0,
) -> typing.Optional[str]:
    """Finds the star system at or closest to screen_pos within preview_rect."""
    if not galaxy or not getattr(galaxy, "systems", None) or not preview_rect.collidepoint(screen_pos):
        return None

    if not pygame.font.get_init():
        pygame.font.init()
    font_size = max(10, int(11 * scale))
    font = pygame.font.Font(None, font_size)

    closest_sys = None
    min_dist_sq = hit_radius * hit_radius

    for name, system in galaxy.systems.items():
        sys_screen_pos = logical_to_screen_galaxy(system.position, preview_rect)
        pos_tuple = (int(sys_screen_pos.x), int(sys_screen_pos.y))

        # Check label bounding box (generous click area around system name)
        text_surface = font.render(name, True, (255, 255, 255))
        text_rect = text_surface.get_rect()
        text_rect.midleft = (pos_tuple[0] + 8, pos_tuple[1])
        click_box = text_rect.inflate(12, 12)
        if click_box.collidepoint(screen_pos):
            return name

        # Check distance to star center
        dx = sys_screen_pos.x - screen_pos[0]
        dy = sys_screen_pos.y - screen_pos[1]
        d_sq = dx * dx + dy * dy
        if d_sq <= min_dist_sq:
            min_dist_sq = d_sq
            closest_sys = name

    return closest_sys

