"""Event routing and dispatching for GUI manager events."""
import logging
import typing
import pygame
import pygame_gui

from constants import DEBUG
from . import context_menu, dynamic_actions

logger = logging.getLogger(__name__)


def _editor_action_to_gui_action(editor_action: str) -> typing.Optional[dict]:
    """Converts a UnitEditorWindow action identifier into a standard GUI action payload dictionary.

    Args:
        editor_action (str): Action string received from the unit editor window.

    Returns:
        typing.Optional[dict]: GUI action dictionary if recognized, or None if unhandled.
    """
    if editor_action == 'close':
        return {'action': 'toggle_unit_editor'}
    elif editor_action == 'design_saved':
        return {'action': 'unit_editor_design_saved'}
    elif editor_action == 'design_deleted':
        return {'action': 'unit_editor_design_deleted'}
    return None


def process_event(gui, event: pygame.event.Event) -> typing.Optional[dict]:
    """Processes a single Pygame event for the GUI Manager.

    Args:
        gui: Target GUI_Handler instance.
        event (pygame.event.Event): Event to process.

    Returns:
        typing.Optional[dict]: Action payload dict, {'action': 'ui_handled'}, or None.
    """
    handled_by_manager = gui.manager.process_events(event)
    action_result = None

    if event.type == pygame_gui.UI_BUTTON_PRESSED:
        if DEBUG:
            logger.debug(f"[GUI_Handler DEBUG] UI_BUTTON_PRESSED: event.ui_element={event.ui_element}")

        # 1. Main Menu Buttons
        if gui.new_game_button and event.ui_element == gui.new_game_button:
            logger.debug("New Game button pressed (GUI)")
            gui.show_new_game_wizard()
            action_result = {'action': 'ui_handled'}
        elif gui.load_game_button and event.ui_element == gui.load_game_button:
            logger.debug("Load Game button pressed (Main Menu GUI)")
            gui.show_load_game_dialog()
        elif gui.about_button and event.ui_element == gui.about_button:
            logger.debug("About button pressed (GUI)")
            gui.show_about_screen()
        elif gui.quit_button and event.ui_element == gui.quit_button:
            logger.debug("Quit button pressed (GUI)")
            action_result = {'action': 'quit'}

        # 2. Load Save Dialog Buttons
        elif gui.load_save_cancel_button and event.ui_element == gui.load_save_cancel_button:
            if gui.load_save_window:
                gui.load_save_window.kill()
                gui.load_save_window = None
        elif gui.load_save_confirm_button and event.ui_element == gui.load_save_confirm_button:
            if gui.load_save_selection_list:
                selected = gui.load_save_selection_list.get_single_selection()
                if selected and selected in gui.save_file_paths:
                    filepath = gui.save_file_paths[selected]
                    if gui.load_save_window:
                        gui.load_save_window.kill()
                        gui.load_save_window = None
                    action_result = {'action': 'load_game_file', 'filepath': filepath}
                else:
                    gui.show_warning_dialog("Please select a save file from the list before clicking Load.", title="No Selection")

        # 3. About Screen Buttons
        elif gui.about_screen_back_button and event.ui_element == gui.about_screen_back_button:
            logger.debug("About Back button pressed (GUI)")
            gui.show_main_menu()

        # 4. In-Game HUD Buttons
        elif gui.end_turn_button and event.ui_element == gui.end_turn_button:
            logger.debug("End Turn button pressed (GUI)")
            action_result = {'action': 'end_turn'}
        elif gui.back_button and event.ui_element == gui.back_button:
            logger.debug("Back button pressed (GUI)")
            action_result = {'action': 'navigate_back'}

        # 5. Inhibitor Toggle Button
        elif event.ui_element and event.ui_element.object_ids and event.ui_element.object_ids[-1] == '#toggle_inhibitor_button':
            action_result = {'action': 'toggle_inhibitor', 'shift_pressed': dynamic_actions._shift_pressed()}

        # 5b. Cloaking Toggle Button
        elif event.ui_element and event.ui_element.object_ids and event.ui_element.object_ids[-1] == '#toggle_cloaking_button':
            action_result = {'action': 'toggle_cloaking', 'shift_pressed': dynamic_actions._shift_pressed()}

        # 6. Context Menu Buttons
        elif gui.context_menu_buttons and event.ui_element in gui.context_menu_buttons:
            index = gui.context_menu_buttons.index(event.ui_element)
            action_result = context_menu.handle_button_index(gui, index)

        # 7. Dynamic Sidebar Buttons
        elif event.ui_element in gui.dynamic_button_actions and gui.dynamic_button_actions[event.ui_element]:
            button_data = gui.dynamic_button_actions[event.ui_element]
            action_id = button_data['action_id']
            target_data = button_data['target_data']
            action_result = dynamic_actions.build_button_payload(gui, action_id, target_data)

        # 8. In-Game Menu / Pause Menu Buttons
        elif gui.menu_button and event.ui_element == gui.menu_button:
            logger.debug("Menu button pressed (GUI)")
            action_result = {'action': 'toggle_ingame_menu'}
        elif gui.resume_button and event.ui_element == gui.resume_button:
            logger.debug("Resume button pressed (GUI)")
            action_result = {'action': 'toggle_ingame_menu'}
        elif gui.save_game_button and event.ui_element == gui.save_game_button:
            logger.debug("Save Game button pressed (GUI)")
            action_result = {'action': 'save_game'}
        elif gui.ingame_load_game_button and event.ui_element == gui.ingame_load_game_button:
            logger.debug("Load Game button pressed (In-Game GUI)")
            gui.show_load_game_dialog()
        elif gui.quit_to_menu_button and event.ui_element == gui.quit_to_menu_button:
            logger.debug("Quit to Main Menu button pressed (GUI)")
            action_result = {'action': 'quit_to_main_menu'}
        elif gui.unit_editor_button and event.ui_element == gui.unit_editor_button:
            logger.debug("Unit Editor button pressed (GUI)")
            action_result = {'action': 'toggle_unit_editor'}

        # 9. New Game Wizard Buttons
        elif gui.new_game_wizard and gui.new_game_wizard.is_alive:
            wizard_action = gui.new_game_wizard.process_event(event)
            if wizard_action:
                if wizard_action['action'] == 'cancel_new_game_wizard':
                    gui.close_new_game_wizard()
                action_result = wizard_action
            else:
                action_result = {'action': 'ui_handled'}

        # 10. Unit Editor Fallthrough
        elif gui.unit_editor_window and gui.unit_editor_window.is_visible:
            editor_action = gui.unit_editor_window.process_event(event)
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

    elif event.type == pygame_gui.UI_TEXT_ENTRY_FINISHED:
        if gui.unit_name_entry and event.ui_element is gui.unit_name_entry:
            action_result = {'action': 'rename_unit', 'new_name': event.text}

    elif event.type == pygame_gui.UI_TEXT_ENTRY_CHANGED:
        if gui.unit_editor_window and gui.unit_editor_window.is_visible:
            editor_action = gui.process_unit_editor_event(event)
            if editor_action:
                action_result = _editor_action_to_gui_action(editor_action)
                if action_result is None:
                    action_result = {'action': 'ui_handled'}

    elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
        editor_action = gui.process_unit_editor_event(event)
        if editor_action:
            action_result = _editor_action_to_gui_action(editor_action)
            if action_result is None:
                action_result = {'action': 'ui_handled'}
        elif event.ui_element in gui.dynamic_dropdown_actions:
            dropdown_data = gui.dynamic_dropdown_actions[event.ui_element]
            action_id = dropdown_data['action_id']
            target_data = dropdown_data['target_data']
            action_result = dynamic_actions.build_dropdown_payload(gui, action_id, target_data, event.text)
        else:
            logger.debug(f"Drop down menu changed (GUI): {event.text}")
            action_result = {'action': 'component_selected', 'component_name': event.text}

    elif event.type == pygame_gui.UI_HORIZONTAL_SLIDER_MOVED:
        if gui.new_game_wizard and gui.new_game_wizard.is_alive:
            gui.new_game_wizard.process_event(event)

    elif event.type == pygame_gui.UI_WINDOW_CLOSE:
        # If the player closed the wizard via the window's own X button
        if gui.new_game_wizard and event.ui_element is gui.new_game_wizard.window:
            gui.close_new_game_wizard()
            action_result = {'action': 'cancel_new_game_wizard'}

    if action_result:
        return action_result
    elif handled_by_manager:
        return {'action': 'ui_handled'}
    else:
        return None
