from player_controller import PlayerController
import os
import tempfile
import unittest
from pathlib import Path
import pygame

from geometry import Position
from entities import Player
from game import Game
from game_ai.contracts import Command, CommandBatch, TurnPlan, SUPPORTED_COMMANDS
from game_ai.schema import responses_text_config, TURN_PLAN_SCHEMA
from game_ai.observation import build_observation, COMMAND_HELP
from game_ai.prompts import SYSTEM_INSTRUCTIONS
from game_ai.commands import CommandGateway
from galaxy import Galaxy, StarSystem

os.environ["SDL_VIDEODRIVER"] = "dummy"


class TestGameAIFeedback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1280, 720))

    def setUp(self):
        self.game = Game()
        self.galaxy = Galaxy()
        sys1 = StarSystem("Sol", Position(0, 0), radius=3)
        self.galaxy.systems["Sol"] = sys1
        self.game.galaxy = self.galaxy

        self.player0 = Player("Player 1", (0, 128, 255), controller=PlayerController.HUMAN)
        self.player1 = Player("Player 2", (255, 0, 0), controller=PlayerController.OPENAI)
        self.game.players = [self.player0, self.player1]
        self.game.current_player_index = 1
        self.game.turn_number = 3

    def test_supported_commands_and_schema(self):
        self.assertIn("message_developer", SUPPORTED_COMMANDS)
        self.assertIn("message_developer", COMMAND_HELP)

        # Verify command properties enum contains message_developer
        config = responses_text_config()
        type_enum = TURN_PLAN_SCHEMA["properties"]["commands"]["items"]["properties"]["type"]["enum"]
        self.assertIn("message_developer", type_enum)

    def test_command_contract_and_serialization(self):
        raw_command = {
            "type": "message_developer",
            "unit_ids": [],
            "target_id": None,
            "system_name": None,
            "hex_coord": None,
            "position": None,
            "template_name": None,
            "amount": None,
            "stance": None,
            "queue": False,
            "ability": None,
            "minefield_type": None,
            "target_component": None,
            "message": "Encountered unexpected carrier bay replenishment cooldown.",
        }
        cmd = Command.from_dict(raw_command)
        self.assertEqual(cmd.type, "message_developer")
        self.assertIsNone(cmd.target_id)
        self.assertEqual(cmd.message, "Encountered unexpected carrier bay replenishment cooldown.")
        self.assertEqual(cmd.unit_ids, ())

        cmd_dict = cmd.to_dict()
        self.assertEqual(cmd_dict["type"], "message_developer")
        self.assertEqual(cmd_dict["message"], "Encountered unexpected carrier bay replenishment cooldown.")
        self.assertEqual(cmd_dict["unit_ids"], [])
        self.assertIsNone(cmd_dict["target_id"])

        # Test turn plan contract
        raw_plan = {
            "plan": ["Report carrier bay observation to developer."],
            "commands": [raw_command],
            "memory_patch": {
                "strategy": "Continue exploration",
                "objectives": [],
                "commitments": [],
                "beliefs": [],
                "lessons": [],
                "misc": [],
            },
            "end_turn": True,
        }
        plan = TurnPlan.from_dict(raw_plan)
        self.assertEqual(len(plan.batch.commands), 1)
        self.assertEqual(plan.batch.commands[0].type, "message_developer")
        self.assertEqual(plan.batch.commands[0].message, "Encountered unexpected carrier bay replenishment cooldown.")

    def test_command_gateway_validation(self):
        gateway = CommandGateway(self.game)

        # Empty message string
        cmd_empty = Command(type="message_developer", message="")
        res1 = gateway.apply_batch(self.player1, CommandBatch(commands=(cmd_empty,)))
        self.assertFalse(res1.accepted)
        self.assertEqual(res1.errors[0].code, "invalid_command_contract")

        # Whitespace-only message string
        cmd_ws = Command(type="message_developer", message="   \n\t  ")
        res2 = gateway.apply_batch(self.player1, CommandBatch(commands=(cmd_ws,)))
        self.assertFalse(res2.accepted)
        self.assertEqual(res2.errors[0].code, "invalid_command_contract")

        # None message
        cmd_none = Command(type="message_developer", message=None)
        res3 = gateway.apply_batch(self.player1, CommandBatch(commands=(cmd_none,)))
        self.assertFalse(res3.accepted)
        self.assertEqual(res3.errors[0].code, "invalid_command_contract")

    def test_command_gateway_execution_and_markdown_persistence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            import save_manager
            original_saves_dir = save_manager.SAVES_DIR
            try:
                save_manager.SAVES_DIR = temp_dir
                gateway = CommandGateway(self.game)
                feedback_text = "The AI noticed that nebulae effectively obscure long-range sensors. Great tactical depth!"
                cmd = Command(
                    type="message_developer",
                    unit_ids=(),
                    message=feedback_text,
                )
                batch = CommandBatch(commands=(cmd,), end_turn=True)

                result = gateway.apply_batch(self.player1, batch)
                self.assertTrue(result.accepted)
                self.assertEqual(result.applied_count, 1)
                self.assertIn("Delivered message to game developer:", result.receipts[0])
                self.assertIn(feedback_text, result.receipts[0])

                # Check in-memory game developer feedback record
                self.assertEqual(len(self.game.developer_feedback), 1)
                entry = self.game.developer_feedback[0]
                self.assertEqual(entry["player_id"], self.player1.id)
                self.assertEqual(entry["player_name"], "Player 2")
                self.assertEqual(entry["turn_number"], 3)
                self.assertEqual(entry["message"], feedback_text)

                # Check markdown file written
                md_file = Path(temp_dir) / "ai_feedback.md"
                self.assertTrue(md_file.exists())
                content = md_file.read_text(encoding="utf-8")
                self.assertIn("# AI Developer Feedback Log", content)
                self.assertIn("## Turn 3 — Player 2", content)
                self.assertIn(feedback_text, content)
                self.assertIn(str(self.game.campaign_id), content)
            finally:
                save_manager.SAVES_DIR = original_saves_dir

    def test_observation_contains_message_developer_reference(self):
        obs = build_observation(self.game, self.player1)
        self.assertIn("command_catalog", obs)
        self.assertIn("message_developer", obs["command_catalog"]["commands"])
        self.assertIn("developer", obs["command_catalog"]["commands"]["message_developer"]["description"].lower())

    def test_system_prompt_contains_message_developer_guidance(self):
        self.assertIn("message_developer", SYSTEM_INSTRUCTIONS)
        self.assertIn("game developer", SYSTEM_INSTRUCTIONS.lower())
        self.assertIn("feedback", SYSTEM_INSTRUCTIONS.lower())


if __name__ == "__main__":
    unittest.main()
