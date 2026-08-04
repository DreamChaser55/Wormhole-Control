"""
unit_editor_gui.py

A self-contained pygame_gui panel that acts as the in-game Unit Designer.
It is opened via a button in the bottom bar and drawn on top of the game.

The editor is intentionally structured as a plain UIPanel (not a UIWindow)
so we have full layout control.  It can be shown/hidden without destroying
and recreating all child elements.

Layout (four columns inside a full-height panel):
  ┌─────────────────────────────────────────────────────────────────────┐
  │  UNIT DESIGNER                                          [X Close]   │
  ├────────────────┬──────────────────┬──────────────────┬──────────────┤
  │  COL1:         │  COL2:           │  COL3:           │  COL4:       │
  │  Config &      │  Components      │  Turrets &       │  Abilities & │
  │  Save/Load     │  (toggle+cost)   │  sub-options     │  Summary     │
  └────────────────┴──────────────────┴──────────────────┴──────────────┘
"""

import copy
import logging
import pygame
import pygame_gui
import typing

from constants import HullSize, HULL_CAPACITIES, TEXT_SCALE, MIN_ANTIMATTER_CAPACITY, get_min_antimatter_capacity
from custom_unit_templates import (
    CustomUnitTemplate, ComponentConfig, TurretConfig,
    CustomTemplateManager, HULL_RESTRICTIONS, ADVANCED_HYPERDRIVE_MIN_HULL,
    ABILITY_REQUIRED_COMPONENTS,
    calc_engine_hull_cost, calc_weapons_hull_cost, calc_defenses_hull_cost,
    calc_hyperdrive_hull_cost,
)
from unit_components import AbilityType, TurretType, TurretVariant

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Component catalogue — defines order and labels.
# Dynamic components (Engines, Hyperdrive, Weapons, Defenses) have
# is_dynamic=True; their hull cost is computed at runtime.
# Fixed components carry a default_cost that is editable.
# ---------------------------------------------------------------------------

COMPONENT_ROWS: typing.List[typing.Dict] = [
    {"key": "has_engine",                "label": "Engines",            "cost_key": "engine_hull_cost",           "default_cost": 5.0,  "is_dynamic": True},
    {"key": "has_antimatter_storage",    "label": "Antimatter Storage", "cost_key": "antimatter_hull_cost",       "default_cost": 5.0,  "is_dynamic": True},
    {"key": "has_antimatter_harvester",  "label": "Antimatter Harvester", "cost_key": "antimatter_harvester_hull_cost", "default_cost": 15.0, "is_dynamic": False},
    {"key": "has_hyperdrive",            "label": "Hyperdrive",         "cost_key": "hyperdrive_hull_cost",       "default_cost": 5.0,  "is_dynamic": True},
    {"key": "has_weapon_bays",           "label": "Weapons",            "cost_key": "weapon_bays_hull_cost",      "default_cost": 10.0, "is_dynamic": True},
    {"key": "has_defenses",              "label": "Defenses",           "cost_key": "defenses_hull_cost",         "default_cost": 10.0, "is_dynamic": True},
    {"key": "has_constructor_component", "label": "Constructor",        "cost_key": "constructor_hull_cost",      "default_cost": 15.0, "is_dynamic": False},
    {"key": "has_repair_component",      "label": "Repair",             "cost_key": "repair_hull_cost",           "default_cost": 15.0, "is_dynamic": True},
    {"key": "has_colony_component",      "label": "Colony",             "cost_key": "colony_hull_cost",           "default_cost": 10.0, "is_dynamic": False},
    {"key": "has_mining_component",      "label": "Mining",             "cost_key": "mining_hull_cost",           "default_cost": 10.0, "is_dynamic": True},
    {"key": "has_metal_refinery_component", "label": "Metal Refinery",  "cost_key": "metal_refinery_hull_cost",   "default_cost": 20.0, "is_dynamic": False},
    {"key": "has_crystal_refinery_component", "label": "Crystal Refinery", "cost_key": "crystal_refinery_hull_cost", "default_cost": 20.0, "is_dynamic": False},
    {"key": "has_hangar",                "label": "Hangar",             "cost_key": "hangar_hull_cost",           "default_cost": 20.0, "is_dynamic": True},
    {"key": "has_strikecraft_bay",       "label": "Strikecraft Bay",    "cost_key": "strikecraft_bay_hull_cost",  "default_cost": 15.0, "is_dynamic": True},
    {"key": "has_inhibitor",             "label": "Inhibitor Field",    "cost_key": "inhibitor_hull_cost",        "default_cost": 20.0, "is_dynamic": True},
    {"key": "has_ability_component",     "label": "Abilities",          "cost_key": "ability_hull_cost",          "default_cost": 10.0, "is_dynamic": True},
    {"key": "has_sensors",               "label": "Sensors",            "cost_key": "sensors_hull_cost",          "default_cost": 2.0,  "is_dynamic": True},
    {"key": "has_minelayer_component",   "label": "Minelayer",          "cost_key": "minelayer_hull_cost",        "default_cost": 15.0, "is_dynamic": False},
]



HULL_SIZE_NAMES = [hs.name for hs in HullSize]

TURRET_TYPES = [t.name for t in TurretType]
TURRET_VARIANTS = [v.name for v in TurretVariant]
ABILITY_NAMES = [a.value for a in AbilityType]
HYPERDRIVE_TYPES = ["BASIC", "ADVANCED"]


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _lerp_color(a: pygame.Color, b: pygame.Color, t: float) -> pygame.Color:
    return pygame.Color(
        int(a.r + (b.r - a.r) * t),
        int(a.g + (b.g - a.g) * t),
        int(a.b + (b.b - a.b) * t),
    )


class UnitEditorWindow:
    """
    Manages the Unit Designer overlay panel.

    Call :meth:`show` / :meth:`hide` to toggle visibility.
    Call :meth:`process_event` each frame to handle widget interactions.
    Call :meth:`draw` each frame to render custom pygame elements (capacity bar).
    The ``pygame_gui.UIManager`` handles all widget drawing automatically.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        manager: pygame_gui.UIManager,
        screen_res: pygame.Vector2,
        template_manager: CustomTemplateManager,
    ):
        self.manager = manager
        self.screen_res = screen_res
        self.template_manager = template_manager
        self.is_visible = False

        # Current design state
        self._hull_size: HullSize = HullSize.MEDIUM
        self._comp: ComponentConfig = ComponentConfig(has_antimatter_storage=True)
        self._design_name: str = ""
        self._display_name: str = ""
        self._turrets: typing.List[TurretConfig] = []
        self._selected_abilities: typing.Set[str] = set()
        self._editing_key: typing.Optional[str] = None  # key of design being edited

        # --- Panel geometry ---
        panel_x = 20
        panel_w = max(100, int(screen_res.x) - 40)
        panel_h = int(screen_res.y * 0.88)
        panel_y = int(screen_res.y * 0.06)
        self._panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        self._abilities_y_start = 0


        pad = int(8 * (screen_res.y / 720.0))
        self._pad = pad

        # 4 column layout parameters
        col_w = (panel_w - pad * 5) // 4
        self._col_w = col_w
        self._col1_x = pad
        self._col2_x = pad + col_w + pad
        self._col3_x = pad + (col_w + pad) * 2
        self._col4_x = pad + (col_w + pad) * 3

        # Tracked UI elements — built once in _build_ui, shown/hidden together
        self._elements: typing.List[pygame_gui.core.UIElement] = []

        # Specific widget references
        self._panel: typing.Optional[pygame_gui.elements.UIPanel] = None
        self._hull_dropdown: typing.Optional[pygame_gui.elements.UIDropDownMenu] = None
        self._comp_toggles: typing.Dict[str, pygame_gui.elements.UIButton] = {}
        self._comp_cost_labels: typing.Dict[str, pygame_gui.elements.UILabel] = {}
        self._comp_select_btns: typing.Dict[str, pygame_gui.elements.UIButton] = {}
        self._selected_component_key: typing.Optional[str] = "has_engine"
        self._details_groups: typing.Dict[str, typing.List[pygame_gui.core.UIElement]] = {}
        self._details_hdr: typing.Optional[pygame_gui.elements.UILabel] = None
        self._capacity_label: typing.Optional[pygame_gui.elements.UILabel] = None

        # Weapons sub-panel widgets
        self._turret_list_box: typing.Optional[pygame_gui.elements.UIScrollingContainer] = None
        self._turret_labels: typing.List[pygame_gui.elements.UILabel] = []
        self._turret_remove_buttons: typing.List[pygame_gui.elements.UIButton] = []
        self._add_turret_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self._turret_type_dd: typing.Optional[pygame_gui.elements.UIDropDownMenu] = None
        self._turret_dmg_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._turret_range_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._turret_cd_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._turret_variant_dd: typing.Optional[pygame_gui.elements.UIDropDownMenu] = None

        # Hyperdrive type dropdown + jump range entry
        self._hd_type_dropdown: typing.Optional[pygame_gui.elements.UIDropDownMenu] = None
        self._hd_jump_range_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None

        # Engine speed & Antimatter capacity entry
        self._engine_speed_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._am_capacity_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None

        # Defenses sub-entries
        self._armor_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._shields_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._pd_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None

        # Repair sub-entries
        self._repair_rate_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._repair_range_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None

        # Mining sub-entries
        self._mining_rate_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._mining_range_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._mining_max_cargo_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None

        # Hangar sub-entries
        self._hangar_slots_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None

        # Strikecraft Bay sub-entries
        self._strikecraft_bay_slots_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None

        # Inhibitor Field sub-entries
        self._inhibitor_radius_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None

        # Ability checkboxes (UIButton toggles)
        self._ability_buttons: typing.Dict[str, pygame_gui.elements.UIButton] = {}
        self._abil_hdr: typing.Optional[pygame_gui.elements.UILabel] = None

        # Right column
        self._name_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._display_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._summary_box: typing.Optional[pygame_gui.elements.UITextBox] = None
        self._save_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self._load_dd: typing.Optional[pygame_gui.elements.UIDropDownMenu] = None
        self._delete_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self._close_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self._status_label: typing.Optional[pygame_gui.elements.UILabel] = None

        # Capacity bar rectangle (absolute screen coords for direct draw)
        self._cap_bar_rect: typing.Optional[pygame.Rect] = None

        self._build_ui()
        self.hide()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create all child widgets inside the panel."""
        pad = self._pad
        pr = self._panel_rect
        scale_y = self.screen_res.y / 720.0

        # --- Outer panel ---
        self._panel = pygame_gui.elements.UIPanel(
            relative_rect=pr,
            starting_height=5,
            manager=self.manager,
            object_id="#unit_editor_panel",
        )
        self._elements.append(self._panel)

        # Title
        title = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(pad, pad, pr.w - pad * 2, int(28 * scale_y)),
            text="⚒  UNIT DESIGNER",
            manager=self.manager,
            container=self._panel,
            object_id="#unit_editor_title",
        )
        self._elements.append(title)

        # Close button (top-right corner)
        close_w = int(80 * (self.screen_res.x / 1280.0))
        close_h = int(24 * scale_y)
        self._close_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(pr.w - close_w - pad, pad, close_w, close_h),
            text="✕  Close",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_close_button",
        )
        self._elements.append(self._close_button)

        separator_y = int(pad + 30 * scale_y)

        # Heights & spacing constants
        row_h = int(26 * scale_y)
        small_h = max(24, int(24 * TEXT_SCALE))
        dd_h = int(28 * scale_y)
        entry_h = int(32 * scale_y)
        btn_h = int(32 * scale_y)

        # Column coordinates & heights setup
        c1x, c1w = self._col1_x, self._col_w
        c2x, c2w = self._col2_x, self._col_w
        c3x, c3w = self._col3_x, self._col_w
        c4x, c4w = self._col4_x, self._col_w

        c1y = separator_y + pad
        c2y = separator_y + pad
        c3y = separator_y + pad
        c4y = separator_y + pad

        # ----------------------------------------------------------------
        # COLUMN 1 (Left): Configuration & Files (Basic info, Save/Load/Delete)
        # ----------------------------------------------------------------

        # Hull Size dropdown
        hull_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c1x, c1y, c1w, row_h),
            text="Hull Size",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_section_label",
        )
        self._elements.append(hull_label)
        c1y += row_h + pad

        self._hull_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=HULL_SIZE_NAMES,
            starting_option=self._hull_size.name,
            relative_rect=pygame.Rect(c1x, c1y, c1w, dd_h),
            manager=self.manager,
            container=self._panel,
            object_id="#hull_size_dropdown",
        )
        self._elements.append(self._hull_dropdown)
        c1y += dd_h + pad

        # Capacity bar label
        self._capacity_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c1x, c1y, c1w, row_h),
            text=self._capacity_text(),
            manager=self.manager,
            container=self._panel,
            object_id="#editor_capacity_label",
        )
        self._elements.append(self._capacity_label)
        c1y += row_h + 2

        # Capacity bar visual (drawn manually — just record its screen rect)
        bar_h = int(10 * scale_y)
        self._cap_bar_rect = pygame.Rect(
            pr.x + c1x,
            pr.y + c1y,
            c1w,
            bar_h,
        )
        c1y += bar_h + pad

        # Design Key
        name_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c1x, c1y, c1w, row_h),
            text="Design Key (unique, no spaces):",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_section_label",
        )
        self._elements.append(name_lbl)
        c1y += row_h + 2

        self._name_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c1x, c1y, c1w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#editor_name_entry",
        )
        self._elements.append(self._name_entry)
        c1y += entry_h + pad

        # Display Name
        display_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c1x, c1y, c1w, row_h),
            text="Display Name:",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_section_label",
        )
        self._elements.append(display_lbl)
        c1y += row_h + 2

        self._display_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c1x, c1y, c1w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#editor_display_entry",
        )
        self._elements.append(self._display_entry)
        c1y += entry_h + pad

        # Load Design
        load_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c1x, c1y, c1w, row_h),
            text="Load / Edit Existing Design:",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_section_label",
        )
        self._elements.append(load_lbl)
        c1y += row_h + 2

        existing = self.template_manager.list_design_names()
        load_options = ["— select —"] + existing
        self._load_dd = pygame_gui.elements.UIDropDownMenu(
            options_list=load_options,
            starting_option="— select —",
            relative_rect=pygame.Rect(c1x, c1y, c1w, dd_h),
            manager=self.manager,
            container=self._panel,
            object_id="#editor_load_dropdown",
        )
        self._elements.append(self._load_dd)
        c1y += dd_h + pad

        # Save Button
        self._save_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(c1x, c1y, c1w, btn_h),
            text="✔  Save Design",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_save_button",
        )
        self._elements.append(self._save_button)
        c1y += btn_h + pad

        # Delete Button
        self._delete_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(c1x, c1y, c1w, btn_h),
            text="✖  Delete Design",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_delete_button",
        )
        self._elements.append(self._delete_button)
        c1y += btn_h + pad

        # Status Label
        self._status_label = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c1x, c1y, c1w, row_h),
            text="",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_status_label",
        )
        self._elements.append(self._status_label)
        c1y += row_h + pad


        # ----------------------------------------------------------------
        # COLUMN 2 (Middle-Left): Components Checklist & Selection
        # ----------------------------------------------------------------

        comp_heading = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c2x, c2y, c2w, row_h),
            text="Components (hull cost)",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_section_label",
        )
        self._elements.append(comp_heading)
        c2y += row_h + 2

        cost_w = max(40, int(40 * TEXT_SCALE))
        select_w = max(38, int(38 * TEXT_SCALE))
        gap = max(2, int(2 * TEXT_SCALE))
        btn_w = c2w - cost_w - select_w - (gap * 2)

        for idx, row in enumerate(COMPONENT_ROWS):
            cx = c2x
            cy = c2y + idx * (small_h + 3)

            key = row["key"]
            label = row["label"]
            cost_display = "~" if row["is_dynamic"] else str(row["default_cost"])

            btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(cx, cy, btn_w, small_h),
                text=f"[ ] {label}",
                manager=self.manager,
                container=self._panel,
                object_id="#comp_toggle_button",
            )
            self._comp_toggles[key] = btn
            self._elements.append(btn)

            cost_lbl = pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(cx + btn_w + gap, cy, cost_w, small_h),
                text=cost_display,
                manager=self.manager,
                container=self._panel,
                object_id="#comp_cost_label",
            )
            self._comp_cost_labels[key] = cost_lbl
            self._elements.append(cost_lbl)

            sel_btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(cx + btn_w + gap + cost_w + gap, cy, select_w, small_h),
                text="▶▶▶" if key == self._selected_component_key else ">>>",
                manager=self.manager,
                container=self._panel,
                object_id="#comp_select_button",
            )
            self._comp_select_btns[key] = sel_btn
            self._elements.append(sel_btn)

        c2y += len(COMPONENT_ROWS) * (small_h + 3) + pad
        self._abilities_y_start = c2y

        # ----------------------------------------------------------------
        # COLUMN 3 (Middle-Right): Component Details (Dynamic View)
        # ----------------------------------------------------------------

        self._details_hdr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, c3y, c3w, row_h),
            text="Component Details",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_section_label",
        )
        self._elements.append(self._details_hdr)
        c3y_base = c3y + row_h + pad

        self._details_groups = {row["key"]: [] for row in COMPONENT_ROWS}

        # --- 1. Engines ---
        y = c3y_base
        lbl_eng = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y, c3w, small_h),
            text="Engine Speed:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._engine_speed_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._engine_speed_entry.set_text(str(int(self._comp.engine_speed)))
        self._details_groups["has_engine"].extend([lbl_eng, self._engine_speed_entry])

        # --- 2. Antimatter Storage ---
        lbl_am = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y, c3w, small_h),
            text="Antimatter Capacity:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._am_capacity_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._am_capacity_entry.set_text(str(int(self._comp.antimatter_capacity)))
        self._details_groups["has_antimatter_storage"].extend([lbl_am, self._am_capacity_entry])

        # --- 3. Hyperdrive ---
        lbl_hd1 = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y, c3w, small_h),
            text="Hyperdrive Type:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._hd_type_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=HYPERDRIVE_TYPES,
            starting_option=self._comp.hyperdrive_type,
            relative_rect=pygame.Rect(c3x, y + small_h + 2, c3w, dd_h),
            manager=self.manager,
            container=self._panel,
            object_id="#hd_type_dropdown",
        )
        y_hd = y + small_h + dd_h + pad
        lbl_hd2 = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_hd, c3w, small_h),
            text="Jump Range:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._hd_jump_range_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y_hd + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._hd_jump_range_entry.set_text(str(self._comp.hyperdrive_jump_range))
        self._details_groups["has_hyperdrive"].extend([lbl_hd1, self._hd_type_dropdown, lbl_hd2, self._hd_jump_range_entry])

        # --- 4. Weapons (Turrets Configuration) ---
        y_w = c3y_base
        ttype_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_w, c3w, small_h),
            text="Turret Type:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        y_w += small_h
        self._turret_type_dd = pygame_gui.elements.UIDropDownMenu(
            options_list=TURRET_TYPES,
            starting_option=TURRET_TYPES[0],
            relative_rect=pygame.Rect(c3x, y_w, c3w, dd_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_type_dropdown",
        )
        y_w += dd_h + pad

        tvar_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_w, c3w, small_h),
            text="Variant:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        y_w += small_h
        self._turret_variant_dd = pygame_gui.elements.UIDropDownMenu(
            options_list=TURRET_VARIANTS,
            starting_option=TURRET_VARIANTS[0],
            relative_rect=pygame.Rect(c3x, y_w, c3w, dd_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_variant_dropdown",
        )
        y_w += dd_h + pad

        label_w = int(c3w * 0.40)
        entry_w = c3w - label_w
        weapon_widgets = [ttype_lbl, self._turret_type_dd, tvar_lbl, self._turret_variant_dd]

        for label_text, placeholder, entry_ref in [
            ("Damage:", "15", "_turret_dmg_entry"),
            ("Range:", "300", "_turret_range_entry"),
            ("Cooldown:", "2", "_turret_cd_entry"),
        ]:
            row_lbl = pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(c3x, y_w, label_w, entry_h),
                text=label_text,
                manager=self.manager,
                container=self._panel,
                object_id="#comp_cost_label",
            )
            entry = pygame_gui.elements.UITextEntryLine(
                relative_rect=pygame.Rect(c3x + label_w, y_w, entry_w, entry_h),
                manager=self.manager,
                container=self._panel,
                object_id="#turret_entry",
            )
            entry.set_text(placeholder)
            setattr(self, entry_ref, entry)
            weapon_widgets.extend([row_lbl, entry])
            y_w += entry_h + int(4 * scale_y)

        y_w += pad
        self._add_turret_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(c3x, y_w, c3w, btn_h),
            text="+ Add Turret",
            manager=self.manager,
            container=self._panel,
            object_id="#add_turret_button",
        )
        weapon_widgets.append(self._add_turret_button)
        y_w += btn_h + pad

        active_hdr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_w, c3w, small_h),
            text="Active Turrets:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        weapon_widgets.append(active_hdr)
        y_w += small_h + 2

        self._turret_list_y_start = y_w
        self._turret_list_lx = c3x
        self._turret_list_lw = c3w
        self._details_groups["has_weapon_bays"].extend(weapon_widgets)

        # --- 5. Defenses ---
        y_d = c3y_base
        def_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_d, c3w, small_h),
            text="Defenses Ratings:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        y_d += small_h + pad
        def_widgets = [def_lbl]

        for stat_label, entry_ref in [
            ("Armor:", "_armor_entry"),
            ("Shields:", "_shields_entry"),
            ("Point Def:", "_pd_entry"),
        ]:
            lbl = pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(c3x, y_d, label_w, entry_h),
                text=stat_label,
                manager=self.manager,
                container=self._panel,
                object_id="#comp_cost_label",
            )
            entry = pygame_gui.elements.UITextEntryLine(
                relative_rect=pygame.Rect(c3x + label_w, y_d, entry_w, entry_h),
                manager=self.manager,
                container=self._panel,
                object_id="#turret_entry",
            )
            entry.set_text("0")
            setattr(self, entry_ref, entry)
            def_widgets.extend([lbl, entry])
            y_d += entry_h + int(4 * scale_y)

        self._details_groups["has_defenses"].extend(def_widgets)

        # --- 6. Sensors ---
        y_s = c3y_base
        sr_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_s, c3w, small_h),
            text="Short Range Radius:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._sensor_short_range_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y_s + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._sensor_short_range_entry.set_text(str(int(self._comp.sensor_short_range)))

        y_s += small_h + entry_h + pad
        lr_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_s, c3w, small_h),
            text="Long Range Hexes:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._sensor_long_range_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y_s + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._sensor_long_range_entry.set_text(str(self._comp.sensor_long_range_hexes))
        self._details_groups["has_sensors"].extend([sr_lbl, self._sensor_short_range_entry, lr_lbl, self._sensor_long_range_entry])

        # --- 7. Strikecraft Bay ---
        y_sc = c3y_base
        self._wt_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_sc, c3w, small_h),
            text="Wing Type:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._wt_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=["FIGHTER", "BOMBER"],
            starting_option=self._comp.wing_type if hasattr(self._comp, "wing_type") else "FIGHTER",
            relative_rect=pygame.Rect(c3x, y_sc + small_h + 2, c3w, dd_h),
            manager=self.manager,
            container=self._panel,
            object_id="#hd_type_dropdown",
        )
        y_sc += small_h + dd_h + pad
        lbl_scs = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_sc, c3w, small_h),
            text="Bay Slots:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._strikecraft_bay_slots_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y_sc + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._strikecraft_bay_slots_entry.set_text(str(int(self._comp.strikecraft_bay_slots)))
        self._details_groups["has_strikecraft_bay"].extend([
            self._wt_lbl, self._wt_dropdown,
            lbl_scs, self._strikecraft_bay_slots_entry,
        ])

        # --- 8. Repair Component ---
        y_rep = c3y_base
        lbl_rr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_rep, c3w, small_h),
            text="Repair Rate:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._repair_rate_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y_rep + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._repair_rate_entry.set_text(str(int(self._comp.repair_rate)))

        y_rep += small_h + entry_h + pad
        lbl_rrange = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_rep, c3w, small_h),
            text="Repair Range:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._repair_range_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y_rep + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._repair_range_entry.set_text(str(int(self._comp.repair_range)))

        self._details_groups["has_repair_component"].extend([
            lbl_rr, self._repair_rate_entry,
            lbl_rrange, self._repair_range_entry,
        ])

        # --- 9. Mining Component ---
        y_min = c3y_base
        lbl_mr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_min, c3w, small_h),
            text="Mining Rate:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._mining_rate_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y_min + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._mining_rate_entry.set_text(str(int(self._comp.mining_rate)))

        y_min += small_h + entry_h + pad
        lbl_mrange = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_min, c3w, small_h),
            text="Mining Range:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._mining_range_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y_min + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._mining_range_entry.set_text(str(int(self._comp.mining_range)))

        y_min += small_h + entry_h + pad
        lbl_mcargo = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_min, c3w, small_h),
            text="Max Cargo:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._mining_max_cargo_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y_min + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._mining_max_cargo_entry.set_text(str(int(self._comp.max_mining_cargo)))
        self._details_groups["has_mining_component"].extend([
            lbl_mr, self._mining_rate_entry,
            lbl_mrange, self._mining_range_entry,
            lbl_mcargo, self._mining_max_cargo_entry,
        ])

        # --- 10. Hangar ---
        y_h = c3y_base
        lbl_hs = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_h, c3w, small_h),
            text="Hangar Slots:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._hangar_slots_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y_h + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._hangar_slots_entry.set_text(str(int(self._comp.hangar_slots)))
        self._details_groups["has_hangar"].extend([lbl_hs, self._hangar_slots_entry])

        # --- 11. Inhibitor Field ---
        y_inh = c3y_base
        lbl_inhr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_inh, c3w, small_h),
            text="Inhibitor Radius:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._inhibitor_radius_entry = pygame_gui.elements.UITextEntryLine(
            relative_rect=pygame.Rect(c3x, y_inh + small_h + 2, c3w, entry_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_entry",
        )
        self._inhibitor_radius_entry.set_text(str(int(self._comp.inhibitor_radius)))
        self._details_groups["has_inhibitor"].extend([lbl_inhr, self._inhibitor_radius_entry])

        # --- 12. Abilities ---
        y_ab = c3y_base
        abil_hdr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, y_ab, c3w, small_h),
            text="Select Active Abilities:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        ab_widgets = [abil_hdr]
        y_ab += small_h + 4

        for aname in ABILITY_NAMES:
            abtn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(c3x, y_ab, c3w, small_h),
                text=f"[ ] {aname}",
                manager=self.manager,
                container=self._panel,
                object_id="#ability_toggle_button",
            )
            self._ability_buttons[aname] = abtn
            ab_widgets.append(abtn)
            y_ab += small_h + 3
        self._details_groups["has_ability_component"].extend(ab_widgets)

        # --- 13. Fixed & Info-only Components ---
        DESCRIPTIONS = {
            "has_antimatter_harvester": "Antimatter Harvester<br><br>Generates antimatter resource automatically over time for hyperdrive jumps and abilities.",
            "has_constructor_component": "Constructor Component<br><br>Enables construction of orbital structures, starbases, and warp gates.",
            "has_colony_component": "Colony Component<br><br>Enables colonizing uncolonized habitable planets.",
            "has_metal_refinery_component": "Metal Refinery<br><br>Processes raw ore into refined metal alloys.",
            "has_crystal_refinery_component": "Crystal Refinery<br><br>Refines raw crystal into energy matrix components.",
        }

        for comp_key, desc in DESCRIPTIONS.items():
            if comp_key in self._details_groups:
                box = pygame_gui.elements.UITextBox(
                    html_text=desc,
                    relative_rect=pygame.Rect(c3x, c3y_base, c3w, int(150 * scale_y)),
                    manager=self.manager,
                    container=self._panel,
                    object_id="#editor_summary_box",
                )
                self._details_groups[comp_key].append(box)

        # Append all dynamic elements to self._elements
        for group in self._details_groups.values():
            for elem in group:
                if elem not in self._elements:
                    self._elements.append(elem)

        # ----------------------------------------------------------------
        # COLUMN 4 (Right): Design Summary
        # ----------------------------------------------------------------

        summary_hdr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c4x, c4y, c4w, row_h),
            text="Design Summary",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_section_label",
        )
        self._elements.append(summary_hdr)
        c4y += row_h + 2

        summary_h = pr.h - c4y - pad * 2
        self._summary_box = pygame_gui.elements.UITextBox(
            html_text="",
            relative_rect=pygame.Rect(c4x, c4y, c4w, summary_h),
            manager=self.manager,
            container=self._panel,
            object_id="#editor_summary_box",
        )
        self._elements.append(self._summary_box)

        # Initial refresh
        self._update_component_toggle_labels()
        self._update_summary()
        self._apply_hull_restrictions()
        self._refresh_component_details()

    # ------------------------------------------------------------------
    # Show / Hide
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Make the editor visible."""
        self.is_visible = True
        if self._panel:
            self._panel.show()
        self._refresh_load_dropdown()
        self._refresh_component_details()

    def hide(self) -> None:
        """Hide the editor without destroying widgets."""
        self.is_visible = False
        if self._panel:
            self._panel.hide()

    def kill(self) -> None:
        """Destroy all widgets."""
        if self._panel:
            self._panel.kill()
            self._panel = None
        self._turret_labels.clear()
        self._turret_remove_buttons.clear()
        self._comp_toggles.clear()
        self._comp_cost_labels.clear()
        self._comp_select_btns.clear()
        self._details_groups.clear()
        self._ability_buttons.clear()
        self._elements.clear()

    # ------------------------------------------------------------------
    # Event processing
    # ------------------------------------------------------------------

    def process_event(self, event: pygame.event.Event) -> typing.Optional[str]:
        """
        Process a pygame event.  Returns a string action key if something
        significant happened ('close', 'design_saved', 'design_deleted'),
        otherwise None.
        """
        if not self.is_visible:
            return None

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            elem = event.ui_element

            if elem is self._close_button:
                return "close"

            if elem is self._save_button:
                return self._do_save()

            if elem is self._delete_button:
                return self._do_delete()

            if elem is self._add_turret_button:
                self._do_add_turret()
                return "ui_handled"

            # Component selection (>>> buttons)
            for key, sbtn in self._comp_select_btns.items():
                if elem is sbtn:
                    self._select_component(key)
                    return "ui_handled"

            # Component toggles ([x] buttons)
            for key, btn in self._comp_toggles.items():
                if elem is btn:
                    self._toggle_component(key)
                    return "ui_handled"

            # Ability toggles
            for aname, abtn in self._ability_buttons.items():
                if elem is abtn:
                    self._toggle_ability(aname)
                    return "ui_handled"

            # Turret remove buttons
            for i, rbtn in enumerate(self._turret_remove_buttons):
                if elem is rbtn:
                    if i < len(self._turrets):
                        self._turrets.pop(i)
                        self._comp.turrets = self._turrets
                        self._rebuild_turret_list()
                        self._sync_dynamic_costs()
                        self._update_summary()
                    return "ui_handled"

        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            elem = event.ui_element
            if elem is self._hull_dropdown:
                self._on_hull_changed(event.text)
                return "ui_handled"
            elif elem is self._hd_type_dropdown:
                self._comp.hyperdrive_type = event.text
                self._sync_dynamic_costs()
                self._update_summary()
                return "ui_handled"
            elif elem is self._wt_dropdown:
                self._comp.wing_type = event.text
                self._update_summary()
                return "ui_handled"
            elif elem is self._load_dd and event.text != "— select —":
                self._load_design(event.text)
                return "ui_handled"

        elif event.type == pygame_gui.UI_TEXT_ENTRY_CHANGED:
            elem = event.ui_element
            if elem is self._hd_jump_range_entry:
                self._read_hyperdrive_params()
                self._sync_dynamic_costs()
                self._update_summary()
                return "ui_handled"
            elif elem is self._engine_speed_entry:
                self._read_engine_params()
                self._sync_dynamic_costs()
                self._update_summary()
                return "ui_handled"
            elif elem is self._am_capacity_entry:
                self._read_antimatter_params()
                self._sync_dynamic_costs()
                self._update_summary()
                return "ui_handled"
            elif elem in (self._armor_entry, self._shields_entry, self._pd_entry):
                self._read_defense_params()
                self._sync_dynamic_costs()
                self._update_summary()
                return "ui_handled"
            elif elem in (getattr(self, '_sensor_short_range_entry', None), getattr(self, '_sensor_long_range_entry', None)):
                self._read_sensor_params()
                self._sync_dynamic_costs()
                self._update_summary()
                return "ui_handled"
            elif elem in (getattr(self, '_repair_rate_entry', None), getattr(self, '_repair_range_entry', None)):
                self._read_repair_params()
                self._sync_dynamic_costs()
                self._update_summary()
                return "ui_handled"
            elif elem in (getattr(self, '_mining_rate_entry', None), getattr(self, '_mining_range_entry', None), getattr(self, '_mining_max_cargo_entry', None)):
                self._read_mining_params()
                self._sync_dynamic_costs()
                self._update_summary()
                return "ui_handled"
            elif elem is getattr(self, '_hangar_slots_entry', None):
                self._read_hangar_params()
                self._sync_dynamic_costs()
                self._update_summary()
                return "ui_handled"
            elif elem is getattr(self, '_strikecraft_bay_slots_entry', None):
                self._read_strikecraft_bay_params()
                self._sync_dynamic_costs()
                self._update_summary()
                return "ui_handled"
            elif elem is getattr(self, '_inhibitor_radius_entry', None):
                self._read_inhibitor_params()
                self._sync_dynamic_costs()
                self._update_summary()
                return "ui_handled"

        return None

    # ------------------------------------------------------------------
    # Draw (capacity bar)
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        """Draw any custom pygame elements (capacity bar)."""
        if not self.is_visible or not self._cap_bar_rect:
            return
        capacity = HULL_CAPACITIES[self._hull_size]
        used = self._current_hull_used()
        frac = min(1.0, used / max(1, capacity))
        bar = self._cap_bar_rect

        # Background
        pygame.draw.rect(surface, (40, 40, 50), bar, border_radius=3)

        # Fill
        fill_w = max(0, int(bar.w * frac))
        if fill_w > 0:
            ok_color = pygame.Color(50, 180, 80)
            warn_color = pygame.Color(220, 170, 30)
            over_color = pygame.Color(220, 50, 50)
            fill_color = _lerp_color(ok_color, warn_color, min(1.0, frac / 0.85)) if frac <= 0.85 else _lerp_color(warn_color, over_color, (frac - 0.85) / 0.15)
            fill_rect = pygame.Rect(bar.x, bar.y, fill_w, bar.h)
            pygame.draw.rect(surface, fill_color, fill_rect, border_radius=3)

        # Border
        pygame.draw.rect(surface, (100, 100, 120), bar, 1, border_radius=3)

    # ------------------------------------------------------------------
    # Internal helpers — parameter reading
    # ------------------------------------------------------------------

    def _read_engine_params(self) -> None:
        """Read engine speed from the entry widget and write to _comp."""
        try:
            speed = float(self._engine_speed_entry.get_text()) if self._engine_speed_entry else 100.0
            self._comp.engine_speed = max(0.0, speed)
        except ValueError:
            pass

    def _read_antimatter_params(self) -> None:
        """Read antimatter capacity from the entry widget and write to _comp."""
        try:
            min_cap = get_min_antimatter_capacity(self._hull_size)
            cap = float(self._am_capacity_entry.get_text()) if self._am_capacity_entry else min_cap
            self._comp.antimatter_capacity = max(min_cap, cap)
        except ValueError:
            pass

    def _read_hyperdrive_params(self) -> None:
        """Read hyperdrive jump range from the entry widget and write to _comp."""
        try:
            jr = int(self._hd_jump_range_entry.get_text()) if self._hd_jump_range_entry else 5
            self._comp.hyperdrive_jump_range = max(1, jr)
        except ValueError:
            pass

    def _read_defense_params(self) -> None:
        """Read armor/shields/point_defense from entry widgets and write to _comp."""
        try:
            self._comp.armor = max(0, int(self._armor_entry.get_text())) if self._armor_entry else 0
        except ValueError:
            pass
        try:
            self._comp.shields = max(0, int(self._shields_entry.get_text())) if self._shields_entry else 0
        except ValueError:
            pass
        try:
            self._comp.point_defense = max(0, int(self._pd_entry.get_text())) if self._pd_entry else 0
        except ValueError:
            pass

    def _read_sensor_params(self) -> None:
        """Read short-range radius and long-range hexes from entry widgets and write to _comp."""
        try:
            sr = float(self._sensor_short_range_entry.get_text()) if getattr(self, '_sensor_short_range_entry', None) else DEFAULT_SENSOR_SHORT_RANGE
            self._comp.sensor_short_range = max(0.0, sr)
        except ValueError:
            pass
        try:
            lr = int(self._sensor_long_range_entry.get_text()) if getattr(self, '_sensor_long_range_entry', None) else 0
            self._comp.sensor_long_range_hexes = max(0, lr)
        except ValueError:
            pass

    def _read_repair_params(self) -> None:
        """Read repair parameters from entry widgets and write to _comp."""
        try:
            rr = float(self._repair_rate_entry.get_text()) if getattr(self, '_repair_rate_entry', None) else 10.0
            self._comp.repair_rate = max(0.0, rr)
        except ValueError:
            pass
        try:
            rrange = float(self._repair_range_entry.get_text()) if getattr(self, '_repair_range_entry', None) else 200.0
            self._comp.repair_range = max(0.0, rrange)
        except ValueError:
            pass

    def _read_mining_params(self) -> None:
        """Read mining parameters from entry widgets and write to _comp."""
        try:
            mr = float(self._mining_rate_entry.get_text()) if getattr(self, '_mining_rate_entry', None) else 10.0
            self._comp.mining_rate = max(0.0, mr)
        except ValueError:
            pass
        try:
            mrange = float(self._mining_range_entry.get_text()) if getattr(self, '_mining_range_entry', None) else 200.0
            self._comp.mining_range = max(0.0, mrange)
        except ValueError:
            pass
        try:
            mcargo = float(self._mining_max_cargo_entry.get_text()) if getattr(self, '_mining_max_cargo_entry', None) else 100.0
            self._comp.max_mining_cargo = max(0.0, mcargo)
        except ValueError:
            pass

    def _read_hangar_params(self) -> None:
        """Read hangar slots from entry widget and write to _comp."""
        try:
            slots = int(self._hangar_slots_entry.get_text()) if getattr(self, '_hangar_slots_entry', None) else 2
            self._comp.hangar_slots = max(1, slots)
        except ValueError:
            pass

    def _read_strikecraft_bay_params(self) -> None:
        """Read strikecraft bay slots from entry widget and write to _comp."""
        try:
            slots = int(self._strikecraft_bay_slots_entry.get_text()) if getattr(self, '_strikecraft_bay_slots_entry', None) else 2
            self._comp.strikecraft_bay_slots = max(1, slots)
        except ValueError:
            pass

    def _read_inhibitor_params(self) -> None:
        """Read inhibitor radius from entry widget and write to _comp."""
        try:
            radius = float(self._inhibitor_radius_entry.get_text()) if getattr(self, '_inhibitor_radius_entry', None) else 100.0
            self._comp.inhibitor_radius = max(0.0, radius)
        except ValueError:
            pass


    # ------------------------------------------------------------------
    # Internal helpers — cost tracking
    # ------------------------------------------------------------------

    def _current_hull_used(self) -> int:
        """Compute total hull cost of enabled components.

        Dynamic components (Engines, Weapons, Defenses, Hyperdrive) use
        the calc_* functions via ComponentConfig properties.  Fixed
        components use their stored hull cost fields.
        """
        total = 0.0
        c = self._comp
        for row in COMPONENT_ROWS:
            key = row["key"]
            if getattr(c, key, False):
                if key == "has_engine":
                    total += c.get_engine_hull_cost(self._hull_size)
                elif key == "has_hyperdrive":
                    total += c.get_hyperdrive_hull_cost(self._hull_size)
                else:
                    total += getattr(c, row["cost_key"], row["default_cost"])
        return total

    def _sync_dynamic_costs(self) -> None:
        """Refresh the cost labels for dynamic components and the capacity label."""
        c = self._comp
        dynamic_values = {
            "has_engine":             c.get_engine_hull_cost(self._hull_size),
            "has_antimatter_storage": c.antimatter_hull_cost,
            "has_hyperdrive":         c.get_hyperdrive_hull_cost(self._hull_size),
            "has_weapon_bays":        c.weapon_bays_hull_cost,
            "has_defenses":           c.defenses_hull_cost,
            "has_ability_component":  c.ability_hull_cost,
            "has_sensors":            c.sensors_hull_cost,
            "has_repair_component":   c.repair_hull_cost,
            "has_mining_component":   c.mining_hull_cost,
            "has_hangar":             c.hangar_hull_cost,
            "has_strikecraft_bay":    c.strikecraft_bay_hull_cost,
            "has_inhibitor":          c.inhibitor_hull_cost,
        }

        for key, computed_cost in dynamic_values.items():
            lbl = self._comp_cost_labels.get(key)
            if lbl:
                lbl.set_text(f"{computed_cost:g}")

        self._update_capacity_label()

    def _capacity_text(self) -> str:
        capacity = HULL_CAPACITIES[self._hull_size]
        used = self._current_hull_used()
        return f"Hull Capacity: {used:g} / {capacity:g}"

    def _toggle_component(self, key: str) -> None:
        current = getattr(self._comp, key, False)
        # Check restrictions before enabling
        if not current:
            restricted = HULL_RESTRICTIONS.get(self._hull_size, set())
            if key in restricted:
                self._set_status(f"⚠ {key} not allowed on {self._hull_size.name} hull.", error=True)
                return
        setattr(self._comp, key, not current)
        self._update_component_toggle_labels()
        self._update_ability_toggle_labels()
        self._sync_dynamic_costs()
        self._update_capacity_label()
        self._update_summary()

    def _toggle_ability(self, aname: str) -> None:
        req_keys = ABILITY_REQUIRED_COMPONENTS.get(aname, [])
        comp_labels = {row["key"]: row["label"] for row in COMPONENT_ROWS}
        missing = [k for k in req_keys if not getattr(self._comp, k, False)]
        if missing and aname not in self._selected_abilities:
            req_names = ", ".join(comp_labels.get(k, k) for k in missing)
            self._set_status(f"⚠ '{aname.replace('_', ' ').title()}' requires component: {req_names}.", error=True)
            return

        if aname in self._selected_abilities:
            self._selected_abilities.remove(aname)
        else:
            self._selected_abilities.add(aname)
        self._comp.abilities = list(self._selected_abilities)
        self._update_ability_toggle_labels()
        self._sync_dynamic_costs()
        self._update_capacity_label()
        self._update_summary()

    def _update_component_toggle_labels(self) -> None:
        c = self._comp
        for row in COMPONENT_ROWS:
            key = row["key"]
            label = row["label"]
            enabled = getattr(c, key, False)
            btn = self._comp_toggles.get(key)
            if btn:
                btn.set_text(f"[x] {label}" if enabled else f"[ ] {label}")

    def _update_ability_toggle_labels(self) -> None:
        c = self._comp
        comp_labels = {row["key"]: row["label"] for row in COMPONENT_ROWS}
        for aname, btn in self._ability_buttons.items():
            req_keys = ABILITY_REQUIRED_COMPONENTS.get(aname, [])
            missing = [k for k in req_keys if not getattr(c, k, False)]
            if missing:
                if aname in self._selected_abilities:
                    self._selected_abilities.remove(aname)
                    self._comp.abilities = list(self._selected_abilities)
                req_names = ", ".join(comp_labels.get(k, k) for k in missing)
                btn.set_text(f"[ ] {aname} (Req: {req_names})")
                btn.disable()
            else:
                btn.enable()
                selected = aname in self._selected_abilities
                btn.set_text(f"[x] {aname}" if selected else f"[ ] {aname}")

    def _update_capacity_label(self) -> None:
        if self._capacity_label:
            self._capacity_label.set_text(self._capacity_text())

    def _on_hull_changed(self, hull_name: str) -> None:
        try:
            self._hull_size = HullSize[hull_name]
        except KeyError:
            return
        self._apply_hull_restrictions()
        self._update_component_toggle_labels()
        self._sync_dynamic_costs()
        self._update_capacity_label()
        self._update_summary()

    def _select_component(self, key: str) -> None:
        """Set the active component and update detail panel displays."""
        self._selected_component_key = key
        for k, btn in self._comp_select_btns.items():
            btn.set_text("▶▶▶" if k == key else ">>>")
        self._refresh_component_details()

    def _refresh_component_details(self) -> None:
        """Refresh visibility of component detail widgets based on selected component."""
        key = self._selected_component_key
        row_label = "Component Details"
        for r in COMPONENT_ROWS:
            if r["key"] == key:
                row_label = f"Details: {r['label']}"
                break
        if self._details_hdr:
            self._details_hdr.set_text(row_label)

        for g_key, group in self._details_groups.items():
            if g_key == key:
                for elem in group:
                    elem.show()
            else:
                for elem in group:
                    elem.hide()

        if key == "has_weapon_bays":
            self._rebuild_turret_list()
        else:
            self._hide_turret_list()

        if key == "has_ability_component":
            self._update_ability_toggle_labels()

    def _hide_turret_list(self) -> None:
        """Hide active turret labels and remove buttons."""
        for lbl in self._turret_labels:
            if lbl.alive():
                lbl.hide()
        for btn in self._turret_remove_buttons:
            if btn.alive():
                btn.hide()

    def _apply_hull_restrictions(self) -> None:
        """Disable forbidden components for the current hull size."""
        restricted = HULL_RESTRICTIONS.get(self._hull_size, set())
        c = self._comp
        for row in COMPONENT_ROWS:
            key = row["key"]
            btn = self._comp_toggles.get(key)
            sbtn = self._comp_select_btns.get(key)
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
        if hull_sizes.index(self._hull_size) < min_idx:
            if self._comp.hyperdrive_type == "ADVANCED":
                self._comp.hyperdrive_type = "BASIC"
                if self._hd_type_dropdown:
                    # UIDropDownMenu doesn't support set_text natively;
                    # we rebuild it by killing and re-creating at same rect.
                    rect = self._hd_type_dropdown.get_relative_rect()
                    container = self._hd_type_dropdown.ui_container
                    self._hd_type_dropdown.kill()
                    self._hd_type_dropdown = pygame_gui.elements.UIDropDownMenu(
                        options_list=HYPERDRIVE_TYPES,
                        starting_option="BASIC",
                        relative_rect=rect,
                        manager=self.manager,
                        container=container,
                        object_id="#hd_type_dropdown",
                    )
        
        # Wing type show/hide & enable/disable
        if self._wt_dropdown and self._wt_lbl:
            if self._hull_size == HullSize.STRIKECRAFT_WING:
                self._wt_dropdown.enable()
                if self._selected_component_key == "has_strikecraft_bay":
                    self._wt_lbl.show()
                    self._wt_dropdown.show()
            else:
                self._wt_dropdown.disable()
                self._wt_lbl.hide()
                self._wt_dropdown.hide()

        # Minimum antimatter capacity restriction for current hull size
        min_am_cap = get_min_antimatter_capacity(self._hull_size)
        if self._comp.has_antimatter_storage and self._comp.antimatter_capacity < min_am_cap:
            self._comp.antimatter_capacity = min_am_cap
            if self._am_capacity_entry:
                self._am_capacity_entry.set_text(str(int(min_am_cap)))

        self._update_component_toggle_labels()
        self._sync_dynamic_costs()
        self._update_capacity_label()

    def _do_add_turret(self) -> None:
        if self._turret_type_dd:
            raw = self._turret_type_dd.selected_option
            ttype = raw[0] if isinstance(raw, tuple) else str(raw)
        else:
            ttype = "MASS_DRIVER"
        try:
            dmg = float(self._turret_dmg_entry.get_text()) if self._turret_dmg_entry else 10.0
        except ValueError:
            dmg = 10.0
        try:
            rng = float(self._turret_range_entry.get_text()) if self._turret_range_entry else 300.0
        except ValueError:
            rng = 300.0
        try:
            cd = int(self._turret_cd_entry.get_text()) if self._turret_cd_entry else 2
        except ValueError:
            cd = 2

        if self._turret_variant_dd:
            raw_variant = self._turret_variant_dd.selected_option
            variant = raw_variant[0] if isinstance(raw_variant, tuple) else str(raw_variant)
        else:
            variant = "STANDARD"

        self._turrets.append(TurretConfig(turret_type=ttype, damage=dmg, range=rng, cooldown=cd, variant=variant))
        self._comp.turrets = self._turrets
        self._rebuild_turret_list()
        self._sync_dynamic_costs()
        self._update_summary()

    def _rebuild_turret_list(self) -> None:
        """Rebuild the turret list display labels and remove buttons."""
        # Kill old labels/buttons
        for lbl in self._turret_labels:
            if lbl.alive():
                lbl.kill()
        for btn in self._turret_remove_buttons:
            if btn.alive():
                btn.kill()
        self._turret_labels.clear()
        self._turret_remove_buttons.clear()

        if not self._panel or self._selected_component_key != "has_weapon_bays":
            return

        scale_y = self.screen_res.y / 720.0
        small_h = int(22 * scale_y)
        lx = self._turret_list_lx
        lw = self._turret_list_lw
        ly = self._turret_list_y_start

        for i, tc in enumerate(self._turrets):
            disp_range = tc.range * 3.0 if tc.variant == "LONG_RANGE" else tc.range
            disp_cooldown = tc.cooldown * 3 if tc.variant == "LONG_RANGE" else tc.cooldown
            text = f"{tc.turret_type} ({tc.variant.lower()})  dmg:{tc.damage:.0f}  rng:{disp_range:.0f}  cd:{disp_cooldown}"
            lbl = pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(lx, ly, int(lw * 0.80), small_h),
                text=text,
                manager=self.manager,
                container=self._panel,
                object_id="#turret_item_label",
            )
            self._turret_labels.append(lbl)

            rbtn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(lx + int(lw * 0.82), ly, int(lw * 0.18), small_h),
                text="✕",
                manager=self.manager,
                container=self._panel,
                object_id="#turret_remove_button",
            )
            self._turret_remove_buttons.append(rbtn)
            ly += small_h + 3

    def _do_save(self) -> typing.Optional[str]:
        key = self._name_entry.get_text().strip() if self._name_entry else ""
        display = self._display_entry.get_text().strip() if self._display_entry else ""
        if not key:
            self._set_status("⚠ Please enter a design key.", error=True)
            return None
        if not display:
            self._set_status("⚠ Please enter a display name.", error=True)
            return None

        # Sync all input fields before saving
        self._read_engine_params()
        self._read_antimatter_params()
        self._read_hyperdrive_params()
        self._read_defense_params()
        self._read_sensor_params()
        self._read_repair_params()
        self._read_mining_params()
        self._read_hangar_params()
        self._read_strikecraft_bay_params()
        self._read_inhibitor_params()
        self._comp.turrets = self._turrets
        self._comp.abilities = list(self._selected_abilities)


        template = CustomUnitTemplate(
            design_name=key,
            display_name=display,
            hull_size=self._hull_size,
            components=self._comp,
        )
        errors = self.template_manager.save_design(template)
        if errors:
            self._set_status(" | ".join(errors), error=True)
            return None

        self._editing_key = template.design_name
        self._set_status(f"✔ Design '{template.design_name}' saved!", error=False)
        self._refresh_load_dropdown()
        self._update_summary()
        return "design_saved"

    def _do_delete(self) -> typing.Optional[str]:
        key = self._editing_key
        if not key:
            key = self._name_entry.get_text().strip() if self._name_entry else ""
        if not key:
            self._set_status("⚠ No design selected to delete.", error=True)
            return None
        deleted = self.template_manager.delete_design(key)
        if deleted:
            self._set_status(f"✖ Design '{key}' deleted.", error=False)
            self._editing_key = None
            self._refresh_load_dropdown()
            return "design_deleted"
        else:
            self._set_status(f"⚠ Design '{key}' not found.", error=True)
            return None

    def _load_design(self, key: str) -> None:
        template = self.template_manager.get_design(key)
        if not template:
            return
        self._editing_key = key
        self._hull_size = template.hull_size
        self._comp = copy.deepcopy(template.components)
        self._turrets = copy.deepcopy(template.components.turrets)
        self._selected_abilities = set(template.components.abilities)
        if self._name_entry:
            self._name_entry.set_text(template.design_name)
        if self._display_entry:
            self._display_entry.set_text(template.display_name)

        # Restore dynamic sub-option entry fields
        if self._engine_speed_entry:
            self._engine_speed_entry.set_text(str(int(self._comp.engine_speed)))
        if self._am_capacity_entry:
            self._am_capacity_entry.set_text(str(int(self._comp.antimatter_capacity)))
        if self._hd_jump_range_entry:
            self._hd_jump_range_entry.set_text(str(self._comp.hyperdrive_jump_range))
        if self._armor_entry:
            self._armor_entry.set_text(str(self._comp.armor))
        if self._shields_entry:
            self._shields_entry.set_text(str(self._comp.shields))
        if self._pd_entry:
            self._pd_entry.set_text(str(self._comp.point_defense))
        if getattr(self, '_sensor_short_range_entry', None):
            self._sensor_short_range_entry.set_text(str(int(self._comp.sensor_short_range)))
        if getattr(self, '_sensor_long_range_entry', None):
            self._sensor_long_range_entry.set_text(str(self._comp.sensor_long_range_hexes))
        if getattr(self, '_repair_rate_entry', None):
            self._repair_rate_entry.set_text(str(int(self._comp.repair_rate)))
        if getattr(self, '_repair_range_entry', None):
            self._repair_range_entry.set_text(str(int(self._comp.repair_range)))
        if getattr(self, '_mining_rate_entry', None):
            self._mining_rate_entry.set_text(str(int(self._comp.mining_rate)))
        if getattr(self, '_mining_range_entry', None):
            self._mining_range_entry.set_text(str(int(self._comp.mining_range)))
        if getattr(self, '_mining_max_cargo_entry', None):
            self._mining_max_cargo_entry.set_text(str(int(self._comp.max_mining_cargo)))
        if getattr(self, '_hangar_slots_entry', None):
            self._hangar_slots_entry.set_text(str(int(self._comp.hangar_slots)))
        if getattr(self, '_strikecraft_bay_slots_entry', None):
            self._strikecraft_bay_slots_entry.set_text(str(int(self._comp.strikecraft_bay_slots)))
        if getattr(self, '_inhibitor_radius_entry', None):
            self._inhibitor_radius_entry.set_text(str(int(self._comp.inhibitor_radius)))


        # Rebuild hull dropdown selection
        if self._hull_dropdown:
            rect = self._hull_dropdown.get_relative_rect()
            container = self._hull_dropdown.ui_container
            self._hull_dropdown.kill()
            self._hull_dropdown = pygame_gui.elements.UIDropDownMenu(
                options_list=HULL_SIZE_NAMES,
                starting_option=self._hull_size.name,
                relative_rect=rect,
                manager=self.manager,
                container=container,
                object_id="#hull_size_dropdown",
            )

        # Rebuild hyperdrive type dropdown selection
        if self._hd_type_dropdown:
            rect = self._hd_type_dropdown.get_relative_rect()
            container = self._hd_type_dropdown.ui_container
            self._hd_type_dropdown.kill()
            self._hd_type_dropdown = pygame_gui.elements.UIDropDownMenu(
                options_list=HYPERDRIVE_TYPES,
                starting_option=self._comp.hyperdrive_type,
                relative_rect=rect,
                manager=self.manager,
                container=container,
                object_id="#hd_type_dropdown",
            )

        # Rebuild wing type dropdown selection
        if self._wt_dropdown:
            rect = self._wt_dropdown.get_relative_rect()
            container = self._wt_dropdown.ui_container
            self._wt_dropdown.kill()
            self._wt_dropdown = pygame_gui.elements.UIDropDownMenu(
                options_list=["FIGHTER", "BOMBER"],
                starting_option=self._comp.wing_type if hasattr(self._comp, "wing_type") else "FIGHTER",
                relative_rect=rect,
                manager=self.manager,
                container=container,
                object_id="#hd_type_dropdown",
            )

        self._apply_hull_restrictions()
        self._update_component_toggle_labels()
        self._update_ability_toggle_labels()
        self._rebuild_turret_list()
        self._sync_dynamic_costs()
        self._update_capacity_label()
        self._refresh_component_details()
        self._update_summary()
        self._set_status(f"Loaded design '{key}'.", error=False)
        self._refresh_load_dropdown()

    def _refresh_load_dropdown(self) -> None:
        """Rebuild the load dropdown list with current designs."""
        if not self._load_dd:
            return
        existing = self.template_manager.list_design_names()
        load_options = ["— select —"] + existing
        rect = self._load_dd.get_relative_rect()
        container = self._load_dd.ui_container
        self._load_dd.kill()
        dd_h = int(28 * (self.screen_res.y / 720.0))
        self._load_dd = pygame_gui.elements.UIDropDownMenu(
            options_list=load_options,
            starting_option="— select —",
            relative_rect=pygame.Rect(rect.x, rect.y, rect.w, dd_h),
            manager=self.manager,
            container=container,
            object_id="#editor_load_dropdown",
        )

    def _update_summary(self) -> None:
        """Refresh the summary text box with current design stats."""
        if not self._summary_box:
            return
        c = self._comp
        capacity = HULL_CAPACITIES[self._hull_size]
        used = self._current_hull_used()
        over = used > capacity

        from constants import HIT_POINTS
        from custom_unit_templates import HULL_BASE_COST, HULL_BASE_BUILD_TIME, COMPONENT_COST_PER_HULL_POINT
        hp = HIT_POINTS[self._hull_size]
        build_cost = HULL_BASE_COST[self._hull_size] + int(round(used * COMPONENT_COST_PER_HULL_POINT))
        base_bt = HULL_BASE_BUILD_TIME[self._hull_size]
        extra_bt = max(0, round((used / max(1.0, capacity)) * base_bt))
        build_time = base_bt + extra_bt

        cap_color = "#FF4444" if over else "#88FF88"
        lines = [
            f"<b>Hull:</b> {self._hull_size.name}   <b>HP:</b> {hp}",
            f"<b>Hull capacity:</b> <font color='{cap_color}'>{used:g} / {capacity:g}</font>",
            f"<b>Build cost:</b> {build_cost} credits",
            f"<b>Build time:</b> {build_time} turns",
            "",
        ]

        comps = []
        for row in COMPONENT_ROWS:
            key = row["key"]
            if getattr(c, key, False):
                if key == "has_engine":
                    cost = c.get_engine_hull_cost(self._hull_size)
                elif key == "has_hyperdrive":
                    cost = c.get_hyperdrive_hull_cost(self._hull_size)
                else:
                    cost = getattr(c, row["cost_key"], row["default_cost"])
                cost_str = f"{cost:g}" if isinstance(cost, float) else str(cost)
                comps.append(f"  • {row['label']} ({cost_str} hull)")
        if comps:
            lines.append("<b>Components:</b>")
            lines.extend(comps)

        # Engine speed detail
        if c.has_engine:
            lines.append(f"    speed={c.engine_speed:.0f}")

        # Antimatter capacity detail
        if c.has_antimatter_storage:
            lines.append(f"    antimatter_capacity={c.antimatter_capacity:.0f}")

        # Hyperdrive detail
        if c.has_hyperdrive:
            lines.append(f"    type={c.hyperdrive_type}  jump_range={c.hyperdrive_jump_range}")

        # Defenses detail
        if c.has_defenses:
            lines.append(f"    armor={c.armor}  shields={c.shields}  PD={c.point_defense}")

        if self._turrets:
            lines.append("")
            lines.append(f"<b>Turrets ({len(self._turrets)}):</b>")
            for t in self._turrets:
                disp_range = t.range * 3.0 if t.variant == "LONG_RANGE" else t.range
                disp_cooldown = t.cooldown * 3 if t.variant == "LONG_RANGE" else t.cooldown
                lines.append(f"  • {t.turret_type} ({t.variant.lower()})  dmg:{t.damage:.0f}  rng:{disp_range:.0f}  cd:{disp_cooldown}")

        if self._selected_abilities:
            lines.append("")
            lines.append(f"<b>Abilities ({len(self._selected_abilities)}):</b>")
            for a in sorted(self._selected_abilities):
                lines.append(f"  • {a}")

        self._summary_box.set_text("<br>".join(lines))

    def _set_status(self, msg: str, error: bool = False) -> None:
        if self._status_label:
            self._status_label.set_text(msg)
