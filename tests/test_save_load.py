from player_controller import PlayerController
import os
import unittest
import pygame
import json
from collections import deque
from geometry import Position, Vector
from constants import HullSize, StarType, PlanetType, NebulaType, StormType
from entities import (
    Player, GameObject, Star, Planet, Moon, ColonizableAsteroid,
    MetalAsteroid, AsteroidField, IceField, DebrisField, Nebula, Storm, Comet, Wormhole, Unit
)
from unit_components import AntimatterStorage, ColonyComponent, MiningComponent, UnitStance
from unit_orders import (
    AttackOrder, MoveOrder, ColonizeOrder, OrderStatus, OrderType, PatrolOrder,
    ORDER_CLASS_REGISTRY,
)
from utils import generate_short_id
from save_manager import (
    serialize_player, deserialize_player,
    serialize_celestial_body, deserialize_celestial_body,
    serialize_unit, deserialize_unit,
    serialize_order, deserialize_order,
    serialize_game_state, deserialize_game_state,
    save_game_to_file, load_game_from_file, list_save_files, _restore_saved_commander
)

os.environ["SDL_VIDEODRIVER"] = "dummy"

class TestSaveLoad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_player_round_trip(self):
        player = Player("Test Player", (0, 128, 255), controller=PlayerController.HUMAN)
        player.ai_repair_retries = 5
        player.credits = 15000.0
        player.metal = 5000.0
        player.crystal = 2500.0

        serialized = serialize_player(player)
        deserialized = deserialize_player(serialized)

        self.assertEqual(deserialized.id, player.id)
        self.assertEqual(deserialized.name, "Test Player")
        self.assertEqual(deserialized.color, (0, 128, 255))
        self.assertEqual(deserialized.controller, PlayerController.HUMAN)
        self.assertEqual(deserialized.credits, 15000.0)
        self.assertEqual(deserialized.metal, 5000.0)
        self.assertEqual(deserialized.crystal, 2500.0)
        self.assertEqual(deserialized.ai_repair_retries, 5)

    def test_codex_controller_round_trip_uses_new_schema(self):
        player = Player("Codex", (12, 34, 56), controller=PlayerController.CODEX)
        serialized = serialize_player(player)
        self.assertEqual(serialized["controller"], "codex")
        restored = deserialize_player(serialized)
        self.assertEqual(restored.controller, PlayerController.CODEX)

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

    def test_commander_payload_separates_stance_current_and_queue(self):
        player = Player("Fleet Cmd", (0, 255, 0))
        unit = Unit(player, Position(0, 0), (0, 0), "Sol", "Flagship", HullSize.HUGE, None)
        commander = unit.commander_component
        commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)

        current = MoveOrder(unit, {
            "destination_system_name": "Sol",
            "destination_hex_coord": (0, 0),
            "destination_position": Position(100, 0),
        })
        current.status = OrderStatus.IN_PROGRESS
        queued = AttackOrder(unit, {"target_unit_id": 12345})
        commander.current_order = current
        commander.orders_queue = deque([queued])

        transient = AttackOrder(unit, {"target_unit_id": 99999}, parent_order=commander.standing_order)
        commander.standing_order.add_sub_order(transient)
        payload = serialize_unit(unit)["commander"]

        self.assertEqual(payload["stance"], "attack_same_sector")
        self.assertEqual(payload["current_order"]["order_type"], "MOVE")
        self.assertEqual([item["order_type"] for item in payload["orders_queue"]], ["ATTACK"])
        self.assertNotIn("standing_order", payload)
        self.assertNotEqual(payload["current_order"]["order_type"], "STANCE")

    def test_nested_order_parameters_and_patrol_runtime_round_trip(self):
        player = Player("Fleet Cmd", (0, 255, 0))
        unit = Unit(player, Position(0, 0), (0, 0), "Sol", "Patroller", HullSize.MEDIUM, None)
        patrol = PatrolOrder(unit, {
            "waypoints": [
                {"system_name": "Sol", "hex_coord": (1, -1), "position": Position(10.5, 20.5)},
                {"system_name": "Sol", "hex_coord": (2, -1), "position": Position(30.5, 40.5)},
            ],
            "metadata": {"formation": ("line", 2), "stance_hint": UnitStance.ATTACK_SAME_SECTOR},
        })
        patrol.status = OrderStatus.IN_PROGRESS
        patrol.start_system_name = "Sol"
        patrol.start_hex_coord = (0, 0)
        patrol.start_position = Position(1.0, 2.0)
        patrol.patrol_phase = "TO_START"
        patrol.current_waypoint_index = 2

        serialized = serialize_order(patrol)
        json.dumps(serialized)
        restored = deserialize_order(serialized, unit, None)

        self.assertIsInstance(restored, PatrolOrder)
        self.assertEqual(restored.parameters["waypoints"][0]["hex_coord"], (1, -1))
        self.assertEqual(restored.parameters["waypoints"][1]["position"], Position(30.5, 40.5))
        self.assertEqual(restored.parameters["metadata"]["formation"], ("line", 2))
        self.assertEqual(restored.parameters["metadata"]["stance_hint"], UnitStance.ATTACK_SAME_SECTOR)
        self.assertEqual(restored.start_system_name, "Sol")
        self.assertEqual(restored.start_hex_coord, (0, 0))
        self.assertEqual(restored.start_position, Position(1.0, 2.0))
        self.assertEqual(restored.patrol_phase, "TO_START")
        self.assertEqual(restored.current_waypoint_index, 2)

    def test_order_registry_covers_every_order_type(self):
        self.assertEqual(set(ORDER_CLASS_REGISTRY), set(OrderType))

    def test_legacy_commander_orders_restore_current_then_queue(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        player = Player("Legacy", (0, 255, 0))
        game = SimpleNamespace(galaxy=MagicMock())
        unit = Unit(player, Position(0, 0), (0, 0), "Sol", "Legacy Ship", HullSize.MEDIUM, game)
        current = MoveOrder(unit, {
            "destination_system_name": "Sol",
            "destination_hex_coord": (0, 0),
            "destination_position": Position(50, 0),
        })
        current.status = OrderStatus.IN_PROGRESS
        queued = AttackOrder(unit, {"target_unit_id": 123})
        payload = serialize_unit(unit)
        payload.pop("commander")
        payload["orders"] = [serialize_order(current), serialize_order(queued)]

        restored = deserialize_unit(payload, {player.id: player}, game)
        _restore_saved_commander(restored, game)

        self.assertEqual(restored.commander_component.stance, UnitStance.DO_NOTHING)
        self.assertEqual(restored.commander_component.current_order.order_type, OrderType.MOVE)
        self.assertEqual([order.order_type for order in restored.commander_component.orders_queue], [OrderType.ATTACK])

    def test_version_3_without_commander_data_loads_idle(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        player = Player("Legacy", (0, 255, 0))
        game = SimpleNamespace(galaxy=MagicMock())
        unit = Unit(player, Position(0, 0), (0, 0), "Sol", "Legacy Ship", HullSize.MEDIUM, game)
        payload = serialize_unit(unit)
        payload.pop("commander")

        restored = deserialize_unit(payload, {player.id: player}, game)
        _restore_saved_commander(restored, game)

        self.assertEqual(restored.commander_component.stance, UnitStance.DO_NOTHING)
        self.assertIsNone(restored.commander_component.current_order)
        self.assertFalse(restored.commander_component.orders_queue)

    def test_full_game_save_load(self):
        from game import Game
        game = Game()
        success = game.start_new_game()
        self.assertTrue(success)

        game.turn_number = 7
        game.players[0].credits = 8888.0
        saved_systems_count = len(game.galaxy.systems)
        stance_unit = next(
            unit
            for system in game.galaxy.systems.values()
            for unit, _ in system.get_all_units()
            if unit.commander_component
        )
        stance_unit.commander_component.set_stance(UnitStance.ATTACK_WEAPON_RANGE)
        stance_unit_id = stance_unit.id

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
        restored_stance_unit = new_game.galaxy.get_unit_by_id(stance_unit_id)
        self.assertEqual(restored_stance_unit.commander_component.stance, UnitStance.ATTACK_WEAPON_RANGE)
        self.assertIs(restored_stance_unit.in_galaxy, new_game.galaxy)

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

    def test_load_game_schedules_ai_turn_if_current_player_is_ai(self):
        from game import Game
        from unittest.mock import patch

        game = Game()
        game.start_new_game()
        # Set player 0 to AI and save
        game.players[0].controller = PlayerController.OPENAI
        game.current_player_index = 0

        test_filename = "test_ai_load_save.json"
        saved_filepath = game.save_game(test_filename)
        self.assertTrue(os.path.exists(saved_filepath))

        new_game = Game()
        with patch('pygame.time.get_ticks', return_value=3000):
            load_success = new_game.load_game(saved_filepath)
            self.assertTrue(load_success)
            self.assertEqual(new_game.pending_ai_turn_end_time, 3500)

        # Cleanup
        if os.path.exists(saved_filepath):
            os.remove(saved_filepath)

    def test_short_id_generation(self):
        token = generate_short_id()
        self.assertEqual(len(token), 8)
        self.assertTrue(all(c in "0123456789abcdef" for c in token))

        token_custom = generate_short_id(prefix="camp-", length=6)
        self.assertTrue(token_custom.startswith("camp-"))
        self.assertEqual(len(token_custom), 11)

        # Uniqueness check across samples
        samples = {generate_short_id() for _ in range(100)}
        self.assertEqual(len(samples), 100)

    def test_short_ids_in_player_and_game(self):
        from game import Game
        player = Player("AI Pilot", (100, 150, 200), controller=PlayerController.OPENAI)
        self.assertEqual(len(player.persistent_id), 8)
        self.assertEqual(len(player.agent_id), 8)
        self.assertTrue(all(c in "0123456789abcdef" for c in player.persistent_id))
        self.assertTrue(all(c in "0123456789abcdef" for c in player.agent_id))

        game = Game()
        self.assertEqual(len(game.campaign_id), 8)
        self.assertTrue(all(c in "0123456789abcdef" for c in game.campaign_id))

        game.start_new_game()
        self.assertEqual(len(game.campaign_id), 8)
        self.assertTrue(all(c in "0123456789abcdef" for c in game.campaign_id))

        # Check serialization preserves short IDs
        serialized = serialize_player(player)
        self.assertEqual(serialized["persistent_id"], player.persistent_id)
        self.assertEqual(serialized["agent_id"], player.agent_id)


if __name__ == "__main__":
    unittest.main()
