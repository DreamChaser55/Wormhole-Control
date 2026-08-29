"""
layout.py

UI construction and dynamic component detail group builders for the Retrofit Customization Options Wizard.
"""

from __future__ import annotations
import typing
import pygame
import pygame_gui

from constants import (
    DEFAULT_ANTIMATTER_CAPACITY,
    DEFAULT_SENSOR_SHORT_RANGE,
    DEFAULT_JUMP_RANGE,
)
from .catalog import (
    RETROFIT_COMPONENTS,
    TURRET_TYPES,
    TURRET_VARIANTS,
    ABILITY_NAMES,
    HYPERDRIVE_TYPES,
    CLOAKING_TYPES,
    WING_TYPES,
)

if typing.TYPE_CHECKING:
    from .wizard import RetrofitWizardWindow


def make_label(
    rect: pygame.Rect,
    text: str,
    manager: pygame_gui.UIManager,
    container: pygame_gui.core.UIContainer,
    object_id: str = "#sidebar_info_label",
) -> pygame_gui.elements.UILabel:
    return pygame_gui.elements.UILabel(
        relative_rect=rect,
        text=text,
        manager=manager,
        container=container,
        object_id=object_id,
    )


def make_entry(
    rect: pygame.Rect,
    text: str,
    manager: pygame_gui.UIManager,
    container: pygame_gui.core.UIContainer,
    object_id: str = "#turret_entry",
) -> pygame_gui.elements.UITextEntryLine:
    entry = pygame_gui.elements.UITextEntryLine(
        relative_rect=rect,
        manager=manager,
        container=container,
        object_id=object_id,
    )
    entry.set_text(text)
    return entry


def make_dropdown(
    rect: pygame.Rect,
    options: list,
    starting_option: str,
    manager: pygame_gui.UIManager,
    container: pygame_gui.core.UIContainer,
    object_id: str = "#hd_type_dropdown",
) -> pygame_gui.elements.UIDropDownMenu:
    return pygame_gui.elements.UIDropDownMenu(
        options_list=options,
        starting_option=starting_option,
        relative_rect=rect,
        manager=manager,
        container=container,
        object_id=object_id,
    )


def make_button(
    rect: pygame.Rect,
    text: str,
    manager: pygame_gui.UIManager,
    container: pygame_gui.core.UIContainer,
    object_id: str = "#comp_toggle_button",
) -> pygame_gui.elements.UIButton:
    return pygame_gui.elements.UIButton(
        relative_rect=rect,
        text=text,
        manager=manager,
        container=container,
        object_id=object_id,
    )


def build_wizard_layout(wizard: RetrofitWizardWindow) -> None:
    """Builds the main container layout and all component-specific control groups."""
    container = wizard.window.get_container()
    cw, ch = container.get_size()
    mgr = wizard.manager
    sx = wizard.scale_x
    sy = wizard.scale_y

    pad = int(10 * sx)
    row_h = int(24 * sy)
    small_h = int(20 * sy)
    entry_h = int(28 * sy)
    dd_h = int(28 * sy)
    btn_h = int(32 * sy)

    # -----------------------------------------------------------------------
    # Top Header
    # -----------------------------------------------------------------------
    target_name = wizard.target_unit.name if wizard.target_unit else "Target Starship"
    hull_name = wizard.target_unit.hull_size.name.capitalize() if wizard.target_unit else ""
    wizard._title_label = make_label(
        pygame.Rect(pad, pad, cw - pad * 2, int(26 * sy)),
        f"Retrofit Starship: {target_name} ({hull_name} Hull)",
        mgr, container, "#sidebar_title_label"
    )

    # Component Selector Row
    sel_lbl_w = int(160 * sx)
    sel_dd_w = cw - pad * 3 - sel_lbl_w
    top_y = pad + int(30 * sy)

    wizard._comp_select_label = make_label(
        pygame.Rect(pad, top_y, sel_lbl_w, dd_h),
        "Component to Install:",
        mgr, container, "#sidebar_info_label"
    )

    # Available options for target unit
    available_labels = [opt["display_name"] for opt in wizard._available_components]
    start_label = wizard._current_comp_meta["display_name"] if wizard._current_comp_meta else (available_labels[0] if available_labels else "None")

    wizard._comp_dropdown = make_dropdown(
        pygame.Rect(pad + sel_lbl_w + pad, top_y, sel_dd_w, dd_h),
        available_labels,
        start_label,
        mgr, container, "#retrofit_component_dropdown"
    )

    # -----------------------------------------------------------------------
    # Split Body: Left pane = Controls (55% width), Right pane = Summary (45% width)
    # -----------------------------------------------------------------------
    body_y = top_y + dd_h + pad
    footer_h = btn_h + pad * 2
    body_h = ch - body_y - footer_h

    left_w = int((cw - pad * 3) * 0.58)
    right_x = pad + left_w + pad
    right_w = cw - pad * 3 - left_w

    # Left Container (Scrolling Container for controls)
    wizard._controls_container = pygame_gui.elements.UIScrollingContainer(
        relative_rect=pygame.Rect(pad, body_y, left_w, body_h),
        manager=mgr,
        container=container,
        object_id="#retrofit_controls_panel",
    )

    # Right Container (Panel for Summary & Capacity Bar)
    wizard._summary_panel = pygame_gui.elements.UIPanel(
        relative_rect=pygame.Rect(right_x, body_y, right_w, body_h),
        manager=mgr,
        container=container,
        object_id="#retrofit_summary_panel",
    )

    # -----------------------------------------------------------------------
    # Build Left Controls Groups
    # -----------------------------------------------------------------------
    _build_component_detail_groups(wizard, left_w - int(24 * sx), row_h, small_h, entry_h, dd_h, btn_h, pad, sy)

    # -----------------------------------------------------------------------
    # Build Right Summary Panel
    # -----------------------------------------------------------------------
    _build_summary_panel(wizard, right_w, body_h, row_h, small_h, pad, sy)

    # -----------------------------------------------------------------------
    # Bottom Action Buttons
    # -----------------------------------------------------------------------
    btn_y = ch - btn_h - pad
    action_btn_w = int(180 * sx)

    wizard._confirm_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect(cw - pad * 2 - action_btn_w * 2, btn_y, action_btn_w, btn_h),
        text="✔ Order Retrofit",
        manager=mgr,
        container=container,
        object_id="#retrofit_confirm_button",
    )

    wizard._cancel_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect(cw - pad - action_btn_w, btn_y, action_btn_w, btn_h),
        text="Cancel",
        manager=mgr,
        container=container,
        object_id="#retrofit_cancel_button",
    )


def _build_component_detail_groups(
    wizard: RetrofitWizardWindow,
    w: int,
    row_h: int,
    small_h: int,
    entry_h: int,
    dd_h: int,
    btn_h: int,
    pad: int,
    scale_y: float,
) -> None:
    """Instantiates and registers control widgets for each component type."""
    mgr = wizard.manager
    pan = wizard._controls_container
    wizard._details_groups = {comp["comp_key"]: [] for comp in RETROFIT_COMPONENTS}

    y = pad

    # 1. Engines
    lbl_eng = make_label(pygame.Rect(pad, y, w, small_h), "Sublight Engine Speed:", mgr, pan)
    wizard._engine_speed_entry = make_entry(pygame.Rect(pad, y + small_h + 2, w, entry_h), "100", mgr, pan)
    wizard._details_groups["Engines"].extend([lbl_eng, wizard._engine_speed_entry])

    # 2. Antimatter Storage
    lbl_am = make_label(pygame.Rect(pad, y, w, small_h), "Antimatter Capacity:", mgr, pan)
    wizard._am_capacity_entry = make_entry(pygame.Rect(pad, y + small_h + 2, w, entry_h), str(int(DEFAULT_ANTIMATTER_CAPACITY)), mgr, pan)
    wizard._details_groups["AntimatterStorage"].extend([lbl_am, wizard._am_capacity_entry])

    # 3. Hyperdrive
    lbl_hd1 = make_label(pygame.Rect(pad, y, w, small_h), "Hyperdrive Type:", mgr, pan)
    wizard._hd_type_dropdown = make_dropdown(pygame.Rect(pad, y + small_h + 2, w, dd_h), HYPERDRIVE_TYPES, "BASIC", mgr, pan)
    lbl_hd2 = make_label(pygame.Rect(pad, y + small_h + 2 + dd_h + pad, w, small_h), "Jump Range (hexes):", mgr, pan)
    wizard._hd_jump_range_entry = make_entry(pygame.Rect(pad, y + (small_h + 2) * 2 + dd_h + pad, w, entry_h), str(DEFAULT_JUMP_RANGE), mgr, pan)
    wizard._details_groups["Hyperdrive"].extend([lbl_hd1, wizard._hd_type_dropdown, lbl_hd2, wizard._hd_jump_range_entry])

    # 4. Weapons
    y_wep = y
    lbl_wep = make_label(pygame.Rect(pad, y_wep, w, small_h), "Add Turret:", mgr, pan)
    y_wep += small_h + 2
    lbl_ttype = make_label(pygame.Rect(pad, y_wep, w, small_h), "Turret Type:", mgr, pan)
    wizard._turret_type_dd = make_dropdown(pygame.Rect(pad, y_wep + small_h + 2, w, dd_h), TURRET_TYPES, TURRET_TYPES[0], mgr, pan, "#turret_type_dropdown")
    y_wep += small_h + 2 + dd_h + pad
    lbl_variant = make_label(pygame.Rect(pad, y_wep, w, small_h), "Variant:", mgr, pan)
    wizard._turret_variant_dd = make_dropdown(pygame.Rect(pad, y_wep + small_h + 2, w, dd_h), TURRET_VARIANTS, "STANDARD", mgr, pan, "#turret_variant_dropdown")
    y_wep += small_h + 2 + dd_h + pad

    half_w = (w - pad) // 2
    lbl_dmg = make_label(pygame.Rect(pad, y_wep, half_w, small_h), "Dmg:", mgr, pan)
    lbl_rng = make_label(pygame.Rect(pad + half_w + pad, y_wep, half_w, small_h), "Range:", mgr, pan)
    y_wep += small_h + 2
    wizard._turret_dmg_entry = make_entry(pygame.Rect(pad, y_wep, half_w, entry_h), "10", mgr, pan)
    wizard._turret_range_entry = make_entry(pygame.Rect(pad + half_w + pad, y_wep, half_w, entry_h), "300", mgr, pan)
    y_wep += entry_h + pad

    lbl_cd = make_label(pygame.Rect(pad, y_wep, half_w, small_h), "Cooldown (turns):", mgr, pan)
    y_wep += small_h + 2
    wizard._turret_cd_entry = make_entry(pygame.Rect(pad, y_wep, half_w, entry_h), "2", mgr, pan)
    wizard._add_turret_button = make_button(pygame.Rect(pad + half_w + pad, y_wep, half_w, btn_h), "+ Add Turret", mgr, pan, "#editor_add_turret_button")
    y_wep += max(entry_h, btn_h) + pad

    wizard._turret_list_lx, wizard._turret_list_lw, wizard._turret_list_y_start = pad, w, y_wep
    wizard._details_groups["Weapons"].extend([
        lbl_wep, lbl_ttype, wizard._turret_type_dd, lbl_variant, wizard._turret_variant_dd,
        lbl_dmg, lbl_rng, wizard._turret_dmg_entry, wizard._turret_range_entry,
        lbl_cd, wizard._turret_cd_entry, wizard._add_turret_button,
    ])

    # 5. Defenses
    lbl_arm = make_label(pygame.Rect(pad, y, w, small_h), "Armor HP:", mgr, pan)
    wizard._armor_entry = make_entry(pygame.Rect(pad, y + small_h + 2, w, entry_h), "50", mgr, pan)
    y_d = y + small_h + 2 + entry_h + pad
    lbl_sh = make_label(pygame.Rect(pad, y_d, w, small_h), "Shield HP:", mgr, pan)
    wizard._shields_entry = make_entry(pygame.Rect(pad, y_d + small_h + 2, w, entry_h), "50", mgr, pan)
    y_d += small_h + 2 + entry_h + pad
    lbl_pd = make_label(pygame.Rect(pad, y_d, w, small_h), "Point Defense Rating:", mgr, pan)
    wizard._pd_entry = make_entry(pygame.Rect(pad, y_d + small_h + 2, w, entry_h), "0", mgr, pan)
    wizard._details_groups["Defenses"].extend([lbl_arm, wizard._armor_entry, lbl_sh, wizard._shields_entry, lbl_pd, wizard._pd_entry])

    # 6. Sensors
    lbl_sr = make_label(pygame.Rect(pad, y, w, small_h), "Short-Range Radius (logical):", mgr, pan)
    wizard._sensor_short_range_entry = make_entry(pygame.Rect(pad, y + small_h + 2, w, entry_h), str(int(DEFAULT_SENSOR_SHORT_RANGE)), mgr, pan)
    y_s = y + small_h + 2 + entry_h + pad
    lbl_lr = make_label(pygame.Rect(pad, y_s, w, small_h), "Long-Range (hexes):", mgr, pan)
    wizard._sensor_long_range_entry = make_entry(pygame.Rect(pad, y_s + small_h + 2, w, entry_h), "1", mgr, pan)
    wizard._details_groups["Sensors"].extend([lbl_sr, wizard._sensor_short_range_entry, lbl_lr, wizard._sensor_long_range_entry])

    # 7. Strikecraft Bay
    lbl_wt = make_label(pygame.Rect(pad, y, w, small_h), "Wing Type:", mgr, pan)
    wizard._wt_dropdown = make_dropdown(pygame.Rect(pad, y + small_h + 2, w, dd_h), WING_TYPES, "FIGHTER", mgr, pan)
    y_sc = y + small_h + dd_h + pad
    lbl_scs = make_label(pygame.Rect(pad, y_sc, w, small_h), "Bay Slots:", mgr, pan)
    wizard._strikecraft_bay_slots_entry = make_entry(pygame.Rect(pad, y_sc + small_h + 2, w, entry_h), "2", mgr, pan)
    wizard._details_groups["StrikecraftBayComponent"].extend([lbl_wt, wizard._wt_dropdown, lbl_scs, wizard._strikecraft_bay_slots_entry])

    # 8. Hangar Bay
    lbl_hs = make_label(pygame.Rect(pad, y, w, small_h), "Hangar Slots:", mgr, pan)
    wizard._hangar_slots_entry = make_entry(pygame.Rect(pad, y + small_h + 2, w, entry_h), "2", mgr, pan)
    wizard._details_groups["HangarComponent"].extend([lbl_hs, wizard._hangar_slots_entry])

    # 9. Repair Module
    lbl_rr = make_label(pygame.Rect(pad, y, w, small_h), "Repair Rate (HP/turn):", mgr, pan)
    wizard._repair_rate_entry = make_entry(pygame.Rect(pad, y + small_h + 2, w, entry_h), "10", mgr, pan)
    y_r = y + small_h + entry_h + pad
    lbl_rrange = make_label(pygame.Rect(pad, y_r, w, small_h), "Repair Range (logical):", mgr, pan)
    wizard._repair_range_entry = make_entry(pygame.Rect(pad, y_r + small_h + 2, w, entry_h), "200", mgr, pan)
    wizard._details_groups["RepairComponent"].extend([lbl_rr, wizard._repair_rate_entry, lbl_rrange, wizard._repair_range_entry])

    # 10. Mining Module
    lbl_mr = make_label(pygame.Rect(pad, y, w, small_h), "Mining Rate (units/turn):", mgr, pan)
    wizard._mining_rate_entry = make_entry(pygame.Rect(pad, y + small_h + 2, w, entry_h), "10", mgr, pan)
    y_m = y + small_h + entry_h + pad
    lbl_mrange = make_label(pygame.Rect(pad, y_m, w, small_h), "Mining Range (logical):", mgr, pan)
    wizard._mining_range_entry = make_entry(pygame.Rect(pad, y_m + small_h + 2, w, entry_h), "200", mgr, pan)
    y_m += small_h + entry_h + pad
    lbl_mcargo = make_label(pygame.Rect(pad, y_m, w, small_h), "Max Cargo Storage:", mgr, pan)
    wizard._mining_max_cargo_entry = make_entry(pygame.Rect(pad, y_m + small_h + 2, w, entry_h), "100", mgr, pan)
    wizard._details_groups["MiningComponent"].extend([lbl_mr, wizard._mining_rate_entry, lbl_mrange, wizard._mining_range_entry, lbl_mcargo, wizard._mining_max_cargo_entry])

    # 11. Inhibitor Field
    lbl_inhr = make_label(pygame.Rect(pad, y, w, small_h), "Inhibitor Field Radius (logical):", mgr, pan)
    wizard._inhibitor_radius_entry = make_entry(pygame.Rect(pad, y + small_h + 2, w, entry_h), "100", mgr, pan)
    wizard._details_groups["HyperspaceInhibitionFieldEmitter"].extend([lbl_inhr, wizard._inhibitor_radius_entry])

    # 12. Marines
    lbl_mar = make_label(pygame.Rect(pad, y, w, small_h), "Marines Count:", mgr, pan)
    wizard._marines_count_entry = make_entry(pygame.Rect(pad, y + small_h + 2, w, entry_h), "10", mgr, pan)
    wizard._details_groups["MarinesComponent"].extend([lbl_mar, wizard._marines_count_entry])

    # 13. Cloaking Device
    lbl_clk_t = make_label(pygame.Rect(pad, y, w, small_h), "Cloaking Type:", mgr, pan)
    wizard._cloaking_type_dropdown = make_dropdown(pygame.Rect(pad, y + small_h + 2, w, dd_h), CLOAKING_TYPES, "BASIC", mgr, pan)
    y_clk = y + small_h + dd_h + pad
    wizard._lbl_clk_r = make_label(pygame.Rect(pad, y_clk, w, small_h), "Area Radius (Advanced):", mgr, pan)
    wizard._cloaking_radius_entry = make_entry(pygame.Rect(pad, y_clk + small_h + 2, w, entry_h), "500", mgr, pan)
    wizard._details_groups["CloakingDevice"].extend([lbl_clk_t, wizard._cloaking_type_dropdown, wizard._lbl_clk_r, wizard._cloaking_radius_entry])

    # 14. Abilities
    abil_hdr = make_label(pygame.Rect(pad, y, w, small_h), "Select Active Abilities:", mgr, pan)
    ab_widgets = [abil_hdr]
    y_ab = y + small_h + 4
    for aname in ABILITY_NAMES:
        abtn = make_button(pygame.Rect(pad, y_ab, w, small_h), f"[ ] {aname}", mgr, pan, "#ability_toggle_button")
        wizard._ability_buttons[aname] = abtn
        ab_widgets.append(abtn)
        y_ab += small_h + 3
    wizard._details_groups["AbilityComponent"].extend(ab_widgets)

    # 15. Intelligence
    lbl_intel_cap = make_label(pygame.Rect(pad, y, w, small_h), "Agent Capacity:", mgr, pan)
    wizard._intel_agents_entry = make_entry(pygame.Rect(pad, y + small_h + 2, w, entry_h), "1", mgr, pan)
    y_intel = y + small_h + 2 + entry_h + pad
    wizard._intel_ci_button = make_button(pygame.Rect(pad, y_intel, w, btn_h), "[ ] Counter-Intelligence", mgr, pan, "#ability_toggle_button")
    wizard._details_groups["IntelligenceComponent"].extend([lbl_intel_cap, wizard._intel_agents_entry, wizard._intel_ci_button])

    # 16. Fixed & Informational Components
    for comp in RETROFIT_COMPONENTS:
        k = comp["comp_key"]
        if k in wizard._details_groups and not wizard._details_groups[k]:
            desc_text = f"<b>{comp['display_name']}</b><br><br>{comp.get('description', '')}"
            box = pygame_gui.elements.UITextBox(
                html_text=desc_text,
                relative_rect=pygame.Rect(pad, pad, w, int(160 * scale_y)),
                manager=mgr,
                container=pan,
                object_id="#editor_summary_box",
            )
            wizard._details_groups[k].append(box)


def _build_summary_panel(
    wizard: RetrofitWizardWindow,
    w: int,
    h: int,
    row_h: int,
    small_h: int,
    pad: int,
    scale_y: float,
) -> None:
    """Builds the right-hand impact & cost summary panel."""
    mgr = wizard.manager
    pan = wizard._summary_panel

    y = pad
    make_label(pygame.Rect(pad, y, w - pad * 2, row_h), "Retrofit Summary", mgr, pan, "#editor_section_label")
    y += row_h + int(6 * scale_y)

    wizard._hull_impact_label = make_label(pygame.Rect(pad, y, w - pad * 2, small_h), "Hull Usage: 0.0 / 0.0 HP", mgr, pan)
    y += small_h + int(4 * scale_y)

    wizard._added_cost_label = make_label(pygame.Rect(pad, y, w - pad * 2, small_h), "Component Hull: +0.0 HP", mgr, pan)
    y += small_h + int(4 * scale_y)

    wizard._credit_cost_label = make_label(pygame.Rect(pad, y, w - pad * 2, small_h), "Credit Cost: 0 c", mgr, pan)
    y += small_h + int(4 * scale_y)

    wizard._player_credits_label = make_label(pygame.Rect(pad, y, w - pad * 2, small_h), "Available Credits: 0 c", mgr, pan)
    y += small_h + int(4 * scale_y)

    wizard._build_time_label = make_label(pygame.Rect(pad, y, w - pad * 2, small_h), "Est. Time to Build: 1 Turn", mgr, pan)
    y += small_h + int(4 * scale_y)

    wizard._upkeep_label = make_label(pygame.Rect(pad, y, w - pad * 2, small_h), "Upkeep Impact: +0.00 cr/turn", mgr, pan)
    y += small_h + int(8 * scale_y)

    # Status / Warning Box
    status_h = int(70 * scale_y)
    wizard._status_box = pygame_gui.elements.UITextBox(
        html_text="Ready for installation.",
        relative_rect=pygame.Rect(pad, y, w - pad * 2, status_h),
        manager=mgr,
        container=pan,
        object_id="#editor_summary_box",
    )


def rebuild_wizard_turret_list(wizard: RetrofitWizardWindow) -> None:
    """Rebuilds the active turret list display widgets in the weapons configuration panel."""
    for lbl in wizard._turret_labels:
        if lbl.alive():
            lbl.kill()
    for btn in wizard._turret_remove_buttons:
        if btn.alive():
            btn.kill()
    wizard._turret_labels.clear()
    wizard._turret_remove_buttons.clear()

    if wizard._current_comp_key != "Weapons":
        return

    scale_y = wizard.scale_y
    small_h = int(22 * scale_y)
    lx = wizard._turret_list_lx
    lw = wizard._turret_list_lw
    ly = wizard._turret_list_y_start

    turrets = wizard._turrets
    for i, tc in enumerate(turrets):
        disp_range = tc["range"] * 3.0 if tc.get("variant") == "LONG_RANGE" else tc["range"]
        disp_cooldown = tc["cooldown"] * 3 if tc.get("variant") == "LONG_RANGE" else tc["cooldown"]
        text = f"{tc['type']} ({tc.get('variant', 'STANDARD').lower()}) dmg:{tc['damage']:.0f} rng:{disp_range:.0f} cd:{disp_cooldown}"

        lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(lx, ly, int(lw * 0.80), small_h),
            text=text,
            manager=wizard.manager,
            container=wizard._controls_container,
            object_id="#turret_item_label",
        )
        wizard._turret_labels.append(lbl)

        rbtn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(lx + int(lw * 0.82), ly, int(lw * 0.18), small_h),
            text="✕",
            manager=wizard.manager,
            container=wizard._controls_container,
            object_id="#turret_remove_button",
        )
        wizard._turret_remove_buttons.append(rbtn)
        ly += small_h + 3
