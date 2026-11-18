from display_config import DisplayConfig
from player_controller import PlayerController
import unittest
from unittest.mock import MagicMock, patch
from constants import (
    HullSize, RED, BLUE,
    DEFAULT_ORBITAL_DEFENSE_RADIUS,
    DEFAULT_ORBITAL_DEFENSE_ATTACK_BONUS,
    DEFAULT_ORBITAL_DEFENSE_DEFENSE_BONUS,
    ORBITAL_DEFENSE_HULL_COST,
)
from geometry import Position
from domain.players import Player
from domain.units import Unit
from domain.celestials import Planet, Moon, ColonizableAsteroid, MetalAsteroid
from galaxy import Galaxy, StarSystem
from unit_components.orbital_defense import OrbitalDefenseComponent
from unit_components.weapons import Weapons, Turret
from unit_components.defenses import Defenses
from unit_components.enums import TurretType
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
        self.game_mock.display_config = DisplayConfig()

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

        self.od_comp = OrbitalDefenseComponent(unit=self.unit)
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

        ally = Player(name="Ally", color=BLUE, team_id=self.player.team_id)
        ship_in = Unit(
            owner=ally,
            position=Position(750.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Allied Corvette",
            hull_size=HullSize.SMALL,
            game=self.game_mock
        )
        ship_in.in_galaxy = self.galaxy
        self.system.add_unit(ship_in)

        ship_out = Unit(
            owner=self.player,
            position=Position(751.0, 0.0),
            in_hex=self.hex_coord,
            in_system="Sol",
            name="Far Corvette",
            hull_size=HullSize.SMALL,
            game=self.game_mock
        )
        ship_out.in_galaxy = self.galaxy
        self.system.add_unit(ship_out)

        self.assertEqual(ship_in.get_orbital_defense_buffs(self.galaxy), (0.25, 0.25))
        self.assertEqual(ship_out.get_orbital_defense_buffs(self.galaxy), (0.0, 0.0))

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
        unit2.add_component(OrbitalDefenseComponent(unit=unit2))
        self.system.add_unit(unit2)

        # Ship in both auras
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

        self.assertEqual(ship.get_orbital_defense_buffs(self.galaxy), (0.50, 0.50))

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

        turret.fire()
        hp_lost = 500 - target.current_hit_points
        self.assertEqual(hp_lost, 125)

    def test_defenses_mitigation_buff(self):
        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 50.0
        self.system.add_celestial_body(planet)

        # Defender with 100 Armor
        defender = Unit(
            owner=self.player,
            position=Position(751.0, 0.0),
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

        with patch("unit_components.defenses.random.uniform", return_value=100.0):
            self.assertEqual(defenses.calculate_mitigation(200, TurretType.MASS_DRIVER), 100)
            defender.position = Position(750.0, 0.0)
            self.assertEqual(defenses.calculate_mitigation(200, TurretType.MASS_DRIVER), 125)

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

    def test_custom_design_defaults_apply_to_omitted_aura_fields(self):
        from custom_unit_templates import template_from_dict
        from unit_components.constructor import instantiate_unit_from_template

        name = "Custom Defense"
        for overrides, expected in (
            ({}, (750.0, 0.25, 0.25)),
            ({"orbital_defense_radius": 500.0, "orbital_defense_defense_bonus": 0.20}, (500.0, 0.25, 0.20)),
        ):
            with self.subTest(overrides=overrides):
                template = {"name": name, "hull_size": "MEDIUM", "has_orbital_defense_component": True, **overrides}
                design = template_from_dict(name, template)
                self.assertEqual(design.validate(), [])
                config = design.components
                self.assertEqual((config.orbital_defense_radius, config.orbital_defense_attack_bonus,
                                  config.orbital_defense_defense_bonus), expected)
                unit = instantiate_unit_from_template(
                    name, self.player, "Sol", self.hex_coord, Position(200.0, 0.0),
                    self.galaxy, self.game_mock, templates={name: template},
                )
                aura = unit.orbital_defense_component
                self.assertEqual((aura.radius, aura.attack_bonus, aura.defense_bonus), expected)

    def test_save_and_load_preserves_explicit_aura(self):
        configuration = {"radius": 500.0, "attack_bonus": 0.20, "defense_bonus": 0.20}
        self.unit.add_component(OrbitalDefenseComponent(self.unit, **configuration))
        serialized = serialize_unit(self.unit)
        self.assertEqual(serialized["components"]["OrbitalDefenseComponent"]["configuration"], configuration)

        players_by_id = {self.player.id: self.player}
        deserialized = deserialize_unit(serialized, players_by_id, self.game_mock)
        aura = deserialized.orbital_defense_component
        self.assertIsNotNone(aura)
        self.assertEqual((aura.radius, aura.attack_bonus, aura.defense_bonus), (500.0, 0.20, 0.20))

    def test_aura_help_sidebar_and_range_ring(self):
        from constants import ORBITAL_DEFENSE_RING_COLOR
        from gui.retrofit_gui.catalog import RETROFIT_COMPONENTS
        from gui.unit_editor_gui.descriptions import component_description
        from rendering.sector_renderer.sector_overlay_renderer import SectorOverlayRenderer

        _, designer_help = component_description("has_orbital_defense_component")
        refit_help = next(component["description"] for component in RETROFIT_COMPONENTS
                          if component["comp_key"] == "OrbitalDefenseComponent")
        for description in (designer_help, refit_help):
            self.assertIn("750", description)
            self.assertIn("+25% weapon damage", description)
            self.assertIn("+25% defense mitigation", description)

        planet = Planet(in_hex=self.hex_coord, in_system="Sol", planet_type=None)
        planet.owner = self.player
        planet.population = 50.0
        self.system.add_celestial_body(planet)
        sidebar = self.od_comp.get_basic_sidebar_data(self.game_mock)
        self.assertTrue(any("+25% Atk/+25% Def (R750)" in row["text"] for row in sidebar))

        parent = MagicMock()
        renderer = SectorOverlayRenderer(parent)
        renderer.draw_unit_range_circles(self.unit, Position(160, 100), 500.0)
        parent.grid_renderer.draw_range_ring.assert_any_call(160, 100, 75, ORBITAL_DEFENSE_RING_COLOR)
