"""Unit tests for the Reset View button, action routing, and R key shortcut."""
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch
import pygame
import pytest
import pygame_gui

from geometry import Position
from gui.event_router import process_event
from game_actions import handle_gui_action
from input_processor.keyboard_handler import handle_key_down


@pytest.fixture
def mock_game():
    game = SimpleNamespace(
        game_started=True,
        view_mode='galaxy',
        galaxy_zoom=2.5,
        galaxy_target_zoom=2.5,
        galaxy_pan_offset=Position(120, -80),
        galaxy_zoom_anchor_pixel=Position(30, 40),
        galaxy_zoom_anchor_logical=Position(10, 20),
        is_dragging_camera=True,
        camera_drag_start_pos=Position(100, 100),
        camera_drag_last_pos=Position(120, 120),
        camera_drag_view='galaxy',
        camera_drag_exceeded_threshold=True,
        pending_ability=None,
        sidebar_needs_update=False,
        current_system_name=None,
        selected_objects=[],
    )

    def reset_galaxy_camera():
        game.galaxy_zoom = 1.0
        game.galaxy_target_zoom = 1.0
        game.galaxy_pan_offset = Position(0, 0)
        game.galaxy_zoom_anchor_pixel = None
        game.galaxy_zoom_anchor_logical = None

    game.reset_galaxy_camera = reset_galaxy_camera
    return game


def test_event_router_dispatches_reset_galaxy_camera():
    gui = SimpleNamespace(
        settings_dialog=None,
        turn_briefing_window=None,
        planetary_window=None,
        antimatter_transport_window=None,
        unit_editor_window=None,
        unit_catalog_window=None,
        communications_window=None,
        new_game_wizard=None,
        ai_settings_dialog=None,
        new_game_button=None,
        load_game_button=None,
        about_button=None,
        quit_button=None,
        load_save_cancel_button=None,
        load_save_confirm_button=None,
        about_screen_back_button=None,
        end_turn_button=None,
        comms_button=None,
        unit_editor_button=None,
        back_button=None,
        reset_view_button=None,
        context_menu_buttons=[],
        dynamic_button_actions={},
        active_windows=[],
        manager=Mock(),
    )
    gui.manager.process_events.return_value = False
    button = Mock(spec=pygame_gui.elements.UIButton)
    gui.reset_view_button = button

    event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {'ui_element': button})
    result = process_event(gui, event)
    assert result == {'action': 'reset_galaxy_camera'}


def test_handle_gui_action_resets_galaxy_camera(mock_game):
    mock_game.gui = Mock()
    with patch('gui.turn_briefing_window.is_open', return_value=False):
        handle_gui_action(mock_game, {'action': 'reset_galaxy_camera'})

    assert mock_game.galaxy_zoom == 1.0
    assert mock_game.galaxy_pan_offset == Position(0, 0)
    assert mock_game.is_dragging_camera is False
    assert mock_game.camera_drag_start_pos is None


def test_keyboard_shortcut_r_resets_galaxy_view(mock_game):
    gui = MagicMock()
    for name in (
        'is_mouse_over_gui_panels', 'is_mouse_over_context_menu',
        'is_ingame_menu_open', 'is_unit_editor_open', 'is_retrofit_wizard_open',
        'is_communications_window_open', 'is_new_game_wizard_open',
        'is_any_text_entry_focused',
    ):
        getattr(gui, name).return_value = False
    gui.active_dialogs = []

    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)
    handled = handle_key_down(mock_game, gui, event)
    assert handled is False  # False means processed as hotkey and not modal-blocked
    assert mock_game.galaxy_zoom == 1.0
    assert mock_game.galaxy_pan_offset == Position(0, 0)
    assert mock_game.is_dragging_camera is False


def test_keyboard_shortcut_r_ignored_outside_galaxy_view(mock_game):
    mock_game.view_mode = 'system'
    mock_game.current_system_name = 'Sol'
    gui = MagicMock()
    for name in (
        'is_mouse_over_gui_panels', 'is_mouse_over_context_menu',
        'is_ingame_menu_open', 'is_unit_editor_open', 'is_retrofit_wizard_open',
        'is_communications_window_open', 'is_new_game_wizard_open',
        'is_any_text_entry_focused',
    ):
        getattr(gui, name).return_value = False
    gui.active_dialogs = []

    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)
    handle_key_down(mock_game, gui, event)
    # Camera should NOT have been reset
    assert mock_game.galaxy_zoom == 2.5
    assert mock_game.galaxy_pan_offset == Position(120, -80)


def test_keyboard_shortcut_r_blocked_while_typing(mock_game):
    gui = MagicMock()
    gui.is_any_text_entry_focused.return_value = True
    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)
    handled = handle_key_down(mock_game, gui, event)
    assert handled is True  # Consumed by typing interception
    assert mock_game.galaxy_zoom == 2.5
    assert mock_game.galaxy_pan_offset == Position(120, -80)
