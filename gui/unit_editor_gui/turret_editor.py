"""
turret_editor.py

Turret list management, adding turrets, and rebuilding turret list widgets.
"""

import pygame
import pygame_gui
from custom_unit_templates import TurretConfig


def hide_turret_list(editor) -> None:
    """Hide active turret labels and remove buttons."""
    for lbl in editor._turret_labels:
        if lbl.alive():
            lbl.hide()
    for btn in editor._turret_remove_buttons:
        if btn.alive():
            btn.hide()


def rebuild_turret_list(editor) -> None:
    """Rebuild the turret list display labels and remove buttons."""
    # Kill old labels/buttons
    for lbl in editor._turret_labels:
        if lbl.alive():
            lbl.kill()
    for btn in editor._turret_remove_buttons:
        if btn.alive():
            btn.kill()
    editor._turret_labels.clear()
    editor._turret_remove_buttons.clear()

    if not editor._panel or editor._selected_component_key != "has_weapon_bays":
        return

    scale_y = editor.screen_res.y / 720.0
    small_h = int(22 * scale_y)
    lx = editor._turret_list_lx
    lw = editor._turret_list_lw
    ly = editor._turret_list_y_start

    for i, tc in enumerate(editor._turrets):
        disp_range = tc.range * 3.0 if tc.variant == "LONG_RANGE" else tc.range
        disp_cooldown = tc.cooldown * 3 if tc.variant == "LONG_RANGE" else tc.cooldown
        text = f"{tc.turret_type} ({tc.variant.lower()})  dmg:{tc.damage:.0f}  rng:{disp_range:.0f}  cd:{disp_cooldown}"
        lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(lx, ly, int(lw * 0.80), small_h),
            text=text,
            manager=editor.manager,
            container=editor._panel,
            object_id="#turret_item_label",
        )
        editor._turret_labels.append(lbl)

        rbtn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(lx + int(lw * 0.82), ly, int(lw * 0.18), small_h),
            text="✕",
            manager=editor.manager,
            container=editor._panel,
            object_id="#turret_remove_button",
        )
        editor._turret_remove_buttons.append(rbtn)
        ly += small_h + 3


def do_add_turret(editor) -> None:
    """Adds a new turret to the design configuration based on current input field values."""
    if editor._turret_type_dd:
        raw = editor._turret_type_dd.selected_option
        ttype = raw[0] if isinstance(raw, tuple) else str(raw)
    else:
        ttype = "MASS_DRIVER"
    try:
        dmg = float(editor._turret_dmg_entry.get_text()) if editor._turret_dmg_entry else 10.0
    except ValueError:
        dmg = 10.0
    try:
        rng = float(editor._turret_range_entry.get_text()) if editor._turret_range_entry else 300.0
    except ValueError:
        rng = 300.0
    try:
        cd = int(editor._turret_cd_entry.get_text()) if editor._turret_cd_entry else 2
    except ValueError:
        cd = 2

    if editor._turret_variant_dd:
        raw_variant = editor._turret_variant_dd.selected_option
        variant = raw_variant[0] if isinstance(raw_variant, tuple) else str(raw_variant)
    else:
        variant = "STANDARD"

    editor._turrets.append(TurretConfig(turret_type=ttype, damage=dmg, range=rng, cooldown=cd, variant=variant))
    editor._comp.turrets = editor._turrets
    rebuild_turret_list(editor)
    editor._sync_dynamic_costs()
    editor._update_summary()
