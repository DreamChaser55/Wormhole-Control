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


class TestConstructorRefresh(unittest.TestCase):
    """Tests for Constructor.refresh_buildable_units."""

    def setUp(self):
        import custom_unit_templates as ctm
        self.tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        )
        self.tmp.write("{}")
        self.tmp.close()
        self._orig_data_file = ctm._DATA_FILE
        ctm._DATA_FILE = self.tmp.name

    def tearDown(self):
        import custom_unit_templates as ctm
        ctm._DATA_FILE = self._orig_data_file
        os.unlink(self.tmp.name)
        for k in list(UNIT_TEMPLATES.keys()):
            if UNIT_TEMPLATES[k].get("is_custom"):
                del UNIT_TEMPLATES[k]

    def test_refresh_adds_new_template(self):
        from unit_components import Constructor, BuildableUnit

        # Register a custom template in UNIT_TEMPLATES without a real Unit
        UNIT_TEMPLATES["CUSTOM_GUNSHIP"] = {
            "name": "Custom Gunship",
            "hull_size": HullSize.SMALL,
            "build_time": 5,
            "build_cost": 300,
            "is_custom": True,
        }

        class FakeUnit:
            name = "Shipyard"
            game = None

        fake_unit = FakeUnit()
        constructor = Constructor.__new__(Constructor)
        constructor.unit = fake_unit
        constructor.buildable_units = [
            BuildableUnit("BATTLESHIP_MEDIUM", 10, 500),
        ]
        constructor.current_construction_target = None
        constructor.time_to_build = 0
        constructor.construction_progress = 0
        constructor.current_hit_points = 100  # ensures is_destroyed == False
        constructor.max_hit_points = 100

        constructor.refresh_buildable_units(["CUSTOM_GUNSHIP"])
        names = {bu.unit_template_name for bu in constructor.buildable_units}
        self.assertIn("CUSTOM_GUNSHIP", names)

    def test_refresh_no_duplicates(self):
        from unit_components import Constructor, BuildableUnit

        UNIT_TEMPLATES["DUPE_TEST"] = {
            "name": "Dupe Test",
            "hull_size": HullSize.MEDIUM,
            "build_time": 5,
            "build_cost": 400,
            "is_custom": True,
        }

        class FakeUnit:
            name = "Shipyard"
            game = None

        fake_unit = FakeUnit()
        constructor = Constructor.__new__(Constructor)
        constructor.unit = fake_unit
        constructor.buildable_units = [
            BuildableUnit("BATTLESHIP_MEDIUM", 10, 500),
            BuildableUnit("DUPE_TEST", 5, 400),  # already present
        ]
        constructor.current_construction_target = None
        constructor.time_to_build = 0
        constructor.construction_progress = 0
        constructor.current_hit_points = 100  # ensures is_destroyed == False
        constructor.max_hit_points = 100

        constructor.refresh_buildable_units(["DUPE_TEST"])
        count = sum(1 for bu in constructor.buildable_units if bu.unit_template_name == "DUPE_TEST")
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
