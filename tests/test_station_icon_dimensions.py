"""Station dimensions and attached UI follow the visible square in both views."""
from types import SimpleNamespace
from unittest.mock import patch

import pygame
import pytest

from constants import (BLUE, HullSize, HULL_BASE_ICON_SCALES, HULL_DOT_COUNTS,
                       SECTOR_VIEW_BASE_ICON_SIZE, SECTOR_CIRCLE_RADIUS_LOGICAL,
                       ICON_DOT_RADIUS)
from display_config import DisplayConfig
from domain.players import Player
from domain.units import Unit
from geometry import Position
from rendering.drawing_utils import darken_color, draw_shape
from rendering.sector_renderer.sector_entity_renderer import SectorEntityRenderer
from rendering.sector_renderer.sector_overlay_renderer import SectorOverlayRenderer


HULLS = [h for h in HullSize if h != HullSize.STRIKECRAFT_WING]


class RecordingSurface(pygame.Surface):
    """Keep text destinations while still drawing into a real Pygame surface."""

    def blit(self, source, dest, *args, **kwargs):
        self.text_bounds.append(pygame.Rect(dest))
        return super().blit(source, dest, *args, **kwargs)


@pytest.mark.parametrize('hull', HULLS)
@pytest.mark.parametrize('zoom', [0.02, 0.2, 1.0, 4.0])
def test_station_raster_dimensions_match_ship(hull, zoom):
    radius = SECTOR_VIEW_BASE_ICON_SIZE * HULL_BASE_ICON_SCALES[hull] * zoom
    bounds = []
    for shape in ('square', 'triangle'):
        surface = pygame.Surface((600, 600), pygame.SRCALPHA)
        draw_shape(surface, shape, BLUE, Position(300, 300), radius)
        bounds.append(surface.get_bounding_rect())
    square, triangle = bounds
    assert square.width == square.height >= 1
    assert abs(square.width - triangle.width) <= 2
    assert abs(square.height - triangle.height) <= 2
    assert abs(square.centerx - 300) <= 1
    assert abs(square.centery - 300) <= 1


@pytest.mark.parametrize('hull', HULLS)
@pytest.mark.parametrize('selected', [False, True])
@pytest.mark.parametrize('zoom', [0.2, 0.3, 1.0, 4.0])
def test_station_annotations_and_brackets_follow_rendered_square(pygame_context, hull, selected, zoom):
    owner = Player('Blue', BLUE)
    station = Unit(owner, Position(0, 0), (0, 0), 'Sol', 'Station', hull, None)
    game = SimpleNamespace(selected_objects=[station] if selected else [],
                           current_player=owner, sector_view_mouse_hover_object=station,
                           display_config=DisplayConfig(960, 720, False))
    screen = RecordingSurface((960, 720))
    screen.text_bounds = []
    station.infiltrating_agents = [SimpleNamespace(owner=owner, active_sabotage=None)]
    parent = SimpleNamespace(game=game, screen=screen,
                             overlay_surface=pygame.Surface((960, 720), pygame.SRCALPHA),
                             _font_cache={})
    center = Position(480, 300)
    dynamic_radius = SECTOR_CIRCLE_RADIUS_LOGICAL * zoom
    with patch('pygame.draw.rect', wraps=pygame.draw.rect) as rectangles, \
         patch('pygame.draw.circle', wraps=pygame.draw.circle) as circles:
        logical_radius = SectorEntityRenderer(parent).draw_unit(station, center, dynamic_radius)
    square_fill, square_outline = rectangles.call_args_list[:2]
    assert square_fill.args[1] == darken_color(BLUE)
    assert square_outline.args[1] == BLUE
    assert square_outline.args[3] == 1
    square = pygame.Rect(square_outline.args[2])
    assert pygame.Rect(square_fill.args[2]) == square
    health_bars = rectangles.call_args_list[2:]
    assert len(health_bars) == (2 if selected else 0)
    for call in health_bars:
        bar = pygame.Rect(call.args[2])
        assert bar.left == square.left
        assert bar.width == square.width
        assert bar.top == square.bottom + 10
    dot_radius = int(ICON_DOT_RADIUS * zoom)
    dots = [call for call in circles.call_args_list
            if len(call.args) == 5 and call.args[4] == 1]
    assert len(dots) == (HULL_DOT_COUNTS[hull] if dot_radius > 0 else 0)
    for call in dots:
        assert call.args[1] == BLUE
        assert call.args[2][1] == square.bottom + dot_radius + 2
        assert call.args[3] == dot_radius
        dot_x, dot_y = map(int, call.args[2])
        expected_interior = darken_color(BLUE) if dot_radius > 1 else BLUE
        assert screen.get_at((dot_x, dot_y))[:3] == expected_interior
        assert screen.get_at((dot_x - dot_radius, dot_y))[:3] == BLUE
    name, badge = screen.text_bounds
    assert badge.bottom == square.top - 4
    assert name.top >= square.bottom + 4
    if dots:
        assert name.top >= max(call.args[2][1] + call.args[3] for call in dots) + 4
    if selected:
        assert name.top >= max(pygame.Rect(call.args[2]).bottom for call in health_bars) + 4
    with patch('rendering.sector_renderer.sector_overlay_renderer.draw_selection_brackets') as brackets:
        SectorOverlayRenderer(parent).draw_selection_brackets(station, center, dynamic_radius, logical_radius)
    if selected:
        assert pygame.Rect(brackets.call_args.args[2]) == square.inflate(10, 10)
    else:
        brackets.assert_not_called()
    # Shrinking the symbol must not shrink the existing hover envelope.
    with patch('pygame.draw.circle') as hover:
        SectorOverlayRenderer(parent).draw_hover_highlight(station, center, dynamic_radius, logical_radius)
    assert hover.call_args.args[3] == int(logical_radius * zoom) + 3
