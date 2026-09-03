from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pygame

import game_camera
from constants import (
    INFO_BOX_WIDTH,
    SCREEN_RES,
    SYSTEM_CENTER_IN_PX,
    SYSTEM_ZOOM_MAX,
    SYSTEM_ZOOM_MIN,
    TOP_BAR_HEIGHT,
)
from geometry import Position
from hexgrid_utils import get_hex_vertices, hex_to_pixel, pixel_to_hex
from input_processor.hover_tracker import update_hover_states
from input_processor.keyboard_handler import handle_keyboard_panning
from input_processor.mouse_handler import (
    handle_mouse_button_down,
    handle_mouse_button_up,
    handle_mouse_motion,
)


def _hex_coords(radius):
    return {
        (q, r): SimpleNamespace()
        for q in range(-radius, radius + 1)
        for r in range(max(-radius, -q - radius), min(radius, -q + radius) + 1)
    }


def _camera_game(*, radius=10):
    viewport = pygame.Rect(
        0,
        TOP_BAR_HEIGHT,
        int(SCREEN_RES.x - INFO_BOX_WIDTH),
        int(SCREEN_RES.y - TOP_BAR_HEIGHT * 2),
    )
    system = SimpleNamespace(name="Sol", radius=radius, hexes=_hex_coords(radius))
    gui = MagicMock()
    gui.galaxy_generation_rect = viewport
    gui.is_mouse_over_gui_panels.return_value = False
    gui.is_mouse_over_context_menu.return_value = False
    return SimpleNamespace(
        view_mode='system',
        game_started=True,
        current_system_name="Sol",
        galaxy=SimpleNamespace(systems={"Sol": system}),
        gui=gui,
        screen=pygame.Surface((int(SCREEN_RES.x), int(SCREEN_RES.y))),
        system_zoom=1.0,
        system_target_zoom=1.0,
        system_pan_offset=Position(0, 0),
        system_zoom_anchor_pixel=None,
        system_zoom_anchor_logical=None,
        system_camera_system_name=None,
        sector_zoom=1.0,
        sector_target_zoom=1.0,
        sector_pan_offset=Position(0, 0),
        zoom_anchor_pixel=None,
        zoom_anchor_logical=None,
        is_dragging_camera=False,
        camera_drag_start_pos=None,
        camera_drag_last_pos=None,
        camera_drag_view=None,
        camera_drag_exceeded_threshold=False,
    )


def test_system_coordinate_roundtrip_with_camera_transform():
    zoom = 1.7
    pan_offset = Position(-135.0, 82.0)
    screen_pos = hex_to_pixel(3, -2, zoom, pan_offset)

    assert pixel_to_hex(screen_pos.x, screen_pos.y, zoom, pan_offset) == (3, -2)

    base_center = hex_to_pixel(0, 0)
    transformed_center = hex_to_pixel(0, 0, zoom, pan_offset)
    assert transformed_center == Position(
        int(base_center.x + pan_offset.x),
        int(base_center.y + pan_offset.y),
    )


def test_system_hex_vertices_scale_with_zoom():
    center = hex_to_pixel(0, 0, 2.0, Position(10, -20))
    vertices = get_hex_vertices(0, 0, 2.0, Position(10, -20))

    assert len(vertices) == 6
    assert max(abs(vertex.y - center.y) for vertex in vertices) > 1
    assert pixel_to_hex(center.x, center.y, 2.0, Position(10, -20)) == (0, 0)


def test_reset_system_camera_auto_fits_radius_ten_in_gameplay_viewport():
    game = _camera_game(radius=10)

    game_camera.reset_system_camera(game)

    viewport = game.gui.galaxy_generation_rect
    points = [
        point
        for q, r in game.galaxy.systems["Sol"].hexes
        for point in get_hex_vertices(q, r, game.system_zoom, game.system_pan_offset)
    ]
    assert SYSTEM_ZOOM_MIN <= game.system_zoom <= 1.0
    assert game.system_target_zoom == game.system_zoom
    assert min(point.x for point in points) >= viewport.left
    assert max(point.x for point in points) <= viewport.right
    assert min(point.y for point in points) >= viewport.top
    assert max(point.y for point in points) <= viewport.bottom
    assert game.system_camera_system_name == "Sol"


def test_system_wheel_zoom_is_cursor_anchored_and_independent():
    game = _camera_game(radius=5)
    game.system_camera_system_name = "Sol"
    mouse_pos = (SYSTEM_CENTER_IN_PX.x + 120, SYSTEM_CENTER_IN_PX.y - 60)

    with patch('pygame.mouse.get_pos', return_value=mouse_pos):
        game_camera.handle_mouse_wheel(game, 1)

    assert game.system_target_zoom == 1.1
    assert game.system_zoom_anchor_pixel == Position(120, -60)
    assert game.system_zoom_anchor_logical == Position(120, -60)
    assert game.sector_target_zoom == 1.0
    assert game.zoom_anchor_pixel is None

    game_camera.update_system_camera(game, 1.0 / 60.0)
    anchor = game.system_zoom_anchor_logical
    assert abs(game.system_pan_offset.x + anchor.x * game.system_zoom - 120) < 1e-6
    assert abs(game.system_pan_offset.y + anchor.y * game.system_zoom + 60) < 1e-6


def test_system_wheel_zoom_clamps_and_ignores_gui():
    game = _camera_game(radius=5)
    game.system_camera_system_name = "Sol"
    game.system_zoom = SYSTEM_ZOOM_MAX
    game.system_target_zoom = SYSTEM_ZOOM_MAX

    with patch('pygame.mouse.get_pos', return_value=SYSTEM_CENTER_IN_PX.to_tuple()):
        game_camera.handle_mouse_wheel(game, 1)
    assert game.system_target_zoom == SYSTEM_ZOOM_MAX

    game.system_zoom = SYSTEM_ZOOM_MIN
    game.system_target_zoom = SYSTEM_ZOOM_MIN
    with patch('pygame.mouse.get_pos', return_value=SYSTEM_CENTER_IN_PX.to_tuple()):
        game_camera.handle_mouse_wheel(game, -1)
    assert game.system_target_zoom == SYSTEM_ZOOM_MIN

    game.gui.is_mouse_over_gui_panels.return_value = True
    with patch('pygame.mouse.get_pos', return_value=SYSTEM_CENTER_IN_PX.to_tuple()):
        game_camera.handle_mouse_wheel(game, 1)
    assert game.system_target_zoom == SYSTEM_ZOOM_MIN


def test_system_hover_uses_inverse_camera_transform():
    game = _camera_game(radius=5)
    game.system_zoom = 1.8
    game.system_pan_offset = Position(-90, 55)
    game.galaxy_view_mouse_hover_system_name = None
    game.system_view_mouse_hover_hex = None
    game.sector_view_mouse_hover_object = None
    target = (2, -1)
    mouse_pos = hex_to_pixel(*target, game.system_zoom, game.system_pan_offset)

    update_hover_states(game, game.gui, mouse_pos)

    assert game.system_view_mouse_hover_hex == target


def test_stationary_system_middle_click_is_deferred_until_release():
    game = _camera_game(radius=5)
    game.system_camera_system_name = "Sol"
    click_handler = Mock()
    start = Position(300, 300)
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2)
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=2)

    handle_mouse_button_down(game, game.gui, down, start, None, click_handler)
    click_handler.assert_not_called()
    handle_mouse_button_up(game, game.gui, start, up, click_handler)

    click_handler.assert_called_once_with(2, start)
    assert game.is_dragging_camera is False


def test_system_camera_drag_does_not_start_over_gui():
    game = _camera_game(radius=5)
    game.gui.is_mouse_over_gui_panels.return_value = True
    click_handler = Mock()
    start = Position(300, 300)
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2)

    handle_mouse_button_down(game, game.gui, down, start, None, click_handler)

    assert game.is_dragging_camera is False
    click_handler.assert_not_called()


def test_system_middle_drag_pans_without_dispatching_navigation_click():
    game = _camera_game(radius=5)
    game.system_camera_system_name = "Sol"
    click_handler = Mock()
    start = Position(300, 300)
    end = Position(320, 288)
    down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2)
    up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=2)

    handle_mouse_button_down(game, game.gui, down, start, None, click_handler)
    handle_mouse_motion(game, end)
    handle_mouse_button_up(game, game.gui, end, up, click_handler)

    assert game.system_pan_offset == Position(20, -12)
    click_handler.assert_not_called()
    assert game.is_dragging_camera is False


def test_arrow_keys_pan_system_camera_without_changing_sector_camera():
    game = _camera_game(radius=5)
    game.system_camera_system_name = "Sol"
    game.ensure_system_camera = Mock()
    game.gui.is_any_text_entry_focused.return_value = False

    class LeftKeyState:
        def __getitem__(self, key):
            return key == pygame.K_LEFT

    with patch('pygame.key.get_pressed', return_value=LeftKeyState()):
        handle_keyboard_panning(game, game.gui, 0.1)

    assert game.system_pan_offset == Position(50.0, 0.0)
    assert game.sector_pan_offset == Position(0, 0)
