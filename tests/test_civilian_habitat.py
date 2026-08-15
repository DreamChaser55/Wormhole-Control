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

    def test_population_habitat_capacity_scaling(self):
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        self.assertEqual(planet.get_supported_habitat_capacity(), 0)  # Unowned

        planet.owner = self.player
        planet.population = 0.0
        self.assertEqual(planet.get_supported_habitat_capacity(), 0)

        planet.population = 10.0
        self.assertEqual(planet.get_supported_habitat_capacity(), 1)

        planet.population = 25.0
        self.assertEqual(planet.get_supported_habitat_capacity(), 1)

        planet.population = 50.0
        self.assertEqual(planet.get_supported_habitat_capacity(), 2)

        planet.population = 75.0
        self.assertEqual(planet.get_supported_habitat_capacity(), 3)

        planet.population = 100.0
        self.assertEqual(planet.get_supported_habitat_capacity(), 4)

        moon = Moon(in_hex=self.hex_coord, in_system="Sol")
        moon.owner = self.player
        moon.population = 50.0
        self.assertEqual(moon.get_supported_habitat_capacity(), 2)

        asteroid = ColonizableAsteroid(in_hex=self.hex_coord, in_system="Sol")
        asteroid.owner = self.player
        asteroid.population = 20.0
        self.assertEqual(asteroid.get_supported_habitat_capacity(), 1)

    def test_habitat_capacity_capping_and_inactivity(self):
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 25.0  # Supports exactly 1 habitat
        self.system.add_celestial_body(planet)

        # Create 2 additional habitat units in the same sector
        unit2 = Unit(
            owner=self.player,
            position=None,
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Habitat Station 2",
            hull_size=HullSize.LARGE,
            game=MagicMock(galaxy=self.galaxy)
        )
        hab2 = CivilianHabitatComponent(unit=unit2, economic_bonus=50.0)
        unit2.add_component(hab2)
        self.system.add_unit(unit2)

        unit3 = Unit(
            owner=self.player,
            position=None,
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Habitat Station 3",
            hull_size=HullSize.LARGE,
            game=MagicMock(galaxy=self.galaxy)
        )
        hab3 = CivilianHabitatComponent(unit=unit3, economic_bonus=50.0)
        unit3.add_component(hab3)
        self.system.add_unit(unit3)

        # Ensure units are sorted by ID
        units_sorted = sorted([self.unit, unit2, unit3], key=lambda u: u.id)
        first_unit = units_sorted[0]
        second_unit = units_sorted[1]
        third_unit = units_sorted[2]

        self.assertTrue(first_unit.civilian_habitat_component.is_active(self.galaxy))
        self.assertFalse(second_unit.civilian_habitat_component.is_active(self.galaxy))
        self.assertFalse(third_unit.civilian_habitat_component.is_active(self.galaxy))

        status2 = second_unit.civilian_habitat_component.get_sector_habitat_status(self.galaxy)
        self.assertFalse(status2['active'])
        self.assertIn("Colony Capacity Reached", status2['reason'])
        self.assertEqual(status2['capacity'], 1)
        self.assertEqual(status2['slot'], 2)

        # Turn processing should only give +50 for the 1 active habitat (+ taxes)
        game_mock = MagicMock()
        game_mock.galaxy = self.galaxy
        game_mock.players = [self.player]
        game_mock.current_player_index = 0
        tp = TurnProcessor(game_mock)

        from constants import TAX_RATE
        initial_credits = self.player.credits
        tp._process_resource_generation(self.player)
        expected = initial_credits + (25.0 * TAX_RATE) + 50.0
        self.assertAlmostEqual(self.player.credits, expected)

    def test_dynamic_population_growth_activates_additional_habitat(self):
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 25.0  # Capacity 1
        self.system.add_celestial_body(planet)

        unit2 = Unit(
            owner=self.player,
            position=None,
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Habitat Station 2",
            hull_size=HullSize.LARGE,
            game=MagicMock(galaxy=self.galaxy)
        )
        hab2 = CivilianHabitatComponent(unit=unit2, economic_bonus=50.0)
        unit2.add_component(hab2)
        self.system.add_unit(unit2)

        self.assertTrue(self.unit.civilian_habitat_component.is_active(self.galaxy))
        self.assertFalse(unit2.civilian_habitat_component.is_active(self.galaxy))

        # Population grows to 50 -> Capacity increases to 2
        planet.population = 50.0
        self.assertTrue(self.unit.civilian_habitat_component.is_active(self.galaxy))
        self.assertTrue(unit2.civilian_habitat_component.is_active(self.galaxy))

    def test_economy_income_calculation_with_habitats(self):
        import economy
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 50.0  # Capacity 2
        self.system.add_celestial_body(planet)

        # 1 habitat unit present
        from constants import TAX_RATE
        expected_income = (50.0 * TAX_RATE) + 50.0
        self.assertAlmostEqual(economy.calculate_player_income(self.galaxy, self.player), expected_income)

        # Add second habitat -> income increases by 50
        unit2 = Unit(
            owner=self.player,
            position=None,
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Habitat Station 2",
            hull_size=HullSize.LARGE,
            game=MagicMock(galaxy=self.galaxy)
        )
        unit2.add_component(CivilianHabitatComponent(unit=unit2, economic_bonus=50.0))
        self.system.add_unit(unit2)
        self.assertAlmostEqual(economy.calculate_player_income(self.galaxy, self.player), expected_income + 50.0)

        # Add third habitat (exceeds capacity 2) -> income does NOT increase
        unit3 = Unit(
            owner=self.player,
            position=None,
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Habitat Station 3",
            hull_size=HullSize.LARGE,
            game=MagicMock(galaxy=self.galaxy)
        )
        unit3.add_component(CivilianHabitatComponent(unit=unit3, economic_bonus=50.0))
        self.system.add_unit(unit3)
        self.assertAlmostEqual(economy.calculate_player_income(self.galaxy, self.player), expected_income + 50.0)

    def test_sidebar_status_labels(self):
        game_mock = MagicMock()
        game_mock.galaxy = self.galaxy

        # Uninhabited sector
        basic_data = self.habitat_comp.get_basic_sidebar_data(game_mock)
        self.assertTrue(any("Inactive" in item.get("text", "") for item in basic_data))

        # Colonize sector with pop 25
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 25.0
        self.system.add_celestial_body(planet)

    def test_habitat_ship_movement_and_sector_transitions(self):
        """Tests that a ship equipped with a civilian habitat correctly updates its active status
        when moving between sectors, leaving colonies, and entering new colonized sectors.
        """
        # 1. Setup colonized planet in origin sector (0, 0)
        planet = Planet(in_hex=(0, 0), in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 25.0  # Capacity 1
        self.system.add_celestial_body(planet)

        # Habitat ship at (0, 0) is initially active
        self.assertTrue(self.habitat_comp.is_active(self.galaxy))

        # Add a second habitat unit in (0, 0) which will be inactive due to capacity
        unit2 = Unit(
            owner=self.player,
            position=None,
            in_hex=(0, 0),
            in_system="Sol",
            name="Habitat Backup",
            hull_size=HullSize.LARGE,
            game=MagicMock(galaxy=self.galaxy)
        )
        hab2 = CivilianHabitatComponent(unit=unit2, economic_bonus=50.0)
        unit2.add_component(hab2)
        self.system.add_unit(unit2)

        # Force deterministic order so self.unit is slot 1, unit2 is slot 2
        if self.unit.id > unit2.id:
            self.unit.id, unit2.id = unit2.id, self.unit.id

        self.assertTrue(self.habitat_comp.is_active(self.galaxy))
        self.assertFalse(hab2.is_active(self.galaxy))

        # 2. Ship moves from (0, 0) to empty sector (1, 0)
        dest_hex = (1, 0)
        self.assertTrue(self.system.move_unit_between_hexes(self.unit, dest_hex))
        self.assertEqual(self.unit.in_hex, dest_hex)

        # Ship in empty sector is now inactive
        self.assertFalse(self.habitat_comp.is_active(self.galaxy))
        status = self.habitat_comp.get_sector_habitat_status(self.galaxy)
        self.assertEqual(status['reason'], 'Inactive (No Colonized Sector Object)')

        # Back in (0, 0), unit2 now takes the available capacity slot and becomes active!
        self.assertTrue(hab2.is_active(self.galaxy))
        status2 = hab2.get_sector_habitat_status(self.galaxy)
        self.assertTrue(status2['active'])
        self.assertEqual(status2['slot'], 1)

        # 3. Ship moves from empty sector (1, 0) to another colonized sector (2, 0)
        dest_hex2 = (2, 0)
        second_planet = Planet(in_hex=dest_hex2, in_system="Sol", planet_type=None)
        second_planet.owner = self.player
        second_planet.population = 50.0  # Capacity 2
        self.system.add_celestial_body(second_planet)

        self.assertTrue(self.system.move_unit_between_hexes(self.unit, dest_hex2))
        self.assertEqual(self.unit.in_hex, dest_hex2)

        # Ship entering the new colony sector becomes active again
        self.assertTrue(self.habitat_comp.is_active(self.galaxy))
        status_new = self.habitat_comp.get_sector_habitat_status(self.galaxy)
        self.assertTrue(status_new['active'])
        self.assertEqual(status_new['slot'], 1)
        self.assertEqual(status_new['capacity'], 2)


if __name__ == "__main__":
    unittest.main()

