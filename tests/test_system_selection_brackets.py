"""System View unit layout and selection geometry."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pygame
import pytest

from constants import BLUE, RED, WHITE, SYSTEM_ZOOM_MIN, SYSTEM_ZOOM_MAX, HullSize, NebulaType, PlanetType, StarType, StormType
from display_config import DisplayConfig
from domain.celestials import AsteroidField, IceField, DebrisField, Nebula, Storm, Planet, Star
from domain.players import Player
from domain.units import Unit
from geometry import Position
from rendering.system_renderer import SystemViewRenderer
from rendering.drawing_utils import darken_color, draw_selection_brackets, selection_color_for
from unit_components.intelligence import Agent
from unit_components.movement import Engines
from visibility import VisibilitySnapshot


def make_scene(zoom=1.0, pan=(0, 0), size=(960, 720)):
    owner = Player('Blue', BLUE)
    units = [Unit(owner, Position(0, 0), (0, 0), 'Sol', str(i), size, None)
             for i, size in enumerate((HullSize.SMALL, HullSize.LARGE, HullSize.STRIKECRAFT_WING))]
    units[0].add_component(Engines(units[0]))
    sector = SimpleNamespace(units=units, celestial_bodies=[], minefields=[])
    game = SimpleNamespace(
        screen=pygame.Surface(size),
        overlay_surface=pygame.Surface(size, pygame.SRCALPHA),
        display_config=DisplayConfig(*size, False),
        current_system_name='Sol', current_player=owner, view_mode='system',
        players=[owner], current_player_index=0,
        galaxy=SimpleNamespace(systems={'Sol': SimpleNamespace(name='Sol', hexes={(0, 0): sector})}),
        system_zoom=zoom, system_pan_offset=Position(*pan),
        system_view_mouse_hover_hex=None, selected_objects=list(units),
        selected_unit_tab='basic_info', is_unit_visible=lambda unit: True,
        hex_has_presence=lambda *args: False,
    )
    renderer = SystemViewRenderer(game)
    return renderer, game, sector


@pytest.mark.parametrize('zoom', [SYSTEM_ZOOM_MIN, 1.0, 4.0])
@pytest.mark.parametrize('pan', [(0, 0), (31, -19)])
def test_unit_brackets_enclose_actual_vertices(zoom, pan):
    renderer, game, sector = make_scene(zoom, pan)
    with patch('rendering.system_renderer.pygame.draw.polygon', wraps=pygame.draw.polygon) as polygons, \
         patch('rendering.system_renderer.pygame.draw.rect', wraps=pygame.draw.rect) as rectangles, \
         patch('rendering.system_renderer.draw_selection_brackets') as brackets:
        renderer.draw_system_view()
    icons = [call.args[2] for call in polygons.call_args_list
             if call.args[0] is game.screen and call.args[1] == BLUE]
    interior_icons = [call.args[2] for call in polygons.call_args_list
                      if call.args[0] is game.screen and call.args[1] == darken_color(BLUE)]
    assert interior_icons == icons
    square = next(pygame.Rect(call.args[2]) for call in rectangles.call_args_list
                  if call.args[0] is game.screen and call.args[1] == BLUE)
    interior_square = next(pygame.Rect(call.args[2]) for call in rectangles.call_args_list
                           if call.args[0] is game.screen and call.args[1] == darken_color(BLUE))
    assert interior_square == square
    assert len(icons) == 4
    groups = [[square.topleft, square.bottomright],
              [point for wing in icons[:3] for point in wing],
              icons[3]]
    assert len(brackets.call_args_list) == len(sector.units)
    for call, points in zip(brackets.call_args_list, groups):
        left, top, width, height = call.args[2]
        assert left == pytest.approx(min(p[0] for p in points) - 2)
        assert top == pytest.approx(min(p[1] for p in points) - 2)
        assert left + width == pytest.approx(max(p[0] for p in points) + 2)
        assert top + height == pytest.approx(max(p[1] for p in points) + 2)


@pytest.mark.parametrize('zoom', [SYSTEM_ZOOM_MIN, 1.0, 4.0, SYSTEM_ZOOM_MAX])
@pytest.mark.parametrize('pan', [(0, 0), (31, -19)])
def test_station_dimensions_match_same_hull_ship_in_system_view(zoom, pan):
    renderer, game, sector = make_scene(zoom, pan)
    sector.units = sector.units[:2]
    sector.units[1].hull_size = sector.units[0].hull_size
    with patch('rendering.system_renderer.pygame.draw.polygon', wraps=pygame.draw.polygon) as polygons, \
         patch('rendering.system_renderer.pygame.draw.rect', wraps=pygame.draw.rect) as rectangles:
        renderer.draw_system_view()
    triangle = next(call.args[2] for call in polygons.call_args_list
                    if call.args[0] is game.screen and call.args[1] == BLUE)
    square = next(pygame.Rect(call.args[2]) for call in rectangles.call_args_list
                  if call.args[0] is game.screen and call.args[1] == BLUE)
    raster_points = [(int(x), int(y)) for x, y in triangle]
    width = max(x for x, y in raster_points) - min(x for x, y in raster_points) + 1
    height = max(y for x, y in raster_points) - min(y for x, y in raster_points) + 1
    assert square.width == square.height >= 1
    assert abs(square.width - width) <= 2
    assert abs(square.height - height) <= 2


@pytest.mark.parametrize('body_factory', [
    lambda: Planet((0, 0), 'Sol', PlanetType.TERRAN),
    lambda: AsteroidField((0, 0), 'Sol'),
    lambda: IceField((0, 0), 'Sol'),
    lambda: DebrisField((0, 0), 'Sol'),
    lambda: Nebula((0, 0), 'Sol', next(iter(NebulaType))),
    lambda: Storm((0, 0), 'Sol', next(iter(StormType))),
])
@pytest.mark.parametrize('zoom', [0.2, 1.0, 4.0])
def test_celestial_bounds_are_stable_and_cover_effects(body_factory, zoom):
    renderer, game, sector = make_scene(zoom)
    body = body_factory()
    sector.units = []
    sector.celestial_bodies = [body]
    game.selected_objects = [body]
    with patch('rendering.system_renderer.draw_selection_brackets') as brackets:
        for tick in (0, 10000):
            with patch('pygame.time.get_ticks', return_value=tick):
                renderer.draw_system_view()
    rect = brackets.call_args_list[0].args[2]
    assert brackets.call_args_list[1].args[2] == rect
    assert brackets.call_args_list[0].args[1] == (255, 255, 255)
    if isinstance(body, Planet):
        radius = int(4 * zoom)
    elif isinstance(body, Nebula):
        radius = 18 * zoom  # cloud offset plus maximum cloud radius
    elif isinstance(body, Storm):
        radius = 15 * zoom  # includes lightning and outer cloud edges
    else:
        radius = 10 * zoom + max(1, int(zoom))
    center = renderer._hex_to_pixel(0, 0)
    assert rect == pytest.approx((center.x - radius - 2, center.y - radius - 2,
                                 2 * radius + 4, 2 * radius + 4))


def test_selection_visibility_owner_changes_and_overlay_order():
    renderer, game, sector = make_scene()
    red = Player('Red', RED)
    sector.units[1].owner = red
    hidden = sector.units[2]
    game.is_unit_visible = lambda unit: unit is not hidden
    planet = Planet((0, 0), 'Sol', PlanetType.TERRAN)
    planet.owner = red
    game.players.append(red)
    game.visibility = VisibilitySnapshot(game.current_player, sensed_colony_ids={planet.id})
    sector.celestial_bodies = [planet]
    game.selected_objects.append(planet)
    # A late range/order overlay must not paint over the brackets.
    renderer._draw_system_view_order_lines = lambda system: game.overlay_surface.fill((0, 0, 0, 0))
    with patch('rendering.system_renderer.draw_selection_brackets',
               wraps=draw_selection_brackets) as brackets:
        renderer.draw_system_view()
        assert [c.args[1] for c in brackets.call_args_list] == [(255, 51, 51), (255, 51, 51), (51, 51, 255)]
        left, top, width, height = brackets.call_args_list[0].args[2]
        assert width == height == 18  # planet + ownership ring + padding
        assert game.overlay_surface.get_at((int(left), int(top)))[:3] == (255, 51, 51)
        planet.owner = game.current_player
        game.selected_objects = [planet]
        brackets.reset_mock()
        renderer.draw_system_view()
        assert [c.args[1] for c in brackets.call_args_list] == [(51, 51, 255)]
        game.selected_objects = []
        brackets.reset_mock()
        renderer.draw_system_view()
        brackets.assert_not_called()


def _colored_fleet(hulls):
    return [Unit(Player(f'Unit {i}', (64 + i, 219, 131)), Position(0, 0), (0, 0), 'Sol', f'Unit {i}', hull, None)
            for i, hull in enumerate(hulls)]


def _mask_for_color(surface, color):
    return pygame.mask.from_threshold(surface, color, (1, 1, 1, 255))


def _hex_mask(renderer, surface):
    mask_surface = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    pygame.draw.polygon(mask_surface, WHITE, [p.to_tuple() for p in renderer._hex_vertices(0, 0)])
    return pygame.mask.from_surface(mask_surface)


def _fleet_mask(surface):
    mask = pygame.mask.from_threshold(surface, (128, 219, 131), (255, 1, 1, 255))
    interiors = pygame.mask.from_threshold(surface, darken_color((128, 219, 131)), (255, 1, 1, 255))
    mask.draw(interiors, (0, 0))
    return mask


def _drawn_units(surface, units):
    fleet = _fleet_mask(surface)
    colors = {surface.get_at((x, y))[:3] for rect in fleet.get_bounding_rects()
              for y in range(rect.top, rect.bottom) for x in range(rect.left, rect.right)}
    return [unit for unit in units if unit.owner.color in colors]


@pytest.mark.parametrize('body_kind,count', [('open', 18), ('star', 8), ('planet', 12)])
@pytest.mark.parametrize('size,zoom', [
    ((1280, 720), SYSTEM_ZOOM_MIN), ((1280, 720), 1.0), ((1280, 720), 4.0),
    ((1920, 1080), SYSTEM_ZOOM_MIN), ((1920, 1080), 4.0),
])
def test_crowded_units_fit_inside_their_hex(size, zoom, body_kind, count, _pygame_runtime):
    renderer, game, sector = make_scene(zoom, (31, -19), size)
    game.galaxy.systems['Sol'].hexes[(1, 0)] = SimpleNamespace(units=[], celestial_bodies=[])
    sector.units = _colored_fleet([HullSize.TITAN] + [HullSize.MEDIUM] * (count - 1))
    game.selected_objects = []
    if body_kind == 'star':
        sector.celestial_bodies = [Star('Sol', StarType.BLUE_GIANT)]
    elif body_kind == 'planet':
        planet = Planet((0, 0), 'Sol', PlanetType.TERRAN)
        planet.owner = Player('Red', RED)
        game.players.append(planet.owner)
        game.visibility = VisibilitySnapshot(game.current_player, sensed_colony_ids={planet.id})
        sector.celestial_bodies = [planet]

    with patch('pygame.draw.circle', wraps=pygame.draw.circle) as circles:
        renderer.draw_system_view()
    mask = _fleet_mask(game.screen)
    assert mask.count() > 0
    assert mask.overlap_area(_hex_mask(renderer, game.screen), (0, 0)) == mask.count()
    assert _drawn_units(game.screen, sector.units) == sector.units

    if body_kind != 'open':
        center = renderer._hex_to_pixel(0, 0).to_tuple()
        body_radii = [call.args[3] for call in circles.call_args_list
                      if call.args[0] is game.screen and call.args[2] == center]
        assert len(body_radii) == (2 if body_kind == 'planet' else 1)
        body_surface = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.circle(body_surface, WHITE, center, max(body_radii))
        assert not mask.overlap(pygame.mask.from_surface(body_surface), (0, 0))


def test_overflow_counts_only_visible_units_and_keeps_selected_icon(_pygame_runtime):
    renderer, game, sector = make_scene(SYSTEM_ZOOM_MIN, (31, -19))
    sector.celestial_bodies = [Star('Sol', StarType.BLUE_GIANT)]
    fleet = _colored_fleet(list(HullSize) * 10 + [HullSize.TINY, HullSize.HUGE])
    for unit in fleet[::2]:
        if unit.hull_size != HullSize.STRIKECRAFT_WING:
            unit.add_component(Engines(unit))
    selected, hidden = fleet[-2:]
    selected.infiltrating_agents.append(Agent(game.current_player, fleet[0].id, 'UNIT', selected.id))
    game.selected_objects = [selected]
    sector.units = fleet
    game.is_unit_visible = lambda unit: unit is not hidden
    game.hex_has_presence = lambda name, coord: True

    font_factory = pygame.font.Font
    font = Mock(wraps=font_factory(None, 10))
    with patch('pygame.font.Font', return_value=font):
        renderer.draw_system_view()

    shown = _drawn_units(game.screen, fleet)
    assert selected in shown
    assert hidden not in shown
    assert len(shown) < len(fleet) - 1
    font.render.assert_called_once_with(f'+{len(fleet) - 1 - len(shown)}', True, WHITE)

    hex_mask = _hex_mask(renderer, game.screen)
    for mask in [_fleet_mask(game.screen), _mask_for_color(game.screen, WHITE),
                 _mask_for_color(game.screen, (50, 220, 255)),
                 _mask_for_color(game.overlay_surface, selection_color_for(selected, game))]:
        assert mask.count() > 0
        assert mask.overlap_area(hex_mask, (0, 0)) == mask.count()

    game.system_zoom = 4.0
    game.screen.fill((0, 0, 0))
    game.overlay_surface.fill((0, 0, 0, 0))
    renderer.draw_system_view()
    assert len(_drawn_units(game.screen, fleet)) > len(shown)


def test_small_hex_uses_compact_overflow_marker(_pygame_runtime):
    renderer, game, sector = make_scene(0.32, (31, -19))
    sector.celestial_bodies = [Star('Sol', StarType.BLUE_GIANT)]
    sector.units = _colored_fleet([HullSize.MEDIUM] * 40)
    game.selected_objects = []
    font = Mock(wraps=pygame.font.Font(None, 10))
    with patch('pygame.font.Font', return_value=font):
        renderer.draw_system_view()

    font.render.assert_called_once_with('+', True, WHITE)
    badge = _mask_for_color(game.screen, WHITE)
    assert badge.count() > 0
    assert badge.overlap_area(_hex_mask(renderer, game.screen), (0, 0)) == badge.count()


@pytest.mark.parametrize('zoom', [0.02, 0.2])
def test_subpixel_icons_and_overflow_stay_inside_the_hex(zoom, _pygame_runtime):
    renderer, game, _ = make_scene(zoom, (31, -19))
    renderer.draw_system_view()
    hex_mask = _hex_mask(renderer, game.screen)
    marks = _mask_for_color(game.screen, BLUE)
    marks.draw(_mask_for_color(game.screen, WHITE), (0, 0))
    marks.draw(_mask_for_color(game.overlay_surface, (51, 51, 255)), (0, 0))
    assert marks.overlap_area(hex_mask, (0, 0)) == marks.count()
