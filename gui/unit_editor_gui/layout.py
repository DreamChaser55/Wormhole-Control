"""
layout.py

Layout orchestrator and column builder functions (Col 1 config, Col 2 components, Col 4 summary).
"""

import pygame
import pygame_gui
from constants import TEXT_SCALE
from .catalog import COMPONENT_ROWS, HULL_SIZE_NAMES
from .layout_details import build_col3_details


def build_col1_config(
    editor, c1x: int, c1y: int, c1w: int, row_h: int, dd_h: int, entry_h: int, btn_h: int, pad: int, scale_y: float
) -> int:
    """Builds Column 1 configuration UI controls (Hull selection, design keys, file management)."""
    # Hull Size dropdown
    hull_label = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(c1x, c1y, c1w, row_h),
        text="Hull Size",
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_section_label",
    )
    editor._elements.append(hull_label)
    c1y += row_h + pad

    editor._hull_dropdown = pygame_gui.elements.UIDropDownMenu(
        options_list=HULL_SIZE_NAMES,
        starting_option=editor._hull_size.name,
        relative_rect=pygame.Rect(c1x, c1y, c1w, dd_h),
        manager=editor.manager,
        container=editor._panel,
        object_id="#hull_size_dropdown",
    )
    editor._elements.append(editor._hull_dropdown)
    c1y += dd_h + pad

    # Capacity bar label
    editor._capacity_label = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(c1x, c1y, c1w, row_h),
        text=editor._capacity_text(),
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_capacity_label",
    )
    editor._elements.append(editor._capacity_label)
    c1y += row_h + 2

    # Capacity bar visual
    bar_h = int(10 * scale_y)
    editor._cap_bar_rect = pygame.Rect(editor._panel_rect.x + c1x, editor._panel_rect.y + c1y, c1w, bar_h)
    c1y += bar_h + pad

    # Display Name
    display_lbl = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(c1x, c1y, c1w, row_h),
        text="Display Name (unique):",
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_section_label",
    )
    editor._elements.append(display_lbl)
    c1y += row_h + 2

    editor._display_entry = pygame_gui.elements.UITextEntryLine(
        relative_rect=pygame.Rect(c1x, c1y, c1w, entry_h),
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_display_entry",
    )
    editor._elements.append(editor._display_entry)
    c1y += entry_h + pad

    # Load Design
    load_lbl = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(c1x, c1y, c1w, row_h),
        text="Load / Edit Existing Design:",
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_section_label",
    )
    editor._elements.append(load_lbl)
    c1y += row_h + 2

    existing = editor.template_manager.list_design_names()
    editor._load_dd = pygame_gui.elements.UIDropDownMenu(
        options_list=["— select —"] + existing,
        starting_option="— select —",
        relative_rect=pygame.Rect(c1x, c1y, c1w, dd_h),
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_load_dropdown",
    )
    editor._elements.append(editor._load_dd)
    c1y += dd_h + pad

    # Save Button
    editor._save_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect(c1x, c1y, c1w, btn_h),
        text="✔  Save Design",
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_save_button",
    )
    editor._elements.append(editor._save_button)
    c1y += btn_h + pad

    # Save as New Button
    editor._save_as_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect(c1x, c1y, c1w, btn_h),
        text="➕  Save as New",
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_save_as_button",
    )
    editor._elements.append(editor._save_as_button)
    c1y += btn_h + pad

    # Delete Button
    editor._delete_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect(c1x, c1y, c1w, btn_h),
        text="✖  Delete Design",
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_delete_button",
    )
    editor._elements.append(editor._delete_button)
    c1y += btn_h + pad

    # Status Label
    editor._status_label = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(c1x, c1y, c1w, row_h),
        text="",
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_status_label",
    )
    editor._elements.append(editor._status_label)
    return c1y


def build_col2_components(
    editor, c2x: int, c2y: int, c2w: int, row_h: int, small_h: int, pad: int
) -> int:
    """Builds Column 2 component selection UI controls (Toggles, selection arrows, cost labels)."""
    comp_heading = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(c2x, c2y, c2w, row_h),
        text="Components (hull cost)",
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_section_label",
    )
    editor._elements.append(comp_heading)
    c2y += row_h + 2

    cost_w = max(40, int(40 * TEXT_SCALE))
    select_w = max(38, int(38 * TEXT_SCALE))
    gap = max(2, int(2 * TEXT_SCALE))
    btn_w = c2w - cost_w - select_w - (gap * 2)

    avail_h = editor._panel_rect.h - c2y - pad
    editor._comp_scroll_container = pygame_gui.elements.UIScrollingContainer(
        relative_rect=pygame.Rect(c2x, c2y, c2w, avail_h),
        manager=editor.manager,
        container=editor._panel,
        object_id="#comp_scrolling_container",
    )
    editor._elements.append(editor._comp_scroll_container)

    scroll_bar_w = 18
    inner_w = c2w - scroll_bar_w
    cost_w = max(40, int(40 * TEXT_SCALE))
    select_w = max(38, int(38 * TEXT_SCALE))
    gap = max(2, int(2 * TEXT_SCALE))
    btn_w = inner_w - cost_w - select_w - (gap * 2)

    row_spacing = small_h + 3
    for idx, row in enumerate(COMPONENT_ROWS):
        cx = 0
        cy = idx * row_spacing

        key, label, cost_display = row["key"], row["label"], ("~" if row["is_dynamic"] else str(row["default_cost"]))

        btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(cx, cy, btn_w, small_h),
            text=f"[ ] {label}",
            manager=editor.manager,
            container=editor._comp_scroll_container,
            object_id="#comp_toggle_button",
        )
        editor._comp_toggles[key] = btn
        editor._elements.append(btn)

        cx += btn_w + gap
        cost_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(cx, cy, cost_w, small_h),
            text=cost_display,
            manager=editor.manager,
            container=editor._comp_scroll_container,
            object_id="#comp_cost_label",
        )
        editor._comp_cost_labels[key] = cost_lbl
        editor._elements.append(cost_lbl)

        cx += cost_w + gap
        sel_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(cx, cy, select_w, small_h),
            text="▶▶▶" if key == "has_engine" else ">>>",
            manager=editor.manager,
            container=editor._comp_scroll_container,
            object_id="#comp_select_button",
        )
        editor._comp_select_btns[key] = sel_btn
        editor._elements.append(sel_btn)

    total_content_h = len(COMPONENT_ROWS) * row_spacing
    editor._comp_scroll_container.set_scrollable_area_dimensions((inner_w, total_content_h))

    c2y += avail_h + pad
    return c2y


def build_col4_summary(
    editor, c4x: int, c4y: int, c4w: int, row_h: int, pad: int, pr: pygame.Rect
) -> None:
    """Builds Column 4 design summary text box and layout container."""
    summary_hdr = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(c4x, c4y, c4w, row_h),
        text="Design Summary",
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_section_label",
    )
    editor._elements.append(summary_hdr)
    c4y += row_h + 2

    summary_h = pr.h - c4y - pad * 2
    editor._summary_box = pygame_gui.elements.UITextBox(
        html_text="",
        relative_rect=pygame.Rect(c4x, c4y, c4w, summary_h),
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_summary_box",
    )
    editor._elements.append(editor._summary_box)


def build_ui(editor) -> None:
    """Creates and lays out all child widgets inside the main unit designer panel."""
    pad = editor._pad
    pr = editor._panel_rect
    scale_y = editor.screen_res.y / 720.0

    # --- Outer panel ---
    editor._panel = pygame_gui.elements.UIPanel(
        relative_rect=pr,
        starting_height=5,
        manager=editor.manager,
        object_id="#unit_editor_panel",
    )
    editor._elements.append(editor._panel)

    # Title
    title = pygame_gui.elements.UILabel(
        relative_rect=pygame.Rect(pad, pad, pr.w - pad * 2, int(28 * scale_y)),
        text="⚒  UNIT DESIGNER",
        manager=editor.manager,
        container=editor._panel,
        object_id="#unit_editor_title",
    )
    editor._elements.append(title)

    # Close button
    close_w = int(80 * (editor.screen_res.x / 1280.0))
    close_h = int(24 * scale_y)
    editor._close_button = pygame_gui.elements.UIButton(
        relative_rect=pygame.Rect(pr.w - close_w - pad, pad, close_w, close_h),
        text="✕  Close",
        manager=editor.manager,
        container=editor._panel,
        object_id="#editor_close_button",
    )
    editor._elements.append(editor._close_button)

    separator_y = int(pad + 30 * scale_y)

    # Heights & spacing
    row_h = int(26 * scale_y)
    small_h = max(24, int(24 * TEXT_SCALE))
    dd_h = int(28 * scale_y)
    entry_h = int(32 * scale_y)
    btn_h = int(32 * scale_y)

    c1x, c2x, c3x, c4x = editor._col1_x, editor._col2_x, editor._col3_x, editor._col4_x
    c1y = c2y = c3y = c4y = separator_y + pad

    # Build columns
    build_col1_config(editor, c1x, c1y, editor._col_w, row_h, dd_h, entry_h, btn_h, pad, scale_y)
    build_col2_components(editor, c2x, c2y, editor._col_w, row_h, small_h, pad)
    build_col3_details(editor, c3x, c3y, editor._col_w, row_h, small_h, dd_h, entry_h, btn_h, pad, scale_y)
    build_col4_summary(editor, c4x, c4y, editor._col_w, row_h, pad, pr)

    # Initial refresh
    editor._update_component_toggle_labels()
    editor._update_summary()
    editor._apply_hull_restrictions()
    editor._refresh_component_details()
