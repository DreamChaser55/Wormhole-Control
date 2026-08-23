"""Keyboard event handling, camera panning, focus management, and global hotkeys."""
import logging
import pygame
import pygame_gui
from geometry import Position

logger = logging.getLogger(__name__)


def handle_keyboard_panning(game, gui, time_delta: float) -> None:
    """Pans the sector camera based on directional arrow key states.

    Args:
        game: Target Game instance.
        gui: Target GUI_Handler instance.
        time_delta (float): Elapsed frame time in seconds.
    """
    keys = pygame.key.get_pressed()
    is_typing = False
    if hasattr(gui, 'is_any_text_entry_focused'):
        val = gui.is_any_text_entry_focused()
        if isinstance(val, bool):
            is_typing = val

    if game.view_mode == 'sector' and game.game_started and not is_typing:
        zoom = game.sector_zoom
        if not isinstance(zoom, (int, float)):
            zoom = 1.0
        pan_offset = game.sector_pan_offset
        if isinstance(pan_offset, Position):
            pan_amount = 500.0 * time_delta

            def is_pressed(k):
                try:
                    return keys[k]
                except (IndexError, KeyError, TypeError):
                    return False

            dx, dy = 0.0, 0.0
            if is_pressed(pygame.K_LEFT):
                dx += pan_amount
            if is_pressed(pygame.K_RIGHT):
                dx -= pan_amount
            if is_pressed(pygame.K_UP):
                dy += pan_amount
            if is_pressed(pygame.K_DOWN):
                dy -= pan_amount

            if dx != 0.0 or dy != 0.0:
                pan_offset.x += dx
                pan_offset.y += dy
                if getattr(game, 'zoom_anchor_pixel', None) is not None:
                    game.zoom_anchor_pixel.x += dx
                    game.zoom_anchor_pixel.y += dy


def handle_key_down(game, gui, event: pygame.event.Event) -> bool:
    """Processes KEYDOWN events and hotkeys.

    Args:
        game: Target Game instance.
        gui: Target GUI_Handler instance.
        event (pygame.event.Event): Pygame KEYDOWN event.

    Returns:
        bool: True if the event was consumed or intercepted by modals/focus, False otherwise.
    """
    # If a text entry field has active focus, intercept KEYDOWN to block shortcuts and handle ESC
    is_typing = False
    if hasattr(gui, 'is_any_text_entry_focused'):
        val = gui.is_any_text_entry_focused()
        if isinstance(val, bool):
            is_typing = val
    if is_typing:
        if event.key == pygame.K_ESCAPE:
            if hasattr(gui, 'manager') and hasattr(gui.manager, 'ui_group') and hasattr(gui.manager.ui_group, 'sprites'):
                for sprite in gui.manager.ui_group.sprites():
                    if isinstance(sprite, (pygame_gui.elements.UITextEntryLine, pygame_gui.elements.UITextEntryBox)):
                        if sprite.is_focused:
                            sprite.unfocus()
        return True

    # If the in-game menu is open, block all further game-world input processing for this event.
    if gui.is_ingame_menu_open():
        if event.key == pygame.K_ESCAPE:
            if hasattr(gui, 'load_save_window') and gui.load_save_window and gui.load_save_window.alive():
                gui.load_save_window.kill()
                gui.load_save_window = None
            else:
                gui.toggle_ingame_menu()
        return True

    # Similarly, block game-world input when the unit editor is open.
    if gui.is_unit_editor_open():
        if event.key == pygame.K_ESCAPE:
            gui.close_unit_editor()
        return True

    # Block game-world input when the retrofit wizard is open.
    if hasattr(gui, 'is_retrofit_wizard_open') and gui.is_retrofit_wizard_open() is True:
        if event.key == pygame.K_ESCAPE:
            gui.close_retrofit_wizard()
        return True

    if event.key == pygame.K_ESCAPE:
        if gui.is_mouse_over_context_menu((-1, -1)):
            gui.close_context_menu()
        elif game.pending_ability is not None:
            # Cancel ability targeting mode
            logger.debug("Ability targeting cancelled via ESC.")
            game.pending_ability = None
            game.sidebar_needs_update = True
        elif game.view_mode == 'about':
            game.view_mode = 'main_menu'
            gui.show_main_menu()
        elif game.view_mode in ['galaxy', 'system', 'sector']:
            gui.toggle_ingame_menu()
    elif event.key == pygame.K_g and game.game_started:
        game.view_mode = 'galaxy'
        game.update_view_specific_labels()
    elif event.key == pygame.K_s and game.game_started and game.current_system_name:
        game.view_mode = 'system'
        game.selected_objects.clear()
        game.update_view_specific_labels()
    elif event.key == pygame.K_e and game.game_started:
        game.end_turn()

    return False
