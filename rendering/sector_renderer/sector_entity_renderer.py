from rendering.drawing_utils import (
    draw_shape,
    draw_wireframe_shape,
    draw_scaffold_brackets,
    draw_dotted_line,
    station_icon_rect,
)
import pygame
from display_config import display_config_for
from constants import (
    SECTOR_CIRCLE_RADIUS_LOGICAL,
    WHITE,
    RED,
    HULL_BASE_ICON_SCALES,
    HULL_DOT_COUNTS,
    SECTOR_VIEW_BASE_ICON_SIZE,
    ICON_DOT_RADIUS,
    ICON_DOT_SPACING,
    INHIBITION_FIELD_COLOR,
    INHIBITION_FIELD_LINE_WIDTH,
    CONSTRUCTOR_RANGE_RING_COLOR,
)
from domain.units import Unit
from domain.minefields import Minefield
from domain.construction_job import ConstructionJob
from unit_components.enums import MinefieldType


class SectorEntityRenderer:
    """Handles rendering of sector entities: Ships, Stations, Strikecraft,
    Minefields, and Inhibition Field overlays.
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

    def draw_inhibition_zones(self, hex_obj, dynamic_radius):
        """Draws opaque inhibition outlines on the shared range-circle overlay."""
        if not hex_obj:
            return
        for zone in hex_obj.get_all_inhibition_zones():
            zone_pixel_center = self.parent.grid_renderer.coords_to_pixels(zone.center)
            zone_pixel_radius = int(zone.radius * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)

            self.parent.grid_renderer.draw_range_ring(
                int(zone_pixel_center.x),
                int(zone_pixel_center.y),
                zone_pixel_radius,
                INHIBITION_FIELD_COLOR,
                width=INHIBITION_FIELD_LINE_WIDTH,
            )

    def draw_cloaking_fields(self, hex_obj, dynamic_radius):
        """Draws active advanced cloaking field boundaries for friendly/visible units."""
        if not hex_obj:
            return
        from unit_components.enums import CloakingType
        viewer = getattr(self.game, 'current_player', None)
        for unit in hex_obj.units:
            if viewer is not None and unit.owner != viewer and not self.game.is_unit_visible(unit):
                continue
            clk = getattr(unit, 'cloaking_component', None)
            if clk and clk.is_active and not clk.is_destroyed and getattr(clk, 'device_type', None) == CloakingType.ADVANCED:
                center_px = self.parent.grid_renderer.coords_to_pixels(unit.position)
                radius_px = int(clk.area_radius * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                if radius_px > 0 and not self.parent.grid_renderer.is_circle_off_screen((center_px.x, center_px.y), radius_px):
                    screen_size = self.screen.get_size()
                    if self.parent._cloaking_surface is None or self.parent._cloaking_surface.get_size() != screen_size:
                        self.parent._cloaking_surface = pygame.Surface(screen_size, pygame.SRCALPHA)
                    self.parent._cloaking_surface.fill((0, 0, 0, 0))
                    pygame.draw.circle(
                        self.parent._cloaking_surface, (70, 160, 240, 25),
                        (int(center_px.x), int(center_px.y)), radius_px
                    )
                    pygame.draw.circle(
                        self.parent._cloaking_surface, (100, 190, 255, 70),
                        (int(center_px.x), int(center_px.y)), radius_px, 1
                    )
                    self.screen.blit(self.parent._cloaking_surface, (0, 0))

    def draw_minefield(self, minefield: Minefield, obj_pixel_pos, dynamic_radius):
        """Draws a minefield circle and its remaining mine dot/diamond icons. Returns obj_radius_logical."""
        obj_color = minefield.owner.color if minefield.owner else RED
        obj_radius_logical = minefield.detonation_radius
        pixel_radius = max(5, int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL))
        is_anti_strikecraft = (getattr(minefield, 'minefield_type', None) == MinefieldType.ANTI_STRIKECRAFT)
        
        pygame.draw.circle(self.screen, obj_color, (int(obj_pixel_pos.x), int(obj_pixel_pos.y)), pixel_radius, 1)

        n_dots = max(0, minefield.mines_remaining)
        if n_dots > 0:
            icon_dot_radius_px = max(2, int(ICON_DOT_RADIUS * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL))
            icon_dot_spacing_px = max(5, int(ICON_DOT_SPACING * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL))
            total_width = (n_dots - 1) * icon_dot_spacing_px
            start_x = obj_pixel_pos.x - total_width / 2
            for di in range(n_dots):
                dot_x = int(start_x + di * icon_dot_spacing_px)
                if is_anti_strikecraft:
                    d_sz = max(2, icon_dot_radius_px)
                    pts = [
                        (dot_x, int(obj_pixel_pos.y) - d_sz),
                        (dot_x + d_sz, int(obj_pixel_pos.y)),
                        (dot_x, int(obj_pixel_pos.y) + d_sz),
                        (dot_x - d_sz, int(obj_pixel_pos.y))
                    ]
                    pygame.draw.polygon(self.screen, obj_color, pts)
                else:
                    pygame.draw.circle(self.screen, obj_color, (dot_x, int(obj_pixel_pos.y)), icon_dot_radius_px)
        return obj_radius_logical

    def draw_unit(self, unit_obj: Unit, obj_pixel_pos, dynamic_radius):
        """Draws a unit's shape icon, health bar, hull dots, and name label. Returns obj_radius_logical."""
        obj_color = unit_obj.owner.color if unit_obj.owner else WHITE

        if unit_obj.hull_size.name == "STRIKECRAFT_WING":
            shape_type = 'strikecraft_wing'
        else:
            shape_type = 'triangle' if unit_obj.engines_component else 'square'
        scale_factor = HULL_BASE_ICON_SCALES[unit_obj.hull_size]
        current_icon_base_size_logical = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
        dot_count = HULL_DOT_COUNTS[unit_obj.hull_size]
        
        icon_radius_px = current_icon_base_size_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
        current_icon_base_size_px = int(icon_radius_px)
        obj_radius_logical = current_icon_base_size_logical

        draw_shape(self.screen, shape_type, obj_color, obj_pixel_pos, icon_radius_px)
        icon_left = obj_pixel_pos.x - current_icon_base_size_px
        icon_top = obj_pixel_pos.y - current_icon_base_size_px
        icon_bottom = obj_pixel_pos.y + current_icon_base_size_px
        icon_width = current_icon_base_size_px * 2
        if shape_type == 'square':
            icon_rect = station_icon_rect(obj_pixel_pos, icon_radius_px)
            icon_left, icon_top = icon_rect.topleft
            icon_bottom, icon_width = icon_rect.bottom, icon_rect.width

        if unit_obj in self.game.selected_objects and unit_obj.max_hit_points > 0:
            health_bar_width = icon_width
            health_bar_height = 4
            
            health_percentage = unit_obj.current_hit_points / unit_obj.max_hit_points
            
            health_bar_x = icon_left
            health_bar_y = icon_bottom + 10
            
            pygame.draw.rect(self.screen, (50, 50, 50), (health_bar_x, health_bar_y, health_bar_width, health_bar_height))
            
            health_color = (0, 255, 0) if health_percentage > 0.5 else (255, 255, 0) if health_percentage > 0.2 else (255, 0, 0)
            pygame.draw.rect(self.screen, health_color, (health_bar_x, health_bar_y, health_bar_width * health_percentage, health_bar_height))

        if dot_count > 0:
            icon_dot_radius_px = int(ICON_DOT_RADIUS * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            icon_dot_spacing_px = int(ICON_DOT_SPACING * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            
            dot_base_y_offset = current_icon_base_size_px * 0.6
            if shape_type == 'square':
                dot_base_y_offset = icon_bottom - obj_pixel_pos.y
            
            dot_base_y = obj_pixel_pos.y + dot_base_y_offset + icon_dot_radius_px + 2

            if shape_type == 'triangle':
                base_p2_x = obj_pixel_pos.x - int(current_icon_base_size_px * 0.8)
                base_p3_x = obj_pixel_pos.x + int(current_icon_base_size_px * 0.8)
                base_width = base_p3_x - base_p2_x
                start_x = base_p2_x + (base_width - (dot_count - 1) * icon_dot_spacing_px) / 2
            else:
                base_p_left_x = icon_left
                base_p_right_x = icon_left + icon_width
                base_width = base_p_right_x - base_p_left_x
                start_x = base_p_left_x + (base_width - (dot_count - 1) * icon_dot_spacing_px) / 2

            for dot_i in range(dot_count):
                dot_x = start_x + dot_i * icon_dot_spacing_px
                pygame.draw.circle(self.screen, obj_color, (dot_x, dot_base_y), icon_dot_radius_px)

        # Draw Unit Name
        bottom_y = icon_bottom
        
        if unit_obj.max_hit_points > 0:
            health_bar_bottom = icon_bottom + 14
            if health_bar_bottom > bottom_y:
                bottom_y = health_bar_bottom
                
        if dot_count > 0:
            icon_dot_radius_px = int(ICON_DOT_RADIUS * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            dot_base_y_offset = current_icon_base_size_px * 0.6 if shape_type == 'triangle' else current_icon_base_size_px
            if shape_type == 'square':
                dot_base_y_offset = icon_bottom - obj_pixel_pos.y
            dot_bottom = obj_pixel_pos.y + dot_base_y_offset + 2 * icon_dot_radius_px + 2
            if dot_bottom > bottom_y:
                bottom_y = dot_bottom
                
        name_font_size = max(1, int(10 * display_config_for(self.game).text_scale))
        if name_font_size not in self.parent._font_cache:
            self.parent._font_cache[name_font_size] = pygame.font.Font(None, name_font_size)
        name_font = self.parent._font_cache[name_font_size]
        name_surface = name_font.render(unit_obj.name, True, obj_color)
        name_rect = name_surface.get_rect()
        name_rect.midtop = (obj_pixel_pos.x, bottom_y + 4)
        self.screen.blit(name_surface, name_rect)

        # Draw Infiltration / Discovered Spy Indicator Badges
        current_viewer = getattr(self.game, 'current_player', None)
        if current_viewer:
            is_infiltrated_by_viewer = (hasattr(unit_obj, 'has_infiltrating_agent_from') and unit_obj.has_infiltrating_agent_from(current_viewer))
            if is_infiltrated_by_viewer:
                agent = next((ag for ag in getattr(unit_obj, 'infiltrating_agents', []) if ag.owner == current_viewer), None)
                badge_text = f"[SABOTAGED: {agent.active_sabotage.name}]" if (agent and agent.active_sabotage) else "[INFILTRATED]"
                badge_color = (255, 140, 40) if (agent and agent.active_sabotage) else (50, 220, 255)
                badge_font_size = max(1, int(9 * display_config_for(self.game).text_scale))
                if badge_font_size not in self.parent._font_cache:
                    self.parent._font_cache[badge_font_size] = pygame.font.Font(None, badge_font_size)
                badge_font = self.parent._font_cache[badge_font_size]
                badge_surf = badge_font.render(badge_text, True, badge_color)
                badge_rect = badge_surf.get_rect()
                badge_rect.midbottom = (obj_pixel_pos.x, icon_top - 4)
                self.screen.blit(badge_surf, badge_rect)

            elif unit_obj.owner == current_viewer and hasattr(unit_obj, 'infiltrating_agents'):
                has_discovered = any(ag.is_discovered and ag.owner != current_viewer for ag in unit_obj.infiltrating_agents)
                if has_discovered:
                    badge_text = "[DISCOVERED SPY]"
                    badge_color = (255, 100, 100)
                    badge_font_size = max(1, int(9 * display_config_for(self.game).text_scale))
                    if badge_font_size not in self.parent._font_cache:
                        self.parent._font_cache[badge_font_size] = pygame.font.Font(None, badge_font_size)
                    badge_font = self.parent._font_cache[badge_font_size]
                    badge_surf = badge_font.render(badge_text, True, badge_color)
                    badge_rect = badge_surf.get_rect()
                    badge_rect.midbottom = (obj_pixel_pos.x, icon_top - 4)
                    self.screen.blit(badge_surf, badge_rect)

        return obj_radius_logical

    def draw_construction_job(self, job: ConstructionJob, obj_pixel_pos, dynamic_radius: float) -> float:
        """Draws an active construction site with blueprint scaffolding, progress bar, and label."""
        shape_type = 'square' if job.is_station else 'triangle'
        scale_factor = HULL_BASE_ICON_SCALES.get(job.hull_size, 1.0)
        current_icon_base_size_logical = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
        dot_count = HULL_DOT_COUNTS.get(job.hull_size, 0)

        icon_radius_px = current_icon_base_size_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
        current_icon_base_size_px = int(icon_radius_px)
        obj_radius_logical = current_icon_base_size_logical

        accent_color = CONSTRUCTOR_RANGE_RING_COLOR  # (255, 200, 50) amber
        owner_color = job.owner.color if job.owner else WHITE

        # 1. Corner scaffold brackets
        draw_scaffold_brackets(self.screen, accent_color, obj_pixel_pos, icon_radius_px, inflate=8)

        # 2. Wireframe shape
        draw_wireframe_shape(self.screen, shape_type, owner_color, obj_pixel_pos, icon_radius_px, width=1)

        icon_left = obj_pixel_pos.x - current_icon_base_size_px
        icon_top = obj_pixel_pos.y - current_icon_base_size_px
        icon_bottom = obj_pixel_pos.y + current_icon_base_size_px
        icon_width = current_icon_base_size_px * 2
        if shape_type == 'square':
            icon_rect = station_icon_rect(obj_pixel_pos, icon_radius_px)
            icon_left, icon_top = icon_rect.topleft
            icon_bottom, icon_width = icon_rect.bottom, icon_rect.width

        # 3. Hull dots
        if dot_count > 0:
            icon_dot_radius_px = int(ICON_DOT_RADIUS * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            icon_dot_spacing_px = int(ICON_DOT_SPACING * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            dot_base_y_offset = current_icon_base_size_px * 0.6 if shape_type == 'triangle' else (icon_bottom - obj_pixel_pos.y)
            dot_base_y = obj_pixel_pos.y + dot_base_y_offset + icon_dot_radius_px + 2

            if shape_type == 'triangle':
                base_p2_x = obj_pixel_pos.x - int(current_icon_base_size_px * 0.8)
                base_p3_x = obj_pixel_pos.x + int(current_icon_base_size_px * 0.8)
                base_width = base_p3_x - base_p2_x
                start_x = base_p2_x + (base_width - (dot_count - 1) * icon_dot_spacing_px) / 2
            else:
                base_p_left_x = icon_left
                base_p_right_x = icon_left + icon_width
                base_width = base_p_right_x - base_p_left_x
                start_x = base_p_left_x + (base_width - (dot_count - 1) * icon_dot_spacing_px) / 2

            for dot_i in range(dot_count):
                dot_x = start_x + dot_i * icon_dot_spacing_px
                pygame.draw.circle(self.screen, accent_color, (int(dot_x), int(dot_base_y)), max(1, icon_dot_radius_px), 1)

        # 4. Progress bar
        bar_width = max(24, icon_width)
        bar_height = 4
        bar_x = obj_pixel_pos.x - bar_width // 2
        bar_y = icon_bottom + (10 if dot_count > 0 else 6)
        pygame.draw.rect(self.screen, (40, 40, 40), (bar_x, bar_y, bar_width, bar_height))
        pct = min(1.0, max(0.0, job.percent / 100.0))
        if pct > 0:
            pygame.draw.rect(self.screen, accent_color, (bar_x, bar_y, int(bar_width * pct), bar_height))
        pygame.draw.rect(self.screen, (80, 80, 80), (bar_x, bar_y, bar_width, bar_height), 1)

        # 5. Label
        viewer = self.game.players[self.game.current_player_index] if (self.game and self.game.players) else None
        display_label = f"{job.get_display_name(viewer)} ({job.progress}/{job.time_to_build}t)"
        name_font_size = max(1, int(10 * display_config_for(self.game).text_scale))
        if name_font_size not in self.parent._font_cache:
            self.parent._font_cache[name_font_size] = pygame.font.Font(None, name_font_size)
        name_font = self.parent._font_cache[name_font_size]
        name_surface = name_font.render(display_label, True, accent_color)
        name_rect = name_surface.get_rect()
        name_rect.midtop = (obj_pixel_pos.x, bar_y + bar_height + 3)
        self.screen.blit(name_surface, name_rect)

        return obj_radius_logical

    def draw_construction_beam(self, job: ConstructionJob, dynamic_radius: float) -> None:
        """Draws a visual construction laser/tether connecting the constructor to the job site."""
        if not job.constructor_unit or not job.position:
            return
        p1 = self.parent.grid_renderer.coords_to_pixels(job.constructor_unit.position)
        p2 = self.parent.grid_renderer.coords_to_pixels(job.position)
        accent_color = CONSTRUCTOR_RANGE_RING_COLOR
        draw_dotted_line(self.screen, accent_color, (p1.x, p1.y), (p2.x, p2.y), width=1, dot_len=4, gap_len=6)
        pygame.draw.circle(self.screen, accent_color, (int(p1.x), int(p1.y)), 2)
        pygame.draw.circle(self.screen, accent_color, (int(p2.x), int(p2.y)), 2)

