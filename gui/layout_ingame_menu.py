"""In-game menu (pause menu) and load game dialog layout functions."""
import pygame
import pygame_gui

_INGAME_MENU_BUTTONS = [
    ('resume_button', 'Resume', '#resume_button'),
    ('unit_editor_button', 'Unit Editor', '#unit_editor_button'),
    ('save_game_button', 'Save Game', '#save_game_button'),
    ('ingame_load_game_button', 'Load Game', '#ingame_load_game_button'),
    ('quit_to_menu_button', 'Quit to Main Menu', '#quit_to_menu_button'),
]


def setup_ingame_menu(gui) -> None:
    """Initializes the Pygame GUI elements for the in-game menu interface.

    Args:
        gui: Target GUI_Handler instance.
    """
    num_buttons = len(_INGAME_MENU_BUTTONS)
    button_height = int(40 * gui.scale_y)
    button_width = int(200 * gui.scale_x)
    internal_padding = int(15 * gui.scale_y)
    panel_width = int(300 * gui.scale_x)
    panel_height = internal_padding + num_buttons * (button_height + internal_padding)

    menu_rect = pygame.Rect(
        (gui.screen_res.x - panel_width) // 2,
        (gui.screen_res.y - panel_height) // 2,
        panel_width,
        panel_height
    )
    gui.ingame_menu_panel = pygame_gui.elements.UIPanel(
        relative_rect=menu_rect,
        starting_height=2,
        manager=gui.manager,
        object_id='#ingame_menu_panel'
    )

    current_y = internal_padding

    for attr_name, text, object_id in _INGAME_MENU_BUTTONS:
        button_rel_rect = pygame.Rect(
            (panel_width - button_width) // 2,
            current_y,
            button_width,
            -1
        )
        button = pygame_gui.elements.UIButton(
            relative_rect=button_rel_rect,
            text=text,
            manager=gui.manager,
            container=gui.ingame_menu_panel,
            object_id=object_id
        )
        setattr(gui, attr_name, button)
        current_y += button_height + internal_padding


def show_load_game_dialog(gui) -> None:
    """Displays a dialog window listing available save files to load.

    Args:
        gui: Target GUI_Handler instance.
    """
    import save_manager
    saves = save_manager.list_save_files()

    window_width = int(520 * gui.scale_x)
    window_height = int(420 * gui.scale_y)
    window_rect = pygame.Rect(
        (gui.screen_res.x - window_width) // 2,
        (gui.screen_res.y - window_height) // 2,
        window_width,
        window_height
    )

    if gui.load_save_window and gui.load_save_window.alive():
        gui.load_save_window.kill()

    gui.load_save_window = pygame_gui.elements.UIWindow(
        rect=window_rect,
        manager=gui.manager,
        window_display_title="Load Saved Game",
        object_id='#load_game_window'
    )

    item_list = []
    gui.save_file_paths = {}
    for s in saves:
        display_text = f"{s['filename']} (Turn {s['turn_number']} - {s['current_system']})"
        item_list.append(display_text)
        gui.save_file_paths[display_text] = s['filepath']

    if not item_list:
        item_list = ["No saved games found."]

    list_rect = pygame.Rect(int(10 * gui.scale_x), int(10 * gui.scale_y), window_width - int(45 * gui.scale_x), int(290 * gui.scale_y))
    gui.load_save_selection_list = pygame_gui.elements.UISelectionList(
        relative_rect=list_rect,
        item_list=item_list,
        manager=gui.manager,
        container=gui.load_save_window,
        object_id='#save_selection_list'
    )

    btn_w = int(120 * gui.scale_x)
    btn_h = int(35 * gui.scale_y)
    btn_y = int(315 * gui.scale_y)

    gui.load_save_confirm_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((window_width // 2 - btn_w - 10, btn_y), (btn_w, btn_h)),
        text='Load',
        manager=gui.manager,
        container=gui.load_save_window,
        object_id='#load_confirm_button'
    )

    gui.load_save_cancel_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((window_width // 2 + 10, btn_y), (btn_w, btn_h)),
        text='Cancel',
        manager=gui.manager,
        container=gui.load_save_window,
        object_id='#load_cancel_button'
    )
