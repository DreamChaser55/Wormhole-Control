import os
import unittest
import pygame
from geometry import Position, Vector
from constants import HullSize, StarType, PlanetType, NebulaType, StormType
from entities import (
    Player, GameObject, Star, Planet, Moon, ColonizableAsteroid,
    MetalAsteroid, AsteroidField, IceField, DebrisField, Nebula, Storm, Comet, Wormhole, Unit
)
from unit_components import AntimatterStorage, ColonyComponent, MiningComponent
from unit_orders import MoveOrder, ColonizeOrder, OrderStatus
from save_manager import (
    serialize_player, deserialize_player,
    serialize_celestial_body, deserialize_celestial_body,
    serialize_unit, deserialize_unit,
    serialize_game_state, deserialize_game_state,
    save_game_to_file, load_game_from_file, list_save_files
)

os.environ["SDL_VIDEODRIVER"] = "dummy"

class TestSaveLoad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_player_round_trip(self):
        player = Player("Test Player", (0, 128, 255), is_human=True)
        player.credits = 15000.0
        player.metal = 5000.0
        player.crystal = 2500.0

        serialized = serialize_player(player)
        deserialized = deserialize_player(serialized)

        self.assertEqual(deserialized.id, player.id)
        self.assertEqual(deserialized.name, "Test Player")
        self.assertEqual(deserialized.color, (0, 128, 255))
        self.assertTrue(deserialized.is_human)
        self.assertEqual(deserialized.credits, 15000.0)
        self.assertEqual(deserialized.metal, 5000.0)
        self.assertEqual(deserialized.crystal, 2500.0)

    def test_celestial_bodies_round_trip(self):
        player = Player("Owner", (255, 0, 0))
        players_by_id = {player.id: player}

        # Planet
        planet = Planet(in_hex=(1, -1), in_system="Sol", planet_type=PlanetType.TERRAN)
        planet.owner = player
        planet.population = 42.5
        serialized = serialize_celestial_body(planet)
        deserialized = deserialize_celestial_body(serialized, players_by_id)

        self.assertIsInstance(deserialized, Planet)
        self.assertEqual(deserialized.id, planet.id)
        self.assertEqual(deserialized.in_hex, (1, -1))
        self.assertEqual(deserialized.in_system, "Sol")
        self.assertEqual(deserialized.owner, player)
        self.assertEqual(deserialized.population, 42.5)

        # Wormhole
        wh = Wormhole(in_hex=(2, -2), in_system="Sol", exit_system_name="Beta", stability=85, diameter=HullSize.LARGE)
        wh.exit_wormhole_id = 999
        serialized_wh = serialize_celestial_body(wh)
        deserialized_wh = deserialize_celestial_body(serialized_wh, players_by_id)

        self.assertIsInstance(deserialized_wh, Wormhole)
        self.assertEqual(deserialized_wh.exit_system_name, "Beta")
        self.assertEqual(deserialized_wh.exit_wormhole_id, 999)
        self.assertEqual(deserialized_wh.stability, 85)
        self.assertEqual(deserialized_wh.diameter, HullSize.LARGE)

    def test_unit_round_trip(self):
        player = Player("Fleet Cmd", (0, 255, 0))
        players_by_id = {player.id: player}

        unit = Unit(owner=player, position=Position(100.0, 200.0), in_hex=(0, 0), in_system="Sol", name="Flagship", hull_size=HullSize.HUGE, game=None)
        unit.current_hit_points = 800
        unit.experience_points = 150
        unit.is_disabled = True
        unit.damage_reduction = 0.25

        if unit.antimatter_component:
            unit.antimatter_component.current_amount = 45.0

        move_order = MoveOrder(unit, {"destination_system_name": "Sol", "destination_hex": (1, 1), "destination_position": Position(50.0, 50.0)})
        unit.commander_component.add_order(move_order)

        serialized = serialize_unit(unit)
        deserialized = deserialize_unit(serialized, players_by_id, game=None)

        self.assertEqual(deserialized.id, unit.id)
        self.assertEqual(deserialized.name, "Flagship")
        self.assertEqual(deserialized.owner, player)
        self.assertEqual(deserialized.hull_size, HullSize.HUGE)
        self.assertEqual(deserialized.current_hit_points, 800)
        self.assertEqual(deserialized.experience_points, 150)
        self.assertTrue(deserialized.is_disabled)
        self.assertEqual(deserialized.damage_reduction, 0.25)
        self.assertEqual(deserialized.antimatter_component.current_amount, 45.0)

    def test_full_game_save_load(self):
        from game import Game
        game = Game()
        success = game.start_new_game()
        self.assertTrue(success)

        game.turn_number = 7
        game.players[0].credits = 8888.0
        saved_systems_count = len(game.galaxy.systems)

        test_filename = "test_autotest_save.json"
        saved_filepath = game.save_game(test_filename)
        self.assertTrue(os.path.exists(saved_filepath))

        # Create fresh game and load
        new_game = Game()
        load_success = new_game.load_game(saved_filepath)
        self.assertTrue(load_success)
        self.assertTrue(new_game.game_started)
        self.assertEqual(new_game.turn_number, 7)
        self.assertEqual(new_game.players[0].credits, 8888.0)
        self.assertEqual(len(new_game.galaxy.systems), saved_systems_count)

        # Cleanup
        if os.path.exists(saved_filepath):
            os.remove(saved_filepath)

    def test_gui_load_dialog_trigger(self):
        from game import Game
        game = Game()
        game.gui.setup_main_menu()
        self.assertIsNotNone(game.gui.load_game_button)

        game.gui.show_load_game_dialog()
        self.assertIsNotNone(game.gui.load_save_window)
        self.assertIsNotNone(game.gui.load_save_confirm_button)
        self.assertIsNotNone(game.gui.load_save_cancel_button)

if __name__ == "__main__":
    unittest.main()
