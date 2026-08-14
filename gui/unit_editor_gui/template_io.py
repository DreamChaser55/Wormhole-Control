"""
template_io.py

Saving, deleting, loading unit design templates, syncing UI widgets from templates,
dropdown refreshing, and status label updates.
"""

import copy
import pygame
import pygame_gui
import typing
from custom_unit_templates import CustomUnitTemplate
from .catalog import HULL_SIZE_NAMES, HYPERDRIVE_TYPES
from .widget_factory import replace_dropdown
from .component_state import (
    apply_hull_restrictions,
    update_component_toggle_labels,
    update_ability_toggle_labels,
    refresh_component_details,
)
from .turret_editor import rebuild_turret_list
from .save_dialog import SaveConfirmationDialog


def set_status(editor, msg: str, error: bool = False) -> None:
    """Updates status label text."""
    if editor._status_label:
        editor._status_label.set_text(msg)


def refresh_load_dropdown(editor) -> None:
    """Rebuild the load dropdown list with current designs."""
    if not editor._load_dd:
        return
    existing = editor.template_manager.list_design_names()
    load_options = ["— select —"] + existing
    rect = editor._load_dd.get_relative_rect()
    dd_h = int(28 * (editor.screen_res.y / 720.0))
    editor._load_dd = replace_dropdown(
        editor,
        editor._load_dd,
        load_options,
        "— select —",
        "#editor_load_dropdown",
        override_rect=pygame.Rect(rect.x, rect.y, rect.w, dd_h),
    )


def sync_widgets_from_template(editor, template: CustomUnitTemplate) -> None:
    """Synchronizes all UI text fields, dropdown menus, and toggle controls to match a unit template.

    Args:
        editor: UnitEditorWindow instance.
        template (CustomUnitTemplate): Design template containing component configuration.
    """
    editor._editing_name = template.display_name
    editor._hull_size = template.hull_size
    editor._comp = copy.deepcopy(template.components)
    editor._turrets = copy.deepcopy(template.components.turrets)
    editor._selected_abilities = set(template.components.abilities)
    if editor._display_entry:
        editor._display_entry.set_text(template.display_name)

    # Restore dynamic sub-option entry fields
    if editor._engine_speed_entry:
        editor._engine_speed_entry.set_text(str(int(editor._comp.engine_speed)))
    if editor._am_capacity_entry:
        editor._am_capacity_entry.set_text(str(int(editor._comp.antimatter_capacity)))
    if editor._hd_jump_range_entry:
        editor._hd_jump_range_entry.set_text(str(editor._comp.hyperdrive_jump_range))
    if editor._armor_entry:
        editor._armor_entry.set_text(str(editor._comp.armor))
    if editor._shields_entry:
        editor._shields_entry.set_text(str(editor._comp.shields))
    if editor._pd_entry:
        editor._pd_entry.set_text(str(editor._comp.point_defense))
    if getattr(editor, '_sensor_short_range_entry', None):
        editor._sensor_short_range_entry.set_text(str(int(editor._comp.sensor_short_range)))
    if getattr(editor, '_sensor_long_range_entry', None):
        editor._sensor_long_range_entry.set_text(str(int(editor._comp.sensor_long_range_hexes)))
    if getattr(editor, '_repair_rate_entry', None):
        editor._repair_rate_entry.set_text(str(int(editor._comp.repair_rate)))
    if getattr(editor, '_repair_range_entry', None):
        editor._repair_range_entry.set_text(str(int(editor._comp.repair_range)))
    if getattr(editor, '_mining_rate_entry', None):
        editor._mining_rate_entry.set_text(str(int(editor._comp.mining_rate)))
    if getattr(editor, '_mining_range_entry', None):
        editor._mining_range_entry.set_text(str(int(editor._comp.mining_range)))
    if getattr(editor, '_mining_max_cargo_entry', None):
        editor._mining_max_cargo_entry.set_text(str(int(editor._comp.max_mining_cargo)))
    if getattr(editor, '_hangar_slots_entry', None):
        editor._hangar_slots_entry.set_text(str(int(editor._comp.hangar_slots)))
    if getattr(editor, '_strikecraft_bay_slots_entry', None):
        editor._strikecraft_bay_slots_entry.set_text(str(int(editor._comp.strikecraft_bay_slots)))
    if getattr(editor, '_inhibitor_radius_entry', None):
        editor._inhibitor_radius_entry.set_text(str(int(editor._comp.inhibitor_radius)))
    if getattr(editor, '_marines_count_entry', None):
        editor._marines_count_entry.set_text(str(int(editor._comp.marines_count)))

    # Rebuild hull dropdown selection
    if editor._hull_dropdown:
        editor._hull_dropdown = replace_dropdown(
            editor,
            editor._hull_dropdown,
            HULL_SIZE_NAMES,
            editor._hull_size.name,
            "#hull_size_dropdown",
        )

    # Rebuild hyperdrive type dropdown selection
    if editor._hd_type_dropdown:
        editor._hd_type_dropdown = replace_dropdown(
            editor,
            editor._hd_type_dropdown,
            HYPERDRIVE_TYPES,
            editor._comp.hyperdrive_type,
            "#hd_type_dropdown",
            group_key="has_hyperdrive",
        )

    # Rebuild wing type dropdown selection
    if editor._wt_dropdown:
        editor._wt_dropdown = replace_dropdown(
            editor,
            editor._wt_dropdown,
            ["FIGHTER", "BOMBER"],
            editor._comp.wing_type if hasattr(editor._comp, "wing_type") else "FIGHTER",
            "#hd_type_dropdown",
            group_key="has_strikecraft_bay",
        )

    apply_hull_restrictions(editor)
    update_component_toggle_labels(editor)
    update_ability_toggle_labels(editor)
    rebuild_turret_list(editor)
    editor._sync_dynamic_costs()
    editor._update_capacity_label()
    refresh_component_details(editor)
    editor._update_summary()


def _show_editor_modal(editor, title: str, message: str, window_type: str = "warning") -> None:
    """Helper to display pop-up modal dialogs within the Unit Designer GUI."""
    if hasattr(editor, 'manager') and editor.manager:
        scale_x = editor.screen_res.x / 1280.0
        scale_y = editor.screen_res.y / 720.0
        dialog_w = int(500 * scale_x)
        dialog_h = int(280 * scale_y)
        x = (editor.screen_res.x - dialog_w) / 2
        y = (editor.screen_res.y - dialog_h) / 2
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
            manager=editor.manager,
            window_title=display_title
        )

        if dialog.dismiss_button:
            btn_w = int(140 * scale_x)
            btn_h = int(38 * scale_y)
            margin = int(14 * scale_x)
            dialog.dismiss_button.set_dimensions((btn_w, btn_h))
            dialog.dismiss_button.set_relative_position((-btn_w - margin, -btn_h - margin))
            container = dialog.get_container()
            if dialog.text_block and container:
                text_h = max(50, container.get_size()[1] - btn_h - (margin * 2))
                dialog.text_block.set_dimensions((container.get_size()[0], text_h))


def _collect_and_validate_template(
    editor, display_name: str
) -> typing.Tuple[typing.Optional[CustomUnitTemplate], typing.List[str]]:
    """Synchronizes all editor parameters into a CustomUnitTemplate and validates it."""
    editor._read_engine_params()
    editor._read_antimatter_params()
    editor._read_hyperdrive_params()
    editor._read_defense_params()
    editor._read_sensor_params()
    editor._read_repair_params()
    editor._read_mining_params()
    editor._read_hangar_params()
    editor._read_strikecraft_bay_params()
    editor._read_inhibitor_params()
    editor._read_marines_params()
    editor._comp.turrets = editor._turrets
    editor._comp.abilities = list(editor._selected_abilities)

    template = CustomUnitTemplate(
        display_name=display_name,
        hull_size=editor._hull_size,
        components=editor._comp,
    )
    errors = template.validate()
    return template, errors


def execute_save(
    editor, template: CustomUnitTemplate, original_name: typing.Optional[str] = None
) -> typing.Optional[str]:
    """Persists the template via template_manager and updates the editor state."""
    errors = editor.template_manager.save_design(template, original_name=original_name)
    if errors:
        error_msg = "<br>".join([f"• {e}" for e in errors])
        set_status(editor, " | ".join(errors), error=True)
        _show_editor_modal(editor, "Design Validation Failed", error_msg, window_type="warning")
        return None

    editor._editing_name = template.display_name
    if editor._display_entry:
        editor._display_entry.set_text(template.display_name)
    set_status(editor, f"✔ Design '{template.display_name}' saved!", error=False)
    refresh_load_dropdown(editor)
    editor._update_summary()
    return "design_saved"


def show_save_confirmation_dialog(
    editor, editing_name: str, suggested_new_name: typing.Optional[str] = None
) -> None:
    """Displays the modal confirmation dialog to confirm overwrite or save as a new template."""
    if editor._save_dialog:
        editor._save_dialog.kill()
        editor._save_dialog = None

    editor._save_dialog = SaveConfirmationDialog(
        manager=editor.manager,
        screen_res=editor.screen_res,
        editing_name=editing_name,
        suggested_new_name=suggested_new_name,
    )


def handle_save_dialog_action(editor, action_data: dict) -> typing.Optional[str]:
    """Handles user action from SaveConfirmationDialog."""
    action = action_data.get("action")

    if action == "overwrite":
        target_name = action_data.get("target_name") or editor._editing_name
        template, errors = _collect_and_validate_template(editor, target_name)
        if editor._save_dialog:
            editor._save_dialog.kill()
            editor._save_dialog = None
        if errors:
            error_msg = "<br>".join([f"• {e}" for e in errors])
            set_status(editor, " | ".join(errors), error=True)
            _show_editor_modal(editor, "Design Validation Failed", error_msg, window_type="warning")
            return None
        return execute_save(editor, template, original_name=target_name)

    elif action == "save_as_new":
        new_name = action_data.get("new_name", "").strip()
        if not new_name:
            set_status(editor, "⚠ Please enter a valid name.", error=True)
            _show_editor_modal(editor, "Invalid Name", "Please enter a valid display name to save as a new template.", window_type="warning")
            return "ui_handled"

        template, errors = _collect_and_validate_template(editor, new_name)
        if editor._save_dialog:
            editor._save_dialog.kill()
            editor._save_dialog = None
        if errors:
            error_msg = "<br>".join([f"• {e}" for e in errors])
            set_status(editor, " | ".join(errors), error=True)
            _show_editor_modal(editor, "Design Validation Failed", error_msg, window_type="warning")
            return None
        return execute_save(editor, template, original_name=None)

    elif action == "cancel":
        if editor._save_dialog:
            editor._save_dialog.kill()
            editor._save_dialog = None
        return "ui_handled"

    return None


def do_save(editor) -> typing.Optional[str]:
    """Saves current editor state as a template, prompting if overwriting an existing template."""
    display = editor._display_entry.get_text().strip() if editor._display_entry else ""
    if not display:
        msg = "Please enter a display name."
        set_status(editor, f"⚠ {msg}", error=True)
        _show_editor_modal(editor, "Display Name Required", msg, window_type="warning")
        return None

    template, errors = _collect_and_validate_template(editor, display)
    if errors:
        error_msg = "<br>".join([f"• {e}" for e in errors])
        set_status(editor, " | ".join(errors), error=True)
        _show_editor_modal(editor, "Design Validation Failed", error_msg, window_type="warning")
        return None

    # Check if this save would overwrite a loaded template or existing template
    if editor._editing_name:
        if display.lower() == editor._editing_name.lower():
            show_save_confirmation_dialog(editor, editing_name=editor._editing_name, suggested_new_name=f"{editor._editing_name} (Copy)")
            return "ui_handled"
        else:
            # User changed name while editing an existing template
            if editor.template_manager.get_design(display):
                show_save_confirmation_dialog(editor, editing_name=display, suggested_new_name=f"{display} (Copy)")
                return "ui_handled"
            else:
                show_save_confirmation_dialog(editor, editing_name=editor._editing_name, suggested_new_name=display)
                return "ui_handled"
    else:
        # Not currently editing a loaded template
        if editor.template_manager.get_design(display):
            show_save_confirmation_dialog(editor, editing_name=display, suggested_new_name=f"{display} (Copy)")
            return "ui_handled"
        return execute_save(editor, template, original_name=None)


def do_save_as_new(editor) -> typing.Optional[str]:
    """Saves the modified design template as a new template without modifying the original."""
    display = editor._display_entry.get_text().strip() if editor._display_entry else ""
    if not display:
        msg = "Please enter a display name."
        set_status(editor, f"⚠ {msg}", error=True)
        _show_editor_modal(editor, "Display Name Required", msg, window_type="warning")
        return None

    template, errors = _collect_and_validate_template(editor, display)
    if errors:
        error_msg = "<br>".join([f"• {e}" for e in errors])
        set_status(editor, " | ".join(errors), error=True)
        _show_editor_modal(editor, "Design Validation Failed", error_msg, window_type="warning")
        return None

    # If display name matches loaded template or existing design, prompt for new name
    if (editor._editing_name and display.lower() == editor._editing_name.lower()) or editor.template_manager.get_design(display):
        show_save_confirmation_dialog(editor, editing_name=display, suggested_new_name=f"{display} (Copy)")
        return "ui_handled"

    # Unique name: save directly as new template without modifying original
    return execute_save(editor, template, original_name=None)


def do_delete(editor) -> typing.Optional[str]:
    """Deletes the active unit design template.

    Returns:
        typing.Optional[str]: 'design_deleted' if successful, or None if deletion failed.
    """
    name = editor._editing_name
    if not name:
        name = editor._display_entry.get_text().strip() if editor._display_entry else ""
    if not name:
        msg = "No design selected to delete."
        set_status(editor, f"⚠ {msg}", error=True)
        _show_editor_modal(editor, "No Design Selected", msg, window_type="warning")
        return None
    deleted = editor.template_manager.delete_design(name)
    if deleted:
        set_status(editor, f"✖ Design '{name}' deleted.", error=False)
        editor._editing_name = None
        refresh_load_dropdown(editor)
        return "design_deleted"
    else:
        msg = f"Design '{name}' not found."
        set_status(editor, f"⚠ {msg}", error=True)
        _show_editor_modal(editor, "Deletion Failed", msg, window_type="warning")
        return None


def load_design(editor, display_name: str) -> None:
    """Loads a unit design template into the editor controls.

    Args:
        display_name (str): Unique design display name identifier to load.
    """
    template = editor.template_manager.get_design(display_name)
    if not template:
        return
    sync_widgets_from_template(editor, template)
    set_status(editor, f"Loaded design '{display_name}'.", error=False)
    refresh_load_dropdown(editor)
