"""
unit_editor_gui.py

A self-contained pygame_gui panel that acts as the in-game Unit Designer.
It is opened via a button in the bottom bar and drawn on top of the game.

The editor is intentionally structured as a plain UIPanel (not a UIWindow)
so we have full layout control.  It can be shown/hidden without destroying
and recreating all child elements.

Layout (three columns inside a full-height panel on the right side):
  ┌────────────────────────────────────────────────────────────────┐
  │  UNIT DESIGNER                                     [X Close]   │
  ├──────────────────────┬─────────────────────────────────────────┤
  │  LEFT: Hull &        │  RIGHT: Summary & Actions               │
  │  Components          │                                         │
  └──────────────────────┴─────────────────────────────────────────┘
"""

import logging
import pygame
import pygame_gui
import typing

from constants import HullSize, HULL_CAPACITIES, TEXT_SCALE
from custom_unit_templates import (
    CustomUnitTemplate, ComponentConfig, TurretConfig,
    CustomTemplateManager, HULL_RESTRICTIONS, ADVANCED_HYPERDRIVE_MIN_HULL,
)
from unit_components import AbilityType, TurretType, TurretVariant

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Component catalogue — defines order, labels, hull-cost defaults
# ---------------------------------------------------------------------------

COMPONENT_ROWS: typing.List[typing.Dict] = [
    {"key": "has_engine",                "label": "Engines",            "cost_key": "engine_hull_cost",           "default_cost": 5},
    {"key": "has_hyperdrive",            "label": "Hyperdrive",         "cost_key": "hyperdrive_hull_cost",       "default_cost": 5},
    {"key": "has_weapon_bays",           "label": "Weapons",            "cost_key": "weapon_bays_hull_cost",      "default_cost": 10},
    {"key": "has_defenses",              "label": "Defenses",           "cost_key": "defenses_hull_cost",         "default_cost": 10},
    {"key": "has_constructor_component", "label": "Constructor",        "cost_key": "constructor_hull_cost",      "default_cost": 15},
    {"key": "has_repair_component",      "label": "Repair",             "cost_key": "repair_hull_cost",           "default_cost": 15},
    {"key": "has_colony_component",      "label": "Colony",             "cost_key": "colony_hull_cost",           "default_cost": 10},
    {"key": "has_mining_component",      "label": "Mining",             "cost_key": "mining_hull_cost",           "default_cost": 10},
    {"key": "has_metal_refinery_component", "label": "Metal Refinery",  "cost_key": "metal_refinery_hull_cost",   "default_cost": 20},
    {"key": "has_crystal_refinery_component", "label": "Crystal Refinery", "cost_key": "crystal_refinery_hull_cost", "default_cost": 20},
    {"key": "has_hangar",                "label": "Hangar",             "cost_key": "hangar_hull_cost",           "default_cost": 20},
    {"key": "has_fighter_bay",           "label": "Fighter Bay",        "cost_key": "fighter_bay_hull_cost",      "default_cost": 15},
    {"key": "has_inhibitor",             "label": "Inhibitor Field",    "cost_key": "inhibitor_hull_cost",        "default_cost": 20},
    {"key": "has_ability_component",     "label": "Abilities",          "cost_key": "ability_hull_cost",          "default_cost": 10},
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
        self._comp: ComponentConfig = ComponentConfig()
        self._design_name: str = ""
        self._display_name: str = ""
        self._turrets: typing.List[TurretConfig] = []
        self._selected_abilities: typing.Set[str] = set()
        self._editing_key: typing.Optional[str] = None  # key of design being edited

        # --- Panel geometry ---
        panel_w = int(min(1760, screen_res.x * 0.95))
        panel_h = int(screen_res.y * 0.88)
        panel_x = (screen_res.x - panel_w) // 2
        panel_y = int(screen_res.y * 0.06)
        self._panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)

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

        # Hyperdrive type dropdown
        self._hd_type_dropdown: typing.Optional[pygame_gui.elements.UIDropDownMenu] = None

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
            text="⚙  UNIT DESIGNER",
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
        small_h = int(22 * scale_y)
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
            text="💾  Save Design",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_save_button",
        )
        self._elements.append(self._save_button)
        c1y += btn_h + pad

        # Delete Button
        self._delete_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(c1x, c1y, c1w, btn_h),
            text="🗑  Delete Design",
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
        # COLUMN 2 (Middle-Left): Components List (Toggles & Hyperdrive)
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

        # Component toggle rows (single column)
        btn_w = c2w - 35
        cost_w = 25

        for idx, row in enumerate(COMPONENT_ROWS):
            cx = c2x
            cy = c2y + idx * (small_h + 3)

            key = row["key"]
            label = row["label"]
            cost = row["default_cost"]

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
                relative_rect=pygame.Rect(cx + btn_w + 5, cy, cost_w, small_h),
                text=str(cost),
                manager=self.manager,
                container=self._panel,
                object_id="#comp_cost_label",
            )
            self._comp_cost_labels[key] = cost_lbl
            self._elements.append(cost_lbl)

        c2y += len(COMPONENT_ROWS) * (small_h + 3) + pad

        # ---- Hyperdrive type sub-row (Stacked) ----
        hd_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c2x, c2y, c2w, small_h),
            text="Hyperdrive Type:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._elements.append(hd_lbl)
        c2y += small_h

        self._hd_type_dropdown = pygame_gui.elements.UIDropDownMenu(
            options_list=HYPERDRIVE_TYPES,
            starting_option=self._comp.hyperdrive_type,
            relative_rect=pygame.Rect(c2x, c2y, c2w, dd_h),
            manager=self.manager,
            container=self._panel,
            object_id="#hd_type_dropdown",
        )
        self._elements.append(self._hd_type_dropdown)
        c2y += dd_h + pad


        # ----------------------------------------------------------------
        # COLUMN 3 (Middle-Right): Weapons (Turrets configuration)
        # ----------------------------------------------------------------

        turret_hdr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, c3y, c3w, row_h),
            text="Turrets Configuration",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_section_label",
        )
        self._elements.append(turret_hdr)
        c3y += row_h + pad

        # Turret Type dropdown
        ttype_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, c3y, c3w, small_h),
            text="Turret Type:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._elements.append(ttype_lbl)
        c3y += small_h

        self._turret_type_dd = pygame_gui.elements.UIDropDownMenu(
            options_list=TURRET_TYPES,
            starting_option=TURRET_TYPES[0],
            relative_rect=pygame.Rect(c3x, c3y, c3w, dd_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_type_dropdown",
        )
        self._elements.append(self._turret_type_dd)
        c3y += dd_h + pad

        # Variant dropdown
        tvar_lbl = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, c3y, c3w, small_h),
            text="Variant:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._elements.append(tvar_lbl)
        c3y += small_h

        self._turret_variant_dd = pygame_gui.elements.UIDropDownMenu(
            options_list=TURRET_VARIANTS,
            starting_option=TURRET_VARIANTS[0],
            relative_rect=pygame.Rect(c3x, c3y, c3w, dd_h),
            manager=self.manager,
            container=self._panel,
            object_id="#turret_variant_dropdown",
        )
        self._elements.append(self._turret_variant_dd)
        c3y += dd_h + pad

        # Numeric inputs: Damage, Range, Cooldown stacked
        label_w = int(c3w * 0.40)
        entry_w = c3w - label_w

        for label_text, placeholder, entry_ref in [
            ("Damage:", "15", "_turret_dmg_entry"),
            ("Range:", "300", "_turret_range_entry"),
            ("Cooldown:", "2", "_turret_cd_entry"),
        ]:
            row_lbl = pygame_gui.elements.UILabel(
                relative_rect=pygame.Rect(c3x, c3y, label_w, entry_h),
                text=label_text,
                manager=self.manager,
                container=self._panel,
                object_id="#comp_cost_label",
            )
            self._elements.append(row_lbl)

            entry = pygame_gui.elements.UITextEntryLine(
                relative_rect=pygame.Rect(c3x + label_w, c3y, entry_w, entry_h),
                manager=self.manager,
                container=self._panel,
                object_id="#turret_entry",
            )
            entry.set_text(placeholder)
            setattr(self, entry_ref, entry)
            self._elements.append(entry)
            c3y += entry_h + int(4 * scale_y)

        c3y += pad

        # Add Turret button
        self._add_turret_button = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(c3x, c3y, c3w, btn_h),
            text="+ Add Turret",
            manager=self.manager,
            container=self._panel,
            object_id="#add_turret_button",
        )
        self._elements.append(self._add_turret_button)
        c3y += btn_h + pad

        # Active Turrets list header and start coordinates
        active_hdr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c3x, c3y, c3w, small_h),
            text="Active Turrets:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        self._elements.append(active_hdr)
        c3y += small_h + 2

        self._turret_list_y_start = c3y
        self._turret_list_lx = c3x
        self._turret_list_lw = c3w


        # ----------------------------------------------------------------
        # COLUMN 4 (Right): Abilities & Design Summary
        # ----------------------------------------------------------------

        # Abilities list is rebuilt dynamically, but we calculate its space
        # to position the summary header and textbox below it.
        abilities_h = small_h + 2 + len(ABILITY_NAMES) * (small_h + 2) + pad
        c4y += abilities_h

        summary_hdr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c4x, c4y, c4w, row_h),
            text="Design Summary:",
            manager=self.manager,
            container=self._panel,
            object_id="#editor_section_label",
        )
        self._elements.append(summary_hdr)
        c4y += row_h + 2

        # Make the summary box take up the remaining vertical space of the panel
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
        self._rebuild_turret_list()
        self._apply_hull_restrictions()

    # ------------------------------------------------------------------
    # Show / Hide
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Make the editor visible."""
        self.is_visible = True
        if self._panel:
            self._panel.show()
        self._refresh_load_dropdown()

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

            # Component toggles
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
                        self._rebuild_turret_list()
                        self._update_summary()
                    return "ui_handled"

        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            elem = event.ui_element
            if elem is self._hull_dropdown:
                self._on_hull_changed(event.text)
                return "ui_handled"
            elif elem is self._hd_type_dropdown:
                self._comp.hyperdrive_type = event.text
                self._comp.hyperdrive_hull_cost = 5 if event.text == "BASIC" else 10
                self._update_summary()
                return "ui_handled"
            elif elem is self._load_dd and event.text != "— select —":
                self._load_design(event.text)
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
    # Internal helpers
    # ------------------------------------------------------------------

    def _current_hull_used(self) -> int:
        """Compute total hull cost of enabled components."""
        total = 0
        c = self._comp
        for row in COMPONENT_ROWS:
            key = row["key"]
            if getattr(c, key, False):
                total += getattr(c, row["cost_key"], row["default_cost"])
        return total

    def _capacity_text(self) -> str:
        capacity = HULL_CAPACITIES[self._hull_size]
        used = self._current_hull_used()
        return f"Hull Capacity: {used} / {capacity}"

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
        self._update_capacity_label()
        self._update_summary()

    def _toggle_ability(self, aname: str) -> None:
        if aname in self._selected_abilities:
            self._selected_abilities.remove(aname)
        else:
            self._selected_abilities.add(aname)
        self._comp.abilities = list(self._selected_abilities)
        self._update_ability_toggle_labels()
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
        for aname, btn in self._ability_buttons.items():
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
        self._update_capacity_label()
        self._update_summary()

    def _apply_hull_restrictions(self) -> None:
        """Disable forbidden components for the current hull size."""
        restricted = HULL_RESTRICTIONS.get(self._hull_size, set())
        c = self._comp
        for row in COMPONENT_ROWS:
            key = row["key"]
            btn = self._comp_toggles.get(key)
            if not btn:
                continue
            if key in restricted:
                # Force off and disable button
                setattr(c, key, False)
                btn.disable()
            else:
                btn.enable()
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
        self._update_component_toggle_labels()
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

        if not self._panel:
            return

        scale_y = self.screen_res.y / 720.0
        small_h = int(22 * scale_y)
        lx = self._turret_list_lx
        lw = self._turret_list_lw
        ly = self._turret_list_y_start
        pad = self._pad

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

        self._rebuild_abilities()

    def _rebuild_abilities(self) -> None:
        """Rebuild the abilities list in Column 4."""
        if hasattr(self, "_abil_hdr") and self._abil_hdr and self._abil_hdr.alive():
            self._abil_hdr.kill()
        self._abil_hdr = None

        for btn in list(self._ability_buttons.values()):
            if btn.alive():
                btn.kill()
        self._ability_buttons.clear()

        if not self._panel:
            return

        scale_y = self.screen_res.y / 720.0
        small_h = int(22 * scale_y)
        c4x = self._col4_x
        c4w = self._col_w
        pad = self._pad

        separator_y = int(pad + 30 * scale_y)
        ay = separator_y + pad

        # Heading
        self._abil_hdr = pygame_gui.elements.UILabel(
            relative_rect=pygame.Rect(c4x, ay, c4w, small_h),
            text="Abilities:",
            manager=self.manager,
            container=self._panel,
            object_id="#comp_cost_label",
        )
        ay += small_h + 2

        # Abilities buttons in a single column
        for aname in ABILITY_NAMES:
            abtn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(c4x, ay, c4w, small_h),
                text=f"[ ] {aname}",
                manager=self.manager,
                container=self._panel,
                object_id="#ability_toggle_button",
            )
            self._ability_buttons[aname] = abtn
            ay += small_h + 2
        
        self._update_ability_toggle_labels()

    def _do_save(self) -> typing.Optional[str]:
        key = self._name_entry.get_text().strip() if self._name_entry else ""
        display = self._display_entry.get_text().strip() if self._display_entry else ""
        if not key:
            self._set_status("⚠ Please enter a design key.", error=True)
            return None
        if not display:
            self._set_status("⚠ Please enter a display name.", error=True)
            return None

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
            self._set_status(f"✔ Design '{key}' deleted.", error=False)
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
        self._comp = template.components
        self._turrets = list(template.components.turrets)
        self._selected_abilities = set(template.components.abilities)
        if self._name_entry:
            self._name_entry.set_text(template.design_name)
        if self._display_entry:
            self._display_entry.set_text(template.display_name)

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

        self._apply_hull_restrictions()
        self._update_component_toggle_labels()
        self._update_ability_toggle_labels()
        self._rebuild_turret_list()
        self._update_capacity_label()
        self._update_summary()
        self._set_status(f"Loaded design '{key}'.", error=False)

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
        build_cost = HULL_BASE_COST[self._hull_size] + used * COMPONENT_COST_PER_HULL_POINT
        base_bt = HULL_BASE_BUILD_TIME[self._hull_size]
        extra_bt = max(0, round((used / max(1, capacity)) * base_bt))
        build_time = base_bt + extra_bt

        cap_color = "#FF4444" if over else "#88FF88"
        lines = [
            f"<b>Hull:</b> {self._hull_size.name}   <b>HP:</b> {hp}",
            f"<b>Hull capacity:</b> <font color='{cap_color}'>{used} / {capacity}</font>",
            f"<b>Build cost:</b> {build_cost} credits",
            f"<b>Build time:</b> {build_time} turns",
            "",
        ]

        comps = []
        for row in COMPONENT_ROWS:
            if getattr(c, row["key"], False):
                comps.append(f"  • {row['label']} ({getattr(c, row['cost_key'], row['default_cost'])} hull)")
        if comps:
            lines.append("<b>Components:</b>")
            lines.extend(comps)

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
