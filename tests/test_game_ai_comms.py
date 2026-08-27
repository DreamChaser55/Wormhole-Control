import os
import unittest
import pygame

from geometry import Position
from entities import Player
from game import Game
from game_ai.contracts import Command, CommandBatch, TurnPlan
from game_ai.schema import responses_text_config, TURN_PLAN_SCHEMA
from game_ai.observation import build_observation
from game_ai.commands import CommandGateway
from galaxy import Galaxy, StarSystem

os.environ["SDL_VIDEODRIVER"] = "dummy"


class TestGameAIComms(unittest.TestCase):
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

        self.player0 = Player("Player 1", (0, 128, 255), is_human=True)
        self.player1 = Player("Player 2", (255, 0, 0), is_human=False)
        self.player2 = Player("Player 3", (0, 255, 0), is_human=False)
        self.game.players = [self.player0, self.player1, self.player2]
        self.game.current_player_index = 1
        self.game.turn_number = 2

    def test_observation_incoming_messages(self):
        # Message from Turn 1 to Player 1
        self.game.messages = [
            {
                "id": 1,
                "sender_id": self.player0.id,
                "sender_name": "Player 1",
                "recipient_id": self.player1.id,
                "turn_sent": 1,
                "text": "Hello AI from Turn 1",
                "read_by_recipient": False,
            },
            {
                "id": 2,
                "sender_id": self.player0.id,
                "sender_name": "Player 1",
                "recipient_id": self.player1.id,
                "turn_sent": 2,
                "text": "Message from Turn 2 (current turn)",
                "read_by_recipient": False,
            },
            {
                "id": 3,
                "sender_id": self.player1.id,
                "sender_name": "Player 2",
                "recipient_id": self.player2.id,
                "turn_sent": 1,
                "text": "Message to Player 3",
                "read_by_recipient": False,
            },
        ]

        obs = build_observation(self.game, self.player1)
        self.assertIn("incoming_messages", obs)
        incoming = obs["incoming_messages"]
        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0]["text"], "Hello AI from Turn 1")
        self.assertEqual(incoming[0]["sender_id"], self.player0.id)
        self.assertEqual(incoming[0]["sender_name"], "Player 1")
        self.assertEqual(incoming[0]["turn_sent"], 1)

        # Check command_reference includes send_message
        self.assertIn("send_message", obs["command_reference"])

    def test_command_contract_and_schema(self):
        raw_command = {
            "type": "send_message",
            "unit_ids": [],
            "target_id": self.player0.id,
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
            "message": "Alliance proposal.",
        }
        cmd = Command.from_dict(raw_command)
        self.assertEqual(cmd.type, "send_message")
        self.assertEqual(cmd.target_id, self.player0.id)
        self.assertEqual(cmd.message, "Alliance proposal.")
        self.assertEqual(cmd.unit_ids, ())

        cmd_dict = cmd.to_dict()
        self.assertEqual(cmd_dict["message"], "Alliance proposal.")
        self.assertEqual(cmd_dict["unit_ids"], [])

        # Test turn plan contract
        raw_plan = {
            "plan": ["Transmit diplomatic proposal to Player 1"],
            "commands": [raw_command],
            "memory_patch": {
                "strategy": "Form alliance",
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
        self.assertEqual(plan.batch.commands[0].message, "Alliance proposal.")

    def test_command_gateway_send_message_execution(self):
        gateway = CommandGateway(self.game)
        cmd = Command(
            type="send_message",
            unit_ids=(),
            target_id=self.player0.id,
            message="We propose open borders and trade.",
        )
        batch = CommandBatch(commands=(cmd,), end_turn=True)

        result = gateway.apply_batch(self.player1, batch)
        self.assertTrue(result.accepted)
        self.assertEqual(result.applied_count, 1)
        self.assertIn("Sent transmission to Player 1: 'We propose open borders and trade.'.", result.receipts[0])

        # Verify message added to game.messages
        self.assertEqual(len(self.game.messages), 1)
        msg = self.game.messages[0]
        self.assertEqual(msg["sender_id"], self.player1.id)
        self.assertEqual(msg["recipient_id"], self.player0.id)
        self.assertEqual(msg["text"], "We propose open borders and trade.")

    def test_command_gateway_send_message_validation(self):
        gateway = CommandGateway(self.game)

        # Missing target_id
        cmd_no_target = Command(type="send_message", target_id=None, message="Hello")
        res1 = gateway.apply_batch(self.player1, CommandBatch(commands=(cmd_no_target,)))
        self.assertFalse(res1.accepted)
        self.assertEqual(res1.errors[0].code, "missing_target")

        # Invalid target_id (non-existent)
        cmd_invalid_target = Command(type="send_message", target_id=999, message="Hello")
        res2 = gateway.apply_batch(self.player1, CommandBatch(commands=(cmd_invalid_target,)))
        self.assertFalse(res2.accepted)
        self.assertEqual(res2.errors[0].code, "invalid_recipient")

        # Self target_id
        cmd_self_target = Command(type="send_message", target_id=self.player1.id, message="Hello")
        res3 = gateway.apply_batch(self.player1, CommandBatch(commands=(cmd_self_target,)))
        self.assertFalse(res3.accepted)
        self.assertEqual(res3.errors[0].code, "invalid_recipient")

        # Empty message
        cmd_empty_msg = Command(type="send_message", target_id=self.player0.id, message="")
        res4 = gateway.apply_batch(self.player1, CommandBatch(commands=(cmd_empty_msg,)))
        self.assertFalse(res4.accepted)
        self.assertEqual(res4.errors[0].code, "empty_message")


if __name__ == "__main__":
    unittest.main()
