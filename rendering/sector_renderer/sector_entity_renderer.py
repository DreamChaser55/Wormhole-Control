import sys
from constants import (
    SECTOR_CIRCLE_RADIUS_LOGICAL, WHITE, RED,
    HULL_BASE_ICON_SCALES, HULL_DOT_COUNTS, SECTOR_VIEW_BASE_ICON_SIZE,
    ICON_DOT_RADIUS, ICON_DOT_SPACING, TEXT_SCALE
)
from entities import Unit, Minefield
from unit_components import MinefieldType


def _sr():
    return sys.modules['rendering.sector_renderer']


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
        """Draws sector inhibition zones into an overlay surface."""
        if not hex_obj:
            return
        screen_size = self.screen.get_size()
        if self.parent._inhibition_surface is None or self.parent._inhibition_surface.get_size() != screen_size:
            self.parent._inhibition_surface = _sr().pygame.Surface(screen_size, _sr().pygame.SRCALPHA)
        self.parent._inhibition_surface.fill((0, 0, 0, 0))
        drew_inhibition_zone = False
        for zone in hex_obj.get_all_inhibition_zones():
            zone_pixel_center = self.parent._coords_to_pixels(zone.center)
            zone_pixel_radius = int(zone.radius * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)

            if zone_pixel_radius <= 0:
                continue
            if self.parent._is_circle_off_screen((zone_pixel_center.x, zone_pixel_center.y), zone_pixel_radius):
                continue

            _sr().pygame.draw.circle(
                self.parent._inhibition_surface, (255, 0, 0, 25),
                (int(zone_pixel_center.x), int(zone_pixel_center.y)), zone_pixel_radius
            )
            drew_inhibition_zone = True
            self.parent.zoom_render_stats['direct_draw_fallbacks'] += 1
        if drew_inhibition_zone:
            self.screen.blit(self.parent._inhibition_surface, (0, 0))

    def draw_minefield(self, minefield: Minefield, obj_pixel_pos, dynamic_radius):
        """Draws a minefield circle and its remaining mine dot/diamond icons. Returns obj_radius_logical."""
        obj_color = minefield.owner.color if minefield.owner else RED
        obj_radius_logical = minefield.detonation_radius
        pixel_radius = max(5, int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL))
        is_anti_strikecraft = (getattr(minefield, 'minefield_type', None) == MinefieldType.ANTI_STRIKECRAFT)
        
        _sr().pygame.draw.circle(self.screen, obj_color, (int(obj_pixel_pos.x), int(obj_pixel_pos.y)), pixel_radius, 1)

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
                    _sr().pygame.draw.polygon(self.screen, obj_color, pts)
                else:
                    _sr().pygame.draw.circle(self.screen, obj_color, (dot_x, int(obj_pixel_pos.y)), icon_dot_radius_px)
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
        
        current_icon_base_size_px = int(current_icon_base_size_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
        obj_radius_logical = current_icon_base_size_logical

        _sr().draw_shape(self.screen, shape_type, obj_color, obj_pixel_pos, current_icon_base_size_px)

        if unit_obj in self.game.selected_objects and unit_obj.max_hit_points > 0:
            health_bar_width = current_icon_base_size_px * 2
            health_bar_height = 4
            health_bar_y_offset = current_icon_base_size_px + 10
            
            health_percentage = unit_obj.current_hit_points / unit_obj.max_hit_points
            
            health_bar_x = obj_pixel_pos.x - health_bar_width / 2
            health_bar_y = obj_pixel_pos.y + health_bar_y_offset
            
            _sr().pygame.draw.rect(self.screen, (50, 50, 50), (health_bar_x, health_bar_y, health_bar_width, health_bar_height))
            
            health_color = (0, 255, 0) if health_percentage > 0.5 else (255, 255, 0) if health_percentage > 0.2 else (255, 0, 0)
            _sr().pygame.draw.rect(self.screen, health_color, (health_bar_x, health_bar_y, health_bar_width * health_percentage, health_bar_height))

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
            else:
                base_p_left_x = obj_pixel_pos.x - current_icon_base_size_px
                base_p_right_x = obj_pixel_pos.x + current_icon_base_size_px
                base_width = base_p_right_x - base_p_left_x
                start_x = base_p_left_x + (base_width - (dot_count - 1) * icon_dot_spacing_px) / 2

            for dot_i in range(dot_count):
                dot_x = start_x + dot_i * icon_dot_spacing_px
                _sr().pygame.draw.circle(self.screen, obj_color, (dot_x, dot_base_y), icon_dot_radius_px)

        # Draw Unit Name
        bottom_y = obj_pixel_pos.y + current_icon_base_size_px
        
        if unit_obj.max_hit_points > 0:
            health_bar_bottom = obj_pixel_pos.y + current_icon_base_size_px + 14
            if health_bar_bottom > bottom_y:
                bottom_y = health_bar_bottom
                
        if dot_count > 0:
            icon_dot_radius_px = int(ICON_DOT_RADIUS * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            dot_base_y_offset = current_icon_base_size_px * 0.6 if shape_type == 'triangle' else current_icon_base_size_px
            dot_bottom = obj_pixel_pos.y + dot_base_y_offset + 2 * icon_dot_radius_px + 2
            if dot_bottom > bottom_y:
                bottom_y = dot_bottom
                
        name_font_size = max(1, int(10 * TEXT_SCALE))
        if name_font_size not in self.parent._font_cache:
            self.parent._font_cache[name_font_size] = _sr().pygame.font.Font(None, name_font_size)
        name_font = self.parent._font_cache[name_font_size]
        name_surface = name_font.render(unit_obj.name, True, obj_color)
        name_rect = name_surface.get_rect()
        name_rect.midtop = (obj_pixel_pos.x, bottom_y + 4)
        self.screen.blit(name_surface, name_rect)

        return obj_radius_logical
