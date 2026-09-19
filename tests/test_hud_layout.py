from display_config import DisplayConfig
import pygame
import pytest
from display_config import DEFAULT_DISPLAY_CONFIG
SCREEN_RES = DEFAULT_DISPLAY_CONFIG.resolution
TOP_BAR_HEIGHT = DEFAULT_DISPLAY_CONFIG.top_bar_height
INFO_BOX_WIDTH = DEFAULT_DISPLAY_CONFIG.info_box_width
from geometry import Position
from gui.handler import GUI_Handler
from gui.layout_hud import setup_game_ui


class DummyGame:
    display_config = DisplayConfig()
    def __init__(self, view_mode="galaxy"):
        self.view_mode = view_mode
        self.current_player = None

    def get_player_income(self, player):
        return 10.0

    def get_player_upkeep(self, player):
        return 2.0


@pytest.fixture
def mock_gui():

    if not pygame.display.get_surface():
        pygame.display.set_mode((int(SCREEN_RES.x), int(SCREEN_RES.y)))
    gui = GUI_Handler(DisplayConfig(int(SCREEN_RES.x), int(SCREEN_RES.y)), DummyGame())
    return gui


def test_top_bar_spans_to_sidebar_edge(mock_gui):
    setup_game_ui(mock_gui)

    assert mock_gui.top_bar_panel is not None
    top_rect = mock_gui.top_bar_panel.get_relative_rect()
    assert top_rect.left == 0
    assert top_rect.top == 0
    assert top_rect.width == int(SCREEN_RES.x) - INFO_BOX_WIDTH
    assert top_rect.height == TOP_BAR_HEIGHT


def test_sidebar_spans_full_window_height(mock_gui):
    setup_game_ui(mock_gui)

    assert mock_gui.side_bar_info_panel is not None
    side_rect = mock_gui.side_bar_info_panel.get_relative_rect()
    assert side_rect.left == int(SCREEN_RES.x) - INFO_BOX_WIDTH
    assert side_rect.top == 0
    assert side_rect.width == INFO_BOX_WIDTH
    assert side_rect.height == int(SCREEN_RES.y)


def test_bottom_bar_spans_to_sidebar_edge(mock_gui):
    setup_game_ui(mock_gui)

    assert mock_gui.bottom_bar_panel is not None
    bottom_rect = mock_gui.bottom_bar_panel.get_relative_rect()
    assert bottom_rect.left == 0
    assert bottom_rect.top == int(SCREEN_RES.y) - TOP_BAR_HEIGHT
    assert bottom_rect.width == int(SCREEN_RES.x) - INFO_BOX_WIDTH
    assert bottom_rect.height == TOP_BAR_HEIGHT


def test_top_bar_elements_layout(mock_gui):
    setup_game_ui(mock_gui)

    # Back button, reset view button and view label
    assert mock_gui.back_button is not None
    assert mock_gui.reset_view_button is not None
    assert mock_gui.view_mode_label is not None
    back_rect = mock_gui.back_button.get_relative_rect()
    reset_rect = mock_gui.reset_view_button.get_relative_rect()
    view_rect = mock_gui.view_mode_label.get_relative_rect()
    assert back_rect.left >= 0
    assert reset_rect.left >= 0
    assert view_rect.left >= back_rect.right
    assert view_rect.left >= reset_rect.right

    # End turn button, player turn label, player color indicator
    assert mock_gui.end_turn_button is not None
    assert mock_gui.player_turn_label is not None
    assert mock_gui.player_color_indicator is not None
    end_turn_rect = mock_gui.end_turn_button.get_relative_rect()
    indicator_rect = mock_gui.player_color_indicator.get_relative_rect()
    turn_rect = mock_gui.player_turn_label.get_relative_rect()

    # End turn button anchored to the right of the shortened top bar
    assert end_turn_rect.right <= (int(SCREEN_RES.x) - INFO_BOX_WIDTH)
    assert turn_rect.right <= end_turn_rect.left
    assert indicator_rect.right <= turn_rect.left
    assert view_rect.right <= indicator_rect.left


def test_bottom_bar_elements_layout(mock_gui):
    setup_game_ui(mock_gui)

    # Action buttons on the left
    assert mock_gui.menu_button is not None
    assert mock_gui.comms_button is not None
    menu_rect = mock_gui.menu_button.get_relative_rect()
    comms_rect = mock_gui.comms_button.get_relative_rect()
    assert menu_rect.left >= 0
    assert comms_rect.left >= menu_rect.right

    # Resource readouts spaced across expanded space
    assert mock_gui.credits_label is not None
    assert mock_gui.metal_label is not None
    assert mock_gui.crystal_label is not None
    credits_rect = mock_gui.credits_label.get_relative_rect()
    metal_rect = mock_gui.metal_label.get_relative_rect()
    crystal_rect = mock_gui.crystal_label.get_relative_rect()

    assert credits_rect.left >= comms_rect.right
    assert metal_rect.left >= credits_rect.right
    assert crystal_rect.left >= metal_rect.right
    assert crystal_rect.right <= (int(SCREEN_RES.x) - INFO_BOX_WIDTH)


def test_is_mouse_over_gui_panels(mock_gui):
    setup_game_ui(mock_gui)
    mock_gui.show_game_ui()

    screen_w = int(SCREEN_RES.x)
    screen_h = int(SCREEN_RES.y)

    # Inside top bar (left, middle, right)
    assert mock_gui.is_mouse_over_gui_panels(Position(50, 15)) is True
    assert mock_gui.is_mouse_over_gui_panels(Position(screen_w // 2, 15)) is True
    assert mock_gui.is_mouse_over_gui_panels(Position(screen_w - 50, 15)) is True

    # Inside bottom bar (left, middle, near sidebar edge)
    assert mock_gui.is_mouse_over_gui_panels(Position(50, screen_h - 15)) is True
    assert mock_gui.is_mouse_over_gui_panels(Position(screen_w // 2, screen_h - 15)) is True
    assert mock_gui.is_mouse_over_gui_panels(Position(screen_w - INFO_BOX_WIDTH - 50, screen_h - 15)) is True

    # Inside sidebar
    assert mock_gui.is_mouse_over_gui_panels(Position(screen_w - (INFO_BOX_WIDTH // 2), screen_h // 2)) is True

    # Inside main game viewport area (should NOT be over UI panels)
    assert mock_gui.is_mouse_over_gui_panels(Position((screen_w - INFO_BOX_WIDTH) // 2, screen_h // 2)) is False


def test_top_bar_navigation_visibility_by_view_mode(mock_gui):
    setup_game_ui(mock_gui)

    # In galaxy view mode: Reset View is shown, Back is hidden
    mock_gui.game_instance.view_mode = 'galaxy'
    mock_gui.update_back_button_visibility()
    assert mock_gui.reset_view_button.visible is True
    assert mock_gui.back_button.visible is False

    # In system view mode: Back is shown, Reset View is hidden
    mock_gui.game_instance.view_mode = 'system'
    mock_gui.update_back_button_visibility()
    assert mock_gui.reset_view_button.visible is False
    assert mock_gui.back_button.visible is True

    # In sector view mode: Back is shown, Reset View is hidden
    mock_gui.game_instance.view_mode = 'sector'
    mock_gui.update_back_button_visibility()
    assert mock_gui.reset_view_button.visible is False
    assert mock_gui.back_button.visible is True

    # In main_menu view mode: both are hidden
    mock_gui.game_instance.view_mode = 'main_menu'
    mock_gui.update_back_button_visibility()
    assert mock_gui.reset_view_button.visible is False
    assert mock_gui.back_button.visible is False


def test_ingame_menu_toggles_reset_view_button(mock_gui):
    setup_game_ui(mock_gui)
    mock_gui.game_instance.view_mode = 'galaxy'
    mock_gui.update_back_button_visibility()
    assert mock_gui.reset_view_button.is_enabled is True

    mock_gui.show_ingame_menu()
    assert mock_gui.reset_view_button.is_enabled is False

    mock_gui.hide_ingame_menu()
    assert mock_gui.reset_view_button.is_enabled is True


pytestmark = pytest.mark.usefixtures("pygame_context")
