"""Fit visible unit glyphs and their decorations into one System View hex."""
from dataclasses import dataclass
import math

import pygame

from constants import BLACK, HULL_BASE_ICON_SCALES, WHITE, HullSize
from domain.units import Unit
from geometry import Position
from rendering.drawing_utils import darken_color, station_icon_rect


_ICON_WIDTH_PER_RADIUS = 1.6
_MIN_ICON_WIDTH = 3
_SIZE_STEP = 15
_EDGE_INSET = 1
_BRACKET_PADDING = 2
_INFILTRATION_COLOR = (50, 220, 255)

_Point = tuple[int, int]
_Bounds = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class _Glyph:
    footprint: pygame.Rect
    station: pygame.Rect | None
    polygons: tuple[tuple[_Point, ...], ...]
    brackets: _Bounds | None
    infiltration_ring: tuple[tuple[int, int], int] | None

    def move(self, x, y, footprint):
        station = self.station.move(x, y) if self.station is not None else None
        polygons = tuple(tuple((px + x, py + y) for px, py in polygon) for polygon in self.polygons)
        brackets = None
        if self.brackets is not None:
            left, top, width, height = self.brackets
            brackets = (left + x, top + y, width, height)
        ring = None
        if self.infiltration_ring is not None:
            (cx, cy), radius = self.infiltration_ring
            ring = ((cx + x, cy + y), radius)
        return _Glyph(footprint, station, polygons, brackets, ring)

    def draw(self, surface, color):
        interior = darken_color(color)
        if self.station is not None:
            pygame.draw.rect(surface, interior, self.station)
            pygame.draw.rect(surface, color, self.station, 1)
        for polygon in self.polygons:
            pygame.draw.polygon(surface, interior, polygon)
        for polygon in self.polygons:
            pygame.draw.polygon(surface, color, polygon, 1)
        if self.infiltration_ring is not None:
            center, radius = self.infiltration_ring
            pygame.draw.circle(surface, _INFILTRATION_COLOR, center, radius, 1)


@dataclass(frozen=True, slots=True)
class _Icon:
    unit: Unit
    radius: float
    shape: str
    selected: bool
    infiltrated: bool

    def at(self, x, y, factor):
        radius = self.radius * factor
        station = None
        polygons = ()
        if self.shape == "station":
            station = station_icon_rect(Position(x, y), radius)
            footprint = station
            left, top, right, bottom = station.left, station.top, station.right, station.bottom
        else:
            y += radius * 0.2
            x = math.floor(x)
            half_width = int(radius * 0.8)
            top, bottom = math.floor(y - radius), math.floor(y + int(radius * 0.6))
            left, right = x - half_width, x + half_width
            if self.shape == "wing":
                inner_width = int(radius * 0.4)
                split_y = math.floor(y - int(radius * 0.2))
                inner_left, inner_right = (x - inner_width, split_y), (x + inner_width, split_y)
                polygons = (
                    ((x, top), inner_left, inner_right),
                    (inner_left, (left, bottom), (x, bottom)),
                    (inner_right, (x, bottom), (right, bottom)),
                )
            else:
                polygons = (((x, top), (left, bottom), (right, bottom)),)
            footprint = _pixel_bounds(left, top, right, bottom)

        brackets = None
        if self.selected:
            left, top = left - _BRACKET_PADDING, top - _BRACKET_PADDING
            right, bottom = right + _BRACKET_PADDING, bottom + _BRACKET_PADDING
            brackets = (left, top, right - left, bottom - top)
            # The two-pixel bracket stroke can extend a pixel past its endpoints.
            footprint = footprint.union(_pixel_bounds(left, top, right, bottom).inflate(2, 2))

        infiltration_ring = None
        if self.infiltrated:
            cx, cy, ring_radius = int(x), int(y), int(radius + 2)
            infiltration_ring = ((cx, cy), ring_radius)
            footprint = footprint.union(_pixel_bounds(
                cx - ring_radius, cy - ring_radius, cx + ring_radius, cy + ring_radius,
            ))
        return _Glyph(footprint, station, polygons, brackets, infiltration_ring)


def _pixel_bounds(left, top, right, bottom):
    """Use Pygame's integer endpoints, with both ends included."""
    x, y = int(left), int(top)
    return pygame.Rect(x, y, int(right) - x + 1, int(bottom) - y + 1)


class _HexSpace:
    def __init__(self, center, vertices, body_radius):
        self.center = center
        self.body_radius = body_radius
        self._grids = {}
        self.bounds = _pixel_bounds(
            min(p.x for p in vertices), min(p.y for p in vertices),
            max(p.x for p in vertices), max(p.y for p in vertices),
        )
        self.edges = []
        for start, end in zip(vertices, vertices[1:] + vertices[:1]):
            dx, dy = end.x - start.x, end.y - start.y
            length = math.hypot(dx, dy)
            if length:
                # Vertices are ordered so this normal points into the hex.
                nx, ny = -dy / length, dx / length
                self.edges.append((nx, ny, nx * start.x + ny * start.y + _EDGE_INSET))

    def fits(self, rect):
        for nx, ny, limit in self.edges:
            # This corner is nearest the edge. The other corners are farther inward.
            x = rect.left if nx > 0 else rect.right - 1
            y = rect.top if ny > 0 else rect.bottom - 1
            if nx * x + ny * y < limit:
                return False
        if self.body_radius is not None:
            dx = max(rect.left - self.center.x, self.center.x - (rect.right - 1), 0)
            dy = max(rect.top - self.center.y, self.center.y - (rect.bottom - 1), 0)
            if dx * dx + dy * dy <= (self.body_radius + _EDGE_INSET) ** 2:
                return False
        return True

    def preferred(self, icons, scale):
        """Retain the centered rows or rings when the entire fleet fits."""
        x, y = self.center.to_tuple()
        count = len(icons)
        pitch = 9 * scale
        rows = (count + 2) // 3
        occupied = []
        placed = {}
        for index, icon in enumerate(icons):
            if self.body_radius is None:
                row, column = divmod(index, 3)
                row_count = min(3, count - row * 3)
                ox = (column - (row_count - 1) / 2) * pitch
                oy = (row - (rows - 1) / 2) * pitch
            else:
                ring, slot = divmod(index, 6)
                ring_count = min(6, count - ring * 6)
                angle = -math.pi / 2 + math.tau * slot / ring_count
                radius = self.body_radius + (6 + 9 * ring) * scale
                ox, oy = radius * math.cos(angle), radius * math.sin(angle)
            glyph = icon.at(x + ox, y + oy, 1)
            if not self.fits(glyph.footprint) or glyph.footprint.collidelist(occupied) >= 0:
                return None
            placed[icon.unit] = glyph
            occupied.append(glyph.footprint)
        return placed

    def grid(self, pitch):
        """Stagger integer rows around the hex center and visit nearby slots first."""
        if pitch in self._grids:
            return self._grids[pitch]
        cx, cy = int(self.center.x), int(self.center.y)
        slots = []
        first_row = -((cy - self.bounds.top) // pitch)
        last_row = (self.bounds.bottom - 1 - cy) // pitch
        for row in range(first_row, last_row + 1):
            y = cy + row * pitch
            x = cx + (row % 2) * (pitch // 2)
            first_x = self.bounds.left + (x - self.bounds.left) % pitch
            for column_x in range(first_x, self.bounds.right, pitch):
                # Every footprint contains its anchor, so impossible anchors
                # can be dropped for all sizes and shapes at this pitch.
                if self.fits(pygame.Rect(column_x, y, 1, 1)):
                    slots.append((column_x, y))
        slots.sort(key=lambda point: ((point[0] - cx)**2 + (point[1] - cy)**2, point[1], point[0]))
        self._grids[pitch] = slots
        return slots

    def pack(self, icons, factor, slots, reserved=None):
        # The mask tracks occupied rectangles in hex-local pixel coordinates.
        occupied = pygame.Mask(self.bounds.size)
        if reserved is not None:
            occupied.draw(pygame.Mask(reserved.size, fill=True),
                          (reserved.left - self.bounds.left, reserved.top - self.bounds.top))
        placed = {}
        templates = {}
        for icon in icons:
            style = icon.shape, icon.radius, icon.selected, icon.infiltrated
            if style not in templates:
                glyph = icon.at(0, 0, factor)
                templates[style] = glyph, pygame.Mask(glyph.footprint.size, fill=True), iter(slots)
            glyph, covered, candidates = templates[style]
            offset_x = glyph.footprint.left - self.bounds.left
            offset_y = glyph.footprint.top - self.bounds.top
            # A rejected slot for the same footprint stays unavailable as the
            # packing fills, so the next matching icon can resume this search.
            for x, y in candidates:
                offset = x + offset_x, y + offset_y
                if occupied.overlap(covered, offset) is not None:
                    continue
                footprint = glyph.footprint.move(x, y)
                if self.fits(footprint):
                    placed[icon.unit] = glyph.move(x, y, footprint)
                    occupied.draw(covered, offset)
                    break
        return placed

    def badge_slot(self, width, height):
        # Start at the bottom tip and try the most centered position on each row.
        columns = sorted(range(self.bounds.left, self.bounds.right - width + 1),
                         key=lambda x: (abs(x + width / 2 - self.center.x), x))
        for y in range(self.bounds.bottom - height, self.bounds.top - 1, -1):
            for x in columns:
                rect = pygame.Rect(x, y, width, height)
                if self.fits(rect):
                    return rect
        return None


class SystemUnitIcons:
    def __init__(self):
        self._count_fonts = {}

    def draw(self, surface, units, *, center, vertices, scale, solid_radius,
             selected, viewer, text_scale):
        space = _HexSpace(center, vertices, solid_radius)
        if (len(space.edges) < 3 or min(space.bounds.size) <= 2 * _EDGE_INSET
                or not space.bounds.colliderect(surface.get_rect())):
            return []

        icons = []
        for unit in sorted(units, key=lambda unit: HULL_BASE_ICON_SCALES[unit.hull_size], reverse=True):
            if unit.hull_size == HullSize.STRIKECRAFT_WING:
                shape = "wing"
            else:
                shape = "ship" if unit.engines_component else "station"
            # Keep the existing compressed hull-size range on the system map.
            radius = 3 * scale * (0.7 + 0.3 * HULL_BASE_ICON_SCALES[unit.hull_size])
            icons.append(_Icon(unit, radius, shape, unit in selected,
                               viewer is not None and unit.has_infiltrating_agent_from(viewer)))

        placed = space.preferred(icons, scale)
        badge = None
        if placed is None:
            smallest_width = _ICON_WIDTH_PER_RADIUS * min(icon.radius for icon in icons)
            minimum = min(1, _MIN_ICON_WIDTH / smallest_width)
            for percentage in range(100, -_SIZE_STEP, -_SIZE_STEP):
                factor = max(minimum, percentage / 100)
                slots = space.grid(max(2, int(smallest_width * factor / 2)))
                placed = space.pack(icons, factor, slots)
                if len(placed) == len(icons):
                    break
                if factor == minimum:
                    placed, badge = self._fit_badge(space, icons, factor, slots, placed, text_scale)
                    break

        selection = []
        for icon in icons:
            glyph = placed.get(icon.unit)
            if glyph is None:
                continue
            glyph.draw(surface, icon.unit.owner.color if icon.unit.owner else WHITE)
            if glyph.brackets is not None:
                selection.append((icon.unit, glyph.brackets))

        if badge is not None:
            rect, text = badge
            if text is None:
                pygame.draw.rect(surface, WHITE, rect)
            else:
                pygame.draw.rect(surface, BLACK, rect)
                surface.blit(text, text.get_rect(center=rect.center))
        return selection

    def _fit_badge(self, space, icons, factor, slots, placed, text_scale):
        size = max(10, round(10 * text_scale))
        if size not in self._count_fonts:
            self._count_fonts[size] = pygame.font.Font(None, size)
        font = self._count_fonts[size]
        ordered = sorted(icons, key=lambda icon: not icon.selected)
        text = f"+{len(icons) - len(placed)}"
        width, height = font.size(text)
        while (rect := space.badge_slot(width + 2, height)) is not None:
            packed = space.pack(ordered, factor, slots, rect)
            if len(packed) == len(icons):
                return packed, None
            text = f"+{len(icons) - len(packed)}"
            required_width, required_height = font.size(text)
            if required_width <= width and required_height <= height:
                return packed, (rect, font.render(text, True, WHITE))
            # Reserving a slot can increase the count and change the text bounds.
            width, height = max(width, required_width), max(height, required_height)

        mark = font.render("+", True, WHITE)
        rect = space.badge_slot(mark.get_width() + 2, mark.get_height())
        if rect is None:
            mark = None
            rect = space.badge_slot(1, 1)
        if rect is None:
            return space.pack(ordered, factor, slots), None
        packed = space.pack(ordered, factor, slots, rect)
        return packed, (rect, mark) if len(packed) < len(icons) else None
