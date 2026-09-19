"""Galaxy camera geometry, gestures, rendering and campaign lifetime."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch

import pygame
import pytest

import game_camera
from constants import GALAXY_ZOOM_MIN, GALAXY_ZOOM_MAX, WORMHOLE_LINE_COLOR
from display_config import DisplayConfig
from galaxy import StarSystem
from galaxy_utils import logical_to_screen_galaxy, screen_to_logical_galaxy
from geometry import Position
from input_processor import InputProcessor
from input_processor.hover_tracker import update_hover_states
from input_processor.keyboard_handler import handle_keyboard_panning, handle_key_down
from input_processor.mouse_handler import (
    handle_mouse_button_down, handle_mouse_button_up, handle_mouse_motion, handle_mouse_click,
)
from rendering.galaxy_renderer import GalaxyViewRenderer, draw_galaxy_preview


def camera_game():
    gui = MagicMock()
    gui.galaxy_generation_rect = pygame.Rect(40, 30, 801, 501)
    for name in (
        'is_mouse_over_gui_panels', 'is_mouse_over_context_menu',
        'is_ingame_menu_open', 'is_unit_editor_open', 'is_retrofit_wizard_open',
        'is_communications_window_open', 'is_new_game_wizard_open',
        'is_any_text_entry_focused',
    ):
        getattr(gui, name).return_value = False
    gui.process_event.return_value = None
    gui.active_dialogs = []
    systems = {}
    for name, position in [('Sol', Position(1280, 720)), ('Beta', Position(1600, 800))]:
        system = StarSystem.__new__(StarSystem)
        system.name, system.position = name, position
        systems[name] = system
    game = SimpleNamespace(
        gui=gui, display_config=DisplayConfig(1000, 600),
        screen=pygame.Surface((1000, 600)),
        overlay_surface=pygame.Surface((1000, 600), pygame.SRCALPHA),
        galaxy=SimpleNamespace(systems=systems, wormholes={}),
        game_started=True, view_mode='galaxy', players=[], selected_objects=[],
        current_system_name=None, current_sector_coord=None, pending_ability=None,
        galaxy_view_mouse_hover_system_name=None,
        is_dragging_selection_box=False, sidebar_needs_update=False,
        update_view_specific_labels=Mock(), update_side_bar_content=Mock(),
        reset_system_camera=Mock(), handle_gui_action=Mock(),
        sector_zoom=2.0, sector_target_zoom=2.0, sector_pan_offset=Position(7, 9),
        system_zoom=3.0, system_target_zoom=3.0, system_pan_offset=Position(-8, 4),
    )
    game_camera.reset_galaxy_camera(game)
    game_camera.cancel_camera_drag(game)
    return game


def screen_position(game, name='Sol'):
    return logical_to_screen_galaxy(
        game.galaxy.systems[name].position, game.gui.galaxy_generation_rect,
        game.galaxy_zoom, game.galaxy_pan_offset,
    )


@pytest.mark.parametrize('rect', [pygame.Rect(0, 0, 1280, 720), pygame.Rect(41, 31, 801, 501), pygame.Rect(30, 80, 640, 1000)])
@pytest.mark.parametrize('zoom', [0.8, 1.0, 3.5, 15.0])
def test_coordinate_round_trip_and_viewport_center(rect, zoom):
    pan = Position(130.5, -75.25)
    logical = Position(357.3, 919.75)
    screen = logical_to_screen_galaxy(logical, rect, zoom, pan)
    restored = screen_to_logical_galaxy(screen, rect, zoom, pan)
    assert restored.to_tuple() == pytest.approx(logical.to_tuple())
    center = logical_to_screen_galaxy(Position(1280, 720), rect, zoom, pan)
    assert center.to_tuple() == pytest.approx((rect.left + rect.width / 2 + pan.x, rect.top + rect.height / 2 + pan.y))


def test_default_transform_preserves_fitted_preview():
    rect = pygame.Rect(20, 40, 1280, 800)
    assert logical_to_screen_galaxy(Position(0, 0), rect) == Position(20, 80)
    assert logical_to_screen_galaxy(Position(2560, 1440), rect) == Position(1300, 800)
    assert screen_to_logical_galaxy(Position(20, 80), rect) == Position(0, 0)
    assert logical_to_screen_galaxy(Position(12, 34), None) == Position(12, 34)
    assert screen_to_logical_galaxy(Position(12, 34), None) == Position(12, 34)


def test_zoom_keeps_cursor_anchor_through_settlement_and_during_panning():
    game = camera_game()
    game.galaxy_pan_offset = Position(35, -17)
    cursor = Position(560, 220)
    logical = screen_to_logical_galaxy(cursor, game.gui.galaxy_generation_rect, 1, game.galaxy_pan_offset)
    with patch('pygame.mouse.get_pos', return_value=cursor.to_tuple()):
        game_camera.handle_mouse_wheel(game, 1)
    assert game.galaxy_target_zoom == 1.1
    assert game.galaxy_zoom == 1.0
    game_camera.update_galaxy_camera(game, 1 / 60)
    with patch('pygame.key.get_pressed', return_value={pygame.K_LEFT: True}):
        handle_keyboard_panning(game, game.gui, 0.1)
    for _ in range(120):
        game_camera.update_galaxy_camera(game, 1 / 60)
        anchored = logical_to_screen_galaxy(logical, game.gui.galaxy_generation_rect, game.galaxy_zoom, game.galaxy_pan_offset)
        assert anchored.to_tuple() == pytest.approx((cursor.x + 50, cursor.y), abs=1e-8)
    assert game.galaxy_zoom == 1.1
    assert game.galaxy_zoom_anchor_pixel is None
    assert game.galaxy_zoom_anchor_logical is None
    assert (game.system_zoom, game.sector_zoom) == (3.0, 2.0)
    assert game.system_pan_offset == Position(-8, 4)
    assert game.sector_pan_offset == Position(7, 9)


@pytest.mark.parametrize('zoom,scroll', [(GALAXY_ZOOM_MIN, -1), (GALAXY_ZOOM_MAX, 1)])
def test_zoom_limits(zoom, scroll):
    game = camera_game()
    game.galaxy_zoom = game.galaxy_target_zoom = zoom
    with patch('pygame.mouse.get_pos', return_value=(400, 200)):
        game_camera.handle_mouse_wheel(game, scroll)
    assert game.galaxy_target_zoom == zoom
    assert game.galaxy_zoom_anchor_pixel is None


@pytest.mark.parametrize('blocker', [
    'is_ingame_menu_open', 'is_unit_editor_open', 'is_retrofit_wizard_open',
    'is_communications_window_open', 'is_new_game_wizard_open', 'is_any_text_entry_focused',
])
def test_modal_and_typing_guards_block_all_camera_input(blocker):
    game = camera_game()
    getattr(game.gui, blocker).return_value = True
    click = Mock()
    with patch('pygame.mouse.get_pos', return_value=(400, 200)), patch('pygame.key.get_pressed', return_value={pygame.K_LEFT: True}):
        game_camera.handle_mouse_wheel(game, 1)
        handle_keyboard_panning(game, game.gui, 0.1)
        handle_mouse_button_down(game, game.gui, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2), Position(400, 200), None, click)
    assert game.galaxy_target_zoom == 1
    assert game.galaxy_pan_offset == Position(0, 0)
    assert not game.is_dragging_camera
    click.assert_not_called()


@pytest.mark.parametrize('over_gui,point', [(True, (400, 200)), (False, (20, 20))])
def test_mouse_gestures_only_start_in_unobstructed_viewport(over_gui, point):
    game = camera_game()
    game.gui.is_mouse_over_gui_panels.return_value = over_gui
    click = Mock()
    with patch('pygame.mouse.get_pos', return_value=point):
        game_camera.handle_mouse_wheel(game, 1)
    handle_mouse_button_down(game, game.gui, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2), Position(*point), None, click)
    assert game.galaxy_target_zoom == 1
    assert not game.is_dragging_camera
    click.assert_not_called()


def test_transformed_selection_and_stationary_middle_click_use_fresh_pick():
    game = camera_game()
    game.galaxy_zoom = 2
    game.galaxy_pan_offset = Position(-40, 30)
    point = screen_position(game, 'Beta')
    game.galaxy_view_mouse_hover_system_name = 'Sol'  # Stale previous-frame hover.
    handle_mouse_click(game, game.gui, 1, point)
    assert game.selected_objects == [game.galaxy.systems['Beta']]
    callback = lambda button, position: handle_mouse_click(game, game.gui, button, position)
    handle_mouse_button_down(game, game.gui, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2), point, None, callback)
    assert game.view_mode == 'galaxy'
    handle_mouse_motion(game, Position(point.x + 2, point.y))
    assert game.galaxy_pan_offset == Position(-40, 30)
    game.galaxy_view_mouse_hover_system_name = 'Sol'
    handle_mouse_button_up(game, game.gui, point, pygame.event.Event(pygame.MOUSEBUTTONUP, button=2), callback)
    assert game.view_mode == 'system'
    assert game.current_system_name == 'Beta'
    game.reset_system_camera.assert_called_once()
    assert game.galaxy_zoom == 2


def test_scaled_hit_radius_and_hud_exclusion():
    game = camera_game()
    game.galaxy_zoom = 3
    center = screen_position(game)
    point = Position(center.x - 60, center.y)
    update_hover_states(game, game.gui, point)
    assert game.galaxy_view_mouse_hover_system_name == 'Sol'
    update_hover_states(game, game.gui, Position(center.x - 67, center.y))
    assert game.galaxy_view_mouse_hover_system_name is None
    game.gui.is_mouse_over_gui_panels.return_value = True
    update_hover_states(game, game.gui, center)
    assert game.galaxy_view_mouse_hover_system_name is None


def test_drag_from_system_marker_preserves_selection_and_moves_zoom_anchor():
    game = camera_game()
    game.selected_objects = [game.galaxy.systems['Sol']]
    start = screen_position(game)
    with patch('pygame.mouse.get_pos', return_value=start.to_tuple()):
        game_camera.handle_mouse_wheel(game, 1)
    anchor = deepcopy(game.galaxy_zoom_anchor_pixel)
    click = Mock()
    handle_mouse_button_down(game, game.gui, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2), start, None, click)
    end = Position(start.x + 25, start.y - 12)
    handle_mouse_motion(game, end)
    game_camera.update_galaxy_camera(game, 1 / 60)
    handle_mouse_button_up(game, game.gui, end, pygame.event.Event(pygame.MOUSEBUTTONUP, button=2), click)
    assert game.view_mode == 'galaxy'
    assert game.selected_objects == [game.galaxy.systems['Sol']]
    assert game.galaxy_zoom_anchor_pixel == Position(anchor.x + 25, anchor.y - 12)
    assert screen_position(game).to_tuple() == pytest.approx(end.to_tuple())
    assert not game.is_dragging_camera
    click.assert_not_called()


@pytest.mark.parametrize('release_kind', ['gui', 'outside', 'moved_without_motion', 'consumed'])
def test_release_clears_gesture_without_navigation(release_kind):
    game = camera_game()
    start = Position(400, 200)
    click = Mock()
    handle_mouse_button_down(game, game.gui, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2), start, None, click)
    end = start
    if release_kind == 'gui':
        game.gui.is_mouse_over_gui_panels.return_value = True
    elif release_kind == 'outside':
        end = Position(10, 10)
    elif release_kind == 'moved_without_motion':
        end = Position(405, 200)
    handle_mouse_button_up(game, game.gui, end, pygame.event.Event(pygame.MOUSEBUTTONUP, button=2), click, allow_click=release_kind != 'consumed')
    assert not game.is_dragging_camera
    assert game.camera_drag_start_pos is game.camera_drag_last_pos is game.camera_drag_view is None
    click.assert_not_called()


@pytest.mark.parametrize('interruption', ['view', 'menu', 'typing'])
def test_interrupted_drag_cannot_resume(interruption):
    game = camera_game()
    click = Mock()
    handle_mouse_button_down(game, game.gui, pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2), Position(400, 200), None, click)
    if interruption == 'view':
        game.view_mode = 'system'
    else:
        name = 'is_ingame_menu_open' if interruption == 'menu' else 'is_any_text_entry_focused'
        getattr(game.gui, name).return_value = True
    handle_mouse_motion(game, Position(440, 240))
    assert not game.is_dragging_camera
    game.view_mode = 'galaxy'
    game.gui.is_ingame_menu_open.return_value = False
    game.gui.is_any_text_entry_focused.return_value = False
    handle_mouse_motion(game, Position(450, 250))
    assert game.galaxy_pan_offset == Position(0, 0)
    click.assert_not_called()


def test_input_processor_uses_each_event_position_and_cleans_modal_drag():
    game = camera_game()
    processor = InputProcessor(game)
    events = [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2, pos=(400, 200)),
              pygame.event.Event(pygame.MOUSEMOTION, pos=(430, 215)),
              pygame.event.Event(pygame.MOUSEBUTTONUP, button=2, pos=(430, 215))]
    with patch('pygame.event.get', return_value=events), patch('pygame.mouse.get_pos', return_value=(430, 215)), patch('pygame.key.get_pressed', return_value={}):
        processor.handle_input()
    assert game.galaxy_pan_offset == Position(30, 15)
    assert not game.is_dragging_camera
    handle_mouse_button_down(game, game.gui, events[0], Position(400, 200), None, Mock())
    game.gui.is_ingame_menu_open.return_value = True
    with patch('pygame.event.get', return_value=[]), patch('pygame.mouse.get_pos', return_value=(400, 200)):
        processor.handle_input()
    assert not game.is_dragging_camera


def test_camera_retained_across_keyboard_and_back_navigation():
    from game_actions.app_actions import handle_navigate_back
    game = camera_game()
    game.current_system_name = 'Sol'
    game.galaxy_zoom = game.galaxy_target_zoom = 2.5
    game.galaxy_pan_offset = Position(70, -40)
    handle_key_down(game, game.gui, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s))
    game_camera.update_galaxy_camera(game, 1)
    handle_navigate_back(game, {})
    assert game.view_mode == 'galaxy'
    assert game.galaxy_zoom == 2.5
    assert game.galaxy_pan_offset == Position(70, -40)


@pytest.mark.parametrize('zoom', [0.8, 1.0, 3.0, 15.0])
def test_render_scales_geometry_but_not_labels_and_aligns_links(zoom):
    game = camera_game()
    game.galaxy_zoom = zoom
    game.galaxy_pan_offset = Position(20, -10)
    game.selected_objects = [game.galaxy.systems['Sol']]
    game.galaxy_view_mouse_hover_system_name = 'Sol'
    game.galaxy.wormholes = {
        1: SimpleNamespace(stability=1, exit_wormhole_id=2, in_system='Sol'),
        2: SimpleNamespace(stability=1, exit_wormhole_id=1, in_system='Beta'),
    }
    font = Mock()
    font.render.return_value = pygame.Surface((30, 10))
    renderer = GalaxyViewRenderer(game)
    renderer.screen = Mock(wraps=game.screen)
    with patch('pygame.draw.circle') as circle, patch('pygame.draw.line') as line, patch('pygame.font.Font', return_value=font) as font_factory:
        renderer.draw_galaxy_view()
        sol = screen_position(game).to_tuple()
        assert circle.call_args_list[0].args[2:] == (sol, max(1, round(7 * zoom)))
        assert circle.call_args_list[1].args[2:] == (sol, max(1, round(11 * zoom)), max(1, round(2 * zoom)))
        wh_line_calls = [c for c in line.call_args_list if len(c.args) > 1 and c.args[1] == WORMHOLE_LINE_COLOR]
        assert wh_line_calls[0].args[1:] == (WORMHOLE_LINE_COLOR, sol, screen_position(game, 'Beta').to_tuple(), max(1, round(zoom)))
        assert all(call.args == (None, max(1, int(12 * game.display_config.text_scale))) for call in font_factory.call_args_list)
    label_rect = renderer.screen.blit.call_args_list[0].args[1]
    assert label_rect.left > sol[0] + max(1, round(11 * zoom))
    assert label_rect.size == (30, 10)


@pytest.mark.parametrize('raise_during_draw', [False, True])
def test_render_clips_both_surfaces_and_restores_original_clips(raise_during_draw):
    game = camera_game()
    screen_clip = pygame.Rect(10, 10, 900, 550)
    overlay_clip = pygame.Rect(60, 0, 900, 450)
    game.screen.set_clip(screen_clip)
    game.overlay_surface.set_clip(overlay_clip)
    renderer = GalaxyViewRenderer(game)

    def draw():
        assert game.screen.get_clip() == screen_clip.clip(game.gui.galaxy_generation_rect)
        assert game.overlay_surface.get_clip() == overlay_clip.clip(game.gui.galaxy_generation_rect)
        game.screen.fill('red')
        game.overlay_surface.fill('green')
        if raise_during_draw:
            raise RuntimeError('drawing interrupted')

    with patch.object(renderer, '_draw_galaxy_map', side_effect=draw):
        if raise_during_draw:
            with pytest.raises(RuntimeError):
                renderer.draw_galaxy_view()
        else:
            renderer.draw_galaxy_view()
    assert game.screen.get_at((20, 20)) == pygame.Color('black')
    assert game.overlay_surface.get_at((20, 20)).a == 0
    assert game.screen.get_clip() == screen_clip
    assert game.overlay_surface.get_clip() == overlay_clip


@pytest.mark.parametrize('zoom', [0.8, 3.0, 15.0])
def test_order_lines_and_arrowheads_follow_camera(zoom):
    import math
    from domain.players import Player
    from domain.units import Unit
    from constants import HullSize
    from unit_components.commander import Commander
    from unit_orders.base import OrderType

    game = camera_game()
    game.galaxy_zoom = zoom
    game.galaxy_pan_offset = Position(-35, 20)
    player = Player('One', (0, 200, 0))
    game.players, game.current_player_index = [player], 0
    unit = Unit(player, Position(0, 0), (0, 0), 'Sol', 'Ship', HullSize.SMALL, game)
    order = SimpleNamespace(order_type=OrderType.REACH_WAYPOINT, parent_order=None,
                            sub_orders=[], parameters={'destination_system_name': 'Beta'})
    unit.components[Commander] = SimpleNamespace(current_order=order, orders_queue=[])
    game.selected_objects = [unit]
    with patch('pygame.draw.line') as line:
        GalaxyViewRenderer(game).draw_galaxy_view()
    order_line_calls = [call for call in line.call_args_list if len(call.args) > 0 and call.args[0] is game.overlay_surface]
    route, arrow1, arrow2 = [call.args for call in order_line_calls]
    assert route[2:4] == (screen_position(game).to_tuple(), screen_position(game, 'Beta').to_tuple())
    for args in (route, arrow1, arrow2):
        assert args[-1] == max(1, round(3 * zoom))
    for arrow in (arrow1, arrow2):
        assert arrow[2] == route[3]
        assert math.dist(arrow[2], arrow[3]) == pytest.approx(max(1, round(7 * zoom)))


def test_preview_render_ignores_gameplay_camera(pygame_context):
    game = camera_game()
    before = pygame.Surface((1000, 600))
    after = pygame.Surface((1000, 600))
    draw_galaxy_preview(before, game.galaxy, game.gui.galaxy_generation_rect)
    game.galaxy_zoom = 15
    game.galaxy_pan_offset = Position(400, 700)
    draw_galaxy_preview(after, game.galaxy, game.gui.galaxy_generation_rect)
    assert pygame.image.tobytes(before, 'RGB') == pygame.image.tobytes(after, 'RGB')


@pytest.mark.parametrize('operation', ['load', 'start'])
@pytest.mark.parametrize('succeeds', [True, False])
def test_campaign_replacement_resets_camera_only_on_success(operation, succeeds):
    from game_setup import start_new_game
    from save_manager import serialize_game_state, deserialize_game_state
    from tests.support.campaigns import campaign
    from tests.support.scenarios import settings_for

    game = campaign()
    game.gui = MagicMock()
    game.recompute_visibility = game.update_side_bar_content = game.update_player_turn_display = Mock()
    game_camera.reset_galaxy_camera(game)
    game.galaxy_zoom = 4
    game.galaxy_target_zoom = 5
    game.galaxy_pan_offset = Position(40, 50)
    game.galaxy_zoom_anchor_pixel = Position(80, 90)
    game.galaxy_zoom_anchor_logical = Position(10, 20)
    game.is_dragging_camera = True
    game.camera_drag_start_pos = game.camera_drag_last_pos = Position(300, 200)
    game.camera_drag_view = 'galaxy'
    game.camera_drag_exceeded_threshold = True
    before = {key: deepcopy(value) for key, value in vars(game).items() if key.startswith(('galaxy_', 'camera_drag_', 'is_dragging_camera'))}
    if operation == 'load':
        data = serialize_game_state(game)
        assert 'galaxy_zoom' not in str(data)
        if not succeeds:
            data['version'] = 'invalid'
        result = deserialize_game_state(game, data)
    else:
        settings = settings_for(game.galaxy)
        if not succeeds:
            settings.player_configs[1].home_system_name = 'Sol'
        result = start_new_game(game, settings)
    assert result is succeeds
    if succeeds:
        assert game.galaxy_zoom == game.galaxy_target_zoom == 1
        assert game.galaxy_pan_offset == Position(0, 0)
        assert game.galaxy_zoom_anchor_pixel is game.galaxy_zoom_anchor_logical is None
        assert not game.is_dragging_camera
        assert game.camera_drag_view is game.camera_drag_start_pos is game.camera_drag_last_pos is None
    else:
        assert {key: getattr(game, key) for key in before} == before
