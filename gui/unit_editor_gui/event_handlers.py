"""
event_handlers.py

Pygame GUI event processing and interaction dispatch logic for UnitDesignerWindow.
"""

import pygame
import pygame_gui
import typing
from .template_io import do_save, do_save_as_new, do_delete, load_design, handle_save_dialog_action
from .turret_editor import do_add_turret, rebuild_turret_list
from .component_state import (
    select_component,
    toggle_component,
    toggle_ability,
    on_hull_changed,
)
from .param_readers import (
    read_hyperdrive_params,
    read_engine_params,
    read_antimatter_params,
    read_defense_params,
    read_sensor_params,
    read_repair_params,
    read_mining_params,
    read_hangar_params,
    read_strikecraft_bay_params,
    read_inhibitor_params,
    read_marines_params,
    read_cloaking_params,
)


def process_event(editor, event: pygame.event.Event) -> typing.Optional[str]:
    """Process a pygame event.

    Returns a string action key if something significant happened
    ('close', 'design_saved', 'design_deleted'), otherwise None.
    """
    if not editor.is_visible:
        return None

    # Route events to active save confirmation dialog if open
    if getattr(editor, "_save_dialog", None) and editor._save_dialog.alive():
        dialog_res = editor._save_dialog.process_event(event)
        if dialog_res is not None:
            res = handle_save_dialog_action(editor, dialog_res)
            return res if res else "ui_handled"
        if event.type in (pygame_gui.UI_BUTTON_PRESSED, pygame_gui.UI_DROP_DOWN_MENU_CHANGED):
            return "ui_handled"

    if event.type == pygame_gui.UI_BUTTON_PRESSED:
        elem = event.ui_element

        if elem is editor._close_button:
            return "close"

        if elem is editor._save_button:
            res = do_save(editor)
            return res if res else "ui_handled"

        if elem is getattr(editor, "_save_as_button", None):
            res = do_save_as_new(editor)
            return res if res else "ui_handled"

        if elem is editor._delete_button:
            res = do_delete(editor)
            return res if res else "ui_handled"

        if elem is editor._add_turret_button:
            do_add_turret(editor)
            return "ui_handled"

        # Component selection (>>> buttons)
        for key, sbtn in editor._comp_select_btns.items():
            if elem is sbtn:
                select_component(editor, key)
                return "ui_handled"

        # Component toggles ([x] buttons)
        for key, btn in editor._comp_toggles.items():
            if elem is btn:
                toggle_component(editor, key)
                return "ui_handled"

        # Ability toggles
        for aname, abtn in editor._ability_buttons.items():
            if elem is abtn:
                toggle_ability(editor, aname)
                return "ui_handled"

        # Turret remove buttons
        for i, rbtn in enumerate(editor._turret_remove_buttons):
            if elem is rbtn:
                if i < len(editor._turrets):
                    editor._turrets.pop(i)
                    editor._comp.turrets = editor._turrets
                    rebuild_turret_list(editor)
                    editor._sync_dynamic_costs()
                    editor._update_summary()
                return "ui_handled"

    elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
        elem = event.ui_element
        if elem is editor._hull_dropdown:
            on_hull_changed(editor, event.text)
            return "ui_handled"
        elif elem is editor._hd_type_dropdown:
            editor._comp.hyperdrive_type = event.text
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem is editor._wt_dropdown:
            editor._comp.wing_type = event.text
            editor._update_summary()
            return "ui_handled"
        elif elem is getattr(editor, '_cloaking_type_dropdown', None):
            editor._comp.cloaking_type = event.text
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem is editor._load_dd and event.text != "— select —":
            load_design(editor, event.text)
            return "ui_handled"

    elif event.type == pygame_gui.UI_TEXT_ENTRY_CHANGED:
        elem = event.ui_element
        if elem is editor._hd_jump_range_entry:
            read_hyperdrive_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem is editor._engine_speed_entry:
            read_engine_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem is editor._am_capacity_entry:
            read_antimatter_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem in (editor._armor_entry, editor._shields_entry, editor._pd_entry):
            read_defense_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem in (getattr(editor, '_sensor_short_range_entry', None), getattr(editor, '_sensor_long_range_entry', None)):
            read_sensor_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem in (getattr(editor, '_repair_rate_entry', None), getattr(editor, '_repair_range_entry', None)):
            read_repair_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem in (getattr(editor, '_mining_rate_entry', None), getattr(editor, '_mining_range_entry', None), getattr(editor, '_mining_max_cargo_entry', None)):
            read_mining_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem is getattr(editor, '_hangar_slots_entry', None):
            read_hangar_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem is getattr(editor, '_strikecraft_bay_slots_entry', None):
            read_strikecraft_bay_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem is getattr(editor, '_inhibitor_radius_entry', None):
            read_inhibitor_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem is getattr(editor, '_marines_count_entry', None):
            read_marines_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"
        elif elem is getattr(editor, '_cloaking_radius_entry', None):
            read_cloaking_params(editor)
            editor._sync_dynamic_costs()
            editor._update_summary()
            return "ui_handled"

    return None

