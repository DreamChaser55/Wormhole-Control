"""
tests/test_unit_editor.py

Unit tests for the custom unit template system:
  - CustomUnitTemplate validation (capacity, hull-size restrictions)
  - Save / delete / load-from-file persistence round-trip
  - UNIT_TEMPLATES registration
  - Constructor.refresh_buildable_units integration
"""

import json
import os
import sys
import tempfile
import unittest

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from constants import HullSize
from custom_unit_templates import (
    CustomTemplateManager,
    CustomUnitTemplate,
    ComponentConfig,
    TurretConfig,
    HULL_RESTRICTIONS,
    ADVANCED_HYPERDRIVE_MIN_HULL,
)
from unit_templates import UNIT_TEMPLATES


def _make_manager(data_file: str) -> CustomTemplateManager:
    """Return a CustomTemplateManager that uses a temporary data file."""
    mgr = CustomTemplateManager()
    # Monkey-patch the module-level _DATA_FILE used by the manager's methods
    import custom_unit_templates as ctm
    ctm._DATA_FILE = data_file
    return mgr


class TestCustomUnitTemplateValidation(unittest.TestCase):
    """Tests for CustomUnitTemplate.validate()."""

    def _make_valid(self, hull_size=HullSize.MEDIUM) -> CustomUnitTemplate:
        t = CustomUnitTemplate("My Ship", hull_size)
        t.components.has_engine = True
        return t

    # ------------------------------------------------------------------ #
    # Basic validation
    # ------------------------------------------------------------------ #

    def test_valid_design_passes(self):
        t = self._make_valid()
        self.assertEqual(t.validate(), [])

    def test_empty_display_name_fails(self):
        t = self._make_valid()
        t.display_name = ""
        errors = t.validate()
        self.assertTrue(any("Display name" in e for e in errors))

    def test_whitespace_display_name_fails(self):
        t = self._make_valid()
        t.display_name = "   "
        errors = t.validate()
        self.assertTrue(any("Display name" in e for e in errors))

    def test_no_components_fails(self):
        t = CustomUnitTemplate("Empty", HullSize.MEDIUM)
        errors = t.validate()
        self.assertTrue(any("component" in e.lower() for e in errors))

    def test_over_capacity_fails(self):
        t = self._make_valid(HullSize.TINY)  # TINY capacity = 20
        c = t.components
        # Fill up way past TINY capacity (20)
        c.has_engine = True               # +5
        c.has_weapon_bays = True          # +10
        c.has_repair_component = True     # +15  → total 30, over 20
        errors = t.validate()
        self.assertTrue(any("capacity" in e.lower() for e in errors))

    # ------------------------------------------------------------------ #
    # Hull-size restrictions
    # ------------------------------------------------------------------ #

    def test_tiny_can_have_basic_hyperdrive(self):
        t = self._make_valid(HullSize.TINY)
        t.components.has_hyperdrive = True
        t.components.hyperdrive_type = "BASIC"
        errors = t.validate()
        self.assertFalse(any("hyperdrive" in e.lower() for e in errors))

    def test_tiny_cannot_have_advanced_hyperdrive(self):
        t = self._make_valid(HullSize.TINY)
        t.components.has_hyperdrive = True
        t.components.hyperdrive_type = "ADVANCED"
        errors = t.validate()
        self.assertTrue(any("advanced hyperdrive" in e.lower() for e in errors))

    def test_tiny_cannot_have_inhibitor(self):
        t = self._make_valid(HullSize.TINY)
        t.components.has_inhibitor = True
        errors = t.validate()
        self.assertTrue(any("inhibitor" in e.lower() for e in errors))

    def test_small_can_have_advanced_hyperdrive(self):
        t = self._make_valid(HullSize.SMALL)
        t.components.has_hyperdrive = True
        t.components.hyperdrive_type = "ADVANCED"
        self.assertEqual(t.validate(), [])

    def test_small_can_have_basic_hyperdrive(self):
        t = self._make_valid(HullSize.SMALL)
        t.components.has_hyperdrive = True
        t.components.hyperdrive_type = "BASIC"
        self.assertEqual(t.validate(), [])

    def test_medium_can_have_advanced_hyperdrive(self):
        t = self._make_valid(HullSize.MEDIUM)
        t.components.has_hyperdrive = True
        t.components.hyperdrive_type = "ADVANCED"
        self.assertEqual(t.validate(), [])

    def test_medium_cannot_have_hangar(self):
        t = self._make_valid(HullSize.MEDIUM)
        t.components.has_hangar = True
        errors = t.validate()
        self.assertTrue(any("hangar" in e.lower() for e in errors))

    def test_large_can_have_hangar(self):
        t = self._make_valid(HullSize.LARGE)
        t.components.has_hangar = True
        self.assertEqual(t.validate(), [])

    def test_huge_can_have_hangar(self):
        t = self._make_valid(HullSize.HUGE)
        t.components.has_hangar = True
        self.assertEqual(t.validate(), [])

    def test_small_cannot_have_strikecraft_bay(self):
        t = self._make_valid(HullSize.SMALL)
        t.components.has_strikecraft_bay = True
        errors = t.validate()
        self.assertTrue(any("strikecraft" in e.lower() for e in errors) or any("bay" in e.lower() for e in errors))

    def test_medium_can_have_strikecraft_bay(self):
        t = self._make_valid(HullSize.MEDIUM)
        t.components.has_strikecraft_bay = True
        self.assertEqual(t.validate(), [])

    # ------------------------------------------------------------------ #
    # Build cost / build time
    # ------------------------------------------------------------------ #

    def test_build_cost_increases_with_components(self):
        t_bare = self._make_valid(HullSize.MEDIUM)
        t_loaded = self._make_valid(HullSize.MEDIUM)
        t_loaded.components.has_weapon_bays = True
        t_loaded.components.has_repair_component = True
        self.assertGreater(t_loaded.build_cost, t_bare.build_cost)

    def test_build_time_increases_with_components(self):
        t_bare = self._make_valid(HullSize.MEDIUM)
        t_loaded = self._make_valid(HullSize.MEDIUM)
        for _ in range(10):
            t_loaded.components.has_weapon_bays = True
            t_loaded.components.has_repair_component = True
        self.assertGreaterEqual(t_loaded.build_time, t_bare.build_time)


class TestCustomTemplateManagerPersistence(unittest.TestCase):
    """Tests for save / load round-trip and UNIT_TEMPLATES registration."""

    def setUp(self):
        # Use a temporary file so tests don't pollute the real data file
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        self.tmp.write("{}")
        self.tmp.close()
        self.data_file = self.tmp.name
        import custom_unit_templates as ctm
        self._orig_data_file = ctm._DATA_FILE
        ctm._DATA_FILE = self.data_file

    def tearDown(self):
        import custom_unit_templates as ctm
        ctm._DATA_FILE = self._orig_data_file
        os.unlink(self.data_file)
        # Clean up any templates we inserted into UNIT_TEMPLATES
        for k in list(UNIT_TEMPLATES.keys()):
            if UNIT_TEMPLATES[k].get("is_custom"):
                del UNIT_TEMPLATES[k]

    def _fresh_manager(self) -> CustomTemplateManager:
        return CustomTemplateManager()

    def _make_template(self, name="Test Cruiser", hull=HullSize.MEDIUM) -> CustomUnitTemplate:
        t = CustomUnitTemplate(name, hull)
        t.components.has_engine = True
        t.components.has_weapon_bays = True
        return t

    def test_save_registers_in_unit_templates(self):
        mgr = self._fresh_manager()
        t = self._make_template()
        errs = mgr.save_design(t)
        self.assertEqual(errs, [])
        self.assertIn("Test Cruiser", UNIT_TEMPLATES)

    def test_saved_template_hull_size_is_enum(self):
        mgr = self._fresh_manager()
        mgr.save_design(self._make_template())
        td = UNIT_TEMPLATES["Test Cruiser"]
        self.assertIsInstance(td["hull_size"], HullSize)

    def test_delete_removes_from_unit_templates(self):
        mgr = self._fresh_manager()
        mgr.save_design(self._make_template())
        self.assertIn("Test Cruiser", UNIT_TEMPLATES)
        deleted = mgr.delete_design("Test Cruiser")
        self.assertTrue(deleted)
        self.assertNotIn("Test Cruiser", UNIT_TEMPLATES)

    def test_persistence_round_trip(self):
        mgr1 = self._fresh_manager()
        mgr1.save_design(self._make_template())

        # Load fresh manager from same file
        mgr2 = self._fresh_manager()
        mgr2.load_from_file()

        self.assertIn("Test Cruiser", mgr2.designs)
        design = mgr2.designs["Test Cruiser"]
        self.assertEqual(design.hull_size, HullSize.MEDIUM)
        self.assertTrue(design.components.has_engine)
        self.assertTrue(design.components.has_weapon_bays)
        self.assertIn("Test Cruiser", UNIT_TEMPLATES)

    def test_persistence_hull_size_survives_round_trip(self):
        mgr1 = self._fresh_manager()
        t = self._make_template(hull=HullSize.HUGE)
        mgr1.save_design(t)

        # Verify the JSON has a string (not an enum)
        with open(self.data_file, "r") as f:
            raw = json.load(f)
        self.assertEqual(raw["Test Cruiser"]["hull_size"], "HUGE")

        # Load back and verify enum is restored
        mgr2 = self._fresh_manager()
        mgr2.load_from_file()
        self.assertEqual(mgr2.designs["Test Cruiser"].hull_size, HullSize.HUGE)

    def test_multiple_designs_persist(self):
        mgr = self._fresh_manager()
        mgr.save_design(self._make_template("Alpha"))
        mgr.save_design(self._make_template("Beta", HullSize.LARGE))

        mgr2 = self._fresh_manager()
        mgr2.load_from_file()
        self.assertIn("Alpha", mgr2.designs)
        self.assertIn("Beta", mgr2.designs)
        self.assertEqual(mgr2.designs["Beta"].hull_size, HullSize.LARGE)

    def test_duplicate_name_rejected_when_new(self):
        mgr = self._fresh_manager()
        t1 = self._make_template("Duplicate Ship")
        err1 = mgr.save_design(t1)
        self.assertEqual(err1, [])

        t2 = self._make_template("Duplicate Ship")
        err2 = mgr.save_design(t2)
        self.assertTrue(any("already exists" in e for e in err2))
        self.assertEqual(len(mgr.list_design_names()), 1)

    def test_edit_existing_name_succeeds(self):
        mgr = self._fresh_manager()
        t1 = self._make_template("Original Ship")
        err1 = mgr.save_design(t1)
        self.assertEqual(err1, [])

        # Edit with same name
        t1.components.has_hyperdrive = True
        err2 = mgr.save_design(t1, original_name="Original Ship")
        self.assertEqual(err2, [])
        self.assertEqual(len(mgr.list_design_names()), 1)
        self.assertTrue(mgr.designs["Original Ship"].components.has_hyperdrive)

    def test_rename_design_updates_key_and_unit_templates(self):
        mgr = self._fresh_manager()
        t1 = self._make_template("Old Name")
        mgr.save_design(t1)
        self.assertIn("Old Name", mgr.designs)
        self.assertIn("Old Name", UNIT_TEMPLATES)

        t1.display_name = "New Name"
        err = mgr.save_design(t1, original_name="Old Name")
        self.assertEqual(err, [])
        self.assertNotIn("Old Name", mgr.designs)
        self.assertNotIn("Old Name", UNIT_TEMPLATES)
        self.assertIn("New Name", mgr.designs)
        self.assertIn("New Name", UNIT_TEMPLATES)

    def test_duplicate_name_case_insensitive_rejected(self):
        mgr = self._fresh_manager()
        t1 = self._make_template("Duplicate Ship")
        err1 = mgr.save_design(t1)
        self.assertEqual(err1, [])

        t2 = self._make_template("duplicate ship")
        err2 = mgr.save_design(t2)
        self.assertTrue(any("already exists" in e for e in err2))
        self.assertEqual(len(mgr.list_design_names()), 1)

    def test_duplicate_builtin_template_name_rejected(self):
        mgr = self._fresh_manager()
        t = self._make_template("Shipyard Mk.I")
        err = mgr.save_design(t)
        self.assertTrue(any("already exists" in e for e in err))
        self.assertEqual(len(mgr.list_design_names()), 0)

    def test_rename_to_existing_name_rejected(self):
        mgr = self._fresh_manager()
        t1 = self._make_template("Ship A")
        mgr.save_design(t1)
        t2 = self._make_template("Ship B")
        mgr.save_design(t2)

        t2.display_name = "Ship A"
        err = mgr.save_design(t2, original_name="Ship B")
        self.assertTrue(any("already exists" in e for e in err))
        self.assertIn("Ship B", mgr.designs)
        self.assertIn("Ship A", mgr.designs)

    def test_case_insensitive_lookup_and_delete(self):
        mgr = self._fresh_manager()
        t = self._make_template("Medium Sensor Ship")
        mgr.save_design(t)

        self.assertIsNotNone(mgr.get_design("medium sensor ship"))
        self.assertIsNotNone(mgr.get_design("MEDIUM SENSOR SHIP"))
        self.assertEqual(mgr.list_design_names(), ["Medium Sensor Ship"])
        self.assertTrue(mgr.delete_design("medium sensor ship"))
        self.assertEqual(len(mgr.list_design_names()), 0)


class TestUnitEditorGuiComponents(unittest.TestCase):
    """Verifies that all valid components are supported by the unit editor GUI."""

    def test_all_components_in_gui(self):
        import dataclasses
        from custom_unit_templates import ComponentConfig
        from gui.unit_editor_gui import COMPONENT_ROWS

        gui_keys = {row["key"] for row in COMPONENT_ROWS}
        config_keys = {f.name for f in dataclasses.fields(ComponentConfig) if f.name.startswith("has_")}

        self.assertEqual(config_keys, gui_keys)

    def test_antimatter_harvester_custom_template(self):
        from constants import HullSize, ANTIMATTER_HARVESTER_HULL_COST
        from custom_unit_templates import ComponentConfig, CustomUnitTemplate
        from unit_templates import UNIT_TEMPLATES

        # Hull cost calculation includes harvester cost (15)
        comp = ComponentConfig(has_antimatter_storage=True, antimatter_capacity=150.0, has_antimatter_harvester=True)
        template = CustomUnitTemplate(
            display_name="Harvester Ship",
            hull_size=HullSize.LARGE,
            components=comp,
        )
        self.assertEqual(template.validate(), [])
        self.assertIn("has_antimatter_harvester", comp.__dataclass_fields__)
        self.assertTrue(template.total_hull_cost >= ANTIMATTER_HARVESTER_HULL_COST)

        # Restrictions: STRIKECRAFT_WING & TINY forbidden
        tiny_template = CustomUnitTemplate(
            display_name="Tiny Harvester",
            hull_size=HullSize.TINY,
            components=comp,
        )
        errors = tiny_template.validate()
        self.assertTrue(any("has_antimatter_harvester" in e for e in errors))

        # Persistence & Dict conversion using temporary data file
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        tmp.close()
        try:
            mgr = _make_manager(tmp.name)
            save_errors = mgr.save_design(template)
            self.assertEqual(save_errors, [])
            retrieved = mgr.get_design("Harvester Ship")
            self.assertIsNotNone(retrieved)
            self.assertTrue(retrieved.components.has_antimatter_harvester)

            # UNIT_TEMPLATES dict entry
            unit_dict = UNIT_TEMPLATES.get("Harvester Ship")
            self.assertIsNotNone(unit_dict)
            self.assertTrue(unit_dict.get("has_antimatter_harvester"))
            self.assertEqual(unit_dict.get("antimatter_harvester_hull_cost"), ANTIMATTER_HARVESTER_HULL_COST)
            mgr.delete_design("Harvester Ship")
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)


class TestUnitEditorWindowSelection(unittest.TestCase):
    """Unit tests for UnitEditorWindow component selection & dynamic details UI."""

    @classmethod
    def setUpClass(cls):
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        import pygame
        pygame.init()
        pygame.display.set_mode((1280, 720))

    def setUp(self):
        import tempfile
        import custom_unit_templates as ctm
        self._temp_data_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self._temp_data_file.close()
        self._orig_data_file = ctm._DATA_FILE
        ctm._DATA_FILE = self._temp_data_file.name

    def tearDown(self):
        import custom_unit_templates as ctm
        ctm._DATA_FILE = self._orig_data_file
        if os.path.exists(self._temp_data_file.name):
            os.remove(self._temp_data_file.name)

    def test_component_selection(self):
        import pygame
        import pygame_gui
        from gui.unit_editor_gui import UnitEditorWindow
        from custom_unit_templates import CustomTemplateManager

        mgr = pygame_gui.UIManager((1280, 720))
        tmp_mgr = CustomTemplateManager()
        win = UnitEditorWindow(mgr, pygame.Vector2(1280, 720), tmp_mgr)

        # Default selected component is "has_engine"
        self.assertEqual(win._selected_component_key, "has_engine")
        self.assertIn("has_engine", win._comp_select_btns)
        self.assertEqual(win._comp_select_btns["has_engine"].text, "▶▶▶")

        # Select "has_hyperdrive" via _select_component
        win._select_component("has_hyperdrive")
        self.assertEqual(win._selected_component_key, "has_hyperdrive")
        self.assertEqual(win._details_hdr.text, "Details: Hyperdrive")
        self.assertEqual(win._comp_select_btns["has_hyperdrive"].text, "▶▶▶")
        self.assertEqual(win._comp_select_btns["has_engine"].text, ">>>")

        # Select "has_weapon_bays"
        win._select_component("has_weapon_bays")
        self.assertEqual(win._selected_component_key, "has_weapon_bays")
        self.assertEqual(win._details_hdr.text, "Details: Weapons")

        win.kill()

    def test_add_turret_button_event(self):
        import pygame
        import pygame_gui
        from gui.unit_editor_gui import UnitEditorWindow
        from custom_unit_templates import CustomTemplateManager

        mgr = pygame_gui.UIManager((1280, 720))
        tmp_mgr = CustomTemplateManager()
        win = UnitEditorWindow(mgr, pygame.Vector2(1280, 720), tmp_mgr)
        win.show()

        # Ensure Add Turret button exists
        self.assertIsNotNone(win._add_turret_button)
        initial_turret_count = len(win._turrets)

        # Simulate clicking the Add Turret button
        event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": win._add_turret_button})
        result = win.process_event(event)

        self.assertEqual(result, "ui_handled")
        self.assertEqual(len(win._turrets), initial_turret_count + 1)
        win.kill()

    def test_configurable_parameter_widgets(self):
        import pygame
        import pygame_gui
        from gui.unit_editor_gui import UnitEditorWindow
        from custom_unit_templates import CustomTemplateManager

        mgr = pygame_gui.UIManager((1280, 720))
        tmp_mgr = CustomTemplateManager()
        win = UnitEditorWindow(mgr, pygame.Vector2(1280, 720), tmp_mgr)

        # Verify entry widgets exist and contain default text
        self.assertIsNotNone(win._repair_rate_entry)
        self.assertEqual(win._repair_rate_entry.get_text(), "10")
        self.assertIsNotNone(win._mining_rate_entry)
        self.assertEqual(win._mining_rate_entry.get_text(), "10")
        self.assertIsNotNone(win._hangar_slots_entry)
        self.assertEqual(win._hangar_slots_entry.get_text(), "2")
        self.assertIsNotNone(win._strikecraft_bay_slots_entry)
        self.assertEqual(win._strikecraft_bay_slots_entry.get_text(), "2")
        self.assertIsNotNone(win._inhibitor_radius_entry)
        self.assertEqual(win._inhibitor_radius_entry.get_text(), "100")

        # Test parameter reading from modified entries
        win._repair_rate_entry.set_text("25")
        win._repair_range_entry.set_text("300")
        win._read_repair_params()
        self.assertEqual(win._comp.repair_rate, 25.0)
        self.assertEqual(win._comp.repair_range, 300.0)

        win._mining_rate_entry.set_text("15")
        win._mining_range_entry.set_text("250")
        win._mining_max_cargo_entry.set_text("200")
        win._read_mining_params()
        self.assertEqual(win._comp.mining_rate, 15.0)
        self.assertEqual(win._comp.mining_range, 250.0)
        self.assertEqual(win._comp.max_mining_cargo, 200.0)

        win._hangar_slots_entry.set_text("4")
        win._read_hangar_params()
        self.assertEqual(win._comp.hangar_slots, 4)

        win._strikecraft_bay_slots_entry.set_text("3")
        win._read_strikecraft_bay_params()
        self.assertEqual(win._comp.strikecraft_bay_slots, 3)

        win._inhibitor_radius_entry.set_text("150")
        win._read_inhibitor_params()
        self.assertEqual(win._comp.inhibitor_radius, 150.0)

        win.kill()

    def test_ability_requires_component_validation_fails(self):
        """Validation fails if an ability is equipped without its required component."""
        t = CustomUnitTemplate("Test Ability Fail", HullSize.MEDIUM)
        t.components.has_engine = True
        t.components.has_ability_component = True
        t.components.abilities = ["adaptive_forcefield"]  # Requires has_defenses
        t.components.has_defenses = False
        errors = t.validate()
        self.assertTrue(any("Adaptive Forcefield" in e and "has_defenses" in e for e in errors))

    def test_ability_requires_component_validation_passes(self):
        """Validation passes if an ability is equipped with its required component."""
        t = CustomUnitTemplate("Test Ability Pass", HullSize.MEDIUM)
        t.components.has_engine = True
        t.components.has_ability_component = True
        t.components.abilities = ["adaptive_forcefield"]  # Requires has_defenses
        t.components.has_defenses = True
        t.components.armor = 5
        errors = t.validate()
        self.assertFalse(any("Adaptive Forcefield" in e for e in errors))

    def test_capture_unit_requires_marines_component(self):
        """Capture Unit ability requires has_marines_component."""
        t = CustomUnitTemplate("Test Capture Unit", HullSize.MEDIUM)
        t.components.has_engine = True
        t.components.has_ability_component = True
        t.components.abilities = ["capture_unit"]
        errors = t.validate()
        self.assertTrue(any("Capture Unit" in e and "has_marines_component" in e for e in errors))

        t.components.has_marines_component = True
        t.components.marines_count = 10
        errors = t.validate()
        self.assertFalse(any("Capture Unit" in e for e in errors))

    def test_load_design_dropdown_visibility(self):
        """Verifies loading a design with hyperdrive unselected keeps hyperdrive dropdown hidden."""
        import pygame
        import pygame_gui
        from gui.unit_editor_gui import UnitEditorWindow
        from custom_unit_templates import CustomTemplateManager

        mgr = pygame_gui.UIManager((1280, 720))
        tmp_mgr = CustomTemplateManager()
        win = UnitEditorWindow(mgr, pygame.Vector2(1280, 720), tmp_mgr)
        win.show()

        t = CustomUnitTemplate("Test Design", HullSize.MEDIUM)
        t.components.has_engine = True
        win._sync_widgets_from_template(t)
        win._select_component("has_engine")

        self.assertFalse(win._hd_type_dropdown.visible)
        self.assertIn(win._hd_type_dropdown, win._details_groups["has_hyperdrive"])
        self.assertIn(win._hd_type_dropdown, win._elements)

        win.kill()

    def test_recreated_dropdown_tab_switching(self):
        """Verifies component tab switching correctly toggles visibility of recreated dropdowns."""
        import pygame
        import pygame_gui
        from gui.unit_editor_gui import UnitEditorWindow
        from custom_unit_templates import CustomTemplateManager

        mgr = pygame_gui.UIManager((1280, 720))
        tmp_mgr = CustomTemplateManager()
        win = UnitEditorWindow(mgr, pygame.Vector2(1280, 720), tmp_mgr)
        win.show()

        t = CustomUnitTemplate("Test Design", HullSize.MEDIUM)
        t.components.has_engine = True
        t.components.has_hyperdrive = True
        win._sync_widgets_from_template(t)

        win._select_component("has_hyperdrive")
        self.assertTrue(win._hd_type_dropdown.visible)

        win._select_component("has_engine")
        self.assertFalse(win._hd_type_dropdown.visible)

        win.kill()

    def test_component_buttons_fit_panel_bounds(self):
        """Verifies that component buttons are placed in UIScrollingContainer with full height."""
        import pygame
        import pygame_gui
        from gui.unit_editor_gui import UnitEditorWindow
        from custom_unit_templates import CustomTemplateManager

        mgr = pygame_gui.UIManager((1280, 720))
        tmp_mgr = CustomTemplateManager()
        win = UnitEditorWindow(mgr, pygame.Vector2(1280, 720), tmp_mgr)

        self.assertIsNotNone(win._comp_scroll_container)
        self.assertTrue(isinstance(win._comp_scroll_container, pygame_gui.elements.UIScrollingContainer))

        for key, btn in win._comp_toggles.items():
            self.assertGreaterEqual(btn.relative_rect.h, 24, f"Component button {key} height is too small: {btn.relative_rect.h}")
            self.assertEqual(btn.ui_container, win._comp_scroll_container.get_container())

        win.kill()

    def test_summary_view_nested_parameters(self):
        """Verifies that component parameters in the design summary are nested directly beneath component lines."""
        import pygame
        import pygame_gui
        from gui.unit_editor_gui import UnitEditorWindow
        from custom_unit_templates import CustomTemplateManager

        mgr = pygame_gui.UIManager((1280, 720))
        tmp_mgr = CustomTemplateManager()
        win = UnitEditorWindow(mgr, pygame.Vector2(1280, 720), tmp_mgr)
        win.show()

        c = win._comp
        c.has_engine = True
        c.engine_speed = 150.0

        c.has_hyperdrive = True
        c.hyperdrive_type = "BASIC"
        c.hyperdrive_jump_range = 7

        c.has_defenses = True
        c.armor = 25
        c.shields = 30
        c.point_defense = 5

        win._update_summary()

        summary_text = win._summary_box.html_text

        # Verify Engines line and nested speed line
        eng_pos = summary_text.find("Engines")
        speed_pos = summary_text.find("speed=150")
        hd_pos = summary_text.find("Hyperdrive")
        hd_detail_pos = summary_text.find("type=BASIC  jump_range=7")
        def_pos = summary_text.find("Defenses")
        def_detail_pos = summary_text.find("armor=25  shields=30  PD=5")

        self.assertNotEqual(eng_pos, -1)
        self.assertNotEqual(speed_pos, -1)
        self.assertNotEqual(hd_pos, -1)
        self.assertNotEqual(hd_detail_pos, -1)
        self.assertNotEqual(def_pos, -1)
        self.assertNotEqual(def_detail_pos, -1)

        # Confirm order: Engines < speed=150 < Hyperdrive < type=BASIC... < Defenses < armor=25...
        self.assertTrue(eng_pos < speed_pos < hd_pos < hd_detail_pos < def_pos < def_detail_pos)

        win.kill()

    def test_save_as_button_exists_and_layout(self):
        """Verifies that the Save as New button exists in Column 1 and is properly positioned."""
        import pygame
        import pygame_gui
        from gui.unit_editor_gui import UnitEditorWindow
        from custom_unit_templates import CustomTemplateManager

        mgr = pygame_gui.UIManager((1280, 720))
        tmp_mgr = CustomTemplateManager()
        win = UnitEditorWindow(mgr, pygame.Vector2(1280, 720), tmp_mgr)

        self.assertIsNotNone(win._save_as_button)
        self.assertIsInstance(win._save_as_button, pygame_gui.elements.UIButton)
        self.assertIn("Save as New", win._save_as_button.text)

        # Ensure Save As New is vertically positioned between Save Design and Delete Design
        self.assertGreater(win._save_as_button.relative_rect.y, win._save_button.relative_rect.y)
        self.assertLess(win._save_as_button.relative_rect.y, win._delete_button.relative_rect.y)

        win.kill()

    def test_save_as_new_creates_independent_template(self):
        """Verifies that _do_save_as_new saves a new template without modifying loaded template."""
        import pygame
        import pygame_gui
        from gui.unit_editor_gui import UnitEditorWindow
        from custom_unit_templates import CustomTemplateManager, CustomUnitTemplate, ComponentConfig

        mgr = pygame_gui.UIManager((1280, 720))
        tmp_mgr = CustomTemplateManager()
        win = UnitEditorWindow(mgr, pygame.Vector2(1280, 720), tmp_mgr)
        win.show()

        # Save an initial template
        t1 = CustomUnitTemplate("Frigate Alpha", HullSize.MEDIUM, ComponentConfig(has_engine=True, engine_speed=80.0))
        tmp_mgr.save_design(t1)

        # Load it into editor
        win._sync_widgets_from_template(t1)
        self.assertEqual(win._editing_name, "Frigate Alpha")

        # Modify parameters and name
        win._engine_speed_entry.set_text("130")
        win._display_entry.set_text("Frigate Alpha Mk II")

        # Call _do_save_as_new
        res = win._do_save_as_new()
        self.assertEqual(res, "design_saved")

        # Verify Frigate Alpha remains untouched
        orig = tmp_mgr.get_design("Frigate Alpha")
        self.assertIsNotNone(orig)
        self.assertEqual(orig.components.engine_speed, 80.0)

        # Verify Frigate Alpha Mk II exists with modified parameters
        new_copy = tmp_mgr.get_design("Frigate Alpha Mk II")
        self.assertIsNotNone(new_copy)
        self.assertEqual(new_copy.components.engine_speed, 130.0)

        # Cleanup
        tmp_mgr.delete_design("Frigate Alpha")
        tmp_mgr.delete_design("Frigate Alpha Mk II")
        win.kill()


if __name__ == "__main__":
    unittest.main()




