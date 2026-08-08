"""
component_state.py

Component selection, component/ability toggles, toggle label updates,
and hull restriction enforcement.
"""

import pygame_gui
from constants import HullSize, get_min_antimatter_capacity
from custom_unit_templates import (
    HULL_RESTRICTIONS,
    ADVANCED_HYPERDRIVE_MIN_HULL,
    ABILITY_REQUIRED_COMPONENTS,
)
from .catalog import COMPONENT_ROWS, HYPERDRIVE_TYPES
from .widget_factory import replace_dropdown
from .turret_editor import rebuild_turret_list, hide_turret_list


def toggle_component(editor, key: str) -> None:
    """Toggles enabling or disabling a component while verifying hull size restrictions.

    Args:
        editor: UnitEditorWindow instance.
        key (str): Attribute key corresponding to the target component (e.g., 'has_engine').
    """
    current = getattr(editor._comp, key, False)
    # Check restrictions before enabling
    if not current:
        restricted = HULL_RESTRICTIONS.get(editor._hull_size, set())
        if key in restricted:
            editor._set_status(f"⚠ {key} not allowed on {editor._hull_size.name} hull.", error=True)
            return
    setattr(editor._comp, key, not current)
    update_component_toggle_labels(editor)
    update_ability_toggle_labels(editor)
    editor._sync_dynamic_costs()
    editor._update_capacity_label()
    editor._update_summary()


def toggle_ability(editor, aname: str) -> None:
    """Toggles selection of a special ability after verifying required component prerequisites.

    Args:
        editor: UnitEditorWindow instance.
        aname (str): Name identifier of the ability to toggle.
    """
    req_keys = ABILITY_REQUIRED_COMPONENTS.get(aname, [])
    comp_labels = {row["key"]: row["label"] for row in COMPONENT_ROWS}
    missing = [k for k in req_keys if not getattr(editor._comp, k, False)]
    if missing and aname not in editor._selected_abilities:
        req_names = ", ".join(comp_labels.get(k, k) for k in missing)
        editor._set_status(f"⚠ '{aname.replace('_', ' ').title()}' requires component: {req_names}.", error=True)
        return

    if aname in editor._selected_abilities:
        editor._selected_abilities.remove(aname)
    else:
        editor._selected_abilities.add(aname)
    editor._comp.abilities = list(editor._selected_abilities)
    update_ability_toggle_labels(editor)
    editor._sync_dynamic_costs()
    editor._update_capacity_label()
    editor._update_summary()


def update_component_toggle_labels(editor) -> None:
    """Refreshes component toggle button text labels."""
    c = editor._comp
    for row in COMPONENT_ROWS:
        key = row["key"]
        label = row["label"]
        enabled = getattr(c, key, False)
        btn = editor._comp_toggles.get(key)
        if btn:
            btn.set_text(f"[x] {label}" if enabled else f"[ ] {label}")


def update_ability_toggle_labels(editor) -> None:
    """Refreshes ability toggle button text labels and enabled states."""
    c = editor._comp
    comp_labels = {row["key"]: row["label"] for row in COMPONENT_ROWS}
    for aname, btn in editor._ability_buttons.items():
        req_keys = ABILITY_REQUIRED_COMPONENTS.get(aname, [])
        missing = [k for k in req_keys if not getattr(c, k, False)]
        if missing:
            if aname in editor._selected_abilities:
                editor._selected_abilities.remove(aname)
                editor._comp.abilities = list(editor._selected_abilities)
            req_names = ", ".join(comp_labels.get(k, k) for k in missing)
            btn.set_text(f"[ ] {aname} (Req: {req_names})")
            btn.disable()
        else:
            btn.enable()
            selected = aname in editor._selected_abilities
            btn.set_text(f"[x] {aname}" if selected else f"[ ] {aname}")


def on_hull_changed(editor, hull_name: str) -> None:
    """Handles hull size dropdown changes."""
    try:
        editor._hull_size = HullSize[hull_name]
    except KeyError:
        return
    apply_hull_restrictions(editor)
    update_component_toggle_labels(editor)
    editor._sync_dynamic_costs()
    editor._update_capacity_label()
    editor._update_summary()


def select_component(editor, key: str) -> None:
    """Set the active component and update detail panel displays."""
    editor._selected_component_key = key
    for k, btn in editor._comp_select_btns.items():
        btn.set_text("▶▶▶" if k == key else ">>>")
    refresh_component_details(editor)


def refresh_component_details(editor) -> None:
    """Refresh visibility of component detail widgets based on selected component."""
    key = editor._selected_component_key
    row_label = "Component Details"
    for r in COMPONENT_ROWS:
        if r["key"] == key:
            row_label = f"Details: {r['label']}"
            break
    if editor._details_hdr:
        editor._details_hdr.set_text(row_label)

    for g_key, group in editor._details_groups.items():
        if g_key == key:
            for elem in group:
                elem.show()
        else:
            for elem in group:
                elem.hide()

    if key == "has_weapon_bays":
        rebuild_turret_list(editor)
    else:
        hide_turret_list(editor)

    if key == "has_ability_component":
        update_ability_toggle_labels(editor)


def apply_hull_restrictions(editor) -> None:
    """Disable forbidden components for the current hull size."""
    restricted = HULL_RESTRICTIONS.get(editor._hull_size, set())
    c = editor._comp
    for row in COMPONENT_ROWS:
        key = row["key"]
        btn = editor._comp_toggles.get(key)
        sbtn = editor._comp_select_btns.get(key)
        if key in restricted:
            # Force off and disable button
            setattr(c, key, False)
            if btn:
                btn.disable()
            if sbtn:
                sbtn.disable()
        else:
            if btn:
                btn.enable()
            if sbtn:
                sbtn.enable()
    # Advanced hyperdrive restriction
    hull_sizes = list(HullSize)
    min_idx = hull_sizes.index(ADVANCED_HYPERDRIVE_MIN_HULL)
    if hull_sizes.index(editor._hull_size) < min_idx:
        if editor._comp.hyperdrive_type == "ADVANCED":
            editor._comp.hyperdrive_type = "BASIC"
            if editor._hd_type_dropdown:
                editor._hd_type_dropdown = replace_dropdown(
                    editor,
                    editor._hd_type_dropdown,
                    HYPERDRIVE_TYPES,
                    "BASIC",
                    "#hd_type_dropdown",
                    group_key="has_hyperdrive",
                )

    # Wing type show/hide & enable/disable
    if editor._wt_dropdown and editor._wt_lbl:
        if editor._hull_size == HullSize.STRIKECRAFT_WING:
            editor._wt_dropdown.enable()
            if editor._selected_component_key == "has_strikecraft_bay":
                editor._wt_lbl.show()
                editor._wt_dropdown.show()
        else:
            editor._wt_dropdown.disable()
            editor._wt_lbl.hide()
            editor._wt_dropdown.hide()

    # Minimum antimatter capacity restriction for current hull size
    min_am_cap = get_min_antimatter_capacity(editor._hull_size)
    if editor._comp.has_antimatter_storage and editor._comp.antimatter_capacity < min_am_cap:
        editor._comp.antimatter_capacity = min_am_cap
        if editor._am_capacity_entry:
            editor._am_capacity_entry.set_text(str(int(min_am_cap)))

    update_component_toggle_labels(editor)
    editor._sync_dynamic_costs()
    editor._update_capacity_label()
