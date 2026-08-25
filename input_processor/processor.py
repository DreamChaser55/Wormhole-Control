"""InputProcessor facade coordinating mouse, keyboard, hover tracking, and context actions."""
import typing
import logging
import pygame
from geometry import Position
from entities import Unit
from input_processor.hover_tracker import update_hover_states
from input_processor.keyboard_handler import handle_keyboard_panning, handle_key_down
from input_processor.mouse_handler import (
    handle_mouse_button_down,
    handle_mouse_button_up,
    handle_mouse_motion,
    handle_mouse_click,
)
from input_processor.context_menu_builder import (
    get_refit_context_options,
    get_ability_context_options,
)
from input_processor.context_actions import handle_context_menu_action

logger = logging.getLogger(__name__)


class InputProcessor:
    """Central input processor coordinating pygame events, viewport manipulation, selection, and orders."""

    def __init__(self, game_instance):
        self.game = game_instance
        self.gui = game_instance.gui

    def handle_input(self, time_delta: float = 0.016) -> None:
        """Processes user input (keyboard, mouse, UI events).

        Args:
            time_delta (float): Elapsed time since last frame in seconds.
        """
        mouse_pos_tuple = pygame.mouse.get_pos()
        mouse_pos = Position(mouse_pos_tuple[0], mouse_pos_tuple[1])

        # Keyboard camera panning in sector view
        handle_keyboard_panning(self.game, self.gui, time_delta)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.game.is_running = False
                return

            gui_action = self.gui.process_event(event)

            if gui_action:
                self.game.handle_gui_action(gui_action)
                if event.type in [pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.MOUSEWHEEL]:
                    continue

            if event.type == pygame.KEYDOWN:
                if handle_key_down(self.game, self.gui, event):
                    continue

            elif event.type == pygame.MOUSEBUTTONDOWN:
                handle_mouse_button_down(
                    self.game,
                    self.gui,
                    event,
                    mouse_pos,
                    gui_action,
                    self.handle_mouse_click
                )

            elif event.type == pygame.MOUSEBUTTONUP:
                handle_mouse_button_up(self.game, mouse_pos, event)

            elif event.type == pygame.MOUSEMOTION:
                handle_mouse_motion(self.game, mouse_pos)

            elif event.type == pygame.MOUSEWHEEL:
                self.game.handle_mouse_wheel(event.y)

        self.update_hover_states(mouse_pos)

    def update_hover_states(self, mouse_pos: Position) -> None:
        """Updates entity hover state tracking across galaxy, system, and sector views.

        Args:
            mouse_pos (Position): Current mouse screen coordinates.
        """
        update_hover_states(self.game, self.gui, mouse_pos)

    def handle_mouse_click(self, button: int, position: Position) -> None:
        """Handles mouse click events that occur over the main game canvas (outside UI elements).

        Args:
            button (int): Pygame mouse button identifier (1=Left, 2=Middle, 3=Right).
            position (Position): Screen coordinates of the click event.
        """
        handle_mouse_click(self.game, self.gui, button, position)

    def handle_context_menu_action(self, action_id: str, target: typing.Any) -> None:
        """Executes the action selected by the user from a right-click context menu.

        Args:
            action_id (str): Identifier of the chosen menu command (e.g., 'move', 'attack', 'patrol').
            target (typing.Any): Target object or coordinate associated with the context menu.
        """
        handle_context_menu_action(self.game, action_id, target)

    def get_refit_context_options(self, actors: typing.List[Unit], target_unit: Unit) -> typing.List[typing.Tuple[str, typing.Any]]:
        """Builds context menu options for adding/removing components from a friendly target unit.

        Args:
            actors (list[Unit]): Selected constructor units.
            target_unit (Unit): Target friendly unit to refit.

        Returns:
            list: Refit option entries.
        """
        return get_refit_context_options(self.game, actors, target_unit)

    def get_ability_context_options(self, actors: typing.List[Unit], target_is_unit: bool) -> typing.List[typing.Tuple[str, str]]:
        """Retrieves available unit special abilities applicable to a right-click context target.

        Args:
            actors (list[Unit]): Selected units attempting to perform an ability.
            target_is_unit (bool): True if target is another unit, False if target is a position.

        Returns:
            list of (action_id, display_label) tuples for valid abilities.
        """
        return get_ability_context_options(self.game, actors, target_is_unit)
