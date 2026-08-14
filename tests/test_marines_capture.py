import unittest
from unittest.mock import MagicMock, patch

from constants import HullSize
from custom_unit_templates import (
    CustomUnitTemplate, ComponentConfig, calc_marines_hull_cost, MARINES_HULL_COST_PER_MARINE
)
from unit_components import (
    MarinesComponent, AbilityComponent, AbilityType, Defenses, Engines, Weapons
)
from unit_components.abilities.capture_unit import CaptureUnitAbility


class TestMarinesComponent(unittest.TestCase):
    def test_marines_hull_cost(self):
        self.assertEqual(calc_marines_hull_cost(0), 0.0)
        self.assertEqual(calc_marines_hull_cost(10), 10.0 * MARINES_HULL_COST_PER_MARINE)

    def test_marines_component_initialization(self):
        unit_mock = MagicMock()
        comp = MarinesComponent(unit_mock, marines_count=15, hull_cost=15.0)
        self.assertEqual(comp.marines_count, 15)
        self.assertEqual(comp.hull_cost, 15.0)
        d = comp.to_dict()
        self.assertEqual(d["marines_count"], 15)
        self.assertEqual(d["hull_cost"], 15.0)

    def test_strikecraft_restriction(self):
        t = CustomUnitTemplate("Scout Wing", HullSize.STRIKECRAFT_WING)
        t.components.has_engine = True
        t.components.has_marines_component = True
        errors = t.validate()
        self.assertTrue(any("has_marines_component" in e for e in errors))

    def test_template_validation_marines_count(self):
        t = CustomUnitTemplate("Boarder Frigate", HullSize.MEDIUM)
        t.components.has_engine = True
        t.components.has_marines_component = True
        t.components.marines_count = 0
        errors = t.validate()
        self.assertTrue(any("Marines count must be at least 1" in e for e in errors))

        t.components.marines_count = 10
        errors = t.validate()
        self.assertFalse(any("Marines count" in e for e in errors))


class TestCaptureUnitWithMarines(unittest.TestCase):
    def setUp(self):
        self.galaxy = MagicMock()
        self.capturing_player = MagicMock(id=1)
        self.enemy_player = MagicMock(id=2)

        # Capturing unit setup
        self.capturing_unit = MagicMock()
        self.capturing_unit.name = "Capturing Ship"
        self.capturing_unit.owner = self.capturing_player

        # Target unit setup (disabled & defenseless)
        self.target_unit = MagicMock()
        self.target_unit.id = 99
        self.target_unit.name = "Target Ship"
        self.target_unit.owner = self.enemy_player
        self.target_unit.hull_capacity = 50.0  # Medium ship capacity
        self.target_unit.engines_component = None
        self.target_unit.weapons_component = None
        self.target_unit.get_component.side_effect = lambda cls: None
        self.target_unit.commander_component = None

        self.galaxy.get_unit_by_id.return_value = self.target_unit

    def test_capture_fails_without_marines_component(self):
        self.capturing_unit.get_component.side_effect = lambda cls: None
        ability = CaptureUnitAbility()
        ability_comp = MagicMock(unit=self.capturing_unit)

        result = ability.on_activate(ability_comp, self.galaxy, target_unit_id=99)
        self.assertFalse(result)
        self.assertEqual(self.target_unit.owner, self.enemy_player)

    @patch("random.random", return_value=0.1)
    def test_capture_success_with_marines(self, mock_rng):
        marines_comp = MarinesComponent(self.capturing_unit, marines_count=10)
        self.capturing_unit.get_component.side_effect = lambda cls: marines_comp if cls == MarinesComponent else None

        ability = CaptureUnitAbility()
        ability_comp = MagicMock(unit=self.capturing_unit)

        result = ability.on_activate(ability_comp, self.galaxy, target_unit_id=99)
        self.assertTrue(result)
        self.assertEqual(self.target_unit.owner, self.capturing_player)

    @patch("random.random", return_value=0.99)
    def test_capture_fail_due_to_rng_roll(self, mock_rng):
        # 5 marines vs 50 capacity target (req: 10 marines) -> 50% success probability
        marines_comp = MarinesComponent(self.capturing_unit, marines_count=5)
        self.capturing_unit.get_component.side_effect = lambda cls: marines_comp if cls == MarinesComponent else None

        ability = CaptureUnitAbility()
        ability_comp = MagicMock(unit=self.capturing_unit)

        result = ability.on_activate(ability_comp, self.galaxy, target_unit_id=99)
        self.assertFalse(result)
        self.assertEqual(self.target_unit.owner, self.enemy_player)


if __name__ == "__main__":
    unittest.main()
