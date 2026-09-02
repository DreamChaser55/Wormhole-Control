"""Right-click context menu construction, hit-testing, and submenu navigation."""
import math
import typing
import pygame
import pygame_gui

from constants import CONTEXT_MENU_WIDTH, CONTEXT_MENU_ITEM_HEIGHT, TOP_BAR_HEIGHT
from geometry import Position
from utils import ContextMenuOption


def calculate_context_menu_min_col_width(
    gui_or_screen_res: typing.Any,
    options: typing.Sequence[typing.Union[typing.Tuple[str, typing.Any], str]]
) -> int:
    """Calculates the minimum column width needed to display all context menu options without clipping.

    Args:
        gui_or_screen_res: Target GUI_Handler instance or screen resolution Vector.
        options: Sequence of context menu option definitions.

    Returns:
        int: Minimum column width in pixels (at least CONTEXT_MENU_WIDTH - 10).
    """
    base_col_width = CONTEXT_MENU_WIDTH - 10
    if not options:
        return base_col_width

    gui = gui_or_screen_res if hasattr(gui_or_screen_res, 'manager') or hasattr(gui_or_screen_res, 'screen_res') else None
    screen_res = getattr(gui, 'screen_res', gui_or_screen_res)
    screen_h = getattr(screen_res, 'y', 720)

    font = None
    if gui is not None and hasattr(gui, 'manager') and getattr(gui.manager, 'ui_theme', None):
        for candidate_ids in [
            ['panel', '#context_menu_panel', 'button', '@context_menu_button'],
            ['button', '@context_menu_button'],
            ['button'],
            []
        ]:
            try:
                f = gui.manager.ui_theme.get_font(candidate_ids)
                if f is not None and hasattr(f, 'get_rect'):
                    font = f
                    break
            except Exception:
                continue

    max_text_width = 0
    for opt in options:
        if isinstance(opt, tuple) and len(opt) >= 2:
            text, action_id = opt[0], opt[1]
            if isinstance(action_id, list) or (isinstance(action_id, tuple) and len(action_id) == 2 and isinstance(action_id[0], list)):
                display_text = f"{text} \u25b8"
            else:
                display_text = str(text)
        else:
            display_text = str(opt)

        text_w = 0
        if font is not None:
            try:
                if hasattr(font, 'get_rect'):
                    rect = font.get_rect(display_text)
                    if hasattr(rect, 'width') and isinstance(rect.width, (int, float)):
                        text_w = int(rect.width)
                elif hasattr(font, 'size'):
                    sz = font.size(display_text)
                    if isinstance(sz, tuple) and len(sz) >= 1 and isinstance(sz[0], (int, float)):
                        text_w = int(sz[0])
            except Exception:
                text_w = 0

        # Heuristic fallback if font measurement is unavailable or failed (e.g. headless/mock tests)
        if text_w <= 0:
            scale = max(0.5, (screen_h / 720.0) ** 1.15)
            text_w = int(len(display_text) * 8.0 * scale)

        if text_w > max_text_width:
            max_text_width = text_w

    # Horizontal padding for UIButton (borders, shadow, and internal text margins on both sides)
    padding = max(36, int(36 * (screen_h / 720.0)))
    return max(base_col_width, max_text_width + padding)


def compute_context_menu_layout(
    screen_res: typing.Any,
    options_count: int,
    max_items_cap: int = 14,
    min_col_width: typing.Optional[int] = None
) -> typing.Tuple[int, int, int, int, int, int, int]:
    """Computes column/row counts and dimensions for context menu options.

    Args:
        screen_res: Screen resolution Vector or Position with x and y attributes.
        options_count (int): Total number of menu options to display.
        max_items_cap (int): Upper bound on items per column for ergonomic compactness.
        min_col_width (int, optional): Minimum column width needed to fit labels without clipping.

    Returns:
        tuple: (num_cols, num_rows, panel_width, panel_height, col_width, col_gap, row_height)
    """
    row_height = CONTEXT_MENU_ITEM_HEIGHT + 2
    margin = 8
    screen_w = getattr(screen_res, 'x', 1280)
    screen_h = getattr(screen_res, 'y', 720)
    avail_h = max(100, screen_h - TOP_BAR_HEIGHT - 2 * margin)
    max_items_per_col = max(4, min(max_items_cap, int((avail_h - 10) // row_height)))

    if options_count <= max_items_per_col:
        num_cols = 1
        num_rows = max(1, options_count)
    else:
        num_cols = max(1, math.ceil(options_count / max_items_per_col))
        num_rows = max(1, math.ceil(options_count / num_cols))

    base_col_width = CONTEXT_MENU_WIDTH - 10
    col_gap = 4
    target_col_width = max(base_col_width, min_col_width) if min_col_width is not None else base_col_width

    # Ensure total width doesn't exceed screen boundary
    avail_w = max(100, screen_w - 2 * margin)
    max_col_width = max(base_col_width, (avail_w - 10 - (num_cols - 1) * col_gap) // num_cols)
    col_width = min(target_col_width, max_col_width)

    panel_width = 10 + num_cols * col_width + (num_cols - 1) * col_gap
    panel_height = num_rows * row_height + 10

    return num_cols, num_rows, panel_width, panel_height, col_width, col_gap, row_height


def calculate_menu_position(
    screen_res: typing.Any,
    anchor_pos: Position,
    panel_width: int,
    panel_height: int,
    margin: int = 8
) -> Position:
    """Calculates optimal (x, y) coordinates for context menu to prevent clipping.

    Chooses opening direction based on available space and guarantees that the
    menu is clamped safely within the screen bounds.

    Args:
        screen_res: Screen resolution object with x and y attributes.
        anchor_pos (Position): Desired anchor coordinate (e.g. mouse click location).
        panel_width (int): Total width of context menu panel.
        panel_height (int): Total height of context menu panel.
        margin (int): Padding distance from screen borders.

    Returns:
        Position: Clamped top-left position for the menu panel.
    """
    screen_w = getattr(screen_res, 'x', 1280)
    screen_h = getattr(screen_res, 'y', 720)

    min_x = margin
    max_x = max(min_x, int(screen_w - panel_width - margin))
    min_y = TOP_BAR_HEIGHT + margin
    max_y = max(min_y, int(screen_h - panel_height - margin))

    # Vertical direction selection
    space_below = screen_h - anchor_pos.y - margin
    space_above = anchor_pos.y - TOP_BAR_HEIGHT - margin

    if panel_height <= space_below:
        pos_y = anchor_pos.y
    elif panel_height <= space_above:
        pos_y = anchor_pos.y - panel_height
    else:
        # Taller than space in one direction; place in direction with more space
        if space_below >= space_above:
            pos_y = anchor_pos.y
        else:
            pos_y = anchor_pos.y - panel_height

    pos_y = max(min_y, min(pos_y, max_y))

    # Horizontal direction selection
    space_right = screen_w - anchor_pos.x - margin
    space_left = anchor_pos.x - margin

    if panel_width <= space_right:
        pos_x = anchor_pos.x
    elif panel_width <= space_left:
        pos_x = anchor_pos.x - panel_width
    else:
        if space_right >= space_left:
            pos_x = anchor_pos.x
        else:
            pos_x = anchor_pos.x - panel_width

    pos_x = max(min_x, min(pos_x, max_x))

    return Position(pos_x, pos_y)


def close_context_menu(gui) -> None:
    """Closes and cleans up any currently active context menu panel.

    Args:
        gui: Target GUI_Handler instance.
    """
    if getattr(gui, 'context_menu_panel', None):
        gui.context_menu_panel.kill()
        gui.context_menu_panel = None
    gui.context_menu_buttons = []
    gui.context_menu_options = []
    gui.context_menu_target = None
    gui.context_menu_submenus = {}
    gui.context_menu_parent_options = None
    gui.context_menu_parent_position = None
    gui.context_menu_anchor = None
    gui.context_menu_history = []


def open_context_menu(gui, position: Position, options: typing.List[ContextMenuOption], target: typing.Any) -> None:
    """Creates and presents a right-click context menu at specified screen coordinates.

    Arranges options in dynamic multi-column layouts when needed and clamps position
    within screen boundaries to prevent clipping.

    Args:
        gui: Target GUI_Handler instance.
        position (Position): Screen position where context menu should open.
        options (typing.List[ContextMenuOption]): List of menu option definitions.
        target (typing.Any): Game entity or coordinate targeted by the context menu.
    """
    if getattr(gui, 'context_menu_panel', None):
        gui.context_menu_panel.kill()
        gui.context_menu_panel = None
    gui.context_menu_buttons = []

    gui.context_menu_options = options
    gui.context_menu_target = target
    gui.context_menu_submenus = {}

    if not options:
        return

    min_col_width = calculate_context_menu_min_col_width(gui, options)
    num_cols, num_rows, panel_width, panel_height, col_width, col_gap, row_height = compute_context_menu_layout(
        gui.screen_res, len(options), min_col_width=min_col_width
    )
    panel_pos = calculate_menu_position(gui.screen_res, position, panel_width, panel_height)

    panel_rect = pygame.Rect(panel_pos.x, panel_pos.y, panel_width, panel_height)

    gui.context_menu_panel = pygame_gui.elements.UIPanel(
        relative_rect=panel_rect,
        starting_height=10,
        manager=gui.manager,
        object_id='#context_menu_panel'
    )

    for i, (text, action_id) in enumerate(options):
        if isinstance(action_id, list):
            display_text = f"{text} \u25b8"
            gui.context_menu_submenus[i] = (action_id, target)
        elif isinstance(action_id, tuple) and len(action_id) == 2 and isinstance(action_id[0], list):
            display_text = f"{text} \u25b8"
            gui.context_menu_submenus[i] = (action_id[0], action_id[1])
        else:
            display_text = text

        col_idx = i // num_rows
        row_idx = i % num_rows
        btn_x = 5 + col_idx * (col_width + col_gap)
        btn_y = 5 + row_idx * row_height
        button_rect = pygame.Rect(btn_x, btn_y, col_width, CONTEXT_MENU_ITEM_HEIGHT)

        button = pygame_gui.elements.UIButton(
            relative_rect=button_rect,
            text=display_text,
            manager=gui.manager,
            container=gui.context_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id='@context_menu_button')
        )
        gui.context_menu_buttons.append(button)


def is_mouse_over_context_menu(gui, mouse_pos: typing.Union[Position, typing.Tuple[int, int], typing.Sequence[int]]) -> bool:
    """Determines if mouse coordinates lie within the open context menu bounds.

    Args:
        gui: Target GUI_Handler instance.
        mouse_pos (Position or tuple): Mouse screen coordinates to test.

    Returns:
        bool: True if mouse collides with open context menu panel.
    """
    if getattr(gui, 'context_menu_panel', None) and gui.context_menu_panel.visible:
        pos_tuple = mouse_pos.to_tuple() if hasattr(mouse_pos, 'to_tuple') else tuple(mouse_pos)
        return gui.context_menu_panel.get_abs_rect().collidepoint(pos_tuple)
    return False


def handle_button_index(gui, index: int) -> typing.Optional[dict]:
    """Handles click on a context menu item index, dealing with submenus, back, and action selection.

    Args:
        gui: Target GUI_Handler instance.
        index (int): Index of the clicked button in context_menu_buttons.

    Returns:
        typing.Optional[dict]: Action dict or {'action': 'ui_handled'}.
    """
    if index in getattr(gui, 'context_menu_submenus', {}):
        parent_options = gui.context_menu_options
        panel_rect = gui.context_menu_panel.get_abs_rect()
        parent_pos = Position(panel_rect.x, panel_rect.y)
        submenu_data = gui.context_menu_submenus[index]
        if isinstance(submenu_data, tuple) and len(submenu_data) == 2 and isinstance(submenu_data[0], list):
            sub_options, sub_target = submenu_data
        else:
            sub_options = submenu_data
            sub_target = gui.context_menu_target

        back_option = ("Back", "__submenu_back__")
        full_sub_options = [back_option] + sub_options

        if not hasattr(gui, 'context_menu_history') or gui.context_menu_history is None:
            gui.context_menu_history = []
        gui.context_menu_history.append((parent_options, parent_pos, gui.context_menu_target))
        gui.context_menu_parent_options = parent_options
        gui.context_menu_parent_position = parent_pos

        open_context_menu(gui, parent_pos, full_sub_options, sub_target)
        return {'action': 'ui_handled'}

    elif index < len(getattr(gui, 'context_menu_options', [])):
        text, action_id = gui.context_menu_options[index]
        if action_id == "__submenu_back__":
            parent_target = gui.context_menu_target
            if getattr(gui, 'context_menu_history', None) and len(gui.context_menu_history) > 0:
                history_entry = gui.context_menu_history.pop()
                if len(history_entry) >= 3:
                    parent_options, parent_pos, parent_target = history_entry[:3]
                else:
                    parent_options, parent_pos = history_entry[:2]
            else:
                parent_options = getattr(gui, 'context_menu_parent_options', None)
                parent_pos = getattr(gui, 'context_menu_parent_position', None) or Position(0, 0)

            if parent_options:
                open_context_menu(gui, parent_pos, parent_options, parent_target)
            else:
                close_context_menu(gui)
            return {'action': 'ui_handled'}
        else:
            action_result = {'action': 'context_menu_select', 'action_id': action_id, 'target': gui.context_menu_target}
            close_context_menu(gui)
            return action_result

    return None
