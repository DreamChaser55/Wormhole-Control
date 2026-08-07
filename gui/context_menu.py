"""Right-click context menu construction, hit-testing, and submenu navigation."""
import typing
import pygame
import pygame_gui

from constants import CONTEXT_MENU_WIDTH, CONTEXT_MENU_ITEM_HEIGHT
from geometry import Position
from utils import ContextMenuOption


def close_context_menu(gui) -> None:
    """Closes and cleans up any currently active context menu panel.

    Args:
        gui: Target GUI_Handler instance.
    """
    if gui.context_menu_panel:
        gui.context_menu_panel.kill()
        gui.context_menu_panel = None
    gui.context_menu_buttons = []
    gui.context_menu_options = []
    gui.context_menu_target = None
    gui.context_menu_submenus = {}
    gui.context_menu_parent_options = None
    gui.context_menu_parent_position = None


def open_context_menu(gui, position: Position, options: typing.List[ContextMenuOption], target: typing.Any) -> None:
    """Creates and presents a right-click context menu at specified screen coordinates.

    Args:
        gui: Target GUI_Handler instance.
        position (Position): Screen position where context menu should open.
        options (typing.List[ContextMenuOption]): List of menu option definitions.
        target (typing.Any): Game entity or coordinate targeted by the context menu.
    """
    close_context_menu(gui)

    gui.context_menu_options = options
    gui.context_menu_target = target
    gui.context_menu_buttons = []
    gui.context_menu_submenus = {}

    if not options:
        return

    panel_width = CONTEXT_MENU_WIDTH
    panel_height = len(options) * (CONTEXT_MENU_ITEM_HEIGHT + 2) + 10

    if position.x + panel_width > gui.screen_res.x:
        position = Position(position.x - panel_width, position.y)
    if position.y + panel_height > gui.screen_res.y:
        position = Position(position.x, position.y - panel_height)
    panel_rect = pygame.Rect(position.x, position.y, panel_width, panel_height)

    gui.context_menu_panel = pygame_gui.elements.UIPanel(
        relative_rect=panel_rect,
        starting_height=10,
        manager=gui.manager,
        object_id='#context_menu_panel'
    )

    button_y = 5
    for i, (text, action_id) in enumerate(options):
        if isinstance(action_id, list):
            display_text = f"{text} \u25b8"
            gui.context_menu_submenus[i] = action_id
        else:
            display_text = text
        button_rect = pygame.Rect(5, button_y, panel_width - 10, CONTEXT_MENU_ITEM_HEIGHT)
        button = pygame_gui.elements.UIButton(
            relative_rect=button_rect,
            text=display_text,
            manager=gui.manager,
            container=gui.context_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id='@context_menu_button')
        )
        gui.context_menu_buttons.append(button)
        button_y += CONTEXT_MENU_ITEM_HEIGHT + 2


def is_mouse_over_context_menu(gui, mouse_pos: Position) -> bool:
    """Determines if mouse coordinates lie within the open context menu bounds.

    Args:
        gui: Target GUI_Handler instance.
        mouse_pos (Position): Mouse screen coordinates to test.

    Returns:
        bool: True if mouse collides with open context menu panel.
    """
    if gui.context_menu_panel and gui.context_menu_panel.visible:
        return gui.context_menu_panel.get_abs_rect().collidepoint(mouse_pos.to_tuple())
    return False


def handle_button_index(gui, index: int) -> typing.Optional[dict]:
    """Handles click on a context menu item index, dealing with submenus, back, and action selection.

    Args:
        gui: Target GUI_Handler instance.
        index (int): Index of the clicked button in context_menu_buttons.

    Returns:
        typing.Optional[dict]: Action dict or {'action': 'ui_handled'}.
    """
    if index in gui.context_menu_submenus:
        parent_options = gui.context_menu_options
        parent_pos = Position(gui.context_menu_panel.get_abs_rect().x, gui.context_menu_panel.get_abs_rect().y)
        sub_options = gui.context_menu_submenus[index]
        target = gui.context_menu_target
        back_option = ContextMenuOption("Back", "__submenu_back__")
        full_sub_options = [back_option] + sub_options
        open_context_menu(gui, parent_pos, full_sub_options, target)
        gui.context_menu_parent_options = parent_options
        gui.context_menu_parent_position = parent_pos
        return {'action': 'ui_handled'}
    elif index < len(gui.context_menu_options):
        text, action_id = gui.context_menu_options[index]
        if action_id == "__submenu_back__":
            parent_options = gui.context_menu_parent_options
            parent_pos = gui.context_menu_parent_position
            target = gui.context_menu_target
            open_context_menu(gui, parent_pos, parent_options, target)
            return {'action': 'ui_handled'}
        else:
            action_result = {'action': 'context_menu_select', 'action_id': action_id, 'target': gui.context_menu_target}
            close_context_menu(gui)
            return action_result
    return None
