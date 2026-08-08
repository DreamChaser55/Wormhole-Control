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
    editor._editing_key = template.design_name
    editor._hull_size = template.hull_size
    editor._comp = copy.deepcopy(template.components)
    editor._turrets = copy.deepcopy(template.components.turrets)
    editor._selected_abilities = set(template.components.abilities)
    if editor._name_entry:
        editor._name_entry.set_text(template.design_name)
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


def do_save(editor) -> typing.Optional[str]:
    """Saves current editor state as a template."""
    key = editor._name_entry.get_text().strip() if editor._name_entry else ""
    display = editor._display_entry.get_text().strip() if editor._display_entry else ""
    if not key:
        set_status(editor, "⚠ Please enter a design key.", error=True)
        return None
    if not display:
        set_status(editor, "⚠ Please enter a display name.", error=True)
        return None

    # Sync all input fields before saving
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
        design_name=key,
        display_name=display,
        hull_size=editor._hull_size,
        components=editor._comp,
    )
    errors = editor.template_manager.save_design(template)
    if errors:
        set_status(editor, " | ".join(errors), error=True)
        return None

    editor._editing_key = template.design_name
    set_status(editor, f"✔ Design '{template.design_name}' saved!", error=False)
    refresh_load_dropdown(editor)
    editor._update_summary()
    return "design_saved"


def do_delete(editor) -> typing.Optional[str]:
    """Deletes the active unit design template.

    Returns:
        typing.Optional[str]: 'design_deleted' if successful, or None if deletion failed.
    """
    key = editor._editing_key
    if not key:
        key = editor._name_entry.get_text().strip() if editor._name_entry else ""
    if not key:
        set_status(editor, "⚠ No design selected to delete.", error=True)
        return None
    deleted = editor.template_manager.delete_design(key)
    if deleted:
        set_status(editor, f"✖ Design '{key}' deleted.", error=False)
        editor._editing_key = None
        refresh_load_dropdown(editor)
        return "design_deleted"
    else:
        set_status(editor, f"⚠ Design '{key}' not found.", error=True)
        return None


def load_design(editor, key: str) -> None:
    """Loads a unit design template into the editor controls.

    Args:
        key (str): Unique design name identifier to load.
    """
    template = editor.template_manager.get_design(key)
    if not template:
        return
    sync_widgets_from_template(editor, template)
    set_status(editor, f"Loaded design '{key}'.", error=False)
    refresh_load_dropdown(editor)
