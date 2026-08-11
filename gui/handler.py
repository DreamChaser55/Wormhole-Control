import logging

logger = logging.getLogger(__name__)

import pygame
import pygame_gui
import typing
from pygame import Color

from constants import INFO_BOX_WIDTH, TOP_BAR_HEIGHT, BLUE
from utils import ContextMenuOption
from geometry import Vector, Position
from .theme_loader import build_ui_manager
from . import layout_main_menu, layout_ingame_menu, layout_hud, text_layout, context_menu, event_router
from .layout_new_game_wizard import NewGameWizard
from .sidebar import view as sidebar_view
if typing.TYPE_CHECKING:
    from game import Game
    from entities import Player
    from .unit_editor_gui import UnitEditorWindow


class GUI_Handler:
    """Manages the Pygame GUI elements."""
    def __init__(self, screen_res: Vector, game_instance: 'Game'):
        self.screen_res = screen_res
        self.game_instance = game_instance
        self.scale_x = screen_res.x / 1280.0
        self.scale_y = screen_res.y / 720.0

        self.manager = build_ui_manager(self.screen_res)
        if self.manager:
            self.manager.set_visual_debug_mode(True)

        # --- UI Elements --- 
        # Main Menu
        self.main_menu_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.new_game_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.load_game_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.about_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.quit_button: typing.Optional[pygame_gui.elements.UIButton] = None

        # New Game Wizard
        self.new_game_wizard: typing.Optional[NewGameWizard] = None

        # About Screen
        self.about_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.about_title: typing.Optional[pygame_gui.elements.UILabel] = None
        self.about_text: typing.Optional[pygame_gui.elements.UITextBox] = None
        self.about_screen_back_button: typing.Optional[pygame_gui.elements.UIButton] = None

        # Load Save Dialog Window
        self.load_save_window: typing.Optional[pygame_gui.elements.UIWindow] = None
        self.load_save_selection_list: typing.Optional[pygame_gui.elements.UISelectionList] = None
        self.load_save_confirm_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.load_save_cancel_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.save_file_paths: typing.Dict[str, str] = {}

        # In-Game UI
        self.left_top_bar_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.left_bottom_bar_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.right_top_bar_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.back_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.view_mode_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self.end_turn_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.player_turn_label: typing.Optional[pygame_gui.elements.UITextBox] = None
        self.player_color_indicator: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.current_player_bg_color: typing.Optional[Color] = None
        self.current_player_border_color: typing.Optional[Color] = None
        self.credits_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self.metal_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self.crystal_label: typing.Optional[pygame_gui.elements.UILabel] = None
        self.side_bar_info_panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self.side_bar_scroll_bar: typing.Optional[pygame_gui.elements.UIVerticalScrollBar] = None
        self.side_bar_dynamic_elements: typing.List[pygame_gui.core.UIElement] = []
        self.dynamic_button_actions: typing.Dict[pygame_gui.elements.UIButton, typing.Dict[str, typing.Any]] = {}
        self.dynamic_dropdown_actions: typing.Dict[pygame_gui.elements.UIDropDownMenu, typing.Dict[str, typing.Any]] = {}
        self.expanded_sections: typing.Dict[str, bool] = {}
        # Editable unit name field — set when a single owned unit is selected
        self.unit_name_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        
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
        self.ingame_load_game_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self.quit_to_menu_button: typing.Optional[pygame_gui.elements.UIButton] = None

        # Unit Editor
        self.unit_editor_window: typing.Optional['UnitEditorWindow'] = None
        self.unit_editor_button: typing.Optional[pygame_gui.elements.UIButton] = None

        # Active Pop-up Dialog Windows
        self.active_dialogs: typing.List[pygame_gui.windows.UIMessageWindow] = []

        # Galaxy generation area
        self.galaxy_generation_rect: typing.Optional[pygame.Rect] = None
        self.galaxy_border_color: pygame.Color = pygame.Color(BLUE)

    def clear_and_reset(self):
        """Clears all UI elements managed by this class."""
        for dialog in self.active_dialogs:
            if dialog.alive():
                dialog.kill()
        self.active_dialogs.clear()

        if self.new_game_wizard:
            if self.new_game_wizard.is_alive:
                self.new_game_wizard.kill()
            self.new_game_wizard = None
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

        if self.load_save_window:
            self.load_save_window.kill()
            self.load_save_window = None

        self.new_game_button = self.load_game_button = self.about_button = self.quit_button = None
        self.about_title = self.about_text = self.about_screen_back_button = None
        self.load_save_selection_list = self.load_save_confirm_button = self.load_save_cancel_button = None
        self.save_file_paths = {}
        self.back_button = self.view_mode_label = self.end_turn_button = self.player_turn_label = self.player_color_indicator = None
        self.credits_label = self.metal_label = self.crystal_label = None
        self.context_menu_buttons = []
        self.context_menu_target = None
        self.context_menu_options = []

        self.menu_button = self.resume_button = self.save_game_button = self.ingame_load_game_button = self.quit_to_menu_button = None
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

    def show_new_game_wizard(self) -> None:
        """Instantiates (if necessary) and displays the New Game Wizard window."""
        if self.new_game_wizard and self.new_game_wizard.is_alive:
            return  # already open
        self.new_game_wizard = NewGameWizard(
            manager=self.manager,
            screen_res=self.screen_res,
            scale_x=self.scale_x,
            scale_y=self.scale_y,
        )

    def close_new_game_wizard(self) -> None:
        """Closes and destroys the New Game Wizard window."""
        if self.new_game_wizard:
            if self.new_game_wizard.is_alive:
                self.new_game_wizard.kill()
            self.new_game_wizard = None

    def is_new_game_wizard_open(self) -> bool:
        """Returns True if the wizard window is currently alive."""
        return self.new_game_wizard is not None and self.new_game_wizard.is_alive

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
        """Toggles the visibility state of the in-game pause menu."""
        if not self.ingame_menu_panel or not self.ingame_menu_panel.visible:
            self.show_ingame_menu()
        else:
            self.hide_ingame_menu()

    def show_ingame_menu(self):
        """Displays the in-game pause menu and disables background game buttons."""
        if not self.ingame_menu_panel:
            self.setup_ingame_menu()
        if self.ingame_menu_panel: self.ingame_menu_panel.show()
        if self.end_turn_button: self.end_turn_button.disable()
        if self.back_button: self.back_button.disable()

    def hide_ingame_menu(self):
        """Hides the in-game pause menu and re-enables HUD buttons."""
        if self.ingame_menu_panel: self.ingame_menu_panel.hide()
        if self.end_turn_button: self.end_turn_button.enable()
        if self.back_button: self.back_button.enable()

    def is_ingame_menu_open(self) -> bool:
        """Determines whether the in-game menu is currently open.

        Returns:
            bool: True if the in-game menu panel is instantiated and visible.
        """
        return self.ingame_menu_panel is not None and self.ingame_menu_panel.visible

    # --- Setup Methods --- 

    def setup_main_menu(self):
        """Creates the main menu UI elements."""
        layout_main_menu.setup_main_menu(self)

    def setup_about_screen(self):
        """Sets up the about screen UI."""
        layout_main_menu.setup_about_screen(self)

    def setup_game_ui(self):
        """Initializes the Pygame GUI elements for the main game interface."""
        layout_hud.setup_game_ui(self)

    def setup_ingame_menu(self):
        """Initializes the Pygame GUI elements for the in-game menu interface."""
        layout_ingame_menu.setup_ingame_menu(self)

    def show_load_game_dialog(self):
        """Displays a dialog window listing available save files to load."""
        layout_ingame_menu.show_load_game_dialog(self)

    def process_event(self, event: pygame.event.Event) -> typing.Optional[dict]:
        """Processes a single Pygame event for the GUI Manager."""
        return event_router.process_event(self, event)

    def update(self, time_delta: float):
        """Updates UI manager animations, timers, and layout states.

        Args:
            time_delta (float): Time elapsed since the last frame in seconds.
        """
        self.manager.update(time_delta)
        # Forward update to unit editor so its internal widgets animate/update
        if self.unit_editor_window and self.unit_editor_window.is_visible:
            pass  # UIManager handles child widget updates automatically

    def draw(self, surface: pygame.Surface):
        """Renders all managed UI elements and custom overlays onto the target Pygame surface.

        Args:
            surface (pygame.Surface): Display surface to render GUI components on.
        """
        if self.galaxy_generation_rect and self.game_instance.view_mode == 'galaxy':
            pygame.draw.rect(surface, self.galaxy_border_color, self.galaxy_generation_rect, 2)
        
        self.manager.draw_ui(surface)

        # Draw colour swatches for the new-game wizard (must be after draw_ui)
        if self.new_game_wizard and self.new_game_wizard.is_alive:
            self.new_game_wizard.draw_swatches(surface)

        # Draw custom pygame elements (capacity bar) after the UI manager
        if self.unit_editor_window and self.unit_editor_window.is_visible:
            self.unit_editor_window.draw(surface)

    def is_any_text_entry_focused(self) -> bool:
        """Checks if any text entry element (input field) currently has active keyboard focus.

        Returns:
            bool: True if a text entry field is focused, False otherwise.
        """
        for sprite in self.manager.ui_group.sprites():
            if isinstance(sprite, (pygame_gui.elements.UITextEntryLine, pygame_gui.elements.UITextEntryBox)):
                if sprite.is_focused:
                    return True
        return False

    # --- Unit Editor helpers ---

    def open_unit_editor(self, template_manager) -> None:
        """Instantiates (if necessary) and displays the Unit Editor window overlay.

        Args:
            template_manager: CustomTemplateManager instance storing custom unit designs.
        """
        if self.unit_editor_window is None:
            from .unit_editor_gui import UnitEditorWindow
            self.unit_editor_window = UnitEditorWindow(
                manager=self.manager,
                screen_res=pygame.Vector2(self.screen_res.x, self.screen_res.y),
                template_manager=template_manager,
            )
        if self.current_player_bg_color and getattr(self.unit_editor_window, '_panel', None):
            try:
                self.unit_editor_window._panel.background_colour = self.current_player_bg_color
                if self.current_player_border_color and hasattr(self.unit_editor_window._panel, 'border_colour'):
                    self.unit_editor_window._panel.border_colour = self.current_player_border_color
                self.unit_editor_window._panel.rebuild()
            except Exception as e:
                logger.debug(f"Error setting unit editor panel color: {e}")
        self.unit_editor_window.show()
        self.hide_ingame_menu()


    def close_unit_editor(self) -> None:
        """Hides the Unit Editor window overlay."""
        if self.unit_editor_window:
            self.unit_editor_window.hide()

    def is_unit_editor_open(self) -> bool:
        """Checks if the Unit Editor window is currently visible.

        Returns:
            bool: True if the unit editor window exists and is visible.
        """
        return self.unit_editor_window is not None and self.unit_editor_window.is_visible

    def process_unit_editor_event(self, event: pygame.event.Event) -> typing.Optional[str]:
        """Forwards Pygame events to the active Unit Editor window.

        Args:
            event (pygame.event.Event): Pygame event to process.

        Returns:
            typing.Optional[str]: Action code returned by unit editor, or None if no action triggered.
        """
        if self.unit_editor_window:
            return self.unit_editor_window.process_event(event)
        return None

    # --- UI Update Methods ---
    def update_back_button_visibility(self):
        """Toggles back button visibility depending on active view mode (hidden on galaxy view)."""
        layout_hud.update_back_button_visibility(self)

    def update_view_mode_label(self, text: str):
        """Updates header text label displaying current camera view mode.

        Args:
            text (str): Display string to set on the view mode label.
        """
        layout_hud.update_view_mode_label(self, text)

    def update_turn_label(self, text: str):
        """Updates header text label displaying current turn number and active player name.

        Args:
            text (str): HTML-formatted turn display string.
        """
        layout_hud.update_turn_label(self, text)

    def update_player_color_indicator(self, color: Color):
        """Sets background color of player indicator badge on top HUD bar.

        Args:
            color (Color): Pygame Color representing active player.
        """
        layout_hud.update_player_color_indicator(self, color)

    def update_player_turn_theme(self, color: Color):
        """Updates GUI panel background and border colors derived from the active player's color.

        Args:
            color (Color): Pygame Color representing active player.
        """
        layout_hud.update_hud_panel_colors(self, color)


    def update_resource_display(self, player: 'Player'):
        """Updates credits, metal, and crystal resource readouts and income tooltips for a player.

        Args:
            player (Player): Active player entity whose resources to render.
        """
        layout_hud.update_resource_display(self, player)

    def clear_side_bar_content(self):
        """Kills and removes all dynamically added UI elements from the sidebar."""
        sidebar_view.clear_side_bar_content(self)

    def is_section_expanded(self, section_id: str) -> bool:
        """Checks if a given UI section is marked as expanded."""
        return sidebar_view.is_section_expanded(self, section_id)

    def toggle_section_expansion(self, section_id: str):
        """Toggles the expansion state of a given UI section."""
        sidebar_view.toggle_section_expansion(self, section_id)

    def wrap_text_to_lines(self, text_to_wrap: str, max_pixel_width: int, font: pygame.font.Font) -> typing.Tuple[typing.List[str], int]:
        """Wraps text to fit within a maximum pixel width."""
        return text_layout.wrap_text_to_lines(text_to_wrap, max_pixel_width, font)

    def update_side_bar_content(self, data_list: typing.List[dict]):
        """Updates the content of the side bar info panel by creating UI elements from structured data."""
        sidebar_view.update_side_bar_content(self, data_list)

    def open_context_menu(self, position: Position, options: typing.List[ContextMenuOption], target: typing.Any):
        """Creates and presents a right-click context menu at specified screen coordinates."""
        context_menu.open_context_menu(self, position, options, target)

    def close_context_menu(self):
        """Closes and cleans up any currently active context menu panel."""
        context_menu.close_context_menu(self)

    def is_mouse_over_context_menu(self, mouse_pos: Position) -> bool:
        """Determines if mouse coordinates lie within the open context menu bounds."""
        return context_menu.is_mouse_over_context_menu(self, mouse_pos)

    def is_mouse_over_gui_panels(self, mouse_pos: Position) -> bool:
        """Determines if mouse coordinates collide with any visible top-level GUI panels.

        Args:
            mouse_pos (Position): Mouse screen coordinates to test.

        Returns:
            bool: True if mouse position collides with any visible HUD or panel element.
        """
        panels = [
            self.left_top_bar_panel,
            self.left_bottom_bar_panel,
            self.right_top_bar_panel,
            self.side_bar_info_panel,
            self.context_menu_panel,
            self.ingame_menu_panel,
        ]
        # Wizard window panel
        if self.new_game_wizard and self.new_game_wizard.is_alive:
            wizard_rect = self.new_game_wizard.window.get_abs_rect()
            if wizard_rect.collidepoint(mouse_pos.to_tuple()):
                return True
        mouse_tuple = mouse_pos.to_tuple()
        for panel in panels:
            if panel and panel.visible:
                if panel.get_abs_rect().collidepoint(mouse_tuple):
                    return True
        return False

    # --- Modal Dialog Methods ---
    def show_message_dialog(
        self,
        title: str,
        message: str,
        window_type: str = "info"
    ) -> pygame_gui.windows.UIMessageWindow:
        """Displays a pop-up modal message dialog window.

        Args:
            title (str): Title of the window dialog.
            message (str): Body message text (HTML supported by Pygame GUI).
            window_type (str): Type identifier ('info', 'warning', 'error').

        Returns:
            pygame_gui.windows.UIMessageWindow: Created message window instance.
        """
        # Clean up dead dialog references
        self.active_dialogs = [d for d in self.active_dialogs if d.alive()]

        dialog_w = int(500 * self.scale_x)
        dialog_h = int(280 * self.scale_y)
        x = (self.screen_res.x - dialog_w) / 2
        y = (self.screen_res.y - dialog_h) / 2
        rect = pygame.Rect(int(x), int(y), dialog_w, dialog_h)

        if window_type == "error":
            display_title = f"Error: {title}" if not title.lower().startswith("error") else title
        elif window_type == "warning":
            display_title = f"Warning: {title}" if not title.lower().startswith("warning") else title
        else:
            display_title = title

        formatted_html = f"<p>{message}</p>"

        dialog = pygame_gui.windows.UIMessageWindow(
            rect=rect,
            html_message=formatted_html,
            manager=self.manager,
            window_title=display_title
        )

        # Enlarge and reposition Dismiss button and adjust text block bounds
        if dialog.dismiss_button:
            btn_w = int(140 * self.scale_x)
            btn_h = int(38 * self.scale_y)
            margin = int(14 * self.scale_x)
            dialog.dismiss_button.set_dimensions((btn_w, btn_h))
            dialog.dismiss_button.set_relative_position((-btn_w - margin, -btn_h - margin))
            container = dialog.get_container()
            if dialog.text_block and container:
                text_h = max(50, container.get_size()[1] - btn_h - (margin * 2))
                dialog.text_block.set_dimensions((container.get_size()[0], text_h))

        self.active_dialogs.append(dialog)
        return dialog

    def show_error_dialog(self, message: str, title: str = "Error") -> pygame_gui.windows.UIMessageWindow:
        """Convenience method to display an Error modal dialog popup."""
        return self.show_message_dialog(title=title, message=message, window_type="error")

    def show_warning_dialog(self, message: str, title: str = "Warning") -> pygame_gui.windows.UIMessageWindow:
        """Convenience method to display a Warning modal dialog popup."""
        return self.show_message_dialog(title=title, message=message, window_type="warning")

    def show_info_dialog(self, message: str, title: str = "Information") -> pygame_gui.windows.UIMessageWindow:
        """Convenience method to display an Informational modal dialog popup."""
        return self.show_message_dialog(title=title, message=message, window_type="info")

