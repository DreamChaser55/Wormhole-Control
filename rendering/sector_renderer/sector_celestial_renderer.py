import sys
import math
import random
from constants import (
    SECTOR_CIRCLE_RADIUS_IN_PX, SECTOR_CIRCLE_RADIUS_LOGICAL,
    STAR_RADIUS, PLANET_RADIUS, WORMHOLE_RADIUS, NEBULA_RADIUS, STORM_RADIUS,
    STORM_LIGHTNING_COLOR, STORM_COMPOSE_MAX_DIAMETER, NEBULA_COLORS, STORM_COLORS,
    WHITE, YELLOW, CYAN, PURPLE, RED, STAR_COLORS, MOON_RADIUS, ASTEROID_RADIUS,
    COMET_RADIUS, CELESTIAL_FIELD_RADIUS, ASTEROID_FIELD_RADIUS, ICE_FIELD_RADIUS, DEBRIS_FIELD_RADIUS,
    PlanetType, FIELD_DENSITY_PARTICLES, ASTEROID_FIELD_PARTICLES, ICE_FIELD_PARTICLES, DEBRIS_FIELD_PARTICLES
)
from entities import (
    Star, Planet, Wormhole, Moon, ColonizableAsteroid, MetalAsteroid, 
    AsteroidField, IceField, Nebula, Storm, Comet, DebrisField
)


def _sr():
    return sys.modules['rendering.sector_renderer']


class SectorCelestialRenderer:
    """Handles rendering of celestial bodies (stars, planets, moons, asteroids,
    comets, wormholes) and environmental effects (nebulae, space storms, asteroid fields).
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

    def get_pre_rendered_nebula(self, nebula):
        if nebula.id in self.parent._nebula_master_surfaces:
            return self.parent._nebula_master_surfaces[nebula.id]

        ref_zoom = 1.0
        ref_dynamic_radius = SECTOR_CIRCLE_RADIUS_IN_PX * ref_zoom
        base_radius_logical = getattr(nebula, 'radius', NEBULA_RADIUS)

        random.seed(nebula.id)

        circles = []
        min_x, max_x = float('inf'), float('-inf')
        min_y, max_y = float('inf'), float('-inf')

        # Generate a dense inner core and wispy outer cloud puffs, strictly confined
        # within base_radius_logical (effective radius)
        num_core_circles = 5
        num_outer_circles = 19
        color_base = NEBULA_COLORS[nebula.nebula_type]

        # Core puffs near the center
        for _ in range(num_core_circles):
            angle = random.uniform(0, 2 * math.pi)
            dist_logical = random.uniform(0, 0.25 * base_radius_logical)
            offset_x_logical = dist_logical * math.cos(angle)
            offset_y_logical = dist_logical * math.sin(angle)

            max_allowed_radius = base_radius_logical - dist_logical
            circle_radius_logical = random.uniform(max_allowed_radius * 0.55, max_allowed_radius * 0.80)

            offset_x_px = offset_x_logical * ref_dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
            offset_y_px = offset_y_logical * ref_dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
            circle_radius_px = int(circle_radius_logical * ref_dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)

            if circle_radius_px <= 0:
                continue

            alpha = random.randint(25, 55)
            color_key = (color_base[0], color_base[1], color_base[2], alpha)
            circles.append((offset_x_px, offset_y_px, circle_radius_px, color_key))

            min_x = min(min_x, offset_x_px - circle_radius_px)
            max_x = max(max_x, offset_x_px + circle_radius_px)
            min_y = min(min_y, offset_y_px - circle_radius_px)
            max_y = max(max_y, offset_y_px + circle_radius_px)

        # Mid and outer puffs spreading up to base_radius_logical
        for _ in range(num_outer_circles):
            angle = random.uniform(0, 2 * math.pi)
            dist_logical = random.uniform(0.15 * base_radius_logical, 0.70 * base_radius_logical)
            offset_x_logical = dist_logical * math.cos(angle)
            offset_y_logical = dist_logical * math.sin(angle)

            max_allowed_radius = base_radius_logical - dist_logical
            circle_radius_logical = random.uniform(max_allowed_radius * 0.45, max_allowed_radius * 0.98)

            offset_x_px = offset_x_logical * ref_dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
            offset_y_px = offset_y_logical * ref_dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
            circle_radius_px = int(circle_radius_logical * ref_dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)

            if circle_radius_px <= 0:
                continue

            alpha = random.randint(20, 50)
            color_key = (color_base[0], color_base[1], color_base[2], alpha)
            circles.append((offset_x_px, offset_y_px, circle_radius_px, color_key))

            min_x = min(min_x, offset_x_px - circle_radius_px)
            max_x = max(max_x, offset_x_px + circle_radius_px)
            min_y = min(min_y, offset_y_px - circle_radius_px)
            max_y = max(max_y, offset_y_px + circle_radius_px)

        random.seed()

        if not circles:
            self.parent._nebula_master_surfaces[nebula.id] = None
            return None

        width = int(max_x - min_x) + 4
        height = int(max_y - min_y) + 4

        center_x = -min_x + 2
        center_y = -min_y + 2

        master_surface = _sr().pygame.Surface((width, height), _sr().pygame.SRCALPHA)

        for offset_x, offset_y, radius, color in circles:
            circle_surface = self.parent._get_cached_circle_surface(radius, color)
            if circle_surface:
                cx = center_x + offset_x - radius
                cy = center_y + offset_y - radius
                master_surface.blit(circle_surface, (cx, cy))

        self.parent._nebula_master_surfaces[nebula.id] = {
            'master': master_surface,
            'center_x': center_x,
            'center_y': center_y,
        }
        return self.parent._nebula_master_surfaces[nebula.id]

    def draw_nebula(self, nebula, pos_px):
        zoom = self.game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0

        pre_rendered = self.get_pre_rendered_nebula(nebula)
        if not pre_rendered:
            return

        target_zoom = getattr(self.game, 'sector_target_zoom', zoom)
        is_zooming = isinstance(target_zoom, (int, float)) and abs(target_zoom - zoom) > 1e-4

        if is_zooming:
            self.parent._blit_scaled_surface_once(
                pre_rendered['master'],
                (pre_rendered['center_x'], pre_rendered['center_y']),
                (pos_px.x, pos_px.y),
                zoom,
                smooth=False,
            )
        else:
            quantized_zoom = self.parent._effect_zoom_bucket(zoom)
            self.parent._blit_visible_scaled_surface(
                pre_rendered['master'],
                (pre_rendered['center_x'], pre_rendered['center_y']),
                (pos_px.x, pos_px.y),
                quantized_zoom,
                ('nebula', nebula.id, quantized_zoom),
                smooth=True,
            )

    def draw_celestial_field(self, field, pos_px, base_color, num_particles=None):
        if num_particles is None:
            density = getattr(field, 'density', None)
            num_objects = FIELD_DENSITY_PARTICLES.get(density, 350) if density else 350
        else:
            num_objects = num_particles
        field_radius = getattr(field, 'radius', CELESTIAL_FIELD_RADIUS)
        time_ms = _sr().pygame.time.get_ticks()
        zoom = self.game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0
        dynamic_radius = SECTOR_CIRCLE_RADIUS_IN_PX * zoom

        random.seed(field.id)

        for i in range(num_objects):
            initial_angle = random.uniform(0, 360)
            initial_radius = random.uniform(field_radius * 0.1, field_radius)
            rotation_speed = random.uniform(-1.5, 1.5)
            object_size = random.randint(1, 3)
            color_variation = random.randint(-20, 20)
            object_color = (max(0, min(255, base_color[0] + color_variation)),
                              max(0, min(255, base_color[1] + color_variation)),
                              max(0, min(255, base_color[2] + color_variation)))

            current_angle_rad = math.radians(initial_angle + (time_ms / 500.0) * rotation_speed)
            offset_x = initial_radius * math.cos(current_angle_rad)
            offset_y = initial_radius * math.sin(current_angle_rad)
            
            offset_x_px = offset_x * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
            offset_y_px = offset_y * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
            object_pos = (pos_px.x + offset_x_px, pos_px.y + offset_y_px)

            _sr().pygame.draw.circle(self.screen, object_color, object_pos, object_size)

        random.seed()

    def get_pre_rendered_storm_circles(self, storm):
        if storm.id in self.parent._storm_base_circle_surfaces:
            return self.parent._storm_base_circle_surfaces[storm.id]

        num_circles = 25
        base_radius_logical = getattr(storm, 'radius', STORM_RADIUS)

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
        s_compose = max(1e-6, (canvas_center_px - padding_px) / max_bounding_logical)

        for particle in particles:
            particle['local_radius_px'] = max(1, round(particle['circle_base_radius_logical'] * s_compose))

        storm_data = {
            'particles': particles,
            'bounding_radius_logical': max_bounding_logical,
            's_compose': s_compose,
            'canvas_diameter': canvas_diameter,
        }
        self.parent._storm_base_circle_surfaces[storm.id] = storm_data
        return storm_data

    def draw_storm(self, storm, pos_px):
        zoom = self.game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0
        dynamic_radius = SECTOR_CIRCLE_RADIUS_IN_PX * zoom
        time_ms = _sr().pygame.time.get_ticks()

        storm_data = self.get_pre_rendered_storm_circles(storm)
        particles = storm_data['particles']
        s_compose = storm_data['s_compose']
        canvas_diameter = storm_data['canvas_diameter']
        bounding_radius_logical = storm_data['bounding_radius_logical']

        bounding_radius_px = bounding_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL
        if bounding_radius_px > 0 and not self.parent._is_circle_off_screen((pos_px.x, pos_px.y), bounding_radius_px):
            canvas_size = (int(canvas_diameter), int(canvas_diameter))
            if self.parent._storm_scratch_surface is None or self.parent._storm_scratch_surface.get_size() != canvas_size:
                self.parent._storm_scratch_surface = _sr().pygame.Surface(canvas_size, _sr().pygame.SRCALPHA)
            scratch = self.parent._storm_scratch_surface
            scratch.fill((0, 0, 0, 0))

            canvas_center_px = canvas_diameter / 2.0
            for particle in particles:
                current_angle_rad = math.radians(particle['initial_angle'] + (time_ms / 100.0) * particle['rotation_speed'])
                offset_x_logical = particle['initial_radius_logical'] * math.cos(current_angle_rad)
                offset_y_logical = particle['initial_radius_logical'] * math.sin(current_angle_rad)

                local_x = canvas_center_px + offset_x_logical * s_compose
                local_y = canvas_center_px + offset_y_logical * s_compose
                local_radius_px = particle['local_radius_px']

                circle_surface = self.parent._get_cached_circle_surface(local_radius_px, particle['color_key'])
                if circle_surface is not None:
                    scratch.blit(circle_surface, (local_x - local_radius_px, local_y - local_radius_px))

            target_zoom = getattr(self.game, 'sector_target_zoom', zoom)
            is_zooming = isinstance(target_zoom, (int, float)) and abs(target_zoom - zoom) > 1e-4
            final_scale = (dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL) / s_compose

            self.parent._blit_scaled_surface_once(
                scratch,
                (canvas_center_px, canvas_center_px),
                (pos_px.x, pos_px.y),
                final_scale,
                smooth=not is_zooming,
            )

        random.seed()

        if random.random() < 0.05:
            num_bolts = random.randint(1, 3)
            base_radius_logical = getattr(storm, 'radius', STORM_RADIUS)
            base_radius_px = int(base_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            for _ in range(num_bolts):
                angle = random.uniform(0, 2 * math.pi)
                length_px = random.uniform(base_radius_px * 1.0, base_radius_px * 1.5)
                end_pos_x = pos_px.x + length_px * math.cos(angle)
                end_pos_y = pos_px.y + length_px * math.sin(angle)
                _sr().pygame.draw.line(self.overlay_surface, STORM_LIGHTNING_COLOR, (pos_px.x, pos_px.y), (end_pos_x, end_pos_y), 2)

    def draw_celestial_object(self, obj, obj_pixel_pos, dynamic_radius):
        """Draws a celestial object or field. Returns (should_draw_circle, obj_color, obj_radius_logical)."""
        obj_radius_logical = 13.89
        obj_color = WHITE
        should_draw_circle = True

        if isinstance(obj, Star):
            obj_color = STAR_COLORS.get(obj.star_type, YELLOW)
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
                _sr().pygame.draw.circle(self.screen, obj.owner.color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)
        elif isinstance(obj, Moon):
            obj_color = (200, 200, 200)
            obj_radius_logical = MOON_RADIUS
            if obj.owner:
                pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                _sr().pygame.draw.circle(self.screen, obj.owner.color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)
        elif isinstance(obj, ColonizableAsteroid):
            obj_color = (90, 60, 50)
            obj_radius_logical = ASTEROID_RADIUS
            if obj.owner:
                pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                _sr().pygame.draw.circle(self.screen, obj.owner.color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 3, 1)
        elif isinstance(obj, MetalAsteroid):
            obj_color = (140, 140, 160)
            obj_radius_logical = ASTEROID_RADIUS
        elif isinstance(obj, AsteroidField):
            density = getattr(obj, 'density', None)
            count = ASTEROID_FIELD_PARTICLES.get(density, 350)
            self.draw_celestial_field(obj, obj_pixel_pos, (100, 100, 100), num_particles=count)
            obj_radius_logical = getattr(obj, 'radius', ASTEROID_FIELD_RADIUS)
            should_draw_circle = False
        elif isinstance(obj, IceField):
            density = getattr(obj, 'density', None)
            count = ICE_FIELD_PARTICLES.get(density, 260)
            self.draw_celestial_field(obj, obj_pixel_pos, (173, 216, 230), num_particles=count)
            obj_radius_logical = getattr(obj, 'radius', ICE_FIELD_RADIUS)
            should_draw_circle = False
        elif isinstance(obj, DebrisField):
            density = getattr(obj, 'density', None)
            count = DEBRIS_FIELD_PARTICLES.get(density, 180)
            self.draw_celestial_field(obj, obj_pixel_pos, (112, 128, 144), num_particles=count)
            obj_radius_logical = getattr(obj, 'radius', DEBRIS_FIELD_RADIUS)
            should_draw_circle = False
        elif isinstance(obj, Nebula):
            self.draw_nebula(obj, obj_pixel_pos)
            obj_radius_logical = getattr(obj, 'radius', NEBULA_RADIUS)
            should_draw_circle = False
        elif isinstance(obj, Storm):
            self.draw_storm(obj, obj_pixel_pos)
            obj_radius_logical = getattr(obj, 'radius', STORM_RADIUS)
            should_draw_circle = False
        elif isinstance(obj, Comet):
            obj_color = CYAN
            obj_radius_logical = COMET_RADIUS
        elif isinstance(obj, Wormhole):
            obj_radius_logical = WORMHOLE_RADIUS
            obj_color = PURPLE
            if obj.stability < 100:
                pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
                _sr().pygame.draw.circle(self.screen, RED, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius + 2, 1)

        if should_draw_circle:
            pixel_radius = int(obj_radius_logical * dynamic_radius / SECTOR_CIRCLE_RADIUS_LOGICAL)
            _sr().pygame.draw.circle(self.screen, obj_color, (obj_pixel_pos.x, obj_pixel_pos.y), pixel_radius)

            # Draw Celestial Body Name
            if hasattr(obj, 'name') and obj.name:
                from constants import TEXT_SCALE
                name_font_size = max(1, int(10 * TEXT_SCALE))
                if name_font_size not in self.parent._font_cache:
                    self.parent._font_cache[name_font_size] = _sr().pygame.font.Font(None, name_font_size)
                name_font = self.parent._font_cache[name_font_size]
                name_surface = name_font.render(obj.name, True, obj_color)
                name_rect = name_surface.get_rect()
                name_rect.midtop = (obj_pixel_pos.x, obj_pixel_pos.y + pixel_radius + 4)
                self.screen.blit(name_surface, name_rect)

            # Infiltration Badge
            current_viewer = getattr(self.game, 'current_player', None)
            if current_viewer and hasattr(obj, 'has_infiltrating_agent_from') and obj.has_infiltrating_agent_from(current_viewer):
                agent = next((ag for ag in getattr(obj, 'infiltrating_agents', []) if ag.owner == current_viewer), None)
                badge_text = f"[SABOTAGED: {agent.active_sabotage.name}]" if (agent and agent.active_sabotage) else "[INFILTRATED]"
                badge_color = (255, 140, 40) if (agent and agent.active_sabotage) else (50, 220, 255)
                from constants import TEXT_SCALE
                badge_font_size = max(1, int(9 * TEXT_SCALE))
                if badge_font_size not in self.parent._font_cache:
                    self.parent._font_cache[badge_font_size] = _sr().pygame.font.Font(None, badge_font_size)
                badge_font = self.parent._font_cache[badge_font_size]
                badge_surf = badge_font.render(badge_text, True, badge_color)
                badge_rect = badge_surf.get_rect()
                badge_rect.midbottom = (obj_pixel_pos.x, obj_pixel_pos.y - pixel_radius - 4)
                self.screen.blit(badge_surf, badge_rect)

            elif current_viewer and getattr(obj, 'owner', None) == current_viewer and hasattr(obj, 'infiltrating_agents'):
                has_discovered = any(ag.is_discovered and ag.owner != current_viewer for ag in obj.infiltrating_agents)
                if has_discovered:
                    badge_text = "[DISCOVERED SPY]"
                    badge_color = (255, 100, 100)
                    from constants import TEXT_SCALE
                    badge_font_size = max(1, int(9 * TEXT_SCALE))
                    if badge_font_size not in self.parent._font_cache:
                        self.parent._font_cache[badge_font_size] = _sr().pygame.font.Font(None, badge_font_size)
                    badge_font = self.parent._font_cache[badge_font_size]
                    badge_surf = badge_font.render(badge_text, True, badge_color)
                    badge_rect = badge_surf.get_rect()
                    badge_rect.midbottom = (obj_pixel_pos.x, obj_pixel_pos.y - pixel_radius - 4)
                    self.screen.blit(badge_surf, badge_rect)

        return obj_color, obj_radius_logical
