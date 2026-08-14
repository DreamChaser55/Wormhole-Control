"""Payload builder registry mapping sidebar buttons and dropdowns to GUI actions."""
import typing
import pygame


def _shift_pressed() -> bool:
    """Helper to check if any Shift key is currently held down."""
    keys = pygame.key.get_pressed()
    return bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])


def build_button_payload(gui, action_id: str, target_data: typing.Any) -> typing.Optional[dict]:
    """Translates a dynamic sidebar button action ID and target payload into a GUI action dict.

    Args:
        gui: Target GUI_Handler instance.
        action_id (str): Action string associated with the button.
        target_data (typing.Any): Associated unit ID, tuple, or metadata.

    Returns:
        typing.Optional[dict]: Constructed action payload dict or None if unhandled.
    """
    if action_id == 'unload_resources_nearest':
        return {
            'action': 'unload_resources_nearest',
            'unit_id': target_data,
            'shift_pressed': _shift_pressed()
        }
    elif action_id == 'lay_minefield_anti_strikecraft':
        return {
            'action': 'lay_minefield',
            'minefield_type': 'anti_strikecraft',
            'unit_id': target_data,
            'shift_pressed': _shift_pressed()
        }
    elif action_id == 'lay_minefield_anti_ship':
        return {
            'action': 'lay_minefield',
            'minefield_type': 'anti_ship',
            'unit_id': target_data,
            'shift_pressed': _shift_pressed()
        }
    elif action_id == 'lay_minefield':
        return {
            'action': 'lay_minefield',
            'unit_id': target_data,
            'shift_pressed': _shift_pressed()
        }
    elif action_id == 'toggle_orders_queue':
        section_key = f"{target_data}_orders_queue"
        gui.toggle_section_expansion(section_key)
        gui.game_instance.sidebar_needs_update = True
        return {'action': 'ui_handled'}
    elif action_id == 'cycle_stance':
        return {
            'action': 'cycle_stance',
            'unit_id': target_data
        }
    elif action_id == 'deploy_ship':
        carrier_id, docked_unit_id = target_data
        return {
            'action': 'deploy_ship',
            'carrier_id': carrier_id,
            'docked_unit_id': docked_unit_id
        }
    elif action_id == 'toggle_build_wing_type':
        return {
            'action': 'toggle_build_wing_type',
            'carrier_id': target_data
        }
    elif action_id == 'launch_all_wings':
        return {
            'action': 'launch_all_wings',
            'carrier_id': target_data
        }
    elif action_id == 'recall_ship':
        carrier_id, launched_unit_id = target_data
        return {
            'action': 'recall_ship',
            'carrier_id': carrier_id,
            'launched_unit_id': launched_unit_id
        }
    elif action_id == 'use_ability':
        return {
            'action': 'use_ability',
            'ability_type_str': target_data.get('ability_type_str'),
            'requires_target_unit': target_data.get('requires_target_unit', False),
            'requires_target_position': target_data.get('requires_target_position', False),
        }
    elif action_id == 'select_individual_unit':
        return {
            'action': 'select_individual_unit',
            'unit_id': target_data,
            'shift_pressed': _shift_pressed()
        }
    elif action_id == 'select_minefield':
        return {
            'action': 'select_minefield',
            'minefield_id': target_data,
        }
    elif action_id == 'remove_minefield':
        return {
            'action': 'remove_minefield',
            'minefield_id': target_data,
        }
    elif action_id == 'select_celestial_body':
        return {
            'action': 'select_celestial_body',
            'body_id': target_data,
        }
    elif action_id == 'switch_unit_sidebar_tab':
        return {
            'action': 'switch_unit_sidebar_tab',
            'tab_name': target_data
        }
    elif action_id == 'stop_unit':
        return {
            'action': 'stop_unit',
            'unit_id': target_data
        }
    elif action_id == 'stop_selected_units':
        return {
            'action': 'stop_selected_units'
        }
    elif action_id:
        return {
            'action': action_id,
            'target_data': target_data
        }
    return None


def build_dropdown_payload(gui, action_id: str, target_data: typing.Any, selected_text: str) -> dict:
    """Translates a dynamic sidebar dropdown change into a GUI action dict.

    Args:
        gui: Target GUI_Handler instance.
        action_id (str): Action string associated with dropdown.
        target_data (typing.Any): Target unit ID or metadata.
        selected_text (str): Currently selected option text.

    Returns:
        dict: Action payload dictionary.
    """
    if action_id == 'set_stance':
        return {
            'action': 'set_stance',
            'unit_id': target_data,
            'stance_display_name': selected_text
        }
    else:
        return {
            'action': action_id,
            'target_data': target_data,
            'selected_text': selected_text
        }
