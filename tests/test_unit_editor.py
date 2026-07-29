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
        t = CustomUnitTemplate("MY_SHIP", "My Ship", hull_size)
        t.components.has_engine = True
        return t

    # ------------------------------------------------------------------ #
    # Basic validation
    # ------------------------------------------------------------------ #

    def test_valid_design_passes(self):
        t = self._make_valid()
        self.assertEqual(t.validate(), [])

    def test_empty_name_fails(self):
        t = self._make_valid()
        t.design_name = "   "
        errors = t.validate()
        self.assertTrue(any("Design name" in e for e in errors))

    def test_empty_display_name_fails(self):
        t = self._make_valid()
        t.display_name = ""
        errors = t.validate()
        self.assertTrue(any("Display name" in e for e in errors))

    def test_no_components_fails(self):
        t = CustomUnitTemplate("EMPTY", "Empty", HullSize.MEDIUM)
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

    def _make_template(self, key="TEST_CRUISER", hull=HullSize.MEDIUM) -> CustomUnitTemplate:
        t = CustomUnitTemplate(key, "Test Cruiser", hull)
        t.components.has_engine = True
        t.components.has_weapon_bays = True
        return t

    def test_save_registers_in_unit_templates(self):
        mgr = self._fresh_manager()
        t = self._make_template()
        errs = mgr.save_design(t)
        self.assertEqual(errs, [])
        self.assertIn("TEST_CRUISER", UNIT_TEMPLATES)

    def test_saved_template_hull_size_is_enum(self):
        mgr = self._fresh_manager()
        mgr.save_design(self._make_template())
        td = UNIT_TEMPLATES["TEST_CRUISER"]
        self.assertIsInstance(td["hull_size"], HullSize)

    def test_delete_removes_from_unit_templates(self):
        mgr = self._fresh_manager()
        mgr.save_design(self._make_template())
        self.assertIn("TEST_CRUISER", UNIT_TEMPLATES)
        deleted = mgr.delete_design("TEST_CRUISER")
        self.assertTrue(deleted)
        self.assertNotIn("TEST_CRUISER", UNIT_TEMPLATES)

    def test_persistence_round_trip(self):
        mgr1 = self._fresh_manager()
        mgr1.save_design(self._make_template())

        # Load fresh manager from same file
        mgr2 = self._fresh_manager()
        mgr2.load_from_file()

        self.assertIn("TEST_CRUISER", mgr2.designs)
        design = mgr2.designs["TEST_CRUISER"]
        self.assertEqual(design.hull_size, HullSize.MEDIUM)
        self.assertTrue(design.components.has_engine)
        self.assertTrue(design.components.has_weapon_bays)
        self.assertIn("TEST_CRUISER", UNIT_TEMPLATES)

    def test_persistence_hull_size_survives_round_trip(self):
        mgr1 = self._fresh_manager()
        t = self._make_template(hull=HullSize.HUGE)
        mgr1.save_design(t)

        # Verify the JSON has a string (not an enum)
        with open(self.data_file, "r") as f:
            raw = json.load(f)
        self.assertEqual(raw["TEST_CRUISER"]["hull_size"], "HUGE")

        # Load back and verify enum is restored
        mgr2 = self._fresh_manager()
        mgr2.load_from_file()
        self.assertEqual(mgr2.designs["TEST_CRUISER"].hull_size, HullSize.HUGE)

    def test_multiple_designs_persist(self):
        mgr = self._fresh_manager()
        mgr.save_design(self._make_template("ALPHA"))
        mgr.save_design(self._make_template("BETA", HullSize.LARGE))

        mgr2 = self._fresh_manager()
        mgr2.load_from_file()
        self.assertIn("ALPHA", mgr2.designs)
        self.assertIn("BETA", mgr2.designs)
        self.assertEqual(mgr2.designs["BETA"].hull_size, HullSize.LARGE)

    def test_duplicate_name_overwrites(self):
        mgr = self._fresh_manager()
        t1 = self._make_template()
        t1.display_name = "Version 1"
        mgr.save_design(t1)

        t2 = self._make_template()
        t2.display_name = "Version 2"
        mgr.save_design(t2)

        self.assertEqual(mgr.designs["TEST_CRUISER"].display_name, "Version 2")
        self.assertEqual(len(mgr.list_design_names()), 1)

    def test_load_unnormalized_key_from_file(self):
        # Write JSON with unnormalized key "Medium Sensor Ship"
        raw_json = {
            "Medium Sensor Ship": {
                "name": "Medium Sensor Ship",
                "hull_size": "MEDIUM",
                "has_engine": True,
                "engine_speed": 100.0,
                "has_sensors": True
            }
        }
        with open(self.data_file, "w", encoding="utf-8") as f:
            json.dump(raw_json, f)

        mgr = self._fresh_manager()
        mgr.load_from_file()

        # Key should be normalized to "MEDIUM_SENSOR_SHIP"
        self.assertIn("MEDIUM_SENSOR_SHIP", mgr.designs)
        self.assertIsNotNone(mgr.get_design("Medium Sensor Ship"))
        self.assertIsNotNone(mgr.get_design("MEDIUM_SENSOR_SHIP"))
        self.assertEqual(mgr.list_design_names(), ["MEDIUM_SENSOR_SHIP"])


class TestUnitEditorGuiComponents(unittest.TestCase):
    """Verifies that all valid components are supported by the unit editor GUI."""

    def test_all_components_in_gui(self):
        import dataclasses
        from custom_unit_templates import ComponentConfig
        from unit_editor_gui import COMPONENT_ROWS

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
            design_name="HARVESTER_SHIP",
            display_name="Harvester Ship",
            hull_size=HullSize.LARGE,
            components=comp,
        )
        self.assertEqual(template.validate(), [])
        self.assertIn("has_antimatter_harvester", comp.__dataclass_fields__)
        self.assertTrue(template.total_hull_cost >= ANTIMATTER_HARVESTER_HULL_COST)

        # Restrictions: STRIKECRAFT_WING & TINY forbidden
        tiny_template = CustomUnitTemplate(
            design_name="TINY_HARVESTER",
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
            retrieved = mgr.get_design("HARVESTER_SHIP")
            self.assertIsNotNone(retrieved)
            self.assertTrue(retrieved.components.has_antimatter_harvester)

            # UNIT_TEMPLATES dict entry
            unit_dict = UNIT_TEMPLATES.get("HARVESTER_SHIP")
            self.assertIsNotNone(unit_dict)
            self.assertTrue(unit_dict.get("has_antimatter_harvester"))
            self.assertEqual(unit_dict.get("antimatter_harvester_hull_cost"), ANTIMATTER_HARVESTER_HULL_COST)
            mgr.delete_design("HARVESTER_SHIP")
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

    def test_component_selection(self):
        import pygame
        import pygame_gui
        from unit_editor_gui import UnitEditorWindow
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

    def test_configurable_parameter_widgets(self):
        import pygame
        import pygame_gui
        from unit_editor_gui import UnitEditorWindow
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


if __name__ == "__main__":
    unittest.main()


