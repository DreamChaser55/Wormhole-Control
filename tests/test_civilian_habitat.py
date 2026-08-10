import unittest
from unittest.mock import MagicMock

from constants import HullSize, RED
from entities import Player, Unit, Planet, Moon, ColonizableAsteroid, MetalAsteroid
from galaxy import Galaxy, StarSystem, Hex
from unit_components import CivilianHabitatComponent, instantiate_unit_from_template
from custom_unit_templates import CustomUnitTemplate, ComponentConfig
from turn_processor import TurnProcessor
from gui.unit_editor_gui.catalog import COMPONENT_ROWS, COMPONENT_DESCRIPTIONS


class TestCivilianHabitatComponent(unittest.TestCase):
    def setUp(self):
        self.player = Player(name="Test Player", color=RED, is_human=True)
        self.player.credits = 1000.0

        self.galaxy = Galaxy()
        self.system = StarSystem(name="Sol", position=None, radius=3)
        self.system.celestial_bodies_by_id.clear()
        for hex_obj in self.system.hexes.values():
            hex_obj.celestial_bodies.clear()
        self.galaxy.systems["Sol"] = self.system

        self.hex_coord = (0, 0)
        self.unit = Unit(
            owner=self.player,
            position=None,
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Habitat Station",
            hull_size=HullSize.LARGE,
            game=MagicMock(galaxy=self.galaxy)
        )
        self.system.add_unit(self.unit)

        self.habitat_comp = CivilianHabitatComponent(
            unit=self.unit,
            economic_bonus=50.0,
            hull_cost=15.0
        )
        self.unit.add_component(self.habitat_comp)

    def test_component_initialization(self):
        self.assertEqual(self.habitat_comp.economic_bonus, 50.0)
        self.assertEqual(self.habitat_comp.hull_cost, 15.0)
        self.assertEqual(self.unit.civilian_habitat_component, self.habitat_comp)

    def test_sector_colonized_object_detection(self):
        hex_obj = self.system.hexes[self.hex_coord]

        # Case 1: Empty sector -> inactive
        self.assertFalse(self.habitat_comp.has_colonized_celestial_object_in_sector(self.galaxy))

        # Case 2: Metal Asteroid (not colonizable) -> inactive
        metal_ast = MetalAsteroid(in_hex=self.hex_coord, in_system="Sol")
        self.system.add_celestial_body(metal_ast)
        self.assertFalse(self.habitat_comp.has_colonized_celestial_object_in_sector(self.galaxy))

        # Case 3: Uncolonized planet (owner=None, population=0) -> inactive
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = None
        planet.population = 0
        self.system.add_celestial_body(planet)
        self.assertFalse(self.habitat_comp.has_colonized_celestial_object_in_sector(self.galaxy))

        # Case 4: Colonized planet owned by player with population > 0 -> active
        planet.owner = self.player
        planet.population = 100.0
        self.assertTrue(self.habitat_comp.has_colonized_celestial_object_in_sector(self.galaxy))

    def test_destroyed_component_inactive(self):
        hex_obj = self.system.hexes[self.hex_coord]
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 100.0
        self.system.add_celestial_body(planet)

        self.assertTrue(self.habitat_comp.has_colonized_celestial_object_in_sector(self.galaxy))

        # Destroy component
        self.habitat_comp.current_hit_points = 0
        self.assertFalse(self.habitat_comp.has_colonized_celestial_object_in_sector(self.galaxy))

    def test_turn_processor_economic_bonus(self):
        game_mock = MagicMock()
        game_mock.galaxy = self.galaxy
        game_mock.players = [self.player]
        game_mock.current_player_index = 0

        tp = TurnProcessor(game_mock)

        # Place colonized planet in sector
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 0.0  # zero pop tax so we isolate civilian habitat bonus
        self.system.add_celestial_body(planet)

        # Non-zero pop for colonization status
        planet.population = 50.0

        initial_credits = self.player.credits
        tp._process_resource_generation(self.player)

        from constants import TAX_RATE
        expected_credits = initial_credits + (50.0 * TAX_RATE) + 50.0
        self.assertAlmostEqual(self.player.credits, expected_credits)

    def test_unit_template_instantiation(self):
        from unit_templates import UNIT_TEMPLATES
        test_template = {
            "name": "Civilian Outpost",
            "hull_size": HullSize.LARGE,
            "has_civilian_habitat_component": True,
            "civilian_habitat_bonus": 75.0,
            "civilian_habitat_hull_cost": 22.5,
        }
        UNIT_TEMPLATES["CIVILIAN_OUTPOST_TEST"] = test_template

        try:
            instantiate_unit_from_template(
                template_name="CIVILIAN_OUTPOST_TEST",
                owner=self.player,
                system_name="Sol",
                hex_coord=(0, 0),
                position=None,
                galaxy=self.galaxy,
                game=MagicMock(galaxy=self.galaxy)
            )

            created_unit = [u for u, _ in self.system.get_all_units() if u.name == "Civilian Outpost"][0]
            self.assertIsNotNone(created_unit.civilian_habitat_component)
            self.assertEqual(created_unit.civilian_habitat_component.economic_bonus, 75.0)
            self.assertEqual(created_unit.civilian_habitat_component.hull_cost, 22.5)
        finally:
            UNIT_TEMPLATES.pop("CIVILIAN_OUTPOST_TEST", None)

    def test_custom_unit_template_and_catalog(self):
        template = CustomUnitTemplate(
            design_name="CIVILIAN_HAB_DESIGN",
            display_name="Habitat Cruiser",
            hull_size=HullSize.LARGE,
            components=ComponentConfig(
                has_engine=True,
                has_civilian_habitat_component=True,
                civilian_habitat_bonus=50.0
            )
        )

        errors = template.validate()
        self.assertEqual(errors, [])
        self.assertIn("has_civilian_habitat_component", [row["key"] for row in COMPONENT_ROWS])
        self.assertIn("has_civilian_habitat_component", COMPONENT_DESCRIPTIONS)


if __name__ == "__main__":
    unittest.main()
