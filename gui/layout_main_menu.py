"""Main menu and About screen layout functions."""
import pygame
import pygame_gui

_ABOUT_HTML = (
    "<b>Wormhole Control v0.1</b><br><br>"
    "A 2D turn-based 4X space strategy game prototype featuring a multi-scale universe with galaxy, system, and sector views.<br><br>"
    "<u>Game Features:</u><br>"
    "• Multi-scale universe navigation<br>"
    "• Modular ship design with customizable components<br>"
    "• Resource management (Credits, Metal, Crystal)<br>"
    "• Complex order system with command queuing<br>"
    "• Wormhole network for faster-than-light travel between star systems<br><br>"
    "<u>Controls:</u><br>"
    "- <b>Left Click:</b> Select units and objects<br>"
    "- <b>Right Click:</b> Context menu / Give orders<br>"
    "- <b>Drag:</b> Multi-select with selection box<br>"
    "- <b>Shift+Click:</b> Add to selection / remove from selection<br>"
    "- <b>ESC:</b> Back to Main menu<br>"
    "- <b>G:</b> Galaxy view<br>"
    "- <b>S:</b> System view<br>"
    "- <b>E:</b> End turn<br>"
    "- <b>End Turn:</b> Process turn and advance to next player<br><br>"
    "Navigate between views to explore your empire and manage your space fleets across the galaxy!"
)


def setup_main_menu(gui) -> None:
    """Creates the main menu UI elements.

    Args:
        gui: Target GUI_Handler instance.
    """
    gui.clear_and_reset()

    menu_width = int(300 * gui.scale_x)
    menu_height = int(360 * gui.scale_y)
    menu_x = (gui.screen_res.x - menu_width) // 2
    menu_y = (gui.screen_res.y - menu_height) // 2

    gui.main_menu_panel = pygame_gui.elements.UIPanel(
        relative_rect=pygame.Rect((menu_x, menu_y), (menu_width, menu_height)),
        starting_height=1,
        manager=gui.manager,
        object_id='#main_menu_panel'
    )

    pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect((0, int(10 * gui.scale_y)), (menu_width, int(50 * gui.scale_y))),
        text='Wormhole Control',
        manager=gui.manager,
        container=gui.main_menu_panel,
        object_id='#title_label'
    )

    button_width = menu_width - int(40 * gui.scale_x)
    button_height = int(50 * gui.scale_y)
    button_x = (menu_width - button_width) // 2

    gui.new_game_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((button_x, int(70 * gui.scale_y)), (button_width, button_height)),
        text='New Game',
        manager=gui.manager,
        container=gui.main_menu_panel,
        object_id='#new_game_button'
    )

    gui.load_game_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((button_x, int(130 * gui.scale_y)), (button_width, button_height)),
        text='Load Game',
        manager=gui.manager,
        container=gui.main_menu_panel,
        object_id='#load_game_button'
    )

    gui.about_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((button_x, int(190 * gui.scale_y)), (button_width, button_height)),
        text='About',
        manager=gui.manager,
        container=gui.main_menu_panel,
        object_id='#about_button'
    )

    gui.quit_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect((button_x, int(250 * gui.scale_y)), (button_width, button_height)),
        text='Quit',
        manager=gui.manager,
        container=gui.main_menu_panel,
        object_id='#quit_button'
    )


def setup_about_screen(gui) -> None:
    """Sets up the about screen UI.

    Args:
        gui: Target GUI_Handler instance.
    """
    gui.clear_and_reset()

    panel_width = int(500 * gui.scale_x)
    panel_height = int(350 * gui.scale_y)
    button_width = int(200 * gui.scale_x)
    button_height = int(40 * gui.scale_y)
    internal_padding = int(20 * gui.scale_y)

    about_rect = pygame.Rect(
        (gui.screen_res.x - panel_width) // 2,
        (gui.screen_res.y - panel_height) // 2,
        panel_width,
        panel_height
    )
    gui.about_panel = pygame_gui.elements.UIPanel(
        relative_rect=about_rect,
        starting_height=2,
        manager=gui.manager,
        object_id='#about_panel'
    )

    current_y = internal_padding

    title_rect = pygame.Rect(
        internal_padding,
        current_y,
        panel_width - (2 * internal_padding),
        int(40 * gui.scale_y)
    )
    gui.about_title = pygame_gui.elements.UILabel(
        relative_rect=title_rect,
        text='About Wormhole Control',
        manager=gui.manager,
        container=gui.about_panel
    )
    current_y += title_rect.height + internal_padding

    gui.about_text = pygame_gui.elements.UITextBox(
        html_text=_ABOUT_HTML,
        relative_rect=pygame.Rect(internal_padding, current_y, panel_width - (2 * internal_padding), int(200 * gui.scale_y)),
        manager=gui.manager,
        container=gui.about_panel
    )

    padding_from_bottom = int(20 * gui.scale_y)
    button_y = panel_height - button_height - padding_from_bottom

    button_rel_rect = pygame.Rect(
        (panel_width - button_width) // 2,
        button_y,
        button_width,
        button_height
    )
    gui.about_screen_back_button = pygame_gui.elements.UIButton(
        relative_rect=button_rel_rect,
        text='Back to Main Menu',
        manager=gui.manager,
        container=gui.about_panel,
        object_id='#about_back_button'
    )
