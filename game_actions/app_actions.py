"""GUI action handlers for application state, menus, persistence, and navigation."""
import logging
import typing

from game_ai.runtime import normalize_repair_retries

logger = logging.getLogger(__name__)


def handle_new_game(game, action: dict) -> None:
    game.start_new_game()


def handle_start_new_game_with_settings(game, action: dict) -> None:
    """Starts a new game using the GameSettings produced by the New Game Wizard."""
    settings = action.get('settings')
    # Close the wizard window before starting (it's still alive at this point)
    if game.gui.is_new_game_wizard_open():
        game.gui.close_new_game_wizard()
    game.start_new_game(settings=settings)


def handle_cancel_new_game_wizard(game, action: dict) -> None:
    """Closes the wizard and returns to the main menu view."""
    game.gui.close_new_game_wizard()


def handle_show_about(game, action: dict) -> None:
    game.gui.show_about_screen()


def handle_quit(game, action: dict) -> None:
    game.is_running = False


def handle_show_main_menu(game, action: dict) -> None:
    game.view_mode = 'main_menu'
    game.game_started = False
    game.gui.show_main_menu()


def handle_context_menu_select(game, action: dict) -> None:
    action_id = action.get('action_id')
    target = action.get('target')
    if action_id and target is not None:
        game.input_processor.handle_context_menu_action(action_id, target)
    else:
        logger.debug(f"Warning: Context menu action '{action_id}' missing ID or target.")


def handle_end_turn(game, action: dict) -> None:
    game.end_turn()


def handle_toggle_ingame_menu(game, action: dict) -> None:
    game.gui.toggle_ingame_menu()


def handle_update_ai_repair_retries(game, action: dict) -> None:
    """Apply per-agent repair retry settings from the in-game dialog."""
    values = action.get("values", {})
    if not isinstance(values, dict):
        return
    for player in getattr(game, "players", []):
        if getattr(player, "is_human", True):
            continue
        agent_id = str(getattr(player, "agent_id", ""))
        if agent_id in values:
            player.ai_repair_retries = normalize_repair_retries(values[agent_id])


def handle_toggle_unit_editor(game, action: dict) -> None:
    if game.gui.is_unit_editor_open():
        game.gui.close_unit_editor()
    else:
        game.gui.open_unit_editor(game.custom_template_manager)


def handle_unit_editor_design_saved(game, action: dict) -> None:
    if game.galaxy:
        all_units = [
            u for system in game.galaxy.systems.values()
            for h in system.hexes.values()
            for u in h.units
        ]
        count = game.custom_template_manager.refresh_shipyard_buildables(all_units)
        if count:
            logger.debug(f"[Game] Refreshed constructors on {count} shipyard unit(s) with custom designs.")


def handle_unit_editor_design_deleted(game, action: dict) -> None:
    pass


def handle_save_game(game, action: dict) -> None:
    game.save_game()


def handle_load_game_file(game, action: dict) -> None:
    filepath = action.get('filepath')
    if filepath:
        game.load_game(filepath)


def handle_quit_to_main_menu(game, action: dict) -> None:
    game.quit_to_main_menu()


def handle_navigate_back(game, action: dict) -> None:
    if game.view_mode == 'sector':
        game.view_mode = 'system'
        game.current_sector_coord = None
        game.update_view_specific_labels()
        game.gui.update_back_button_visibility()
        game.update_side_bar_content()
    elif game.view_mode == 'system':
        game.view_mode = 'galaxy'
        game.current_system_name = None
        game.current_sector_coord = None
        game.update_view_specific_labels()
        game.gui.update_back_button_visibility()
        game.update_side_bar_content()


def handle_ui_handled(game, action: dict) -> None:
    pass


HANDLERS: typing.Dict[str, typing.Callable[[typing.Any, dict], None]] = {
    'new_game': handle_new_game,
    'start_new_game_with_settings': handle_start_new_game_with_settings,
    'cancel_new_game_wizard': handle_cancel_new_game_wizard,
    'show_about': handle_show_about,
    'quit': handle_quit,
    'show_main_menu': handle_show_main_menu,
    'context_menu_select': handle_context_menu_select,
    'end_turn': handle_end_turn,
    'toggle_ingame_menu': handle_toggle_ingame_menu,
    'update_ai_repair_retries': handle_update_ai_repair_retries,
    'toggle_unit_editor': handle_toggle_unit_editor,
    'unit_editor_design_saved': handle_unit_editor_design_saved,
    'unit_editor_design_deleted': handle_unit_editor_design_deleted,
    'save_game': handle_save_game,
    'load_game_file': handle_load_game_file,
    'quit_to_main_menu': handle_quit_to_main_menu,
    'navigate_back': handle_navigate_back,
    'ui_handled': handle_ui_handled,
}
