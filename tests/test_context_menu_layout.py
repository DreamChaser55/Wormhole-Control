import pytest
import pygame
import pygame_gui
from unittest.mock import MagicMock

from geometry import Position, Vector
from constants import CONTEXT_MENU_WIDTH, CONTEXT_MENU_ITEM_HEIGHT, TOP_BAR_HEIGHT
from gui.context_menu import (
    compute_context_menu_layout,
    calculate_menu_position,
    open_context_menu,
    close_context_menu,
    handle_button_index,
    is_mouse_over_context_menu,
)


@pytest.fixture(autouse=True)
def setup_pygame_display():
    pygame.init()
    try:
        pygame.display.set_mode((1280, 720))
    except Exception:
        pass


def test_compute_context_menu_layout_single_column():
    screen_res = Vector(1920, 1080)
    # 3 options (e.g. default system/sector context menu)
    num_cols, num_rows, panel_width, panel_height, col_width, col_gap, row_height = compute_context_menu_layout(
        screen_res, 3, max_items_cap=14
    )
    assert num_cols == 1
    assert num_rows == 3
    assert panel_width == CONTEXT_MENU_WIDTH
    assert panel_height == 3 * (CONTEXT_MENU_ITEM_HEIGHT + 2) + 10


def test_compute_context_menu_layout_multi_column():
    screen_res = Vector(1920, 1080)
    # 16 options (e.g. Back + 15 unit templates)
    num_cols, num_rows, panel_width, panel_height, col_width, col_gap, row_height = compute_context_menu_layout(
        screen_res, 16, max_items_cap=14
    )
    assert num_cols >= 2
    assert num_rows <= 14
    expected_col_width = CONTEXT_MENU_WIDTH - 10
    expected_width = 10 + num_cols * expected_col_width + (num_cols - 1) * 4
    assert panel_width == expected_width
    assert panel_height == num_rows * (CONTEXT_MENU_ITEM_HEIGHT + 2) + 10


def test_compute_context_menu_layout_three_columns():
    screen_res = Vector(1920, 1080)
    # 30 options
    num_cols, num_rows, panel_width, panel_height, col_width, col_gap, row_height = compute_context_menu_layout(
        screen_res, 30, max_items_cap=14
    )
    assert num_cols >= 3
    assert panel_height == num_rows * (CONTEXT_MENU_ITEM_HEIGHT + 2) + 10


def test_calculate_menu_position_open_downward():
    screen_res = Vector(1920, 1080)
    anchor = Position(500, 300)
    panel_width = 250
    panel_height = 200
    pos = calculate_menu_position(screen_res, anchor, panel_width, panel_height)
    # Plenty of space below (1080 - 300 = 780 >= 200), so opens downwards at y=300
    assert pos.x == 500
    assert pos.y == 300


def test_calculate_menu_position_open_upward_near_bottom():
    screen_res = Vector(1920, 1080)
    anchor = Position(500, 950)
    panel_width = 250
    panel_height = 300
    pos = calculate_menu_position(screen_res, anchor, panel_width, panel_height)
    # Space below is only 1080 - 950 - 8 = 122 < 300; space above is 950 - 52 - 8 = 890 >= 300
    # Opens upwards at y = 950 - 300 = 650
    assert pos.x == 500
    assert pos.y == 650
    assert pos.y >= TOP_BAR_HEIGHT


def test_calculate_menu_position_clamping_at_edges():
    screen_res = Vector(1920, 1080)
    # 1. Extreme bottom edge
    anchor = Position(500, 1075)
    panel_width = 200
    panel_height = 400
    pos = calculate_menu_position(screen_res, anchor, panel_width, panel_height)
    assert pos.y + panel_height <= 1080 - 8
    assert pos.y >= TOP_BAR_HEIGHT + 8

    # 2. Extreme right edge
    anchor_right = Position(1900, 400)
    pos_right = calculate_menu_position(screen_res, anchor_right, panel_width, panel_height)
    assert pos_right.x + panel_width <= 1920 - 8
    assert pos_right.x >= 8

    # 3. Extreme top edge
    anchor_top = Position(100, 10)
    pos_top = calculate_menu_position(screen_res, anchor_top, panel_width, panel_height)
    assert pos_top.y >= TOP_BAR_HEIGHT + 8


def test_open_context_menu_multi_column_button_layout():
    screen_res = Vector(1280, 720)
    manager = pygame_gui.UIManager((1280, 720))

    gui = MagicMock()
    gui.screen_res = screen_res
    gui.manager = manager
    gui.context_menu_panel = None
    gui.context_menu_buttons = []
    gui.context_menu_options = []
    gui.context_menu_target = None
    gui.context_menu_submenus = {}
    gui.context_menu_parent_options = None
    gui.context_menu_parent_position = None
    gui.context_menu_anchor = None
    gui.context_menu_history = []

    # 16 options
    options = [(f"Template {i}", f"construct_tpl_{i}") for i in range(16)]
    click_pos = Position(400, 300)

    open_context_menu(gui, click_pos, options, target=None)

    assert gui.context_menu_panel is not None
    assert len(gui.context_menu_buttons) == 16

    num_cols, num_rows, panel_width, panel_height, col_width, col_gap, row_height = compute_context_menu_layout(
        screen_res, len(options)
    )

    for i, btn in enumerate(gui.context_menu_buttons):
        expected_col = i // num_rows
        expected_row = i % num_rows
        expected_x = 5 + expected_col * (col_width + col_gap)
        expected_y = 5 + expected_row * row_height
        assert btn.relative_rect.x == expected_x
        assert btn.relative_rect.y == expected_y

    close_context_menu(gui)
    assert gui.context_menu_panel is None
    assert gui.context_menu_buttons == []


def test_submenu_navigation_and_back():
    screen_res = Vector(1280, 720)
    manager = pygame_gui.UIManager((1280, 720))

    gui = MagicMock()
    gui.screen_res = screen_res
    gui.manager = manager
    gui.context_menu_panel = None
    gui.context_menu_buttons = []
    gui.context_menu_options = []
    gui.context_menu_target = None
    gui.context_menu_submenus = {}
    gui.context_menu_parent_options = None
    gui.context_menu_parent_position = None
    gui.context_menu_anchor = None
    gui.context_menu_history = []

    sub_options = [("Fighter", "construct_fighter"), ("Cruiser", "construct_cruiser")]
    parent_options = [
        ("Move Here", "move_here"),
        ("Construct", sub_options),
    ]

    click_pos = Position(300, 400)
    open_context_menu(gui, click_pos, parent_options, target="TargetHex")

    assert len(gui.context_menu_buttons) == 2
    assert 1 in gui.context_menu_submenus

    # 1. Click Construct (index 1) to navigate into submenu
    action = handle_button_index(gui, 1)
    assert action == {'action': 'ui_handled'}
    # Submenu should have 3 options: Back + 2 sub options
    assert len(gui.context_menu_options) == 3
    assert gui.context_menu_options[0] == ("Back", "__submenu_back__")
    assert len(gui.context_menu_buttons) == 3
    assert len(gui.context_menu_history) == 1

    # 2. Click Back (index 0)
    action_back = handle_button_index(gui, 0)
    assert action_back == {'action': 'ui_handled'}
    # Restored to 2 parent options
    assert len(gui.context_menu_options) == 2
    assert len(gui.context_menu_buttons) == 2
    assert gui.context_menu_options[0] == ("Move Here", "move_here")

    # 3. Select action from parent menu
    action_select = handle_button_index(gui, 0)
    assert action_select == {'action': 'context_menu_select', 'action_id': 'move_here', 'target': 'TargetHex'}
    assert gui.context_menu_panel is None
