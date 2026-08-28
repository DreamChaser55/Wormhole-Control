import logging
import sys
import typing
import uuid
from datetime import datetime, timezone
from pathlib import Path
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
from entities import Player, Unit, Order, Conversation, Message
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
from game_ai.coordinator import AgentTurnCoordinator

# Subsystem modules
import game_camera
import economy
import game_setup
from gui import sidebar
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
        self.campaign_id = str(uuid.uuid4())

        # Visibility / Fog of War State
        self.visibility: typing.Optional[VisibilitySnapshot] = None
        self.visibility_dirty: bool = True

        # Inter-player communications
        self.conversations: typing.Dict[typing.Tuple[int, int], Conversation] = {}
        self.message_counter: int = 0

        # AI developer feedback history
        self.developer_feedback: typing.List[typing.Dict[str, typing.Any]] = []

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
        self.ai_coordinator = AgentTurnCoordinator(self)

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

    @property
    def current_player(self) -> typing.Optional[Player]:
        """Returns the currently active Player object, or None if players list is empty."""
        if self.players and 0 <= self.current_player_index < len(self.players):
            return self.players[self.current_player_index]
        return None

    def reset_sector_camera(self):
        """Resets the sector camera zoom and pan offset."""
        game_camera.reset_sector_camera(self)

    def start_new_game(self, settings=None):
        """Initializes a new game when the New Game button is clicked."""
        return game_setup.start_new_game(self, settings=settings)

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
        input_locked = isinstance(self, Game) and self.is_ai_input_locked()
        if input_locked and action.get('action') not in {
            'toggle_ingame_menu', 'save_game', 'load_game_file',
            'quit_to_main_menu', 'show_main_menu', 'quit',
            'update_ai_repair_retries',
        }:
            return
        game_actions.handle_gui_action(self, action)

    def is_ai_input_locked(self) -> bool:
        current = self.current_player
        return bool(
            self.game_started
            and current is not None
            and not current.is_human
            and (self.pending_ai_turn_end_time > 0 or self.ai_coordinator.is_busy)
        )

    def update_sector_camera(self, dt: float):
        """Smoothly interpolates the sector camera zoom and pan offset."""
        game_camera.update_sector_camera(self, dt)

    def recompute_visibility(self):
        """Recomputes the fog-of-war visibility snapshot for the active human/spectator player."""
        if self.game_started and self.galaxy and self.players:
            viewer = self.players[self.current_player_index]
            self.visibility = VisibilityService.compute(self.galaxy, viewer, turn_number=getattr(self, 'turn_number', 1))
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
                if not self.ai_coordinator.start_current_turn():
                    current = self.current_player
                    if current is not None and not current.is_human:
                        logger.warning("AI coordinator did not start; ending turn as fallback.")
                        self.end_turn()

        self.ai_coordinator.update()


    def end_turn(self):
        """Delegates end_turn processing to the TurnProcessor instance."""
        if self.ai_coordinator.is_busy:
            self.ai_coordinator.reset()
        self.turn_manager.end_turn()
        self.visibility_dirty = True
        self.sidebar_needs_update = True # Ensure sidebar refreshes after turn processing

    def check_and_schedule_ai_turn(self):
        """Schedules automated turn completion if the active player is an AI."""
        if hasattr(self, 'turn_manager') and self.turn_manager:
            self.turn_manager.check_and_schedule_ai_turn()


    def update_view_specific_labels(self):
        """Updates UI labels that depend on the current view mode."""
        if self.view_mode == 'system' and self.current_system_name:
            self.gui.update_view_mode_label(f"{self.current_system_name} system")
        elif self.view_mode == 'sector' and self.current_sector_coord:
            self.gui.update_view_mode_label(f"Sector ( {self.current_sector_coord.q} | {self.current_sector_coord.r} ) in {self.current_system_name} system")
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
        ai_status = ""
        if not getattr(current_player, 'is_human', True):
            coordinator = getattr(self, 'ai_coordinator', None)
            status = getattr(coordinator, 'status_message', '') or "AI"
            ai_status = f" ({status})"
        self.gui.update_turn_label(f"<font color='{color_hex}'>Turn {turn_num}: {current_player.name}{ai_status}</font>")
        # Update color indicator panel's background and dynamic panel theme hue
        self.gui.update_player_color_indicator(Color(color)) # Convert tuple to pygame.Color
        self.gui.update_player_turn_theme(Color(color))
        self.gui.update_resource_display(current_player)
        if hasattr(self.gui, 'update_comms_button'):
            self.gui.update_comms_button()



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

    def save_game(self, filename: typing.Optional[str] = None) -> typing.Optional[str]:
        """Saves current game state to a file.

        Args:
            filename (typing.Optional[str]): Optional custom save file name or path.

        Returns:
            typing.Optional[str]: Absolute or relative filepath where the save file was created, or None on failure.
        """
        import save_manager
        try:
            filepath = save_manager.save_game_to_file(self, filename)
            logger.debug(f"Game state saved to {filepath}")
            if self.gui:
                self.gui.show_info_dialog(f"Game saved successfully.", title="Save Game")
            return filepath
        except Exception as e:
            logger.error(f"Error saving game state: {e}", exc_info=True)
            if self.gui:
                self.gui.show_error_dialog(f"Failed to save game state:<br>{e}", title="Save Error")
            return None

    def load_game(self, filepath: str) -> bool:
        """Loads game state from a save file and refreshes all GUI displays.

        Args:
            filepath (str): Path to the save file.

        Returns:
            bool: True if game state was loaded successfully, False otherwise.
        """
        import save_manager
        logger.debug(f"Loading game state from {filepath}...")
        self.ai_coordinator.reset()
        try:
            success = save_manager.load_game_from_file(self, filepath)
        except Exception as e:
            logger.error(f"Error loading save file {filepath}: {e}", exc_info=True)
            success = False

        if success:
            self.gui.show_game_ui()
            self.update_view_specific_labels()
            self.update_side_bar_content()
            self.update_player_turn_display()
            logger.debug("Game state loaded successfully.")
        else:
            logger.error(f"Failed to load game state from {filepath}")
            if self.gui:
                self.gui.show_error_dialog(
                    f"Failed to load save file:<br>'{filepath}'<br><br>File may be missing or corrupted.",
                    title="Load Game Error"
                )
        return success

    def quit_to_main_menu(self):
        """Resets active game state and returns the UI to the main menu."""
        logger.debug("Quitting to main menu...")
        self.ai_coordinator.reset()
        self.game_started = False
        self.view_mode = 'main_menu'
        self.gui.clear_and_reset()
        self.gui.show_main_menu()

    def get_player_by_id(self, player_id: int) -> typing.Optional[Player]:
        """Returns the Player matching player_id, or None."""
        if not self.players:
            return None
        for p in self.players:
            if getattr(p, "id", None) == player_id:
                return p
        return None

    def get_conversation(self, p1_id: int, p2_id: int, create_if_missing: bool = True) -> typing.Optional[Conversation]:
        """Returns the Conversation between two players, creating it if needed."""
        key = Conversation.make_key(p1_id, p2_id)
        if key not in self.conversations and create_if_missing:
            self.conversations[key] = Conversation(participant_ids=key)
        return self.conversations.get(key)

    def get_conversations_for_player(self, player_id: int) -> typing.List[Conversation]:
        """Returns all Conversation objects involving player_id."""
        return [conv for key, conv in self.conversations.items() if player_id in key]

    def send_message(self, sender: typing.Any, recipient_id: int, text: str) -> bool:
        """Sends a text message from sender to recipient player within their Conversation thread.

        Args:
            sender: Sender Player instance or player_id int.
            recipient_id (int): Target recipient player ID.
            text (str): Message content.

        Returns:
            bool: True if message was sent successfully, False otherwise.
        """
        if not text or not str(text).strip():
            return False
        sender_player = sender if isinstance(sender, Player) else self.get_player_by_id(sender)
        recipient_player = self.get_player_by_id(recipient_id)
        if not sender_player or not recipient_player:
            return False

        sender_id = int(sender_player.id)
        target_id = int(recipient_player.id)
        if sender_id == target_id:
            return False

        self.message_counter += 1
        msg = Message(
            id=self.message_counter,
            sender_id=sender_id,
            sender_name=str(sender_player.name),
            recipient_id=target_id,
            turn_sent=int(self.turn_number),
            text=str(text).strip()[:500],
            timestamp="",
            read_by_recipient=False,
        )
        conv = self.get_conversation(sender_id, target_id, create_if_missing=True)
        if conv is not None:
            conv.add_message(msg)

        logger.debug(f"[Comms] Message #{msg.id} sent from {sender_player.name} to {recipient_player.name} (Turn {self.turn_number}): '{msg.text}'")
        return True

    def get_messages_for_player(self, player_id: int) -> typing.List[Message]:
        """Returns all messages involving player_id (sent or received)."""
        result: typing.List[Message] = []
        for conv in self.get_conversations_for_player(player_id):
            result.extend(conv.messages)
        result.sort(key=lambda m: (m.turn_sent, m.id))
        return result

    def get_incoming_messages(self, player_id: int, before_turn: typing.Optional[int] = None) -> typing.List[Message]:
        """Returns messages addressed to player_id, optionally filtered to those sent before before_turn."""
        result: typing.List[Message] = []
        for conv in self.get_conversations_for_player(player_id):
            for m in conv.messages:
                if m.recipient_id == player_id:
                    if before_turn is None or m.turn_sent < before_turn:
                        result.append(m)
        result.sort(key=lambda m: (m.turn_sent, m.id))
        return result

    def get_unread_messages_for_player(self, player_id: int, before_turn: typing.Optional[int] = None) -> typing.List[Message]:
        """Returns unread messages addressed to player_id."""
        result: typing.List[Message] = []
        for conv in self.get_conversations_for_player(player_id):
            for m in conv.messages:
                if m.recipient_id == player_id and not m.read_by_recipient:
                    if before_turn is None or m.turn_sent < before_turn:
                        result.append(m)
        result.sort(key=lambda m: (m.turn_sent, m.id))
        return result

    def mark_messages_as_read(self, player_id: int) -> None:
        """Marks all incoming messages for player_id as read across all conversations."""
        for conv in self.get_conversations_for_player(player_id):
            conv.mark_as_read(player_id)

    def mark_conversation_as_read(self, player_id: int, other_player_id: int) -> None:
        """Marks incoming messages in a specific conversation as read."""
        conv = self.get_conversation(player_id, other_player_id, create_if_missing=False)
        if conv is not None:
            conv.mark_as_read(player_id)

    def record_developer_feedback(self, sender: typing.Any, text: str) -> bool:
        """Records feedback, suggestions, or bug reports from a player/agent to the developer.

        Persists the entry in human-readable Markdown to saves/ai_feedback.md and logs it.
        """
        if not text or not str(text).strip():
            return False
        sender_player = sender if isinstance(sender, Player) else self.get_player_by_id(sender)
        player_name = str(sender_player.name) if sender_player else f"Player {sender}"
        player_id = int(sender_player.id) if sender_player else int(sender)
        agent_id = str(getattr(sender_player, "agent_id", f"player-{player_id}"))
        campaign_id = str(getattr(self, "campaign_id", "unknown"))
        turn_number = int(getattr(self, "turn_number", 1))
        clean_text = str(text).strip()[:2000]

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "campaign_id": campaign_id,
            "turn_number": turn_number,
            "player_id": player_id,
            "player_name": player_name,
            "agent_id": agent_id,
            "message": clean_text,
        }
        self.developer_feedback.append(entry)

        try:
            import save_manager
            feedback_path = Path(save_manager.SAVES_DIR) / "ai_feedback.md"
            feedback_path.parent.mkdir(parents=True, exist_ok=True)

            md_content = ""
            if not feedback_path.exists() or feedback_path.stat().st_size == 0:
                md_content += "# AI Developer Feedback Log\n\n"

            md_content += (
                f"## Turn {turn_number} — {player_name} (Agent: `{agent_id}`)\n"
                f"- **Timestamp**: {entry['timestamp']}\n"
                f"- **Campaign**: `{campaign_id}`\n"
                f"- **Player**: {player_name} (ID: {player_id})\n\n"
                f"### Message\n{clean_text}\n\n---\n\n"
            )
            with feedback_path.open("a", encoding="utf-8") as f:
                f.write(md_content)
        except Exception as exc:
            logger.warning(f"Could not persist developer feedback: {exc}", exc_info=True)

        logger.info(f"[Developer Feedback] Turn {turn_number} - {player_name} (Agent {agent_id}): {clean_text}")
        return True

# Application entry point
if __name__ == '__main__':
    setup_logging(log_to_file=True)
    logger.debug("Initializing Game...")
    game = Game()
    logger.debug("Starting Game Loop...")
    game.run()
