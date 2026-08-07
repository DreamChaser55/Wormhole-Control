"""
layout_details.py

Column 3 component detail widgets construction (13 per-component detail groups).
Uses widget_factory helper functions to streamline widget creation.
"""

import pygame
import pygame_gui
from .catalog import (
    COMPONENT_ROWS,
    HYPERDRIVE_TYPES,
    TURRET_TYPES,
    TURRET_VARIANTS,
    ABILITY_NAMES,
    COMPONENT_DESCRIPTIONS,
)
from .widget_factory import make_label, make_entry, make_dropdown, make_button


def build_col3_details(
    editor, c3x: int, c3y: int, c3w: int, row_h: int, small_h: int, dd_h: int, entry_h: int, btn_h: int, pad: int, scale_y: float
) -> int:
    """Builds Column 3 dynamic component detail controls (sub-option fields, turret list, ability toggles)."""
    mgr = editor.manager
    pan = editor._panel

    editor._details_hdr = make_label(pygame.Rect(c3x, c3y, c3w, row_h), "Component Details", mgr, pan, "#editor_section_label")
    editor._elements.append(editor._details_hdr)
    c3y_base = c3y + row_h + pad
    y = c3y_base
    editor._details_groups = {row["key"]: [] for row in COMPONENT_ROWS}

    # --- 1. Engines ---
    lbl_eng = make_label(pygame.Rect(c3x, y, c3w, small_h), "Engine Speed:", mgr, pan)
    editor._engine_speed_entry = make_entry(pygame.Rect(c3x, y + small_h + 2, c3w, entry_h), str(int(editor._comp.engine_speed)), mgr, pan)
    editor._details_groups["has_engine"].extend([lbl_eng, editor._engine_speed_entry])

    # --- 2. Antimatter Storage ---
    lbl_am = make_label(pygame.Rect(c3x, y, c3w, small_h), "Antimatter Capacity:", mgr, pan)
    editor._am_capacity_entry = make_entry(pygame.Rect(c3x, y + small_h + 2, c3w, entry_h), str(int(editor._comp.antimatter_capacity)), mgr, pan)
    editor._details_groups["has_antimatter_storage"].extend([lbl_am, editor._am_capacity_entry])

    # --- 3. Hyperdrive ---
    lbl_hd1 = make_label(pygame.Rect(c3x, y, c3w, small_h), "Hyperdrive Type:", mgr, pan)
    editor._hd_type_dropdown = make_dropdown(pygame.Rect(c3x, y + small_h + 2, c3w, dd_h), HYPERDRIVE_TYPES, editor._comp.hyperdrive_type, mgr, pan)
    lbl_hd2 = make_label(pygame.Rect(c3x, y + small_h + 2 + dd_h + pad, c3w, small_h), "Jump Range (hexes):", mgr, pan)
    editor._hd_jump_range_entry = make_entry(pygame.Rect(c3x, y + (small_h + 2) * 2 + dd_h + pad, c3w, entry_h), str(editor._comp.hyperdrive_jump_range), mgr, pan)
    editor._details_groups["has_hyperdrive"].extend([lbl_hd1, editor._hd_type_dropdown, lbl_hd2, editor._hd_jump_range_entry])

    # --- 4. Weapon Bays ---
    lbl_wep = make_label(pygame.Rect(c3x, y, c3w, small_h), "Add Turret:", mgr, pan)
    y += small_h + 2
    lbl_ttype = make_label(pygame.Rect(c3x, y, c3w, small_h), "Turret Type:", mgr, pan)
    editor._turret_type_dd = make_dropdown(pygame.Rect(c3x, y + small_h + 2, c3w, dd_h), TURRET_TYPES, TURRET_TYPES[0], mgr, pan, "#turret_type_dropdown")
    y += small_h + 2 + dd_h + pad
    lbl_variant = make_label(pygame.Rect(c3x, y, c3w, small_h), "Variant:", mgr, pan)
    editor._turret_variant_dd = make_dropdown(pygame.Rect(c3x, y + small_h + 2, c3w, dd_h), TURRET_VARIANTS, "STANDARD", mgr, pan, "#turret_variant_dropdown")
    y += small_h + 2 + dd_h + pad
    half_w = (c3w - pad) // 2
    lbl_dmg = make_label(pygame.Rect(c3x, y, half_w, small_h), "Dmg:", mgr, pan)
    lbl_rng = make_label(pygame.Rect(c3x + half_w + pad, y, half_w, small_h), "Range:", mgr, pan)
    y += small_h + 2
    editor._turret_dmg_entry = make_entry(pygame.Rect(c3x, y, half_w, entry_h), "10", mgr, pan)
    editor._turret_range_entry = make_entry(pygame.Rect(c3x + half_w + pad, y, half_w, entry_h), "300", mgr, pan)
    y += entry_h + pad
    lbl_cd = make_label(pygame.Rect(c3x, y, half_w, small_h), "Cooldown (turns):", mgr, pan)
    y += small_h + 2
    editor._turret_cd_entry = make_entry(pygame.Rect(c3x, y, half_w, entry_h), "2", mgr, pan)
    editor._add_turret_button = make_button(pygame.Rect(c3x + half_w + pad, y, half_w, btn_h), "+ Add Turret", mgr, pan, "#editor_add_turret_button")
    y += max(entry_h, btn_h) + pad
    editor._turret_list_lx, editor._turret_list_lw, editor._turret_list_y_start = c3x, c3w, y
    editor._details_groups["has_weapon_bays"].extend([
        lbl_wep, lbl_ttype, editor._turret_type_dd, lbl_variant, editor._turret_variant_dd,
        lbl_dmg, lbl_rng, editor._turret_dmg_entry, editor._turret_range_entry,
        lbl_cd, editor._turret_cd_entry, editor._add_turret_button,
    ])

    # --- 5. Defenses ---
    y_def = c3y_base
    lbl_arm = make_label(pygame.Rect(c3x, y_def, c3w, small_h), "Armor HP:", mgr, pan)
    editor._armor_entry = make_entry(pygame.Rect(c3x, y_def + small_h + 2, c3w, entry_h), str(editor._comp.armor), mgr, pan)
    y_def += small_h + 2 + entry_h + pad
    lbl_sh = make_label(pygame.Rect(c3x, y_def, c3w, small_h), "Shield HP:", mgr, pan)
    editor._shields_entry = make_entry(pygame.Rect(c3x, y_def + small_h + 2, c3w, entry_h), str(editor._comp.shields), mgr, pan)
    y_def += small_h + 2 + entry_h + pad
    lbl_pd = make_label(pygame.Rect(c3x, y_def, c3w, small_h), "Point Defense Rating:", mgr, pan)
    editor._pd_entry = make_entry(pygame.Rect(c3x, y_def + small_h + 2, c3w, entry_h), str(editor._comp.point_defense), mgr, pan)
    editor._details_groups["has_defenses"].extend([lbl_arm, editor._armor_entry, lbl_sh, editor._shields_entry, lbl_pd, editor._pd_entry])

    # --- 6. Sensors ---
    y_sen = c3y_base
    lbl_sr = make_label(pygame.Rect(c3x, y_sen, c3w, small_h), "Short-Range Radius (px):", mgr, pan)
    editor._sensor_short_range_entry = make_entry(pygame.Rect(c3x, y_sen + small_h + 2, c3w, entry_h), str(int(editor._comp.sensor_short_range)), mgr, pan)
    y_sen += small_h + 2 + entry_h + pad
    lbl_lr = make_label(pygame.Rect(c3x, y_sen, c3w, small_h), "Long-Range (hexes):", mgr, pan)
    editor._sensor_long_range_entry = make_entry(pygame.Rect(c3x, y_sen + small_h + 2, c3w, entry_h), str(int(editor._comp.sensor_long_range_hexes)), mgr, pan)
    editor._details_groups["has_sensors"].extend([lbl_sr, editor._sensor_short_range_entry, lbl_lr, editor._sensor_long_range_entry])

    # --- 7. Strikecraft Bay ---
    y_sc = c3y_base
    editor._wt_lbl = make_label(pygame.Rect(c3x, y_sc, c3w, small_h), "Wing Type:", mgr, pan)
    editor._wt_dropdown = make_dropdown(
        pygame.Rect(c3x, y_sc + small_h + 2, c3w, dd_h),
        ["FIGHTER", "BOMBER"],
        editor._comp.wing_type if hasattr(editor._comp, "wing_type") else "FIGHTER",
        mgr, pan, "#hd_type_dropdown",
    )
    y_sc += small_h + dd_h + pad
    lbl_scs = make_label(pygame.Rect(c3x, y_sc, c3w, small_h), "Bay Slots:", mgr, pan)
    editor._strikecraft_bay_slots_entry = make_entry(pygame.Rect(c3x, y_sc + small_h + 2, c3w, entry_h), str(int(editor._comp.strikecraft_bay_slots)), mgr, pan)
    editor._details_groups["has_strikecraft_bay"].extend([
        editor._wt_lbl, editor._wt_dropdown,
        lbl_scs, editor._strikecraft_bay_slots_entry,
    ])

    # --- 8. Repair Component ---
    y_rep = c3y_base
    lbl_rr = make_label(pygame.Rect(c3x, y_rep, c3w, small_h), "Repair Rate:", mgr, pan)
    editor._repair_rate_entry = make_entry(pygame.Rect(c3x, y_rep + small_h + 2, c3w, entry_h), str(int(editor._comp.repair_rate)), mgr, pan)

    y_rep += small_h + entry_h + pad
    lbl_rrange = make_label(pygame.Rect(c3x, y_rep, c3w, small_h), "Repair Range:", mgr, pan)
    editor._repair_range_entry = make_entry(pygame.Rect(c3x, y_rep + small_h + 2, c3w, entry_h), str(int(editor._comp.repair_range)), mgr, pan)

    editor._details_groups["has_repair_component"].extend([
        lbl_rr, editor._repair_rate_entry,
        lbl_rrange, editor._repair_range_entry,
    ])

    # --- 9. Mining Component ---
    y_min = c3y_base
    lbl_mr = make_label(pygame.Rect(c3x, y_min, c3w, small_h), "Mining Rate:", mgr, pan)
    editor._mining_rate_entry = make_entry(pygame.Rect(c3x, y_min + small_h + 2, c3w, entry_h), str(int(editor._comp.mining_rate)), mgr, pan)

    y_min += small_h + entry_h + pad
    lbl_mrange = make_label(pygame.Rect(c3x, y_min, c3w, small_h), "Mining Range:", mgr, pan)
    editor._mining_range_entry = make_entry(pygame.Rect(c3x, y_min + small_h + 2, c3w, entry_h), str(int(editor._comp.mining_range)), mgr, pan)

    y_min += small_h + entry_h + pad
    lbl_mcargo = make_label(pygame.Rect(c3x, y_min, c3w, small_h), "Max Cargo:", mgr, pan)
    editor._mining_max_cargo_entry = make_entry(pygame.Rect(c3x, y_min + small_h + 2, c3w, entry_h), str(int(editor._comp.max_mining_cargo)), mgr, pan)
    editor._details_groups["has_mining_component"].extend([
        lbl_mr, editor._mining_rate_entry,
        lbl_mrange, editor._mining_range_entry,
        lbl_mcargo, editor._mining_max_cargo_entry,
    ])

    # --- 10. Hangar ---
    y_h = c3y_base
    lbl_hs = make_label(pygame.Rect(c3x, y_h, c3w, small_h), "Hangar Slots:", mgr, pan)
    editor._hangar_slots_entry = make_entry(pygame.Rect(c3x, y_h + small_h + 2, c3w, entry_h), str(int(editor._comp.hangar_slots)), mgr, pan)
    editor._details_groups["has_hangar"].extend([lbl_hs, editor._hangar_slots_entry])

    # --- 11. Inhibitor Field ---
    y_inh = c3y_base
    lbl_inhr = make_label(pygame.Rect(c3x, y_inh, c3w, small_h), "Inhibitor Radius:", mgr, pan)
    editor._inhibitor_radius_entry = make_entry(pygame.Rect(c3x, y_inh + small_h + 2, c3w, entry_h), str(int(editor._comp.inhibitor_radius)), mgr, pan)
    editor._details_groups["has_inhibitor"].extend([lbl_inhr, editor._inhibitor_radius_entry])

    # --- Marines ---
    y_mar = c3y_base
    lbl_mar = make_label(pygame.Rect(c3x, y_mar, c3w, small_h), "Marines Count:", mgr, pan)
    editor._marines_count_entry = make_entry(pygame.Rect(c3x, y_mar + small_h + 2, c3w, entry_h), str(int(editor._comp.marines_count)), mgr, pan)
    editor._details_groups["has_marines_component"].extend([lbl_mar, editor._marines_count_entry])

    # --- 12. Abilities ---
    y_ab = c3y_base
    abil_hdr = make_label(pygame.Rect(c3x, y_ab, c3w, small_h), "Select Active Abilities:", mgr, pan)
    ab_widgets = [abil_hdr]
    y_ab += small_h + 4

    for aname in ABILITY_NAMES:
        abtn = make_button(pygame.Rect(c3x, y_ab, c3w, small_h), f"[ ] {aname}", mgr, pan, "#ability_toggle_button")
        editor._ability_buttons[aname] = abtn
        ab_widgets.append(abtn)
        y_ab += small_h + 3
    editor._details_groups["has_ability_component"].extend(ab_widgets)

    # --- 13. Fixed & Info-only Components ---
    for comp_key, desc in COMPONENT_DESCRIPTIONS.items():
        if comp_key in editor._details_groups:
            box = pygame_gui.elements.UITextBox(
                html_text=desc,
                relative_rect=pygame.Rect(c3x, c3y_base, c3w, int(150 * scale_y)),
                manager=mgr,
                container=pan,
                object_id="#editor_summary_box",
            )
            editor._details_groups[comp_key].append(box)

    # Append all dynamic elements to editor._elements
    for group in editor._details_groups.values():
        for elem in group:
            if elem not in editor._elements:
                editor._elements.append(elem)

    return c3y_base
