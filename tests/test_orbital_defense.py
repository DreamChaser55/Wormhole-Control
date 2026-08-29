from player_controller import PlayerController
import unittest
from unittest.mock import MagicMock

from constants import (
    HullSize, RED, BLUE,
    DEFAULT_ORBITAL_DEFENSE_RADIUS,
    DEFAULT_ORBITAL_DEFENSE_ATTACK_BONUS,
    DEFAULT_ORBITAL_DEFENSE_DEFENSE_BONUS,
    ORBITAL_DEFENSE_HULL_COST,
    BASE_ORBITAL_DEFENSE_CAPACITY,
    POPULATION_PER_ORBITAL_DEFENSE,
)
from geometry import Position
from entities import Player, Unit, Planet, Moon, ColonizableAsteroid, MetalAsteroid
from galaxy import Galaxy, StarSystem, Hex
from unit_components import (
    OrbitalDefenseComponent, Weapons, Turret, Defenses, TurretType, TurretVariant,
    instantiate_unit_from_template,
)
from custom_unit_templates import CustomUnitTemplate, ComponentConfig
from gui.unit_editor_gui.catalog import COMPONENT_ROWS, COMPONENT_DESCRIPTIONS
from save_manager import serialize_unit, deserialize_unit


class TestOrbitalDefenseComponent(unittest.TestCase):
    def setUp(self):
        self.player = Player(name="Test Player", color=RED, controller=PlayerController.HUMAN)
        self.enemy = Player(name="Enemy Player", color=BLUE, controller=PlayerController.OPENAI)

        self.galaxy = Galaxy()
        self.system = StarSystem(name="Sol", position=None, radius=3)
        self.system.celestial_bodies_by_id.clear()
        for hex_obj in self.system.hexes.values():
            hex_obj.celestial_bodies.clear()
        self.galaxy.systems["Sol"] = self.system

        self.hex_coord = (0, 0)
        self.game_mock = MagicMock(galaxy=self.galaxy)

        self.unit = Unit(
            owner=self.player,
            position=Position(0.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Defense Station",
            hull_size=HullSize.LARGE,
            game=self.game_mock
        )
        self.unit.in_galaxy = self.galaxy
        self.system.add_unit(self.unit)

        self.od_comp = OrbitalDefenseComponent(
            unit=self.unit,
            radius=DEFAULT_ORBITAL_DEFENSE_RADIUS,
            attack_bonus=DEFAULT_ORBITAL_DEFENSE_ATTACK_BONUS,
            defense_bonus=DEFAULT_ORBITAL_DEFENSE_DEFENSE_BONUS,
            hull_cost=ORBITAL_DEFENSE_HULL_COST
        )
        self.unit.add_component(self.od_comp)

    def test_component_initialization(self):
        self.assertEqual(self.od_comp.radius, DEFAULT_ORBITAL_DEFENSE_RADIUS)
        self.assertEqual(self.od_comp.attack_bonus, DEFAULT_ORBITAL_DEFENSE_ATTACK_BONUS)
        self.assertEqual(self.od_comp.defense_bonus, DEFAULT_ORBITAL_DEFENSE_DEFENSE_BONUS)
        self.assertEqual(self.od_comp.hull_cost, ORBITAL_DEFENSE_HULL_COST)
        self.assertEqual(self.unit.orbital_defense_component, self.od_comp)
        self.assertEqual(OrbitalDefenseComponent.calc_hull_cost(), ORBITAL_DEFENSE_HULL_COST)

    def test_sector_colonized_object_detection(self):
        # 1. Empty sector -> inactive
        self.assertFalse(self.od_comp.has_colonized_celestial_object_in_sector(self.galaxy))

        # 2. Non-colonizable metal asteroid -> inactive
        metal_ast = MetalAsteroid(in_hex=self.hex_coord, in_system="Sol")
        self.system.add_celestial_body(metal_ast)
        self.assertFalse(self.od_comp.has_colonized_celestial_object_in_sector(self.galaxy))

        # 3. Uncolonized planet (unowned, 0 pop) -> inactive
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = None
        planet.population = 0
        self.system.add_celestial_body(planet)
        self.assertFalse(self.od_comp.has_colonized_celestial_object_in_sector(self.galaxy))

        # 4. Enemy colonized planet -> inactive for self.player
        planet.owner = self.enemy
        planet.population = 50.0
        self.assertFalse(self.od_comp.has_colonized_celestial_object_in_sector(self.galaxy))

        # 5. Friendly colonized planet -> active
        planet.owner = self.player
        self.assertTrue(self.od_comp.has_colonized_celestial_object_in_sector(self.galaxy))

    def test_population_capacity_scaling(self):
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        self.assertEqual(planet.get_supported_orbital_defense_capacity(), 0)  # Unowned

        planet.owner = self.player
        planet.population = 0.0
        self.assertEqual(planet.get_supported_orbital_defense_capacity(), 0)  # 0 pop

        planet.population = 10.0
        self.assertEqual(planet.get_supported_orbital_defense_capacity(), 1)  # Base 1

        planet.population = 25.0
        self.assertEqual(planet.get_supported_orbital_defense_capacity(), 1)

        planet.population = 50.0
        self.assertEqual(planet.get_supported_orbital_defense_capacity(), 2)

        planet.population = 75.0
        self.assertEqual(planet.get_supported_orbital_defense_capacity(), 3)

        planet.population = 100.0
        self.assertEqual(planet.get_supported_orbital_defense_capacity(), 4)

        moon = Moon(in_hex=self.hex_coord, in_system="Sol")
        moon.owner = self.player
        moon.population = 50.0
        self.assertEqual(moon.get_supported_orbital_defense_capacity(), 2)

        asteroid = ColonizableAsteroid(in_hex=self.hex_coord, in_system="Sol")
        asteroid.owner = self.player
        asteroid.population = 20.0
        self.assertEqual(asteroid.get_supported_orbital_defense_capacity(), 1)

    def test_multiple_units_slot_allocation(self):
        # Planet supporting 2 orbital defense modules
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 50.0  # capacity = 2
        self.system.add_celestial_body(planet)

        # Unit 1 (self.unit, lowest ID)
        self.unit.id = 1
        unit2 = Unit(
            owner=self.player,
            position=Position(100.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="OD 2",
            hull_size=HullSize.MEDIUM,
            game=self.game_mock
        )
        unit2.id = 2
        unit2.in_galaxy = self.galaxy
        od2 = OrbitalDefenseComponent(unit=unit2)
        unit2.add_component(od2)
        self.system.add_unit(unit2)

        unit3 = Unit(
            owner=self.player,
            position=Position(200.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="OD 3",
            hull_size=HullSize.MEDIUM,
            game=self.game_mock
        )
        unit3.id = 3
        unit3.in_galaxy = self.galaxy
        od3 = OrbitalDefenseComponent(unit=unit3)
        unit3.add_component(od3)
        self.system.add_unit(unit3)

        # Unit 1 (slot 1) -> active
        st1 = self.od_comp.get_sector_orbital_defense_status(self.galaxy)
        self.assertTrue(st1['active'])
        self.assertEqual(st1['slot'], 1)
        self.assertEqual(st1['capacity'], 2)

        # Unit 2 (slot 2) -> active
        st2 = od2.get_sector_orbital_defense_status(self.galaxy)
        self.assertTrue(st2['active'])
        self.assertEqual(st2['slot'], 2)
        self.assertEqual(st2['capacity'], 2)

        # Unit 3 (slot 3) -> inactive (capacity reached)
        st3 = od3.get_sector_orbital_defense_status(self.galaxy)
        self.assertFalse(st3['active'])
        self.assertEqual(st3['slot'], 3)
        self.assertEqual(st3['capacity'], 2)
        self.assertIn("Colony Capacity Reached", st3['reason'])

    def test_aoe_effective_radius_distance_check(self):
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 50.0
        self.system.add_celestial_body(planet)

        # Ship within radius (distance 300 <= 500)
        ship_in = Unit(
            owner=self.player,
            position=Position(300.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Friendly Corvette",
            hull_size=HullSize.SMALL,
            game=self.game_mock
        )
        ship_in.in_galaxy = self.galaxy
        self.system.add_unit(ship_in)

        # Ship outside radius (distance 600 > 500)
        ship_out = Unit(
            owner=self.player,
            position=Position(600.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Far Corvette",
            hull_size=HullSize.SMALL,
            game=self.game_mock
        )
        ship_out.in_galaxy = self.galaxy
        self.system.add_unit(ship_out)

        atk_in, def_in = ship_in.get_orbital_defense_buffs(self.galaxy)
        self.assertAlmostEqual(atk_in, 0.20)
        self.assertAlmostEqual(def_in, 0.20)

        atk_out, def_out = ship_out.get_orbital_defense_buffs(self.galaxy)
        self.assertAlmostEqual(atk_out, 0.0)
        self.assertAlmostEqual(def_out, 0.0)

    def test_additive_stacking(self):
        # Planet supporting 2 modules
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 50.0
        self.system.add_celestial_body(planet)

        # OD Station 1 at (0, 0)
        self.unit.position = Position(0.0, 0.0)

        # OD Station 2 at (200, 0)
        unit2 = Unit(
            owner=self.player,
            position=Position(200.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Defense Station 2",
            hull_size=HullSize.LARGE,
            game=self.game_mock
        )
        unit2.in_galaxy = self.galaxy
        od2 = OrbitalDefenseComponent(unit=unit2, radius=500.0, attack_bonus=0.20, defense_bonus=0.20)
        unit2.add_component(od2)
        self.system.add_unit(unit2)

        # Ship at (100, 0) -> distance to Unit 1 is 100 <= 500, distance to Unit 2 is 100 <= 500
        ship = Unit(
            owner=self.player,
            position=Position(100.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Battleship",
            hull_size=HullSize.LARGE,
            game=self.game_mock
        )
        ship.in_galaxy = self.galaxy
        self.system.add_unit(ship)

        atk_bonus, def_bonus = ship.get_orbital_defense_buffs(self.galaxy)
        # Should sum additively: 0.20 + 0.20 = 0.40
        self.assertAlmostEqual(atk_bonus, 0.40)
        self.assertAlmostEqual(def_bonus, 0.40)

    def test_friendly_only_buff(self):
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 50.0
        self.system.add_celestial_body(planet)

        # Enemy ship inside radius
        enemy_ship = Unit(
            owner=self.enemy,
            position=Position(100.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Enemy Raider",
            hull_size=HullSize.SMALL,
            game=self.game_mock
        )
        enemy_ship.in_galaxy = self.galaxy
        self.system.add_unit(enemy_ship)

        atk_bonus, def_bonus = enemy_ship.get_orbital_defense_buffs(self.galaxy)
        self.assertEqual(atk_bonus, 0.0)
        self.assertEqual(def_bonus, 0.0)

    def test_turret_fire_damage_buff(self):
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 50.0
        self.system.add_celestial_body(planet)

        # Target enemy
        target = Unit(
            owner=self.enemy,
            position=Position(50.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Enemy Target",
            hull_size=HullSize.LARGE,
            game=self.game_mock
        )
        target.in_galaxy = self.galaxy
        target.current_hit_points = 500
        target.max_hit_points = 500
        self.system.add_unit(target)

        # Friendly firing ship within OD radius
        shooter = Unit(
            owner=self.player,
            position=Position(10.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Firing Cruiser",
            hull_size=HullSize.MEDIUM,
            game=self.game_mock
        )
        shooter.in_galaxy = self.galaxy
        wep = Weapons(unit=shooter)
        turret = Turret(
            turret_type=TurretType.MASS_DRIVER,
            damage=100.0,
            range=300.0,
            cooldown=1,
            parent_unit=shooter,
            target=target
        )
        wep.add_turret(turret)
        shooter.add_component(wep)
        self.system.add_unit(shooter)

        # Damage should be 100 * (1 + 0.20) = 120
        turret.fire()
        hp_lost = 500 - target.current_hit_points
        self.assertEqual(hp_lost, 120)

    def test_defenses_mitigation_buff(self):
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 50.0
        self.system.add_celestial_body(planet)

        # Defender with 100 Armor
        defender = Unit(
            owner=self.player,
            position=Position(50.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Armored Cruiser",
            hull_size=HullSize.LARGE,
            game=self.game_mock
        )
        defender.in_galaxy = self.galaxy
        defenses = Defenses(unit=defender, armor=100, shields=0, point_defense=0)
        defender.add_component(defenses)
        self.system.add_unit(defender)

        # Without OD (e.g. at distance 1000)
        defender.position = Position(1000.0, 0.0)
        _, def_bonus_far = defender.get_orbital_defense_buffs(self.galaxy)
        self.assertEqual(def_bonus_far, 0.0)

        # Inside OD radius
        defender.position = Position(50.0, 0.0)
        _, def_bonus_near = defender.get_orbital_defense_buffs(self.galaxy)
        self.assertAlmostEqual(def_bonus_near, 0.20)

    def test_destroyed_component_deactivation(self):
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 50.0
        self.system.add_celestial_body(planet)

        self.assertTrue(self.od_comp.is_active(self.galaxy))

        # Destroy component
        self.od_comp.current_hit_points = 0
        self.assertFalse(self.od_comp.is_active(self.galaxy))

        # Check friendly ship gets no buff from destroyed OD
        ship = Unit(
            owner=self.player,
            position=Position(50.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Friendly Corvette",
            hull_size=HullSize.SMALL,
            game=self.game_mock
        )
        ship.in_galaxy = self.galaxy
        self.system.add_unit(ship)

        atk, defense = ship.get_orbital_defense_buffs(self.galaxy)
        self.assertEqual(atk, 0.0)
        self.assertEqual(defense, 0.0)

    def test_unit_editor_catalog_and_restrictions(self):
        # 1. Present in COMPONENT_ROWS and COMPONENT_DESCRIPTIONS
        self.assertIn("has_orbital_defense_component", [row["key"] for row in COMPONENT_ROWS])
        self.assertIn("has_orbital_defense_component", COMPONENT_DESCRIPTIONS)

        # 2. Forbidden on STRIKECRAFT_WING and TINY
        from custom_unit_templates import HULL_RESTRICTIONS
        self.assertIn("has_orbital_defense_component", HULL_RESTRICTIONS[HullSize.STRIKECRAFT_WING])
        self.assertIn("has_orbital_defense_component", HULL_RESTRICTIONS[HullSize.TINY])

        # 3. Allowed on SMALL, MEDIUM, LARGE, HUGE
        self.assertNotIn("has_orbital_defense_component", HULL_RESTRICTIONS[HullSize.SMALL])
        self.assertNotIn("has_orbital_defense_component", HULL_RESTRICTIONS[HullSize.MEDIUM])
        self.assertNotIn("has_orbital_defense_component", HULL_RESTRICTIONS[HullSize.LARGE])
        self.assertNotIn("has_orbital_defense_component", HULL_RESTRICTIONS[HullSize.HUGE])

        # 4. CustomUnitTemplate validation
        valid_template = CustomUnitTemplate(
            display_name="Defense Platform",
            hull_size=HullSize.MEDIUM,
            components=ComponentConfig(has_orbital_defense_component=True)
        )
        self.assertEqual(valid_template.validate(), [])

        invalid_tiny = CustomUnitTemplate(
            display_name="Tiny Defense",
            hull_size=HullSize.TINY,
            components=ComponentConfig(has_orbital_defense_component=True)
        )
        self.assertTrue(len(invalid_tiny.validate()) > 0)

    def test_save_and_load_persistence(self):
        serialized = serialize_unit(self.unit)
        self.assertIn("OrbitalDefenseComponent", serialized["components"])
        self.assertEqual(serialized["components"]["OrbitalDefenseComponent"]["radius"], DEFAULT_ORBITAL_DEFENSE_RADIUS)

        players_by_id = {self.player.id: self.player}
        deserialized = deserialize_unit(serialized, players_by_id, self.game_mock)
        deserialized.in_galaxy = self.galaxy
        self.assertIsNotNone(deserialized.orbital_defense_component)
        self.assertEqual(deserialized.orbital_defense_component.radius, DEFAULT_ORBITAL_DEFENSE_RADIUS)
        self.assertEqual(deserialized.orbital_defense_component.attack_bonus, DEFAULT_ORBITAL_DEFENSE_ATTACK_BONUS)
        self.assertEqual(deserialized.orbital_defense_component.defense_bonus, DEFAULT_ORBITAL_DEFENSE_DEFENSE_BONUS)


if __name__ == "__main__":
    unittest.main()
