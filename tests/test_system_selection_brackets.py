"""Selection bounds follow rendered symbols rather than logical object sizes."""
from types import SimpleNamespace
from unittest.mock import patch

import pygame
import pytest

from constants import BLUE, RED, HullSize, NebulaType, PlanetType, StormType
from display_config import DisplayConfig
from domain.celestials import AsteroidField, IceField, DebrisField, Nebula, Storm, Planet
from domain.players import Player
from domain.units import Unit
from geometry import Position
from rendering.system_renderer import SystemViewRenderer
from rendering.drawing_utils import draw_selection_brackets
from unit_components.movement import Engines


def make_scene(zoom=1.0, pan=(0, 0)):
    owner = Player('Blue', BLUE)
    units = [Unit(owner, Position(0, 0), (0, 0), 'Sol', str(i), size, None)
             for i, size in enumerate((HullSize.SMALL, HullSize.LARGE, HullSize.STRIKECRAFT_WING))]
    units[0].add_component(Engines(units[0]))
    sector = SimpleNamespace(units=units, celestial_bodies=[], minefields=[])
    game = SimpleNamespace(
        screen=pygame.Surface((960, 720)),
        overlay_surface=pygame.Surface((960, 720), pygame.SRCALPHA),
        display_config=DisplayConfig(960, 720, False),
        current_system_name='Sol', current_player=owner, view_mode='system',
        players=[owner], current_player_index=0,
        galaxy=SimpleNamespace(systems={'Sol': SimpleNamespace(hexes={(0, 0): sector})}),
        system_zoom=zoom, system_pan_offset=Position(*pan),
        system_view_mouse_hover_hex=None, selected_objects=list(units),
        selected_unit_tab='basic_info', is_unit_visible=lambda unit: True,
        hex_has_presence=lambda *args: False,
    )
    renderer = SystemViewRenderer(game)
    return renderer, game, sector


@pytest.mark.parametrize('zoom', [0.2, 1.0, 4.0])
@pytest.mark.parametrize('pan', [(0, 0), (31, -19)])
def test_unit_brackets_enclose_actual_vertices(zoom, pan):
    renderer, game, sector = make_scene(zoom, pan)
    with patch('rendering.system_renderer.pygame.draw.polygon', wraps=pygame.draw.polygon) as polygons, \
         patch('rendering.system_renderer.draw_selection_brackets') as brackets:
        renderer.draw_system_view()
    icons = [call.args[2] for call in polygons.call_args_list
             if call.args[0] is game.screen and call.args[1] == BLUE]
    groups = [icons[0], icons[1], sum((list(points) for points in icons[2:]), [])]
    assert len(brackets.call_args_list) == len(sector.units)
    for call, points in zip(brackets.call_args_list, groups):
        left, top, width, height = call.args[2]
        assert left == pytest.approx(min(p[0] for p in points) - 2)
        assert top == pytest.approx(min(p[1] for p in points) - 2)
        assert left + width == pytest.approx(max(p[0] for p in points) + 2)
        assert top + height == pytest.approx(max(p[1] for p in points) + 2)


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
    sector.celestial_bodies = [planet]
    game.selected_objects.append(planet)
    # A late range/order overlay must not paint over the brackets.
    renderer._draw_system_view_order_lines = lambda system: game.overlay_surface.fill((0, 0, 0, 0))
    with patch('rendering.system_renderer.draw_selection_brackets',
               wraps=draw_selection_brackets) as brackets:
        renderer.draw_system_view()
        assert [c.args[1] for c in brackets.call_args_list] == [RED, BLUE, RED]
        left, top, width, height = brackets.call_args_list[0].args[2]
        assert width == height == 18  # planet + ownership ring + padding
        assert game.overlay_surface.get_at((int(left), int(top)))[:3] == RED
        planet.owner = game.current_player
        game.selected_objects = [planet]
        brackets.reset_mock()
        renderer.draw_system_view()
        assert [c.args[1] for c in brackets.call_args_list] == [BLUE]
        game.selected_objects = []
        brackets.reset_mock()
        renderer.draw_system_view()
        brackets.assert_not_called()
