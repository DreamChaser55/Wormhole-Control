import logging
import sys
import typing
import pygame
from pygame import Color

# Re-exported for backwards-compatibility with tests and entry points
from game_logging import GameLogFormatter, setup_logging
from game_camera import CAMERA_SMOOTH_SPEED

setup_logging(log_to_file=False)
logger = logging.getLogger(__name__)

# Local module imports
from constants import SCREEN_RES, FULLSCREEN, PROFILE, RED, BLUE, YELLOW
from utils import HexCoord
from geometry import Position
from entities import Player, Unit, Order
from gui import GUI_Handler
from renderer import Renderer
from input_processor import InputProcessor
from turn_processor import TurnProcessor
from events import EventBus
from order_system import OrderSystem
from custom_unit_templates import CustomTemplateManager
from visibility import (
    VisibilityService, VisibilitySnapshot,
    is_unit_visible as vis_is_unit_visible,
    hex_has_presence as vis_hex_has_presence,
    is_minefield_visible as vis_is_minefield_visible
)

# Subsystem modules
import game_camera
import economy
import game_setup
import sidebar
import game_actions

# --- Game Class ---
class Game:
    """Main game class, handles initialization, game loop, drawing, and input."""
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Wormhole Control")
        if FULLSCREEN:
            self.screen = pygame.display.set_mode(SCREEN_RES.to_tuple(), pygame.FULLSCREEN | pygame.DOUBLEBUF)
        else:
            self.screen = pygame.display.set_mode(SCREEN_RES.to_tuple())
        self.clock = pygame.time.Clock()
        
        # Instantiate the GUI Handler
        self.gui = GUI_Handler(SCREEN_RES, self)

        # Game State - Controls the current game status and view context
        self.is_running = True  # Controls the main game loop
        self.view_mode = 'main_menu'  # Valid modes: 'main_menu', 'galaxy', 'system', 'sector'
        self.game_started = False  # Set to True after starting a new game
        self.current_system_name: typing.Optional[str] = None  # Name of currently viewed star system
        self.current_sector_coord: typing.Optional[HexCoord] = None  # Hex coordinates of the sector being viewed

        # UI State / Selections - Tracks current user interactions with game objects
        self.selected_objects: typing.List[typing.Any] = [] # List of all selected game objects
        self.hovered_object: typing.Optional[typing.Any] = None  # Object directly under mouse cursor
        self.is_dragging_selection_box = False
        self.selection_box_start_pos = None
        
        # View-specific hover tracking
        self.galaxy_view_mouse_hover_system_name: typing.Optional[str] = None
        self.system_view_mouse_hover_hex: typing.Optional[HexCoord] = None
        self.sector_view_mouse_hover_object: typing.Any = None

        # Initialize empty galaxy and players - will be created after New Game is clicked
        self.galaxy = None
        self.players: typing.List[Player] = []
        self.current_player_index = 0
        self.turn_number = 1

        # Visibility / Fog of War State
        self.visibility: typing.Optional[VisibilitySnapshot] = None
        self.visibility_dirty: bool = True

        # Alpha Surface for drawing overlays (highlights and order lines)
        self.overlay_surface = pygame.Surface(SCREEN_RES.to_tuple(), pygame.SRCALPHA)


        # Instantiate the Renderer
        self.renderer = Renderer(self)

        # Initialize Event Bus and Order System
        self.event_bus = EventBus()
        self.order_system = OrderSystem(self, self.event_bus)

        # Instantiate the InputProcessor
        self.input_processor = InputProcessor(self)

        # Instantiate the TurnProcessor
        self.turn_manager = TurnProcessor(self)

        # Initialize the main menu UI
        self.gui.show_main_menu()
        self.sidebar_needs_update: bool = True
        self.pending_ai_turn_end_time: int = 0
        self.selected_component_name: typing.Optional[str] = None
        self.selected_unit_tab: str = 'basic_info'


        # Pending ability activation state (when targeting mode is active)
        # Holds (ability_type_str, requires_target_unit, requires_target_position)
        self.pending_ability: typing.Optional[typing.Tuple[str, bool, bool]] = None

        # Custom unit template manager (persists designs across sessions)
        self.custom_template_manager = CustomTemplateManager()
        self.custom_template_manager.load_from_file()

        # Sector View Camera variables
        # Follower state: what the renderer and hit-testing actually use
        self.sector_zoom = 1.0
        self.sector_pan_offset = Position(0, 0)
        # Leader state: updated instantly by input, follower lerps toward these
        self.sector_target_zoom = 1.0
        # Active zoom anchor variables (used to lock zoom/pan together)
        self.zoom_anchor_pixel = None
        self.zoom_anchor_logical = None

    def reset_sector_camera(self):
        """Resets the sector camera zoom and pan offset."""
        game_camera.reset_sector_camera(self)

    def start_new_game(self):
        """Initializes a new game when the New Game button is clicked."""
        return game_setup.start_new_game(self)

    def spawn_units(self, player_homeworld_hexes: typing.Dict[Player, HexCoord] = None):
        """Sets up the starting units of all players."""
        game_setup.spawn_units(self, player_homeworld_hexes)

    def handle_input(self, time_delta: float):
        """Delegates input processing to the InputProcessor instance."""
        self.input_processor.handle_input(time_delta)

    def deselect_object(self, obj_to_deselect: typing.Any):
        """Removes a specific object from the selection."""
        if obj_to_deselect in self.selected_objects:
            self.selected_objects.remove(obj_to_deselect)
            self.sidebar_needs_update = True
            if not any(isinstance(obj, Unit) for obj in self.selected_objects):
                self.selected_component_name = None

    # --- GUI Action Handling ---
    def handle_gui_action(self, action: typing.Dict[str, typing.Any]):
        """Handles action events triggered by user interactions with GUI controls."""
        game_actions.handle_gui_action(self, action)

    def update_sector_camera(self, dt: float):
        """Smoothly interpolates the sector camera zoom and pan offset."""
        game_camera.update_sector_camera(self, dt)

    def recompute_visibility(self):
        """Recomputes the fog-of-war visibility snapshot for the active human/spectator player."""
        if self.game_started and self.galaxy and self.players:
            viewer = self.players[self.current_player_index]
            self.visibility = VisibilityService.compute(self.galaxy, viewer)
        else:
            self.visibility = None
        self.visibility_dirty = False

    def is_unit_visible(self, unit: Unit) -> bool:
        """Determines whether a given unit is visible to the active player.

        Args:
            unit (Unit): Target unit object to check visibility for.

        Returns:
            bool: True if friendly or within detailed sensor/visibility range of active player.
        """
        return vis_is_unit_visible(self.visibility, unit)

    def hex_has_presence(self, system_name: str, hex_coord: HexCoord) -> bool:
        """Determines if a hex has undetailed enemy presence for the active player.

        Args:
            system_name (str): System containing the target hex.
            hex_coord (HexCoord): Hex coordinate to evaluate.

        Returns:
            bool: True if an undetailed sensor signature exists in the hex.
        """
        return vis_hex_has_presence(self.visibility, system_name, hex_coord)

    def is_minefield_visible(self, minefield: typing.Any) -> bool:
        """Determines whether a minefield is visible to the current player.

        Args:
            minefield (typing.Any): Minefield entity to check.

        Returns:
            bool: True if minefield belongs to current player or if spectator mode is active.
        """
        return vis_is_minefield_visible(self.visibility, minefield)

    def update(self, time_delta: float):
        """Called every frame. Updates the UI. Game logic updates are done in TurnProcessor.process_turn(), which is called at the end of each turn."""
        if self.game_started and (self.visibility_dirty or self.visibility is None):
            self.recompute_visibility()

        # Smooth sector camera zoom
        self.update_sector_camera(time_delta)

        # Update the GUI Handler
        self.gui.update(time_delta)

        # Update view-specific labels if game is running
        if self.game_started:
            self.update_view_specific_labels()
        
        # Update info box based on selection only if needed
        if self.sidebar_needs_update:
            self.update_side_bar_content()
        
        # Update turn display
        if self.game_started and self.players:
            self.update_player_turn_display()

        # Handle pending non-blocking AI turn progression
        if self.game_started and self.pending_ai_turn_end_time > 0:
            if pygame.time.get_ticks() >= self.pending_ai_turn_end_time:
                self.pending_ai_turn_end_time = 0

                self.end_turn()


    def end_turn(self):
        """Delegates end_turn processing to the TurnProcessor instance."""
        self.turn_manager.end_turn()
        self.visibility_dirty = True
        self.sidebar_needs_update = True # Ensure sidebar refreshes after turn processing


    def update_view_specific_labels(self):
        """Updates UI labels that depend on the current view mode."""
        if self.view_mode == 'system' and self.current_system_name:
            self.gui.update_view_mode_label(f"{self.current_system_name} system")
        elif self.view_mode == 'sector' and self.current_sector_coord:
            self.gui.update_view_mode_label(f"{self.current_sector_coord} sector in {self.current_system_name} system")
        elif self.view_mode == 'galaxy':
            self.gui.update_view_mode_label("Galaxy map")
        else:
            self.gui.update_view_mode_label(f"View: {self.view_mode.capitalize()}")

    def _format_order_state_data(self, state_data: dict) -> list:
        """Formats raw order state parameters into HTML-styled text strings for sidebar display."""
        return sidebar.format_order_state_data(state_data, getattr(self, 'galaxy', None))

    def _generate_order_data_recursive(self, order: Order, current_indent_level: int) -> str:
        """Helper method to recursively generate an HTML-formatted string representing an order tree."""
        return sidebar.generate_order_data_html(order, current_indent_level, getattr(self, 'galaxy', None))

    def update_side_bar_content(self):
        """Constructs and updates the sidebar data payload based on current selections and view mode."""
        sidebar.update_side_bar_content(self)

    def get_player_income(self, player: Player) -> float:
        """Calculates total credit income per turn generated by a player's colonies."""
        return economy.calculate_player_income(getattr(self, 'galaxy', None), player)

    def get_player_upkeep(self, player: Player) -> float:
        """Calculates total credit upkeep cost per turn for a player's active fleet."""
        return economy.calculate_player_upkeep(getattr(self, 'galaxy', None), player)

    def update_player_turn_display(self):
        """Updates turn header text, player color indicators, and resource status HUD elements."""
        if not self.players:
            return
        current_player = self.players[self.current_player_index]
        
        # Format the player's name with their player color
        color = getattr(current_player, 'color', (255, 255, 255))
        if color and len(color) >= 3:
            color_hex = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
        else:
            color_hex = "#FFFFFF"

        turn_num = getattr(self, 'turn_number', 1)
        self.gui.update_turn_label(f"<font color='{color_hex}'>Turn {turn_num}: {current_player.name}'s Turn</font>")
        # Update color indicator panel's background
        self.gui.update_player_color_indicator(Color(color)) # Convert tuple to pygame.Color
        self.gui.update_resource_display(current_player)


    def draw(self):
        """Delegates rendering to the Renderer instance."""
        self.renderer.draw()

    def handle_mouse_wheel(self, scroll_y: int):
        """Processes mouse scroll wheel input for smooth sector camera zooming."""
        game_camera.handle_mouse_wheel(self, scroll_y)

    def run(self):
        """Main game loop."""
        if not self.is_running: # Check if init failed
             logger.debug("Game initialization failed. Exiting.")
             pygame.quit()
             sys.exit()

        while self.is_running:
            time_delta = self.clock.tick(60) / 1000.0

            self.handle_input(time_delta)
            self.update(time_delta)
            self.draw()

        pygame.quit()
        sys.exit()

    def save_game(self, filename: typing.Optional[str] = None) -> str:
        """Saves current game state to a file.

        Args:
            filename (typing.Optional[str]): Optional custom save file name or path.

        Returns:
            str: Absolute or relative filepath where the save file was created.
        """
        import save_manager
        filepath = save_manager.save_game_to_file(self, filename)
        logger.debug(f"Game state saved to {filepath}")
        return filepath

    def load_game(self, filepath: str) -> bool:
        """Loads game state from a save file and refreshes all GUI displays.

        Args:
            filepath (str): Path to the save file.

        Returns:
            bool: True if game state was loaded successfully, False otherwise.
        """
        import save_manager
        logger.debug(f"Loading game state from {filepath}...")
        success = save_manager.load_game_from_file(self, filepath)
        if success:
            self.gui.show_game_ui()
            self.update_view_specific_labels()
            self.update_side_bar_content()
            self.update_player_turn_display()
            logger.debug("Game state loaded successfully.")
        else:
            logger.error(f"Failed to load game state from {filepath}")
        return success

    def quit_to_main_menu(self):
        """Resets active game state and returns the UI to the main menu."""
        logger.debug("Quitting to main menu...")
        self.game_started = False
        self.view_mode = 'main_menu'
        self.gui.clear_and_reset()
        self.gui.show_main_menu()

# Application entry point
if __name__ == '__main__':
    setup_logging(log_to_file=True)
    logger.debug("Initializing Game...")
    game = Game()
    logger.debug("Starting Game Loop...")
    game.run()
