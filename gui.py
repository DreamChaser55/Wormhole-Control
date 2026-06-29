import logging

logger = logging.getLogger(__name__)

import pygame
import pygame_gui
import typing
import json
import os
from pygame import Color

from constants import (
    INFO_BOX_WIDTH, TOP_BAR_HEIGHT, CONTEXT_MENU_WIDTH, CONTEXT_MENU_ITEM_HEIGHT, BLUE, DEBUG, PROFILE, TEXT_SCALE
)
from utils import ContextMenuOption, resource_path
from geometry import Vector, Position
if typing.TYPE_CHECKING:
    from game import Game
    from entities import Player
    from unit_editor_gui import UnitEditorWindow


def _editor_action_to_gui_action(editor_action: str) -> typing.Optional[dict]:
    """Convert a UnitEditorWindow action string to a GUI action dict."""
    if editor_action == 'close':
        return {'action': 'toggle_unit_editor'}
    elif editor_action == 'design_saved':
        return {'action': 'unit_editor_design_saved'}
    elif editor_action == 'design_deleted':
        return {'action': 'unit_editor_design_deleted'}
    return None


class GUI_Handler:
    """Manages the Pygame GUI elements."""
    def __init__(self, screen_res: Vector, game_instance: 'Game'):
        self.screen_res = screen_res
        self.game_instance = game_instance
        self.scale_x = screen_res.x / 1280.0
        self.scale_y = screen_res.y / 720.0

        try:
            theme_path = resource_path('theme.json')
            
            # Dynamically scale theme text sizes
            scaled_theme_path = resource_path('theme_scaled.json')
            try:
                with open(theme_path, 'r') as f:
                    theme_data = json.load(f)
                
                # Scale fonts array
                for font in theme_data.get('fonts', []):
                    if 'size' in font:
                        font['size'] = str(max(1, int(int(font['size']) * TEXT_SCALE)))
                    if 'point_size' in font:
                        font['point_size'] = max(1, int(int(font['point_size']) * TEXT_SCALE))
                
                # Scale individual element font sizes
                for key, value in theme_data.items():
                    if isinstance(value, dict) and 'font' in value and 'size' in value['font']:
                        value['font']['size'] = str(max(1, int(int(value['font']['size']) * TEXT_SCALE)))

                # Scale drop-down menu options list item height
                dropdown_list_theme_id = "drop_down_menu.#drop_down_options_list"
                if dropdown_list_theme_id not in theme_data:
                    theme_data[dropdown_list_theme_id] = {"misc": {}}
                elif "misc" not in theme_data[dropdown_list_theme_id]:
                    theme_data[dropdown_list_theme_id]["misc"] = {}
                
                # Match the base height of 30 used for the dropdown button in game.py
                scaled_item_height = max(20, int(30 * TEXT_SCALE))
                theme_data[dropdown_list_theme_id]["misc"]["list_item_height"] = str(scaled_item_height)

                with open(scaled_theme_path, 'w') as f:
                    json.dump(theme_data, f)
                
                theme_path_to_use = scaled_theme_path
            except Exception as e:
                logger.error(f"Error generating scaled theme: {e}")
                theme_path_to_use = theme_path
                
            self.manager = pygame_gui.UIManager(self.screen_res.to_tuple(), theme_path_to_use)
        except FileNotFoundError:
             logger.debug("Warning: theme.json not found. Using default UI theme.")
             self.manager = pygame_gui.UIManager(self.screen_res.to_tuple())
        except pygame.error as e:
             logger.debug(f"Pygame error initializing UIManager (maybe font issue?): {e}")
             self.manager = pygame_gui.UIManager(self.screen_res.to_tuple())

        # Programmatic preloading for problematic fonts
        if self.manager and self.manager.ui_theme and self.manager.ui_theme.get_font_dictionary():
            font_dict = self.manager.ui_theme.get_font_dictionary()
            
            # Preload Arial 18 Regular
            arial_18_reg_id = font_dict.create_font_id(font_size=max(1, int(18 * TEXT_SCALE)), font_name='arial', bold=False, italic=False, antialiased=True)
            if not font_dict.check_font_preloaded(arial_18_reg_id):
                font_dict.preload_font(font_size=max(1, int(18 * TEXT_SCALE)), font_name='arial', bold=False, italic=False, antialiased=True)
            
            # Preload Arial 16 Regular
            arial_16_reg_id = font_dict.create_font_id(font_size=max(1, int(16 * TEXT_SCALE)), font_name='arial', bold=False, italic=False, antialiased=True)
            if not font_dict.check_font_preloaded(arial_16_reg_id):
                font_dict.preload_font(font_size=max(1, int(16 * TEXT_SCALE)), font_name='arial', bold=False, italic=False, antialiased=True)

            # Preload Noto Sans 14 Bold
            noto_sans_14_bold_id = font_dict.create_font_id(font_size=max(1, int(14 * TEXT_SCALE)), font_name='noto_sans', bold=True, italic=False, antialiased=True)
            if not font_dict.check_font_preloaded(noto_sans_14_bold_id):
                font_dict.preload_font(font_size=max(1, int(14 * TEXT_SCALE)), font_name='noto_sans', bold=True, italic=False, antialiased=True)

        if self.manager:
           self.manager.set_visual_debug_mode(True)

        # --- UI Elements --- 
        # Main Menu
        self.main_menu_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.new_game_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.about_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.quit_button: typing.Optional[pygame_gui.elements.UIButton] = None

        # About Screen
        self.about_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.about_title: typing.Optional[pygame_gui.elements.UILabel] = None
        self.about_text: typing.Optional[pygame_gui.elements.UITextBox] = None
        self.about_screen_back_button: typing.Optional[pygame_gui.elements.UIButton] = None

        # In-Game UI
        self.left_top_bar_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.left_bottom_bar_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.right_top_bar_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.back_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.view_mode_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self.end_turn_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.player_turn_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self.player_color_indicator: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.credits_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self.metal_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self.crystal_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self.side_bar_info_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.side_bar_scroll_bar: typing.Optional[pygame_gui.elements.UIVerticalScrollBar] = None
        self.side_bar_dynamic_elements: typing.List[pygame_gui.core.UIElement] = []
        self.dynamic_button_actions: typing.Dict[pygame_gui.elements.UIButton, typing.Dict[str, typing.Any]] = {}
        self.expanded_sections: typing.Dict[str, bool] = {}
        
        # Context Menu (Placeholders)
        self.context_menu_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.context_menu_buttons: typing.List[pygame_gui.elements.UIButton] = []
        self.context_menu_target: typing.Any = None
        self.context_menu_options: typing.List[ContextMenuOption] = []
        # Submenu support: maps button index -> list of sub-options
        self.context_menu_submenus: typing.Dict[int, typing.List[typing.Tuple[str, str]]] = {}
        self.context_menu_parent_options: typing.Optional[typing.List[ContextMenuOption]] = None
        self.context_menu_parent_position: typing.Optional[Position] = None

        # In-Game Menu
        self.ingame_menu_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.menu_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.resume_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.save_game_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.quit_to_menu_button: typing.Optional[pygame_gui.elements.UIButton] = None

        # Unit Editor
        self.unit_editor_window: typing.Optional['UnitEditorWindow'] = None
        self.unit_editor_button: typing.Optional[pygame_gui.elements.UIButton] = None

        # Galaxy generation area
        self.galaxy_generation_rect: typing.Optional[pygame.Rect] = None
        self.galaxy_border_color: pygame.Color = pygame.Color(BLUE)

    def clear_and_reset(self):
        """Clears all UI elements managed by this class."""
        if self.main_menu_panel: self.main_menu_panel.kill(); self.main_menu_panel = None
        if self.about_panel: self.about_panel.kill(); self.about_panel = None
        if self.left_top_bar_panel: self.left_top_bar_panel.kill(); self.left_top_bar_panel = None
        if self.left_bottom_bar_panel: self.left_bottom_bar_panel.kill(); self.left_bottom_bar_panel = None
        if self.right_top_bar_panel: self.right_top_bar_panel.kill(); self.right_top_bar_panel = None
        
        self.clear_side_bar_content()
        if self.side_bar_info_panel: self.side_bar_info_panel.kill(); self.side_bar_info_panel = None
        
        if self.context_menu_panel: self.context_menu_panel.kill(); self.context_menu_panel = None

        if self.ingame_menu_panel: self.ingame_menu_panel.kill(); self.ingame_menu_panel = None

        if self.unit_editor_window:
            self.unit_editor_window.kill()
            self.unit_editor_window = None

        self.new_game_button = self.about_button = self.quit_button = None
        self.about_title = self.about_text = self.about_screen_back_button = None
        self.back_button = self.view_mode_label = self.end_turn_button = self.player_turn_label = self.player_color_indicator = None
        self.credits_label = self.metal_label = self.crystal_label = None
        self.context_menu_buttons = []
        self.context_menu_target = None
        self.context_menu_options = []

        self.menu_button = self.resume_button = self.save_game_button = self.quit_to_menu_button = None
        self.unit_editor_button = None

        self.manager.clear_and_reset()

    # --- Visibility Control --- 
    def hide_all_panels(self):
        """Internal helper to hide all major UI panels."""
        if self.main_menu_panel: self.main_menu_panel.hide()
        if self.about_panel: self.about_panel.hide()
        if self.left_top_bar_panel: self.left_top_bar_panel.hide()
        if self.left_bottom_bar_panel: self.left_bottom_bar_panel.hide()
        if self.right_top_bar_panel: self.right_top_bar_panel.hide()
        if self.side_bar_info_panel: self.side_bar_info_panel.hide()
        if self.context_menu_panel: self.context_menu_panel.hide()
        if self.ingame_menu_panel: self.ingame_menu_panel.hide()
        if self.unit_editor_window: self.unit_editor_window.hide()

    def show_main_menu(self):
        """Configures and shows the Main Menu UI."""
        if not self.main_menu_panel or not self.main_menu_panel.alive():
            self.setup_main_menu()
        self.hide_all_panels()
        if self.main_menu_panel: self.main_menu_panel.show()

    def show_about_screen(self):
        """Configures and shows the About Screen UI."""
        if not self.about_panel or not self.about_panel.alive():
            self.setup_about_screen()
        self.hide_all_panels()
        if self.about_panel: self.about_panel.show()

    def show_game_ui(self):
        """Configures and shows the In-Game UI."""
        if not self.left_top_bar_panel or not self.left_top_bar_panel.alive():
             self.setup_game_ui()
        self.hide_all_panels()
        if self.left_top_bar_panel: self.left_top_bar_panel.show()
        if self.left_bottom_bar_panel: self.left_bottom_bar_panel.show()
        if self.right_top_bar_panel: self.right_top_bar_panel.show()
        if self.side_bar_info_panel: self.side_bar_info_panel.show()
        self.update_back_button_visibility()

    def toggle_ingame_menu(self):
        if not self.ingame_menu_panel or not self.ingame_menu_panel.visible:
            self.show_ingame_menu()
        else:
            self.hide_ingame_menu()

    def show_ingame_menu(self):
        # Configures and shows the In-Game Menu UI.
        if not self.ingame_menu_panel:
            self.setup_ingame_menu()
        if self.ingame_menu_panel: self.ingame_menu_panel.show()
        if self.end_turn_button: self.end_turn_button.disable()
        if self.back_button: self.back_button.disable()

    def hide_ingame_menu(self):
        # Hides the In-Game Menu UI.
        if self.ingame_menu_panel: self.ingame_menu_panel.hide()
        if self.end_turn_button: self.end_turn_button.enable()
        if self.back_button: self.back_button.enable()

    def is_ingame_menu_open(self) -> bool:
        return self.ingame_menu_panel is not None and self.ingame_menu_panel.visible

    # --- Setup Methods --- 

    def setup_main_menu(self):
        """Creates the main menu UI elements."""
        self.clear_and_reset()

        menu_width = int(300 * self.scale_x)
        menu_height = int(300 * self.scale_y)
        menu_x = (self.screen_res.x - menu_width) // 2
        menu_y = (self.screen_res.y - menu_height) // 2

        self.main_menu_panel = pygame_gui.elements.UIPanel(
            relative_rect=pygame.Rect((menu_x, menu_y), (menu_width, menu_height)),
            starting_height=1,
            manager=self.manager,
            object_id='#main_menu_panel'
        )

        title_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect((0, int(10 * self.scale_y)), (menu_width, int(50 * self.scale_y))),
            text='Wormhole Control',
            manager=self.manager,
            container=self.main_menu_panel,
            object_id='#title_label'
        )

        button_width = menu_width - int(40 * self.scale_x)
        button_height = int(50 * self.scale_y)
        button_x = (menu_width - button_width) // 2

        self.new_game_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((button_x, int(70 * self.scale_y)), (button_width, button_height)),
            text='New Game',
            manager=self.manager,
            container=self.main_menu_panel,
            object_id='#new_game_button'
        )

        self.about_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((button_x, int(130 * self.scale_y)), (button_width, button_height)),
            text='About',
            manager=self.manager,
            container=self.main_menu_panel,
            object_id='#about_button'
        )

        self.quit_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((button_x, int(190 * self.scale_y)), (button_width, button_height)),
            text='Quit',
            manager=self.manager,
            container=self.main_menu_panel,
            object_id='#quit_button'
        )

    def setup_about_screen(self):
        """Sets up the about screen UI."""
        self.clear_and_reset()

        panel_width = int(500 * self.scale_x)
        panel_height = int(350 * self.scale_y)
        button_width = int(200 * self.scale_x)
        button_height = int(40 * self.scale_y)
        internal_padding = int(20 * self.scale_y)

        about_rect = pygame.Rect(
            (self.screen_res.x - panel_width) // 2,
            (self.screen_res.y - panel_height) // 2,
            panel_width,
            panel_height
        )
        self.about_panel = pygame_gui.elements.UIPanel(
            relative_rect=about_rect,
            starting_height=2,
            manager=self.manager,
            object_id='#about_panel'
        )

        current_y = internal_padding

        title_rect = pygame.Rect(
            internal_padding,
            current_y,
            panel_width - (2 * internal_padding),
            int(40 * self.scale_y)
        )
        self.about_title = pygame_gui.elements.UILabel(
            relative_rect=title_rect,
            text='About Wormhole Control',
            manager=self.manager,
            container=self.about_panel
        )
        current_y += title_rect.height + internal_padding

        about_text = (
            "<b>Wormhole Control v0.1</b><br><br>" +
            "A 2D turn-based 4X space strategy game prototype featuring a multi-scale universe with galaxy, system, and sector views.<br><br>" +
            "<u>Game Features:</u><br>" +
            "• Multi-scale universe navigation<br>" +
            "• Modular ship design with customizable components<br>" +
            "• Resource management (Credits, Metal, Crystal)<br>" +
            "• Complex order system with command queuing<br>" +
            "• Wormhole network for faster-than-light travel between star systems<br><br>" +
            "<u>Controls:</u><br>" +
            "- <b>Left Click:</b> Select units and objects<br>" +
            "- <b>Right Click:</b> Context menu / Give orders<br>" +
            "- <b>Drag:</b> Multi-select with selection box<br>" +
            "- <b>Shift+Click:</b> Add to selection / remove from selection<br>" +
            "- <b>ESC:</b> Back to Main menu<br>" +
            "- <b>G:</b> Galaxy view<br>" +
            "- <b>S:</b> System view<br>" +
            "- <b>E:</b> End turn<br>" +
            "- <b>End Turn:</b> Process turn and advance to next player<br><br>" +
            "Navigate between views to explore your empire and manage your space fleets across the galaxy!"
        )
        self.about_text = pygame_gui.elements.UITextBox(
            html_text=about_text,
            relative_rect=pygame.Rect(internal_padding, current_y, panel_width - (2 * internal_padding), int(200 * self.scale_y)),
            manager=self.manager,
            container=self.about_panel
        )

        padding_from_bottom = int(20 * self.scale_y)
        button_y = panel_height - button_height - padding_from_bottom

        button_rel_rect = pygame.Rect(
            (panel_width - button_width) // 2,
            button_y,
            button_width,
            button_height
        )
        self.about_screen_back_button = pygame_gui.elements.UIButton(
            relative_rect=button_rel_rect,
            text='Back to Main Menu',
            manager=self.manager,
            container=self.about_panel,
            object_id='#about_back_button'
        )

    def setup_game_ui(self):
        """Initializes the Pygame GUI elements for the main game interface."""
        self.clear_and_reset()

        element_height = int(25 * self.scale_y)
        padding = int(5 * self.scale_y)
        panel_width = self.screen_res.x // 3

        # --- Top Left Panel ---
        left_panel_rect = pygame.Rect(0, 0, panel_width, TOP_BAR_HEIGHT)
        self.left_top_bar_panel = pygame_gui.elements.UIPanel(relative_rect=left_panel_rect,
                                                            starting_height=1,
                                                            manager=self.manager,
                                                            object_id='#left_top_bar')

        # --- Elements in Top Left Panel (left-alinged) ---
        back_button_width = int(60 * self.scale_x)
        back_button_rect = pygame.Rect(padding, padding, back_button_width, -1)
        self.back_button = pygame_gui.elements.UIButton(
            relative_rect=back_button_rect,
            text='Back',
            manager=self.manager,
            container=self.left_top_bar_panel,
            visible=False,
            object_id='#back_button'
        )

        view_label_width = int(300 * self.scale_x)
        view_label_rect = pygame.Rect(back_button_rect.right + padding, padding, view_label_width, -1)
        self.view_mode_label = pygame_gui.elements.UILabel(relative_rect=view_label_rect,
                                                      text=f"View: {self.game_instance.view_mode.capitalize()}",
                                                      manager=self.manager,
                                                      container=self.left_top_bar_panel,
                                                      object_id='#view_label')

        # --- Bottom Left Panel ---
        bottom_panel_width = panel_width
        left_bottom_panel_rect = pygame.Rect(0, self.screen_res.y - TOP_BAR_HEIGHT, bottom_panel_width, TOP_BAR_HEIGHT)
        self.left_bottom_bar_panel = pygame_gui.elements.UIPanel(relative_rect=left_bottom_panel_rect,
                                                              starting_height=1,
                                                              manager=self.manager,
                                                              object_id='#left_bottom_bar')

        # --- Elements in Bottom Left Panel (single row layout) ---
        menu_button_width = int(70 * self.scale_x)
        menu_button_rect = pygame.Rect(padding, padding, menu_button_width, -1)
        self.menu_button = pygame_gui.elements.UIButton(relative_rect=menu_button_rect,
                                                         text='Menu',
                                                         manager=self.manager,
                                                         container=self.left_bottom_bar_panel,
                                                         object_id='#menu_button')

        buttons_right = menu_button_rect.right
        label_spacing = int(5 * self.scale_x)
        remaining_width = bottom_panel_width - buttons_right - padding
        label_width = (remaining_width - 2 * label_spacing) // 3

        credits_x = buttons_right + padding
        self.credits_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(credits_x, padding, label_width, -1),
            text="Credits: 0",
            manager=self.manager,
            container=self.left_bottom_bar_panel,
            object_id='#resource_label'
        )
        self.credits_label.text_horiz_alignment='left'

        metal_x = credits_x + label_width + label_spacing
        self.metal_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(metal_x, padding, label_width, -1),
            text="Metal: 0",
            manager=self.manager,
            container=self.left_bottom_bar_panel,
            object_id='#resource_label'
        )
        self.metal_label.text_horiz_alignment='left'

        crystal_x = metal_x + label_width + label_spacing
        self.crystal_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(crystal_x, padding, label_width, -1),
            text="Crystal: 0",
            manager=self.manager,
            container=self.left_bottom_bar_panel,
            object_id='#resource_label'
        )
        self.crystal_label.text_horiz_alignment='left'

        # --- Top Right Panel ---
        right_panel_rect = pygame.Rect(self.screen_res.x - panel_width, 0, panel_width, TOP_BAR_HEIGHT)
        self.right_top_bar_panel = pygame_gui.elements.UIPanel(relative_rect=right_panel_rect,
                                                             starting_height=1,
                                                             manager=self.manager,
                                                             object_id='#right_top_bar')

        # --- Elements in Top Right Panel (right-aligned) ---

        end_turn_button_width = int(100 * self.scale_x)
        end_turn_button_rect = pygame.Rect(panel_width - end_turn_button_width - padding,
                                             padding,
                                             end_turn_button_width,
                                             -1)
        self.end_turn_button = pygame_gui.elements.UIButton(relative_rect=end_turn_button_rect,
                                                              text='End Turn',
                                                              manager=self.manager,
                                                              container=self.right_top_bar_panel,
                                                              object_id='#end_turn_button')

        turn_label_width = int(180 * self.scale_x)
        turn_label_rect = pygame.Rect(end_turn_button_rect.left - turn_label_width - padding,
                                        padding,
                                        turn_label_width,
                                        -1)
        self.player_turn_label = pygame_gui.elements.UILabel(relative_rect=turn_label_rect,
                                                            text="",
                                                            manager=self.manager,
                                                            container=self.right_top_bar_panel,
                                                            object_id='#turn_label')

        indicator_size = int(15 * min(self.scale_x, self.scale_y))
        indicator_rect = pygame.Rect(turn_label_rect.left - indicator_size - padding,
                                      (TOP_BAR_HEIGHT - indicator_size) // 2,
                                      indicator_size,
                                      indicator_size)
        self.player_color_indicator = pygame_gui.elements.UIPanel(relative_rect=indicator_rect,
                                                                 manager=self.manager,
                                                                 container=self.right_top_bar_panel,
                                                                 object_id='#player_color_indicator')

        # --- Side Bar Info Panel ---
        side_bar_info_panel_x = self.screen_res.x - INFO_BOX_WIDTH
        side_bar_info_panel_y = TOP_BAR_HEIGHT
        side_bar_info_panel_h = self.screen_res.y - side_bar_info_panel_y

        side_bar_info_panel_rect = pygame.Rect(
            side_bar_info_panel_x,
            side_bar_info_panel_y,
            INFO_BOX_WIDTH,
            side_bar_info_panel_h
        )

        self.side_bar_info_panel = pygame_gui.elements.UIPanel(
            relative_rect=side_bar_info_panel_rect,
            starting_height=1,
            manager=self.manager,
            object_id='#side_bar_info_panel'
        )

        galaxy_rect_x = 0
        galaxy_rect_y = TOP_BAR_HEIGHT
        galaxy_rect_width = side_bar_info_panel_x 
        galaxy_rect_height = self.screen_res.y - TOP_BAR_HEIGHT * 2
        self.galaxy_generation_rect = pygame.Rect(galaxy_rect_x, galaxy_rect_y, galaxy_rect_width, galaxy_rect_height)

        self.hide_all_panels()

    def setup_ingame_menu(self):
        """Initializes the Pygame GUI elements for the in-game menu interface."""
        num_buttons = 4
        button_height = int(40 * self.scale_y)  # Used only for panel height estimation
        button_width = int(200 * self.scale_x)
        internal_padding = int(15 * self.scale_y)
        panel_width = int(300 * self.scale_x)
        panel_height = internal_padding + num_buttons * (button_height + internal_padding)

        menu_rect = pygame.Rect(
            (self.screen_res.x - panel_width) // 2,
            (self.screen_res.y - panel_height) // 2,
            panel_width,
            panel_height
        )
        self.ingame_menu_panel = pygame_gui.elements.UIPanel(
            relative_rect=menu_rect,
            starting_height=2,
            manager=self.manager,
            object_id='#ingame_menu_panel'
        )

        current_y = internal_padding

        # Resume Button
        button_rel_rect = pygame.Rect(
            (panel_width - button_width) // 2,
            current_y,
            button_width,
            -1
        )
        self.resume_button = pygame_gui.elements.UIButton(
            relative_rect=button_rel_rect,
            text='Resume',
            manager=self.manager,
            container=self.ingame_menu_panel,
            object_id='#resume_button'
        )
        current_y += button_height + internal_padding

        # Unit Editor Button
        button_rel_rect = pygame.Rect(
            (panel_width - button_width) // 2,
            current_y,
            button_width,
            -1
        )
        self.unit_editor_button = pygame_gui.elements.UIButton(
            relative_rect=button_rel_rect,
            text='Unit Editor',
            manager=self.manager,
            container=self.ingame_menu_panel,
            object_id='#unit_editor_button'
        )
        current_y += button_height + internal_padding

        # Save Game Button
        button_rel_rect = pygame.Rect(
            (panel_width - button_width) // 2,
            current_y,
            button_width,
            -1
        )
        self.save_game_button = pygame_gui.elements.UIButton(
            relative_rect=button_rel_rect,
            text='Save Game',
            manager=self.manager,
            container=self.ingame_menu_panel,
            object_id='#save_game_button'
        )
        current_y += button_height + internal_padding

        # Quit to Main Menu Button
        button_rel_rect = pygame.Rect(
            (panel_width - button_width) // 2,
            current_y,
            button_width,
            -1
        )
        self.quit_to_menu_button = pygame_gui.elements.UIButton(
            relative_rect=button_rel_rect,
            text='Quit to Main Menu',
            manager=self.manager,
            container=self.ingame_menu_panel,
            object_id='#quit_to_menu_button'
        )

    def process_event(self, event: pygame.event.Event) -> typing.Optional[dict]:
        """Processes a single Pygame event for the GUI Manager.

        Handles button clicks and returns a dictionary describing the action
        requested by the user via the UI (e.g., {'action': 'new_game'}).
        Returns {'action': 'ui_handled'} if the event was handled by the GUI but requires no specific game action.
        Returns None if the event was not handled by the GUI manager at all.
        """

        handled_by_manager = self.manager.process_events(event)
        action_result = None

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if DEBUG:
                logger.debug(f"[GUI_Handler DEBUG] UI_BUTTON_PRESSED: event.ui_element={event.ui_element}")
            
            # --- Main Menu Buttons ---
            if self.new_game_button and event.ui_element == self.new_game_button:
                logger.debug("New Game button pressed (GUI)")
                action_result = {'action': 'new_game'}
            elif self.about_button and event.ui_element == self.about_button:
                logger.debug("About button pressed (GUI)")
                self.show_about_screen()
            elif self.quit_button and event.ui_element == self.quit_button:
                logger.debug("Quit button pressed (GUI)")
                action_result = {'action': 'quit'}

            # --- About Screen Buttons ---
            elif self.about_screen_back_button and event.ui_element == self.about_screen_back_button:
                logger.debug("About Back button pressed (GUI)")
                self.show_main_menu()
            
            # --- In-Game UI Buttons ---
            elif self.end_turn_button and event.ui_element == self.end_turn_button:
                logger.debug("End Turn button pressed (GUI)")
                action_result = {'action': 'end_turn'}
            elif self.back_button and event.ui_element == self.back_button:
                 logger.debug("Back button pressed (GUI)")
                 action_result = {'action': 'navigate_back'}

            elif event.ui_element and event.ui_element.object_ids and event.ui_element.object_ids[-1] == '#toggle_inhibitor_button':
                from entities import Unit, ToggleInhibitorOrder

                keys = pygame.key.get_pressed()
                shift_pressed = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]

                for selected_unit in self.game_instance.selected_objects:
                    if isinstance(selected_unit, Unit) and selected_unit.inhibitor_component:
                        if shift_pressed:
                            # Queue an order if SHIFT is pressed
                            inhibitor = selected_unit.inhibitor_component
                            turn_on = not inhibitor.is_active
                            new_order = ToggleInhibitorOrder(selected_unit, {'turn_on': turn_on})
                            selected_unit.commander_component.add_order(new_order)
                            logger.debug(f"Queued TOGGLE_INHIBITOR order for {selected_unit.name}.")
                        else:
                            # Directly toggle if SHIFT is not pressed
                            success = selected_unit.inhibitor_component.toggle(galaxy_ref=self.game_instance.galaxy)
                            if success:
                                logger.debug(f"Directly toggled inhibitor for {selected_unit.name}.")
                            else:
                                logger.debug(f"Direct inhibitor toggle failed for {selected_unit.name}.")

                self.game_instance.sidebar_needs_update = True
                action_result = {'action': 'ui_handled'}

            # --- Context Menu Buttons ---
            elif self.context_menu_buttons:
                for i, button in enumerate(self.context_menu_buttons):
                    if event.ui_element == button and i < len(self.context_menu_options):
                        # Check if this is a submenu parent button
                        if i in self.context_menu_submenus:
                            # Replace menu in-place with submenu options
                            sub_options = self.context_menu_submenus[i]
                            saved_target = self.context_menu_target
                            saved_parent_options = list(self.context_menu_options)
                            saved_position = self.context_menu_parent_position or Position(
                                self.context_menu_panel.get_abs_rect().x,
                                self.context_menu_panel.get_abs_rect().y
                            )
                            # Build child menu with a back item
                            child_options = [("← Back", "__submenu_back__")] + sub_options
                            self.open_context_menu(saved_position, child_options, saved_target)
                            # Store parent options for back navigation
                            self.context_menu_parent_options = saved_parent_options
                            self.context_menu_parent_position = saved_position
                            action_result = {'action': 'ui_handled'}
                            break
                        # Check if this is the "back" button
                        elif self.context_menu_options[i][1] == "__submenu_back__":
                            if self.context_menu_parent_options:
                                saved_target = self.context_menu_target
                                saved_position = self.context_menu_parent_position or Position(
                                    self.context_menu_panel.get_abs_rect().x,
                                    self.context_menu_panel.get_abs_rect().y
                                )
                                parent_options = self.context_menu_parent_options
                                self.open_context_menu(saved_position, parent_options, saved_target)
                                self.context_menu_parent_options = None
                            action_result = {'action': 'ui_handled'}
                            break
                        else:
                            action_id = self.context_menu_options[i][1]
                            logger.debug(f"[GUI] Context menu button '{action_id}' pressed")
                            action_result = {
                                'action': 'context_menu_select', 
                                'action_id': action_id, 
                                'target': self.context_menu_target
                            } 
                            self.close_context_menu()
                            break
            
            elif event.ui_element in self.dynamic_button_actions and self.dynamic_button_actions[event.ui_element]:
                button_data = self.dynamic_button_actions[event.ui_element]
                action_id = button_data['action_id']
                target_data = button_data['target_data']

                if action_id == 'toggle_orders_queue':
                    section_key = f"{target_data}_orders_queue"
                    current_state_before_toggle = self.is_section_expanded(section_key)
                    self.toggle_section_expansion(section_key)
                    current_state_after_toggle = self.is_section_expanded(section_key)
                    self.game_instance.sidebar_needs_update = True
                    action_result = {'action': 'ui_handled'}
                elif action_id == 'deploy_ship':
                    carrier_id, docked_unit_id = target_data
                    action_result = {
                        'action': 'deploy_ship',
                        'carrier_id': carrier_id,
                        'docked_unit_id': docked_unit_id
                    }
                elif action_id == 'launch_all_wings':
                    carrier_id = target_data
                    action_result = {
                        'action': 'launch_all_wings',
                        'carrier_id': carrier_id
                    }
                elif action_id == 'recall_ship':
                    carrier_id, launched_unit_id = target_data
                    action_result = {
                        'action': 'recall_ship',
                        'carrier_id': carrier_id,
                        'launched_unit_id': launched_unit_id
                    }
                elif action_id == 'use_ability':
                    # target_data is a dict with ability_type_str and targeting flags
                    action_result = {
                        'action': 'use_ability',
                        'ability_type_str': target_data.get('ability_type_str'),
                        'requires_target_unit': target_data.get('requires_target_unit', False),
                        'requires_target_position': target_data.get('requires_target_position', False),
                    }

                        # --- In-Game Menu Buttons ---
            elif self.menu_button and event.ui_element == self.menu_button:
                logger.debug("Menu button pressed (GUI)")
                action_result = {'action': 'toggle_ingame_menu'}
            elif self.resume_button and event.ui_element == self.resume_button:
                logger.debug("Resume button pressed (GUI)")
                action_result = {'action': 'toggle_ingame_menu'}
            elif self.save_game_button and event.ui_element == self.save_game_button:
                logger.debug("Save Game button pressed (GUI)")
                action_result = {'action': 'save_game'}
            elif self.quit_to_menu_button and event.ui_element == self.quit_to_menu_button:
                logger.debug("Quit to Main Menu button pressed (GUI)")
                action_result = {'action': 'quit_to_main_menu'}
            elif self.unit_editor_button and event.ui_element == self.unit_editor_button:
                logger.debug("Unit Editor button pressed (GUI)")
                action_result = {'action': 'toggle_unit_editor'}
            elif self.unit_editor_window and self.unit_editor_window.is_visible:
                # Let the unit editor handle its own button presses
                editor_action = self.unit_editor_window.process_event(event)
                if editor_action:
                    action_result = _editor_action_to_gui_action(editor_action)
                    if action_result is None:
                        action_result = {'action': 'ui_handled'}
                else:
                    if DEBUG:
                        logger.debug(f"[GUI_Handler DEBUG] Clicked UI element {event.ui_element} not found in dynamic_button_actions or no action_id.")
            else:
                if DEBUG:
                    logger.debug(f"[GUI_Handler DEBUG] Clicked UI element {event.ui_element} not found in dynamic_button_actions or no action_id.")

        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            # Forward dropdown change to unit editor first; if it consumes it, don't treat it as a component_selected
            editor_action = self.process_unit_editor_event(event)
            if editor_action:
                action_result = _editor_action_to_gui_action(editor_action)
                if action_result is None:
                    action_result = {'action': 'ui_handled'}
            else:
                logger.debug(f"Drop down menu changed (GUI): {event.text}")
                action_result = {'action': 'component_selected', 'component_name': event.text}

        # If no action from standard handling, check if the unit editor consumed this event
        if not action_result and self.unit_editor_window and self.unit_editor_window.is_visible:
            editor_action = self.process_unit_editor_event(event)
            if editor_action:
                action_result = _editor_action_to_gui_action(editor_action)
                if action_result is None:
                    action_result = {'action': 'ui_handled'}

        if action_result:
            return action_result
        elif handled_by_manager:
             return {'action': 'ui_handled'}
        else:
             return None

    def update(self, time_delta: float):
        """Updates the GUI Manager."""
        self.manager.update(time_delta)
        # Forward update to unit editor so its internal widgets animate/update
        if self.unit_editor_window and self.unit_editor_window.is_visible:
            pass  # UIManager handles child widget updates automatically

    def draw(self, surface: pygame.Surface):
        """Draws the UI elements onto the provided surface."""
        if self.galaxy_generation_rect and self.game_instance.view_mode == 'galaxy':
            pygame.draw.rect(surface, self.galaxy_border_color, self.galaxy_generation_rect, 2)
        
        self.manager.draw_ui(surface)

        # Draw custom pygame elements (capacity bar) after the UI manager
        if self.unit_editor_window and self.unit_editor_window.is_visible:
            self.unit_editor_window.draw(surface)

    # --- Unit Editor helpers ---

    def open_unit_editor(self, template_manager) -> None:
        """Create (if needed) and show the Unit Editor window."""
        if self.unit_editor_window is None:
            from unit_editor_gui import UnitEditorWindow
            self.unit_editor_window = UnitEditorWindow(
                manager=self.manager,
                screen_res=pygame.Vector2(self.screen_res.x, self.screen_res.y),
                template_manager=template_manager,
            )
        self.unit_editor_window.show()
        self.hide_ingame_menu()

    def close_unit_editor(self) -> None:
        """Hide the Unit Editor window."""
        if self.unit_editor_window:
            self.unit_editor_window.hide()

    def is_unit_editor_open(self) -> bool:
        """Return True if the unit editor is currently visible."""
        return self.unit_editor_window is not None and self.unit_editor_window.is_visible

    def process_unit_editor_event(self, event: pygame.event.Event) -> typing.Optional[str]:
        """Forward a pygame event to the unit editor and return any action string."""
        if self.unit_editor_window:
            return self.unit_editor_window.process_event(event)
        return None

    # --- UI Update Methods ---
    def update_back_button_visibility(self):
        """Shows/hides the back button based on game view mode."""
        if self.back_button:
            if self.game_instance.view_mode in ['system', 'sector']:
                self.back_button.show()
            else:
                self.back_button.hide()

    def update_view_mode_label(self, text: str):
        """Updates the text of the view mode label."""
        if self.view_mode_label:
            self.view_mode_label.set_text(text)
        self.update_back_button_visibility()

    def update_turn_label(self, text: str):
        """Updates the text of the player turn label."""
        if self.player_turn_label:
            self.player_turn_label.set_text(text)

    def update_player_color_indicator(self, color: Color):
        """Updates the background color of the player indicator panel."""
        if self.player_color_indicator:
            try:
                valid_color = Color(color)
                self.player_color_indicator.background_colour = valid_color
                self.player_color_indicator.rebuild() # Necessary to apply color change
            except (ValueError, TypeError) as e:
                 logger.debug(f"Error setting player indicator color ({color}): {e}")

    def update_resource_display(self, player: 'Player'):
        """Updates the resource labels with the current player's values."""
        if self.credits_label:
            self.credits_label.set_text(f"Credits: {player.credits:.0f}")
        if self.metal_label:
            self.metal_label.set_text(f"Metal: {player.metal:.0f}")
        if self.crystal_label:
            self.crystal_label.set_text(f"Crystal: {player.crystal:.0f}")

    def clear_side_bar_content(self):
        """Kills and removes all dynamically added UI elements from the sidebar."""
        for element in self.side_bar_dynamic_elements:
            if element.alive():
                element.kill()
        self.side_bar_dynamic_elements.clear()
        self.dynamic_button_actions.clear()

    def is_section_expanded(self, section_id: str) -> bool:
        """Checks if a given UI section is marked as expanded."""
        return self.expanded_sections.get(section_id, False)

    def toggle_section_expansion(self, section_id: str):
        """Toggles the expansion state of a given UI section."""
        self.expanded_sections[section_id] = not self.is_section_expanded(section_id)

    def wrap_text_to_lines(self, text_to_wrap: str, max_pixel_width: int, font: pygame.font.Font) -> typing.Tuple[typing.List[str], int]:
        """
        Wraps text to fit within a maximum pixel width.

        Args:
            text_to_wrap: The string to wrap.
            max_pixel_width: The maximum width in pixels for a line.
            font: The pygame.font.Font object used for measuring text.

        Returns:
            A tuple containing:
                - A list of strings, where each string is a wrapped line.
                - The height of a single line of text with the given font.
        """
        if not text_to_wrap:
            return [""], font.get_rect("A").height if font else 10

        line_height = font.get_rect("A").height
        if max_pixel_width <= 0:
             return [text_to_wrap], line_height

        lines = []
        words = text_to_wrap.split(' ')
        current_line = ""

        if not words:
            return [""], line_height

        for word_idx, word in enumerate(words):
            try:
                word_width = font.get_rect(word).width
            except pygame.error as e:
                logger.debug(f"Warning: Pygame font error sizing word '{word}': {e}. Treating as zero width for layout.")
                word_width = 0


            if word_width > max_pixel_width and len(word) > 1:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                
                temp_char_line = ""
                for char_idx, char in enumerate(word):
                    try:
                        char_render_width = font.get_rect(temp_char_line + char).width
                    except pygame.error:
                        char_render_width = max_pixel_width + 1

                    if char_render_width <= max_pixel_width:
                        temp_char_line += char
                    else:
                        if temp_char_line:
                            lines.append(temp_char_line)
                        temp_char_line = char
                        if font.get_rect(char).width > max_pixel_width and len(temp_char_line) > 1 :
                             lines.append(char)
                             temp_char_line = ""

                if temp_char_line:
                    lines.append(temp_char_line)
                current_line = ""
            else:
                if not current_line:
                    current_line = word
                else:
                    test_line = current_line + " " + word
                    try:
                        test_line_width = font.get_rect(test_line).width
                    except pygame.error:
                        test_line_width = max_pixel_width + 1

                    if test_line_width <= max_pixel_width:
                        current_line = test_line
                    else:
                        lines.append(current_line)
                        current_line = word
        
        if current_line:
            lines.append(current_line)
        
        if not lines:
            lines.append("")

        return lines, line_height

    def update_side_bar_content(self, data_list: typing.List[dict]):
        """Updates the content of the side bar info panel by creating UI elements from structured data."""
        if not self.side_bar_info_panel or not self.side_bar_info_panel.alive():
            return

        self.clear_side_bar_content()

        current_y_offset = 5
        element_padding = 3
        base_container_rect = self.side_bar_info_panel.get_container().get_rect()
        base_container_width = base_container_rect.width if base_container_rect else INFO_BOX_WIDTH
        indent_size = 15

        for item_data in data_list:
            item_type = item_data.get('type')
            text = item_data.get('text', '')
            object_id_str = item_data.get('object_id', None)
            class_id_str = item_data.get('class_id', None)
            height_from_data = int(item_data.get('height', 25) * TEXT_SCALE)
            item_indent_level = item_data.get('indent_level', 0)

            actual_element_total_height = 0

            target_container_for_element = self.side_bar_info_panel.get_container()
            current_element_y = current_y_offset
            current_element_x = 5 + (item_indent_level * indent_size)
            current_element_width = base_container_width - (item_indent_level * indent_size) - (5 * 2)
            
            if current_element_width <= 0: current_element_width = 1
            
            obj_id = None
            if object_id_str:
                obj_id = pygame_gui.core.ObjectID(object_id=object_id_str, class_id=class_id_str)
            elif class_id_str:
                obj_id = pygame_gui.core.ObjectID(class_id=class_id_str)

            obj_id = None
            if object_id_str:
                obj_id = pygame_gui.core.ObjectID(object_id=object_id_str, class_id=class_id_str)
            elif class_id_str:
                obj_id = pygame_gui.core.ObjectID(class_id=class_id_str)

            if item_type == 'label':
                font = self.manager.get_theme().get_font(obj_id)
                lines, line_height = self.wrap_text_to_lines(text, current_element_width, font)
                
                total_height = 0
                for i, line in enumerate(lines):
                    label_rect = pygame.Rect(current_element_x, current_element_y + total_height, current_element_width, -1)
                    label = pygame_gui.elements.UILabel(
                        relative_rect=label_rect,
                        text=line,
                        manager=self.manager,
                        container=target_container_for_element,
                        object_id=obj_id
                    )
                    self.side_bar_dynamic_elements.append(label)
                    total_height += label.get_relative_rect().height
                
                actual_element_total_height = total_height
            
            elif item_type == 'text_box':
                html_text = item_data.get('html_text', '')
                text_box_rect = pygame.Rect(current_element_x, current_element_y, current_element_width, height_from_data)
                text_box = pygame_gui.elements.UITextBox(
                    html_text=html_text,
                    relative_rect=text_box_rect,
                    manager=self.manager,
                    container=target_container_for_element,
                    object_id=obj_id
                )
                self.side_bar_dynamic_elements.append(text_box)
                actual_element_total_height = height_from_data

            elif item_type == 'button':
                action_id = item_data.get('action_id', '')
                target_data = item_data.get('target_data', None)
                
                button_rect = pygame.Rect(current_element_x, current_element_y, current_element_width, -1)
                button = pygame_gui.elements.UIButton(
                    relative_rect=button_rect,
                    text=text,
                    manager=self.manager,
                    container=target_container_for_element, # Use determined target container
                    object_id=obj_id,
                )
                self.dynamic_button_actions[button] = {'action_id': action_id, 'target_data': target_data}
                self.side_bar_dynamic_elements.append(button)
                actual_element_total_height = button.get_relative_rect().height # Button height
            
            elif item_type == 'inhibitor_button':
                is_active = item_data.get('is_active', False)
                button_text = "Deactivate Inhibitor" if is_active else "Activate Inhibitor"
                button_rect = pygame.Rect(current_element_x, current_element_y, current_element_width, -1)
                button = pygame_gui.elements.UIButton(
                    relative_rect=button_rect,
                    text=button_text,
                    manager=self.manager,
                    container=target_container_for_element,
                    object_id='#toggle_inhibitor_button'
                )
                self.side_bar_dynamic_elements.append(button)
                actual_element_total_height = button.get_relative_rect().height

            elif item_type == 'progress_bar':
                progress = item_data.get('progress', 0)
                total = item_data.get('total', 100)
                progress_bar_rect = pygame.Rect(current_element_x, current_element_y, current_element_width, height_from_data)
                progress_bar = pygame_gui.elements.UIProgressBar(
                    relative_rect=progress_bar_rect,
                    manager=self.manager,
                    container=target_container_for_element,
                    object_id='#constructor_progress_bar'
                )
                if total > 0:
                    percent = (progress / total) * 100.0
                else:
                    percent = 100.0
                progress_bar.set_current_progress(percent)
                self.side_bar_dynamic_elements.append(progress_bar)
                actual_element_total_height = height_from_data

            elif item_type == 'drop_down_menu':
                options_list = item_data.get('options_list', [])
                starting_option = item_data.get('starting_option', '')
                dropdown_rect = pygame.Rect(current_element_x, current_element_y, current_element_width, height_from_data)
                dropdown = pygame_gui.elements.UIDropDownMenu(
                    options_list=options_list,
                    starting_option=starting_option,
                    relative_rect=dropdown_rect,
                    manager=self.manager,
                    container=target_container_for_element,
                    object_id=obj_id
                )
                self.side_bar_dynamic_elements.append(dropdown)
                actual_element_total_height = height_from_data

            if actual_element_total_height > 0:
                current_y_offset += actual_element_total_height + element_padding
            else:
                current_y_offset += element_padding

    def open_context_menu(self, position: Position, options: typing.List[ContextMenuOption], target: typing.Any):
        """Creates and displays a context menu at the given position.
        
        Options can be flat (label, action_id) or submenu parents (label, [(label, action_id), ...]).
        Submenu parent items are rendered with a ▸ suffix indicator.
        """
        self.close_context_menu()

        self.context_menu_options = options
        self.context_menu_target = target
        self.context_menu_buttons = []
        self.context_menu_submenus = {}

        if not options:
            return

        panel_width = CONTEXT_MENU_WIDTH
        panel_height = len(options) * (CONTEXT_MENU_ITEM_HEIGHT + 2) + 10

        if position.x + panel_width > self.screen_res.x:
            position = Position(position.x - panel_width, position.y)
        if position.y + panel_height > self.screen_res.y:
            position = Position(position.x, position.y - panel_height)
        panel_rect = pygame.Rect(position.x, position.y, panel_width, panel_height)

        self.context_menu_panel = pygame_gui.elements.UIPanel(relative_rect=panel_rect, 
                                            starting_height=10,
                                            manager=self.manager, 
                                            object_id='#context_menu_panel')

        button_y = 5
        for i, (text, action_id) in enumerate(options):
            # Detect submenu parent: action_id is a list of (label, action_id) tuples
            if isinstance(action_id, list):
                display_text = f"{text} \u25b8"
                self.context_menu_submenus[i] = action_id
            else:
                display_text = text
            button_rect = pygame.Rect(5, button_y, panel_width - 10, CONTEXT_MENU_ITEM_HEIGHT)
            button = pygame_gui.elements.UIButton(relative_rect=button_rect,
                              text=display_text,
                              manager=self.manager,
                              container=self.context_menu_panel,
                              object_id=pygame_gui.core.ObjectID(class_id='@context_menu_button'))
            self.context_menu_buttons.append(button)
            button_y += CONTEXT_MENU_ITEM_HEIGHT + 2

    def close_context_menu(self):
        """Closes the currently open context menu."""
        if self.context_menu_panel:
            self.context_menu_panel.kill()
            self.context_menu_panel = None
        self.context_menu_buttons = []
        self.context_menu_options = []
        self.context_menu_target = None
        self.context_menu_submenus = {}
        self.context_menu_parent_options = None
        self.context_menu_parent_position = None

    def is_mouse_over_context_menu(self, mouse_pos: Position) -> bool:
        """Checks if the mouse position is over the context menu panel."""
        if self.context_menu_panel and self.context_menu_panel.visible:
            return self.context_menu_panel.get_abs_rect().collidepoint(mouse_pos.to_tuple())
        return False
