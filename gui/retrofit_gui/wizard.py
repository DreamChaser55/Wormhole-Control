"""
wizard.py

RetrofitWizardWindow implementation: Interactive modal window for configuring component
retrofits on friendly starships.
"""

from __future__ import annotations
import logging
import typing
from typing import Optional, List, Dict, Any, Set

import pygame
import pygame_gui

from constants import (
    HullSize,
    UPKEEP_COST_PER_HULL_POINT,
    DEFAULT_ANTIMATTER_CAPACITY,
    DEFAULT_SENSOR_SHORT_RANGE,
    DEFAULT_JUMP_RANGE,
)
from custom_unit_templates import HULL_RESTRICTIONS, COMPONENT_COST_PER_HULL_POINT
from unit_orders.refit import get_hull_restriction_flag
from unit_components.constructor import get_component_hull_cost

from .catalog import RETROFIT_COMPONENTS, ABILITY_NAMES
from . import layout
from . import param_readers

if typing.TYPE_CHECKING:
    from entities import Unit

logger = logging.getLogger(__name__)

_WIN_W = 720
_WIN_H = 580


class RetrofitWizardWindow:
    """Modal UI window providing fine-grained customization for starship retrofits."""

    def __init__(
        self,
        manager: pygame_gui.UIManager,
        screen_res: pygame.Vector2,
        target_unit: Unit,
        constructor_units: List[Unit],
        initial_comp_key: Optional[str] = None,
        shift_pressed: bool = False,
    ):
        self.manager = manager
        self.screen_res = screen_res
        self.target_unit = target_unit
        self.constructor_units = constructor_units
        self.shift_pressed = shift_pressed
        self.scale_x = screen_res.x / 1280.0
        self.scale_y = screen_res.y / 720.0
        self.is_visible = True

        # Calculate eligible mountable components for this target unit
        self._available_components = self._get_eligible_components()
        if not self._available_components:
            self._available_components = RETROFIT_COMPONENTS[:1]

        # Determine starting component
        self._current_comp_key = initial_comp_key if initial_comp_key else self._available_components[0]["comp_key"]
        # Ensure initial_comp_key exists in available, otherwise fallback
        meta_match = next((c for c in self._available_components if c["comp_key"] == self._current_comp_key), None)
        if not meta_match:
            meta_match = self._available_components[0]
            self._current_comp_key = meta_match["comp_key"]
        self._current_comp_meta = meta_match

        # Component state
        self._comp_config: Dict[str, Any] = {}
        self._turrets: List[Dict[str, Any]] = [
            {"type": "MASS_DRIVER", "variant": "STANDARD", "damage": 10.0, "range": 300.0, "cooldown": 2}
        ]
        self._selected_abilities: Set[str] = set()

        # Calculated costs
        self.calculated_hull_cost: float = 0.0
        self.cost_credits: int = 0
        self.time_to_build: int = 1
        self.is_valid: bool = True

        # Widgets
        win_w = int(_WIN_W * self.scale_x)
        win_h = int(_WIN_H * self.scale_y)
        win_x = int((screen_res.x - win_w) / 2)
        win_y = int((screen_res.y - win_h) / 2)

        self.window = pygame_gui.elements.UIWindow(
            rect=pygame.Rect(win_x, win_y, win_w, win_h),
            manager=manager,
            window_display_title="Unit Retrofit Configuration",
            object_id="#retrofit_wizard_window",
            resizable=False,
        )

        # Widget references populated by layout builder
        self._title_label: Optional[pygame_gui.elements.UILabel] = None
        self._comp_select_label: Optional[pygame_gui.elements.UILabel] = None
        self._comp_dropdown: Optional[pygame_gui.elements.UIDropDownMenu] = None
        self._controls_container: Optional[pygame_gui.elements.UIScrollingContainer] = None
        self._summary_panel: Optional[pygame_gui.elements.UIPanel] = None

        self._details_groups: Dict[str, List[pygame_gui.core.UIElement]] = {}

        # Component control widget refs
        self._engine_speed_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._am_capacity_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._hd_type_dropdown: Optional[pygame_gui.elements.UIDropDownMenu] = None
        self._hd_jump_range_entry: Optional[pygame_gui.elements.UITextEntryLine] = None

        self._turret_labels: List[pygame_gui.elements.UILabel] = []
        self._turret_remove_buttons: List[pygame_gui.elements.UIButton] = []
        self._add_turret_button: Optional[pygame_gui.elements.UIButton] = None
        self._turret_type_dd: Optional[pygame_gui.elements.UIDropDownMenu] = None
        self._turret_variant_dd: Optional[pygame_gui.elements.UIDropDownMenu] = None
        self._turret_dmg_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._turret_range_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._turret_cd_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._turret_list_lx: int = 0
        self._turret_list_lw: int = 0
        self._turret_list_y_start: int = 0

        self._armor_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._shields_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._pd_entry: Optional[pygame_gui.elements.UITextEntryLine] = None

        self._sensor_short_range_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._sensor_long_range_entry: Optional[pygame_gui.elements.UITextEntryLine] = None

        self._wt_dropdown: Optional[pygame_gui.elements.UIDropDownMenu] = None
        self._strikecraft_bay_slots_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._hangar_slots_entry: Optional[pygame_gui.elements.UITextEntryLine] = None

        self._repair_rate_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._repair_range_entry: Optional[pygame_gui.elements.UITextEntryLine] = None

        self._mining_rate_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._mining_range_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._mining_max_cargo_entry: Optional[pygame_gui.elements.UITextEntryLine] = None

        self._inhibitor_radius_entry: Optional[pygame_gui.elements.UITextEntryLine] = None
        self._marines_count_entry: Optional[pygame_gui.elements.UITextEntryLine] = None

        self._cloaking_type_dropdown: Optional[pygame_gui.elements.UIDropDownMenu] = None
        self._lbl_clk_r: Optional[pygame_gui.elements.UILabel] = None
        self._cloaking_radius_entry: Optional[pygame_gui.elements.UITextEntryLine] = None

        self._ability_buttons: Dict[str, pygame_gui.elements.UIButton] = {}

        # Summary widget refs
        self._hull_impact_label: Optional[pygame_gui.elements.UILabel] = None
        self._added_cost_label: Optional[pygame_gui.elements.UILabel] = None
        self._credit_cost_label: Optional[pygame_gui.elements.UILabel] = None
        self._player_credits_label: Optional[pygame_gui.elements.UILabel] = None
        self._build_time_label: Optional[pygame_gui.elements.UILabel] = None
        self._upkeep_label: Optional[pygame_gui.elements.UILabel] = None
        self._status_box: Optional[pygame_gui.elements.UITextBox] = None

        # Bottom buttons
        self._confirm_button: Optional[pygame_gui.elements.UIButton] = None
        self._cancel_button: Optional[pygame_gui.elements.UIButton] = None

        self._build_ui()
        self.select_component(self._current_comp_key)

    def _get_eligible_components(self) -> List[Dict[str, Any]]:
        """Filters catalogue components against target unit hull size and existing components."""
        if not self.target_unit:
            return RETROFIT_COMPONENTS

        forbidden = HULL_RESTRICTIONS.get(self.target_unit.hull_size, set())
        eligible = []
        for comp in RETROFIT_COMPONENTS:
            k = comp["comp_key"]
            cls = comp["comp_cls"]
            if cls in self.target_unit.components:
                continue
            flag = get_hull_restriction_flag(k)
            if flag in forbidden:
                continue
            if k == "TradeComponent" and not getattr(self.target_unit, 'engines_component', None):
                continue
            eligible.append(comp)
        return eligible

    def _build_ui(self) -> None:
        """Constructs layout inside the window."""
        layout.build_wizard_layout(self)

    def select_component(self, comp_key: str) -> None:
        """Switches the active component customization group."""
        meta = next((c for c in RETROFIT_COMPONENTS if c["comp_key"] == comp_key), None)
        if not meta:
            return

        self._current_comp_key = comp_key
        self._current_comp_meta = meta

        # Hide all groups first
        for k, group in self._details_groups.items():
            for elem in group:
                if elem.alive():
                    elem.hide()

        # Hide turrets if not weapons
        if comp_key != "Weapons":
            for lbl in self._turret_labels:
                if lbl.alive():
                    lbl.hide()
            for btn in self._turret_remove_buttons:
                if btn.alive():
                    btn.hide()

        # Show target group
        if comp_key in self._details_groups:
            for elem in self._details_groups[comp_key]:
                if elem.alive():
                    elem.show()

        if comp_key == "Weapons":
            layout.rebuild_wizard_turret_list(self)

        # Update comp dropdown if needed
        if self._comp_dropdown and self._comp_dropdown.selected_option != meta["display_name"]:
            # avoid recursive events
            pass

        self._sync_cost_and_summary()

    def _add_turret(self) -> None:
        """Adds a configured turret to the weapons configuration list."""
        if self._turret_type_dd:
            raw = self._turret_type_dd.selected_option
            ttype = raw[0] if isinstance(raw, tuple) else str(raw)
        else:
            ttype = "MASS_DRIVER"

        if self._turret_variant_dd:
            raw_v = self._turret_variant_dd.selected_option
            tvar = raw_v[0] if isinstance(raw_v, tuple) else str(raw_v)
        else:
            tvar = "STANDARD"

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

        self._turrets.append({"type": ttype, "variant": tvar, "damage": dmg, "range": rng, "cooldown": cd})
        self._comp_config["turrets"] = self._turrets
        layout.rebuild_wizard_turret_list(self)
        self._sync_cost_and_summary()

    def _remove_turret(self, index: int) -> None:
        """Removes a turret at the given index."""
        if 0 <= index < len(self._turrets):
            self._turrets.pop(index)
            self._comp_config["turrets"] = self._turrets
            layout.rebuild_wizard_turret_list(self)
            self._sync_cost_and_summary()

    def _toggle_ability(self, ability_name: str) -> None:
        """Toggles an active special ability."""
        if ability_name in self._selected_abilities:
            self._selected_abilities.remove(ability_name)
        else:
            self._selected_abilities.add(ability_name)

        if ability_name in self._ability_buttons:
            btn = self._ability_buttons[ability_name]
            is_active = ability_name in self._selected_abilities
            btn.set_text(f"[{'X' if is_active else ' '}] {ability_name}")

        self._comp_config["ability_types"] = list(self._selected_abilities)
        self._sync_cost_and_summary()

    def _read_current_params(self) -> None:
        """Reads input parameters for the currently active component."""
        k = self._current_comp_key
        if k == "Engines":
            param_readers.read_engine_params(self)
        elif k == "AntimatterStorage":
            param_readers.read_antimatter_params(self)
        elif k == "Hyperdrive":
            param_readers.read_hyperdrive_params(self)
            if self._hd_type_dropdown:
                raw_hd = self._hd_type_dropdown.selected_option
                self._comp_config["drive_type"] = raw_hd[0] if isinstance(raw_hd, tuple) else str(raw_hd)
        elif k == "Weapons":
            self._comp_config["turrets"] = self._turrets
        elif k == "Defenses":
            param_readers.read_defense_params(self)
        elif k == "Sensors":
            param_readers.read_sensor_params(self)
        elif k == "StrikecraftBayComponent":
            param_readers.read_strikecraft_bay_params(self)
            if self._wt_dropdown:
                raw_wt = self._wt_dropdown.selected_option
                self._comp_config["wing_type"] = raw_wt[0] if isinstance(raw_wt, tuple) else str(raw_wt)
        elif k == "HangarComponent":
            param_readers.read_hangar_params(self)
        elif k == "RepairComponent":
            param_readers.read_repair_params(self)
        elif k == "MiningComponent":
            param_readers.read_mining_params(self)
        elif k == "HyperspaceInhibitionFieldEmitter":
            param_readers.read_inhibitor_params(self)
        elif k == "MarinesComponent":
            param_readers.read_marines_params(self)
        elif k == "CloakingDevice":
            param_readers.read_cloaking_params(self)
            if self._cloaking_type_dropdown:
                raw_c = self._cloaking_type_dropdown.selected_option
                self._comp_config["device_type"] = raw_c[0] if isinstance(raw_c, tuple) else str(raw_c)
        elif k == "AbilityComponent":
            self._comp_config["ability_types"] = list(self._selected_abilities)

    def _sync_cost_and_summary(self) -> None:
        """Recalculates hull cost, credits, build time, and updates summary UI elements."""
        self._read_current_params()
        self._comp_config.pop("hull_cost", None)

        hull_cost = get_component_hull_cost(self._current_comp_key, self.target_unit, self._comp_config)
        self.calculated_hull_cost = hull_cost
        self._comp_config["hull_cost"] = hull_cost

        cost_credits = int(round(hull_cost * COMPONENT_COST_PER_HULL_POINT))
        self.cost_credits = cost_credits

        time_to_build = max(1, int(round(hull_cost / 5.0)))
        self.time_to_build = time_to_build

        upkeep = hull_cost * UPKEEP_COST_PER_HULL_POINT

        curr_usage = self.target_unit.current_hull_usage if self.target_unit else 0.0
        cap = self.target_unit.hull_capacity if self.target_unit else 100.0
        projected = curr_usage + hull_cost
        pct = int((projected / cap) * 100) if cap > 0 else 0

        player = self.target_unit.owner if self.target_unit else None
        player_credits = player.credits if player else 0

        # Update Labels
        if self._hull_impact_label:
            self._hull_impact_label.set_text(f"Hull Usage: {projected:.1f} / {cap:.1f} HP ({pct}%)")
        if self._added_cost_label:
            self._added_cost_label.set_text(f"Component Hull: +{hull_cost:.1f} HP")
        if self._credit_cost_label:
            self._credit_cost_label.set_text(f"Credit Cost: {cost_credits} c")
        if self._player_credits_label:
            self._player_credits_label.set_text(f"Available Credits: {player_credits} c")
        if self._build_time_label:
            self._build_time_label.set_text(f"Est. Time to Build: {time_to_build} Turn{'s' if time_to_build > 1 else ''}")
        if self._upkeep_label:
            self._upkeep_label.set_text(f"Upkeep Impact: +{upkeep:.2f} cr/turn")

        # Check Validations
        is_over_cap = (projected > cap)
        is_over_budget = (player_credits < cost_credits)

        if is_over_cap:
            over_hp = projected - cap
            status_html = f"<font color='#FF5555'><b>⚠ Insufficient Hull Capacity</b><br>Exceeds available capacity by {over_hp:.1f} HP.</font>"
            self.is_valid = False
        elif is_over_budget:
            needed = cost_credits - player_credits
            status_html = f"<font color='#FF5555'><b>⚠ Insufficient Credits</b><br>Short by {needed} credits ({cost_credits} required).</font>"
            self.is_valid = False
        else:
            status_html = f"<font color='#55FF55'><b>✔ Ready to Install</b><br>Click 'Order Retrofit' to dispatch constructor.</font>"
            self.is_valid = True

        if self._status_box:
            self._status_box.set_text(status_html)

        if self._confirm_button:
            if not self.is_valid:
                self._confirm_button.disable()
            else:
                self._confirm_button.enable()

    def process_event(self, event: pygame.event.Event) -> Optional[Dict[str, Any]]:
        """Processes pygame events and returns an action payload if an action occurred."""
        if not self.is_visible or not self.window.alive():
            return None

        if event.type == pygame_gui.UI_WINDOW_CLOSE and event.ui_element == self.window:
            return {"action": "cancel_retrofit"}

        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            elem = event.ui_element

            if elem is self._cancel_button:
                return {"action": "cancel_retrofit"}

            elif elem is self._confirm_button:
                if self.is_valid:
                    return {
                        "action": "confirm_retrofit",
                        "target_unit": self.target_unit,
                        "constructor_units": self.constructor_units,
                        "component_type": self._current_comp_key,
                        "component_config": self._comp_config,
                        "cost_credits": self.cost_credits,
                        "time_to_build": self.time_to_build,
                        "shift_pressed": self.shift_pressed,
                    }
                return {"action": "ui_handled"}

            elif elem is self._add_turret_button:
                self._add_turret()
                return {"action": "ui_handled"}

            # Turret remove buttons
            for i, rbtn in enumerate(self._turret_remove_buttons):
                if elem is rbtn:
                    self._remove_turret(i)
                    return {"action": "ui_handled"}

            # Ability toggles
            for aname, abtn in self._ability_buttons.items():
                if elem is abtn:
                    self._toggle_ability(aname)
                    return {"action": "ui_handled"}

        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            elem = event.ui_element

            if elem is self._comp_dropdown:
                selected_label = event.text
                meta = next((c for c in RETROFIT_COMPONENTS if c["display_name"] == selected_label), None)
                if meta:
                    self.select_component(meta["comp_key"])
                return {"action": "ui_handled"}

            elif elem in (self._hd_type_dropdown, self._wt_dropdown, self._cloaking_type_dropdown):
                self._sync_cost_and_summary()
                return {"action": "ui_handled"}

        elif event.type == pygame_gui.UI_TEXT_ENTRY_CHANGED:
            self._sync_cost_and_summary()
            return {"action": "ui_handled"}

        return None

    def kill(self) -> None:
        """Closes and destroys the window and its child elements."""
        self.is_visible = False
        if self.window and self.window.alive():
            self.window.kill()
