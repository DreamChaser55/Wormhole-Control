"""
window.py

UnitEditorWindow class definition for the Unit Designer GUI overlay panel.
"""

import logging
import pygame
import pygame_gui
import typing

from constants import HullSize
from custom_unit_templates import CustomUnitTemplate, ComponentConfig, TurretConfig, CustomTemplateManager

from . import catalog
from . import widget_factory
from . import cost_model
from . import param_readers
from . import turret_editor
from . import component_state
from . import template_io
from . import summary_view
from . import event_handlers
from . import layout
from . import layout_details
from .save_dialog import SaveConfirmationDialog

logger = logging.getLogger(__name__)


class UnitEditorWindow:
    """
    Manages the Unit Designer overlay panel.

    Call :meth:`show` / :meth:`hide` to toggle visibility.
    Call :meth:`process_event` each frame to handle widget interactions.
    Call :meth:`draw` each frame to render custom pygame elements (capacity bar).
    The ``pygame_gui.UIManager`` handles all widget drawing automatically.
    """

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
        self._turrets: typing.List[TurretConfig] = []
        self._selected_abilities: typing.Set[str] = set()
        self._editing_name: typing.Optional[str] = None  # display name of design being edited
        self._save_dialog: typing.Optional[SaveConfirmationDialog] = None

        # --- Panel geometry ---
        panel_x = 20
        panel_w = max(100, int(screen_res.x) - 40)
        panel_h = int(screen_res.y * 0.88)
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
        self._comp_scroll_container: typing.Optional[pygame_gui.elements.UIScrollingContainer] = None
        self._comp_toggles: typing.Dict[str, pygame_gui.elements.UIButton] = {}
        self._comp_cost_labels: typing.Dict[str, pygame_gui.elements.UILabel] = {}
        self._comp_select_btns: typing.Dict[str, pygame_gui.elements.UIButton] = {}
        self._selected_component_key: typing.Optional[str] = "has_engine"
        self._details_groups: typing.Dict[str, typing.List[pygame_gui.core.UIElement]] = {}
        self._details_hdr: typing.Optional[pygame_gui.elements.UILabel] = None
        self._capacity_label: typing.Optional[pygame_gui.elements.UILabel] = None

        # Weapons sub-panel widgets
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

        # Right column
        self._display_entry: typing.Optional[pygame_gui.elements.UITextEntryLine] = None
        self._summary_box: typing.Optional[pygame_gui.elements.UITextBox] = None
        self._save_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self._save_as_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self._load_dd: typing.Optional[pygame_gui.elements.UIDropDownMenu] = None
        self._delete_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self._close_button: typing.Optional[pygame_gui.elements.UIButton] = None
        self._status_label: typing.Optional[pygame_gui.elements.UILabel] = None

        # Capacity bar rectangle (absolute screen coords for direct draw)
        self._cap_bar_rect: typing.Optional[pygame.Rect] = None

        self._build_ui()
        self.hide()

    def _build_ui(self) -> None:
        """Creates and lays out all child widgets inside the main unit designer panel."""
        layout.build_ui(self)

    def _build_col1_config(
        self, c1x: int, c1y: int, c1w: int, row_h: int, dd_h: int, entry_h: int, btn_h: int, pad: int, scale_y: float
    ) -> int:
        """Builds Column 1 configuration UI controls (Hull selection, design keys, file management)."""
        return layout.build_col1_config(self, c1x, c1y, c1w, row_h, dd_h, entry_h, btn_h, pad, scale_y)

    def _build_col2_components(
        self, c2x: int, c2y: int, c2w: int, row_h: int, small_h: int, pad: int
    ) -> int:
        """Builds Column 2 component selection UI controls (Toggles, selection arrows, cost labels)."""
        return layout.build_col2_components(self, c2x, c2y, c2w, row_h, small_h, pad)

    def _build_col3_details(
        self, c3x: int, c3y: int, c3w: int, row_h: int, small_h: int, dd_h: int, entry_h: int, btn_h: int, pad: int, scale_y: float
    ) -> int:
        """Builds Column 3 dynamic component detail controls (sub-option fields, turret list, ability toggles)."""
        return layout_details.build_col3_details(self, c3x, c3y, c3w, row_h, small_h, dd_h, entry_h, btn_h, pad, scale_y)

    def _build_col4_summary(
        self, c4x: int, c4y: int, c4w: int, row_h: int, pad: int, pr: pygame.Rect
    ) -> None:
        """Builds Column 4 design summary text box and layout container."""
        layout.build_col4_summary(self, c4x, c4y, c4w, row_h, pad, pr)

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
        if self._save_dialog:
            self._save_dialog.kill()
            self._save_dialog = None
        if self._panel:
            self._panel.hide()

    def kill(self) -> None:
        """Destroy all widgets."""
        if self._save_dialog:
            self._save_dialog.kill()
            self._save_dialog = None
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
        self._save_as_button = None

    def process_event(self, event: pygame.event.Event) -> typing.Optional[str]:
        """Process a pygame event."""
        return event_handlers.process_event(self, event)

    def draw(self, surface: pygame.Surface) -> None:
        """Draw any custom pygame elements (capacity bar)."""
        cost_model.draw_capacity_bar(self, surface)

    def _read_engine_params(self) -> None:
        """Reads engine speed from UI input field and updates component configuration."""
        param_readers.read_engine_params(self)

    def _read_antimatter_params(self) -> None:
        """Reads antimatter capacity from UI input field and updates component configuration."""
        param_readers.read_antimatter_params(self)

    def _read_hyperdrive_params(self) -> None:
        """Reads hyperdrive jump range from UI input field and updates component configuration."""
        param_readers.read_hyperdrive_params(self)

    def _read_defense_params(self) -> None:
        """Reads armor, shields, and point defense from UI input fields and updates component configuration."""
        param_readers.read_defense_params(self)

    def _read_sensor_params(self) -> None:
        """Reads short/long range sensor values from UI input fields and updates component configuration."""
        param_readers.read_sensor_params(self)

    def _read_repair_params(self) -> None:
        """Reads repair rate and range parameters from UI input fields and updates component configuration."""
        param_readers.read_repair_params(self)

    def _read_mining_params(self) -> None:
        """Reads mining rate, range, and cargo capacity from UI input fields and updates component configuration."""
        param_readers.read_mining_params(self)

    def _read_hangar_params(self) -> None:
        """Reads hangar slots count from UI input field and updates component configuration."""
        param_readers.read_hangar_params(self)

    def _read_strikecraft_bay_params(self) -> None:
        """Reads strikecraft bay slots count from UI input field and updates component configuration."""
        param_readers.read_strikecraft_bay_params(self)

    def _read_inhibitor_params(self) -> None:
        """Reads inhibitor radius from UI input field and updates component configuration."""
        param_readers.read_inhibitor_params(self)

    def _read_marines_params(self) -> None:
        """Reads marines count from UI input field and updates component configuration."""
        param_readers.read_marines_params(self)

    def _read_cloaking_params(self) -> None:
        """Reads cloaking radius from UI input field and updates component configuration."""
        param_readers.read_cloaking_params(self)

    def _read_intelligence_params(self) -> None:
        """Reads agent capacity from UI input field and updates component configuration."""
        param_readers.read_intelligence_params(self)


    def _current_hull_used(self) -> float:
        """Computes total hull points consumed by active/enabled components."""
        return cost_model.current_hull_used(self)

    def _sync_dynamic_costs(self) -> None:
        """Refreshes displayed hull cost labels for dynamic components and updates capacity indicators."""
        cost_model.sync_dynamic_costs(self)

    def _capacity_text(self) -> str:
        """Generates formatted display string comparing current used hull capacity to total max capacity."""
        return cost_model.capacity_text(self)

    def _update_capacity_label(self) -> None:
        """Updates capacity label text."""
        cost_model.update_capacity_label(self)

    def _toggle_component(self, key: str) -> None:
        """Toggles enabling or disabling a component while verifying hull size restrictions."""
        component_state.toggle_component(self, key)

    def _toggle_ability(self, aname: str) -> None:
        """Toggles selection of a special ability after verifying required component prerequisites."""
        component_state.toggle_ability(self, aname)

    def _update_component_toggle_labels(self) -> None:
        """Refreshes component toggle button text labels."""
        component_state.update_component_toggle_labels(self)

    def _update_ability_toggle_labels(self) -> None:
        """Refreshes ability toggle button text labels and enabled states."""
        component_state.update_ability_toggle_labels(self)

    def _on_hull_changed(self, hull_name: str) -> None:
        """Handles hull size dropdown changes."""
        component_state.on_hull_changed(self, hull_name)

    def _select_component(self, key: str) -> None:
        """Set the active component and update detail panel displays."""
        component_state.select_component(self, key)

    def _refresh_component_details(self) -> None:
        """Refresh visibility of component detail widgets based on selected component."""
        component_state.refresh_component_details(self)

    def _apply_hull_restrictions(self) -> None:
        """Disable forbidden components for the current hull size."""
        component_state.apply_hull_restrictions(self)

    def _hide_turret_list(self) -> None:
        """Hide active turret labels and remove buttons."""
        turret_editor.hide_turret_list(self)

    def _rebuild_turret_list(self) -> None:
        """Rebuild the turret list display labels and remove buttons."""
        turret_editor.rebuild_turret_list(self)

    def _do_add_turret(self) -> None:
        """Adds a new turret to the design configuration."""
        turret_editor.do_add_turret(self)

    def _do_save(self) -> typing.Optional[str]:
        """Saves current editor state as a template."""
        return template_io.do_save(self)

    def _do_save_as_new(self) -> typing.Optional[str]:
        """Saves current editor state as a new template without modifying original."""
        return template_io.do_save_as_new(self)

    def _do_delete(self) -> typing.Optional[str]:
        """Deletes the active unit design template."""
        return template_io.do_delete(self)

    def _sync_widgets_from_template(self, template: CustomUnitTemplate) -> None:
        """Synchronizes all UI text fields, dropdown menus, and toggle controls to match a unit template."""
        template_io.sync_widgets_from_template(self, template)

    def _load_design(self, key: str) -> None:
        """Loads a unit design template into the editor controls."""
        template_io.load_design(self, key)

    def _refresh_load_dropdown(self) -> None:
        """Rebuild the load dropdown list with current designs."""
        template_io.refresh_load_dropdown(self)

    def _update_summary(self) -> None:
        """Refresh the summary text box with current design stats."""
        summary_view.update_summary(self)

    def _set_status(self, msg: str, error: bool = False) -> None:
        """Updates status label text."""
        template_io.set_status(self, msg, error)
