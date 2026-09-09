

from player_controller import PlayerController
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from game_ai.adapters.base import (
    PlanningRequest,
    RepairContext,
    RepairIssue,
)
from game_ai.contracts import Command, CommandBatch, ContractError, TurnPlan
from game_ai.memory import AgentMemory, write_memory_sidecar
from game_ai.runtime import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_REPAIR_RETRIES,
    LUNA_MODEL,
    MAX_REPAIR_RETRIES,
    MIN_REPAIR_RETRIES,
    SUPPORTED_REASONING_EFFORTS,
    get_runtime_config,
    normalize_repair_retries,
)
from tests.support.ai import EMPTY_PATCH


class TestRuntimeConfiguration(unittest.TestCase):
    def test_supported_efforts_share_the_luna_runtime_envelope(self):
        for effort in SUPPORTED_REASONING_EFFORTS:
            runtime_config = get_runtime_config(effort)
            self.assertEqual(runtime_config.model, LUNA_MODEL)
            self.assertEqual(runtime_config.reasoning_effort, effort)
            self.assertEqual(runtime_config.max_output_tokens, 7000)
            self.assertEqual(runtime_config.timeout_seconds, 120.0)
            self.assertEqual(runtime_config.max_commands, 40)

    def test_missing_and_invalid_efforts_default_to_medium(self):
        for effort in (None, "", "unsupported"):
            self.assertEqual(
                get_runtime_config(effort).reasoning_effort,
                DEFAULT_REASONING_EFFORT,
            )

    def test_repair_retries_are_normalized_and_bounded(self):
        self.assertEqual(normalize_repair_retries(None), DEFAULT_REPAIR_RETRIES)
        self.assertEqual(normalize_repair_retries("invalid"), DEFAULT_REPAIR_RETRIES)
        self.assertEqual(normalize_repair_retries(True), DEFAULT_REPAIR_RETRIES)
        self.assertEqual(normalize_repair_retries(-10), MIN_REPAIR_RETRIES)
        self.assertEqual(normalize_repair_retries(99), MAX_REPAIR_RETRIES)
        self.assertEqual(normalize_repair_retries("4"), 4)


class TestContracts(unittest.TestCase):
    def test_turn_plan_round_trip_and_command_limit(self):
        raw = {
            "plan": ["Move the scout."],
            "commands": [
                {
                    "type": "move",
                    "unit_ids": [3],
                    "system_name": "Sol",
                    "hex_coord": [0, 1],
                    "position": [10, 20],
                }
            ],
            "memory_patch": EMPTY_PATCH,
            "end_turn": True,
        }
        plan = TurnPlan.from_dict(raw)
        self.assertEqual(plan.batch.commands[0].hex_coord, (0, 1))
        self.assertTrue(plan.batch.end_turn)
        with self.assertRaises(ContractError):
            TurnPlan.from_dict({**raw, "commands": raw["commands"] * 2}, max_commands=1)

    def test_unknown_command_is_rejected(self):
        with self.assertRaises(ContractError):
            Command.from_dict({"type": "teleport", "unit_ids": [1]})

    def test_defend_and_precision_attack_contracts_roundtrip(self):
        raw = {
            "plan": ["Defend post and snipe engines."],
            "commands": [
                {
                    "type": "attack",
                    "unit_ids": [1],
                    "target_id": 2,
                    "target_component": "Engines",
                },
                {
                    "type": "defend",
                    "unit_ids": [1],
                    "system_name": "Sol",
                    "hex_coord": [0, 0],
                    "position": [100.0, 200.0],
                },
            ],
            "memory_patch": EMPTY_PATCH,
            "end_turn": True,
        }
        plan = TurnPlan.from_dict(raw)
        self.assertEqual(plan.batch.commands[0].target_component, "Engines")
        self.assertEqual(plan.batch.commands[1].type, "defend")
        self.assertEqual(plan.batch.commands[1].position, (100.0, 200.0))
        serialized = plan.to_dict()
        self.assertEqual(serialized["commands"][0]["target_component"], "Engines")
        self.assertEqual(serialized["commands"][1]["type"], "defend")

    def test_planning_request_serializes_repair_context_separately(self):
        plan = TurnPlan((), CommandBatch((), True), EMPTY_PATCH)
        request = PlanningRequest(
            "campaign",
            "agent",
            "AI",
            1,
            {"schema_version": 2},
            {},
            RepairContext(plan, (RepairIssue(0, "invalid", "Fix command 0."),)),
        )
        payload = request.to_dict()
        self.assertEqual(payload["observation"], {"schema_version": 2})
        self.assertEqual(payload["repair_context"]["rejected_plan"], plan.to_dict())
        self.assertEqual(
            payload["repair_context"]["validation_errors"][0]["command_index"],
            0,
        )


class TestMemory(unittest.TestCase):
    def test_memory_is_bounded_and_sidecar_is_derived(self):
        memory = AgentMemory()
        memory.apply_patch(
            {
                "strategy": "Expand",
                "objectives": [f"Objective {index}" for index in range(20)],
                "misc": [f"Misc Note {index}" for index in range(20)],
            },
            turn=4,
        )
        memory.add_receipt("Scout moved.", turn=4)
        self.assertEqual(len(memory.objectives), 12)
        self.assertEqual(len(memory.misc), 16)
        with tempfile.TemporaryDirectory() as directory:
            path = write_memory_sidecar(
                Path(directory),
                campaign_id="campaign",
                agent_id="agent",
                player_name="AI",
                memory=memory,
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("# AI — Agent Memory", text)
            self.assertIn("## Misc\n\n- Misc Note 0", text)
            self.assertIn("- Turn 4:\n  - Scout moved.", text)

    def test_memory_misc_field_roundtrip_and_defaults(self):
        memory = AgentMemory()
        self.assertEqual(memory.misc, [])
        markdown = memory.to_markdown(
            player_name="AI", campaign_id="camp", agent_id="ag"
        )
        self.assertIn("## Misc\n\n- None recorded.", markdown)

        memory.apply_patch({"misc": ["Important reminder.", "Enemy spotted."]}, turn=2)
        self.assertEqual(memory.misc, ["Important reminder.", "Enemy spotted."])
        serialized = memory.to_dict()
        self.assertEqual(serialized["misc"], ["Important reminder.", "Enemy spotted."])

        restored = AgentMemory.from_dict(serialized)
        self.assertEqual(restored.misc, ["Important reminder.", "Enemy spotted."])

    def test_receipts_markdown_formatting_multiline(self):
        memory = AgentMemory()
        memory.add_receipt("Move Scout.; Colonize Planet 1.; Build Ship.", turn=1)
        memory.add_receipt("No commands issued.", turn=2)
        memory.add_receipt("Attack Enemy A.; Defend Base.", turn=3)

        markdown = memory.to_markdown(
            player_name="Player 2",
            campaign_id="test-campaign",
            agent_id="test-agent",
        )

        expected_receipts_block = (
            "## Recent receipts\n\n"
            "- Turn 1:\n"
            "  - Move Scout.\n"
            "  - Colonize Planet 1.\n"
            "  - Build Ship.\n"
            "- Turn 2:\n"
            "  - No commands issued.\n"
            "- Turn 3:\n"
            "  - Attack Enemy A.\n"
            "  - Defend Base."
        )
        self.assertIn(expected_receipts_block, markdown)

    def test_receipts_markdown_empty_and_fallback(self):
        memory = AgentMemory()
        markdown = memory.to_markdown(
            player_name="Player 2",
            campaign_id="test-campaign",
            agent_id="test-agent",
        )
        self.assertIn("## Recent receipts\n\n- None recorded.", markdown)

        memory.receipts = ["Direct Action 1; Direct Action 2"]
        markdown_custom = memory.to_markdown(
            player_name="Player 2",
            campaign_id="test-campaign",
            agent_id="test-agent",
        )
        self.assertIn("## Recent receipts\n\n- Direct Action 1\n- Direct Action 2", markdown_custom)

    def test_receipts_individual_turns_retained_in_full(self):
        memory = AgentMemory()
        # Build a turn receipt with 20 commands that significantly exceeds the old 600-char limit
        actions = [f"Attack Player 2 Ship {idx} with Player 1 Destroyer {idx}." for idx in range(20)]
        long_receipt = "; ".join(actions)
        self.assertGreater(len(long_receipt), 800)

        memory.add_receipt(long_receipt, turn=16)
        self.assertEqual(len(memory.receipts), 1)
        self.assertEqual(memory.receipts[0], f"Turn 16: {long_receipt}")

        markdown = memory.to_markdown(
            player_name="Player 1",
            campaign_id="camp",
            agent_id="ag",
        )
        for act in actions:
            self.assertIn(f"  - {act}", markdown)

    def test_receipts_total_size_bounded_evicts_oldest_turns_entirely(self):
        memory = AgentMemory()
        # Create 10 turns of 1,500 characters each (15,000 characters total)
        for turn in range(1, 11):
            body = f"Action for turn {turn}: " + ("x" * 1400)
            memory.add_receipt(body, turn=turn)

        total_chars = sum(len(r) for r in memory.receipts)
        self.assertLessEqual(total_chars, 10_000)
        # Verify older turns were removed completely in FIFO order
        first_turn_str = memory.receipts[0]
        self.assertTrue(first_turn_str.startswith("Turn "))
        # The latest turns must be preserved in full
        self.assertTrue(memory.receipts[-1].startswith("Turn 10: Action for turn 10: "))
        self.assertEqual(len(memory.receipts[-1]), len("Turn 10: ") + len(f"Action for turn 10: " + ("x" * 1400)))
        # Turn 1 and Turn 2 should have been evicted entirely
        surviving_turns = [r.split(":")[0] for r in memory.receipts]
        self.assertNotIn("Turn 1", surviving_turns)
        self.assertNotIn("Turn 2", surviving_turns)

    def test_receipts_from_dict_total_bounding(self):
        # Deserializing raw receipts exceeding 10k chars should evict oldest turns entirely
        raw_receipts = [
            f"Turn {turn}: " + ("y" * 2000)
            for turn in range(1, 8)  # 7 * ~2008 chars = ~14,056 chars
        ]
        memory = AgentMemory.from_dict({"receipts": raw_receipts})
        total_chars = sum(len(r) for r in memory.receipts)
        self.assertLessEqual(total_chars, 10_000)
        self.assertNotIn("Turn 1: ", memory.receipts[0])
        self.assertTrue(memory.receipts[-1].startswith("Turn 7: "))
        self.assertEqual(len(memory.receipts[-1]), len(raw_receipts[-1]))

    def test_player_identity_reasoning_and_memory_survive_save_round_trip(self):

        from domain.players import Player
        from save_manager import deserialize_player, serialize_player

        player = Player(
            "Luna High",
            (12, 34, 56),
            controller=PlayerController.OPENAI,
            persistent_id="player-stable",
            agent_id="agent-stable",
            ai_reasoning_effort="high",
            ai_repair_retries=4,
            ai_memory={"strategy": "Hold Sol."},
        )
        restored = deserialize_player(serialize_player(player))
        self.assertEqual(restored.persistent_id, "player-stable")
        self.assertEqual(restored.agent_id, "agent-stable")
        self.assertEqual(restored.ai_reasoning_effort, "high")
        self.assertEqual(restored.ai_repair_retries, 4)
        self.assertEqual(restored.ai_memory["strategy"], "Hold Sol.")
        serialized = serialize_player(player)
        self.assertEqual(serialized["ai_reasoning_effort"], "high")
        self.assertEqual(serialized["ai_repair_retries"], 4)
        self.assertNotIn("ai_profile", serialized)

    def test_player_deserialization_reasoning_effort_normalization(self):

        from save_manager import deserialize_player

        for raw_effort, expected_effort in (
            ("low", "low"),
            ("LOW", "low"),
            ("medium", "medium"),
            ("high", "high"),
            ("HIGH", "high"),
            ("fast", "medium"),
            ("balanced", "medium"),
            ("strategic", "medium"),
            ("unknown", "medium"),
            ("max", "medium"),
            (None, "medium"),
        ):
            data = {"name": "AI Player", "controller": PlayerController.OPENAI.value}
            if raw_effort is not None:
                data["ai_reasoning_effort"] = raw_effort
            restored = deserialize_player(data)
            self.assertEqual(
                restored.ai_reasoning_effort,
                expected_effort,
            )

    def test_new_save_schema_requires_controller_and_normalizes_repair_retries(self):

        from save_manager import deserialize_player

        with self.assertRaises(KeyError):
            deserialize_player({"name": "Old schema"})
        self.assertEqual(
            deserialize_player({"controller": "openai", "ai_repair_retries": 0}).ai_repair_retries,
            MIN_REPAIR_RETRIES,
        )
        self.assertEqual(
            deserialize_player({"controller": "openai", "ai_repair_retries": 100}).ai_repair_retries,
            MAX_REPAIR_RETRIES,
        )
        self.assertEqual(
            deserialize_player({"controller": "openai", "ai_repair_retries": "bad"}).ai_repair_retries,
            DEFAULT_REPAIR_RETRIES,
        )

    def test_game_state_uses_save_version_4(self):

        from save_manager import serialize_game_state

        game = SimpleNamespace(
            players=[],
            galaxy=None,
            turn_number=1,
            current_player_index=0,
            view_mode="galaxy",
            current_system_name=None,
            current_sector_coord=None,
            campaign_id="campaign",
        )
        self.assertEqual(serialize_game_state(game)["version"], "4.0")
