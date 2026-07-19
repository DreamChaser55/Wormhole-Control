"""Static sci-fi space background renderer for the main menu / about screens.

This module builds a single decorative space scene (deep-space radial
gradient, soft nebula clouds, a starfield, a couple of glowing stars, a
distant shaded/ringed planet, and a small thematic "wormhole" portal accent)
entirely with Pygame's built-in drawing primitives. Because the scene never
changes at runtime, it is composited once into a cached surface the first
time it's needed (or whenever the screen size changes) and simply blitted
each frame afterwards, keeping the per-frame cost of the menu background to
a single blit.
"""

import math
import random
import typing

import pygame


# --- Tuning constants (kept local to this module; purely decorative) ---

# Random seed used for the starfield/nebula so the layout is stable across runs.
_BACKGROUND_SEED = 20240607

# Radial gradient colors (inner = near screen center, outer = corners/edges).
_GRADIENT_INNER_COLOR = (14, 18, 38)
_GRADIENT_OUTER_COLOR = (2, 2, 6)
_GRADIENT_LOW_RES = 128  # low-res buffer that gets smoothscaled up

# Nebula cloud definitions: relative center (0-1 of width/height), color, blob
# count, and max blob spread (fraction of the low-res canvas' larger side).
# Blobs are kept small/numerous (rather than a few large circles) so that,
# combined with the blur pass in _draw_nebulae, they read as soft hazy clouds
# instead of visible overlapping circles.
_NEBULA_LOW_RES_DIVISOR = 10
_NEBULA_CLOUDS = [
    {'color': (90, 40, 160), 'center': (0.22, 0.28), 'count': 50, 'max_spread': 0.30, 'min_r': 0.015, 'max_r': 0.08, 'alpha': (14, 32)},
    {'color': (30, 70, 160), 'center': (0.78, 0.62), 'count': 50, 'max_spread': 0.30, 'min_r': 0.015, 'max_r': 0.08, 'alpha': (14, 32)},
    {'color': (160, 40, 110), 'center': (0.55, 0.12), 'count': 34, 'max_spread': 0.20, 'min_r': 0.015, 'max_r': 0.065, 'alpha': (12, 26)},
]


# Starfield tuning.
_STAR_DENSITY_DIVISOR = 3500  # lower = more stars
_STAR_COUNT_MIN = 250
_STAR_COUNT_MAX = 2200
_STAR_BRIGHTNESS_RANGE = (70, 220)

# Glowing "feature" stars.
_GLOW_STAR_COUNT_BASE_RES = (1280.0, 720.0)
_GLOW_STAR_COUNT_PER_BASE_RES = 9
_GLOW_STAR_COLORS = [
    (200, 220, 255),
    (255, 232, 200),
    (215, 200, 255),
    (255, 255, 255),
]

# Distant planet placement/appearance.
_PLANET_RADIUS_FRACTION = 0.15  # of min(width, height)
_PLANET_CENTER_FRACTION = (0.09, 0.90)  # near bottom-left, partly off-screen
_PLANET_BASE_COLOR = (70, 95, 130)
_PLANET_SHADOW_COLOR = (10, 13, 22)
_PLANET_HIGHLIGHT_COLOR = (150, 175, 210)
_PLANET_RING_COLOR = (150, 140, 110)

# Thematic wormhole/portal accent placement/appearance.
_WORMHOLE_CENTER_FRACTION = (0.88, 0.14)  # top-right corner
_WORMHOLE_RADIUS_FRACTION = 0.10  # of min(width, height)
_WORMHOLE_RING_COLOR = (180, 80, 255)
_WORMHOLE_CORE_COLOR = (230, 190, 255)


class MainMenuRenderer:
    """Renders a cached, static sci-fi space background for menu screens."""

    def __init__(self, game_instance):
        self.game = game_instance
        self.screen = game_instance.screen
        self._background_surface: typing.Optional[pygame.Surface] = None
        self._cached_size = None

    def draw(self):
        """Blits the cached background, (re)building it first if necessary."""
        size = self.screen.get_size()
        if self._background_surface is None or self._cached_size != size:
            self._background_surface = self._build_background(size)
            self._cached_size = size
        self.screen.blit(self._background_surface, (0, 0))

    # --- Construction ---

    def _build_background(self, size: tuple) -> pygame.Surface:
        width, height = size
        surface = pygame.Surface(size).convert()

        self._draw_gradient(surface, width, height)
        self._draw_nebulae(surface, width, height)
        self._draw_starfield(surface, width, height)
        self._draw_glow_stars(surface, width, height)
        self._draw_planet(surface, width, height)
        self._draw_wormhole_accent(surface, width, height)

        return surface

    def _draw_gradient(self, surface: pygame.Surface, width: int, height: int):
        """Draws a soft radial vignette (dark corners, slightly lighter center)."""
        low_size = _GRADIENT_LOW_RES
        grad_surf = pygame.Surface((low_size, low_size))
        cx = low_size / 2.0
        cy = low_size / 2.0
        max_dist = math.hypot(cx, cy)

        inner = _GRADIENT_INNER_COLOR
        outer = _GRADIENT_OUTER_COLOR

        for y in range(low_size):
            for x in range(low_size):
                dist = min(1.0, math.hypot(x - cx, y - cy) / max_dist)
                r = int(inner[0] + (outer[0] - inner[0]) * dist)
                g = int(inner[1] + (outer[1] - inner[1]) * dist)
                b = int(inner[2] + (outer[2] - inner[2]) * dist)
                grad_surf.set_at((x, y), (r, g, b))

        grad_surf = pygame.transform.smoothscale(grad_surf, (width, height))
        surface.blit(grad_surf, (0, 0))

    def _draw_nebulae(self, surface: pygame.Surface, width: int, height: int):
        """Draws a few soft, translucent nebula clouds.

        Each cloud is built from many small overlapping blobs on its own
        low-resolution SRCALPHA surface, softened with a cheap down/up-scale
        blur pass, and then composited onto a shared nebula layer with a
        normal alpha blit (which properly blends colors where clouds
        overlap). The combined layer is finally smoothscaled up to full
        screen resolution, giving a soft, hazy cloud look rather than
        visible hard-edged circles.
        """
        rng = random.Random(_BACKGROUND_SEED)

        low_w = max(8, width // _NEBULA_LOW_RES_DIVISOR)
        low_h = max(8, height // _NEBULA_LOW_RES_DIVISOR)
        canvas_extent = max(low_w, low_h)

        master_nebula_surf = pygame.Surface((low_w, low_h), pygame.SRCALPHA)

        blur_w = max(1, low_w // 3)
        blur_h = max(1, low_h // 3)

        for cloud in _NEBULA_CLOUDS:
            cloud_surf = pygame.Surface((low_w, low_h), pygame.SRCALPHA)
            center_x = cloud['center'][0] * low_w
            center_y = cloud['center'][1] * low_h
            color = cloud['color']
            alpha_lo, alpha_hi = cloud['alpha']

            for _ in range(cloud['count']):
                angle = rng.uniform(0.0, math.tau)
                # Bias distances toward the center for a denser core with a
                # softer, more sparsely-blobbed periphery.
                dist = (rng.random() ** 0.5) * cloud['max_spread'] * canvas_extent
                bx = center_x + math.cos(angle) * dist
                by = center_y + math.sin(angle) * dist
                radius = rng.uniform(cloud['min_r'], cloud['max_r']) * canvas_extent
                alpha = rng.randint(alpha_lo, alpha_hi)
                pygame.draw.circle(
                    cloud_surf,
                    (color[0], color[1], color[2], alpha),
                    (int(bx), int(by)),
                    max(1, int(radius))
                )

            # Cheap box-blur: shrink then grow back, softening blob edges.
            cloud_surf = pygame.transform.smoothscale(cloud_surf, (blur_w, blur_h))
            cloud_surf = pygame.transform.smoothscale(cloud_surf, (low_w, low_h))

            # Normal alpha blit correctly blends this cloud's colors with
            # whatever has already been composited (unlike pygame.draw calls,
            # which overwrite pixels rather than blend them).
            master_nebula_surf.blit(cloud_surf, (0, 0))

        master_nebula_surf = pygame.transform.smoothscale(master_nebula_surf, (width, height))
        surface.blit(master_nebula_surf, (0, 0))

    def _draw_starfield(self, surface: pygame.Surface, width: int, height: int):
        """Draws a static field of small stars with varying size/brightness/tint."""
        rng = random.Random(_BACKGROUND_SEED + 1)

        num_stars = int((width * height) / _STAR_DENSITY_DIVISOR)
        num_stars = max(_STAR_COUNT_MIN, min(_STAR_COUNT_MAX, num_stars))

        lo, hi = _STAR_BRIGHTNESS_RANGE
        for _ in range(num_stars):
            x = rng.randint(0, max(0, width - 1))
            y = rng.randint(0, max(0, height - 1))
            brightness = rng.randint(lo, hi)

            size_roll = rng.random()
            if size_roll < 0.85:
                radius = 1
            elif size_roll < 0.97:
                radius = 2
            else:
                radius = 3

            tint_roll = rng.random()
            if tint_roll < 0.7:
                color = (brightness, brightness, brightness)
            elif tint_roll < 0.85:
                # Cool bluish tint
                color = (brightness, brightness, min(255, brightness + 30))
            else:
                # Warm tint
                color = (min(255, brightness + 20), brightness, max(0, brightness - 25))

            if radius <= 1:
                surface.set_at((x, y), color)
            else:
                pygame.draw.circle(surface, color, (x, y), radius)

    def _draw_glow_star(self, surface: pygame.Surface, x: int, y: int, base_radius: float, color: tuple):
        """Draws a single star with a soft additive glow halo."""
        halo_layers = [
            (base_radius * 6.0, 10),
            (base_radius * 4.0, 22),
            (base_radius * 2.5, 55),
            (base_radius * 1.4, 120),
            (base_radius * 1.0, 255),
        ]
        max_r = int(halo_layers[0][0]) + 2
        halo_size = max_r * 2
        halo_surf = pygame.Surface((halo_size, halo_size), pygame.SRCALPHA)
        center = (max_r, max_r)

        for radius, alpha in halo_layers:
            pygame.draw.circle(halo_surf, (color[0], color[1], color[2], alpha), center, max(1, int(radius)))

        surface.blit(halo_surf, (x - max_r, y - max_r), special_flags=pygame.BLEND_RGBA_ADD)

    def _draw_glow_stars(self, surface: pygame.Surface, width: int, height: int):
        """Scatters a handful of larger, glowing feature stars across the scene."""
        rng = random.Random(_BACKGROUND_SEED + 2)

        base_w, base_h = _GLOW_STAR_COUNT_BASE_RES
        num_glow_stars = max(4, int((width * height) / (base_w * base_h) * _GLOW_STAR_COUNT_PER_BASE_RES))

        for _ in range(num_glow_stars):
            x = rng.randint(0, max(0, width - 1))
            y = rng.randint(0, max(0, height - 1))
            base_radius = rng.uniform(1.4, 2.6)
            color = rng.choice(_GLOW_STAR_COLORS)
            self._draw_glow_star(surface, x, y, base_radius, color)

    def _draw_planet(self, surface: pygame.Surface, width: int, height: int):
        """Draws a distant shaded, ringed planet partially off-screen in a corner."""
        planet_radius = max(24, int(min(width, height) * _PLANET_RADIUS_FRACTION))
        cx = int(width * _PLANET_CENTER_FRACTION[0])
        cy = int(height * _PLANET_CENTER_FRACTION[1])

        margin = int(planet_radius * 2.6)
        local_surf = pygame.Surface((margin * 2, margin * 2), pygame.SRCALPHA)
        center = (margin, margin)

        # Ring (back half) drawn first so the planet body occludes the far side.
        ring_rect = pygame.Rect(0, 0, int(planet_radius * 3.6), int(planet_radius * 1.1))
        ring_rect.center = center
        ring_width = max(2, planet_radius // 12)
        pygame.draw.ellipse(local_surf, (*_PLANET_RING_COLOR, 90), ring_rect, ring_width)

        # Planet body (fully opaque base sphere).
        pygame.draw.circle(local_surf, (*_PLANET_BASE_COLOR, 255), center, planet_radius)

        # Shadow lobe, layered from a larger/fainter radius down to a
        # smaller/fully-opaque core. Each ring is kept within the base
        # circle's bounds (offset + radius <= planet_radius) so nothing
        # spills outside the sphere outline, while the layering itself
        # produces a soft gradient terminator instead of one hard edge.
        shadow_offset = int(planet_radius * 0.28)
        shadow_max_radius = planet_radius * 0.68
        shadow_center = (center[0] + shadow_offset, center[1] + shadow_offset)
        for r_frac, alpha in ((1.0, 50), (0.78, 110), (0.56, 180), (0.38, 255)):
            pygame.draw.circle(
                local_surf,
                (*_PLANET_SHADOW_COLOR, alpha),
                shadow_center,
                max(1, int(shadow_max_radius * r_frac))
            )

        # Highlight glint on the "sunlit" side, composited additively on a
        # small overlay so it lightens the existing sphere colors instead of
        # flatly replacing them with a hard-edged patch.
        highlight_offset = int(planet_radius * 0.38)
        highlight_radius = max(3, int(planet_radius * 0.24))
        highlight_pos = (center[0] - highlight_offset, center[1] - highlight_offset)
        halo_size = highlight_radius * 4
        highlight_surf = pygame.Surface((halo_size, halo_size), pygame.SRCALPHA)
        hcenter = (halo_size // 2, halo_size // 2)
        for r_frac, alpha in ((1.0, 35), (0.6, 80), (0.32, 140)):
            pygame.draw.circle(highlight_surf, (*_PLANET_HIGHLIGHT_COLOR, alpha), hcenter, max(1, int(highlight_radius * r_frac)))
        local_surf.blit(
            highlight_surf,
            (highlight_pos[0] - halo_size // 2, highlight_pos[1] - halo_size // 2),
            special_flags=pygame.BLEND_RGBA_ADD
        )

        # Front sliver of the ring, drawn on top of the planet body.
        pygame.draw.arc(
            local_surf,
            _PLANET_RING_COLOR,
            ring_rect,
            math.radians(200),
            math.radians(340),
            ring_width
        )

        surface.blit(local_surf, (cx - margin, cy - margin))

    def _draw_wormhole_accent(self, surface: pygame.Surface, width: int, height: int):
        """Draws a small stylized wormhole/portal accent as a thematic nod to the game.

        Deliberately avoids large filled glow disks: since the final
        composite uses additive blending, filled circles would stack up
        brightness toward the center and read as a solid glowing ball
        instead of a hollow portal. Instead, only ring *outlines* (each with
        a tight, localized soft glow around the line itself) are drawn, plus
        a small bright core, so the shape reads as a ringed wormhole throat.
        """
        cx = int(width * _WORMHOLE_CENTER_FRACTION[0])
        cy = int(height * _WORMHOLE_CENTER_FRACTION[1])
        max_radius = max(16, int(min(width, height) * _WORMHOLE_RADIUS_FRACTION))

        margin = max_radius + 24
        local_surf = pygame.Surface((margin * 2, margin * 2), pygame.SRCALPHA)
        center = (margin, margin)

        # Concentric ring outlines, each with a small local glow (a few
        # close-radius passes with falling alpha) rather than a filled disk.
        ring_fracs = (0.95, 0.72, 0.50, 0.30)
        for idx, rf in enumerate(ring_fracs):
            r = max(2, int(max_radius * rf))
            core_alpha = 140 - idx * 18
            for d_off, d_alpha in ((5, 10), (3, 18), (0, core_alpha), (-3, 18)):
                rr = max(1, r + d_off)
                pygame.draw.circle(local_surf, (*_WORMHOLE_RING_COLOR, max(0, d_alpha)), center, rr, width=2)

        # Small bright core — kept modest so the portal stays a hollow ring
        # rather than filling in as a solid glowing sphere.
        pygame.draw.circle(local_surf, (*_WORMHOLE_CORE_COLOR, 200), center, max(2, int(max_radius * 0.07)))

        surface.blit(local_surf, (cx - margin, cy - margin), special_flags=pygame.BLEND_RGBA_ADD)
