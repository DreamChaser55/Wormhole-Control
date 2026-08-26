import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from game_ai.adapters.base import PlanningRequest, PlanningResult
from game_ai.adapters.fake import FakePlanningProvider
from game_ai.adapters.openai_responses import OpenAIResponsesProvider
from game_ai.commands import CommandError, CommandGateway, CommandResult
from game_ai.coordinator import AgentTurnCoordinator
from game_ai.contracts import Command, CommandBatch, ContractError, TurnPlan
from game_ai.evaluation import EvaluationCase, run_evaluation, score_plan
from game_ai.memory import AgentMemory, write_memory_sidecar
from game_ai.observation import build_observation
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


EMPTY_PATCH = {
    "strategy": None,
    "objectives": None,
    "commitments": None,
    "beliefs": None,
    "lessons": None,
}


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
            "analysis_summary": "Expand carefully.",
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


class TestMemory(unittest.TestCase):
    def test_memory_is_bounded_and_sidecar_is_derived(self):
        memory = AgentMemory()
        memory.apply_patch(
            {
                "strategy": "Expand",
                "objectives": [f"Objective {index}" for index in range(20)],
            },
            turn=4,
        )
        memory.add_receipt("Scout moved.", turn=4)
        self.assertEqual(len(memory.objectives), 12)
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
            self.assertIn("Scout moved.", text)

    def test_player_identity_reasoning_and_memory_survive_save_round_trip(self):
        import builtins
        import typing

        builtins.typing = typing
        from entities import Player
        from save_manager import deserialize_player, serialize_player

        player = Player(
            "Luna High",
            (12, 34, 56),
            is_human=False,
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

    def test_legacy_profiles_migrate_to_luna_reasoning_efforts(self):
        import builtins
        import typing

        builtins.typing = typing
        from save_manager import deserialize_player

        for legacy_profile, expected_effort in (
            ("fast", "low"),
            ("balanced", "medium"),
            ("strategic", "high"),
            ("unknown", "medium"),
            (None, "medium"),
        ):
            data = {"name": "Legacy AI", "is_human": False}
            if legacy_profile is not None:
                data["ai_profile"] = legacy_profile
            restored = deserialize_player(data)
            self.assertEqual(
                restored.ai_reasoning_effort,
                expected_effort,
            )

        invalid_new_value = deserialize_player(
            {"ai_reasoning_effort": "max", "ai_profile": "strategic"}
        )
        self.assertEqual(invalid_new_value.ai_reasoning_effort, "medium")

    def test_legacy_and_invalid_repair_retry_values_are_normalized(self):
        import builtins
        import typing

        builtins.typing = typing
        from save_manager import deserialize_player

        self.assertEqual(
            deserialize_player({"name": "Legacy AI"}).ai_repair_retries,
            DEFAULT_REPAIR_RETRIES,
        )
        self.assertEqual(
            deserialize_player({"ai_repair_retries": 0}).ai_repair_retries,
            MIN_REPAIR_RETRIES,
        )
        self.assertEqual(
            deserialize_player({"ai_repair_retries": 100}).ai_repair_retries,
            MAX_REPAIR_RETRIES,
        )
        self.assertEqual(
            deserialize_player({"ai_repair_retries": "bad"}).ai_repair_retries,
            DEFAULT_REPAIR_RETRIES,
        )

    def test_game_state_uses_save_version_2_2(self):
        import builtins
        import typing

        builtins.typing = typing
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
        self.assertEqual(serialize_game_state(game)["version"], "2.2")


class _FakeResponses:
    def __init__(self, output):
        self.output = output
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="response-1",
            output_text=json.dumps(self.output),
            usage=SimpleNamespace(input_tokens=12, output_tokens=8, total_tokens=20),
        )


class TestOpenAIAdapter(unittest.TestCase):
    def test_responses_adapter_uses_strict_stateless_output(self):
        output = {
            "analysis_summary": "Wait.",
            "plan": [],
            "commands": [],
            "memory_patch": EMPTY_PATCH,
            "end_turn": True,
        }
        responses = _FakeResponses(output)
        client = SimpleNamespace(responses=responses)
        provider = OpenAIResponsesProvider(client=client)
        request = PlanningRequest("campaign", "agent", "AI", 1, {}, {})
        result = provider.plan_turn(request, get_runtime_config("high"))
        self.assertEqual(result.response_id, "response-1")
        self.assertFalse(responses.kwargs["store"])
        self.assertTrue(responses.kwargs["text"]["format"]["strict"])
        self.assertEqual(responses.kwargs["model"], "gpt-5.6-luna")
        self.assertEqual(responses.kwargs["reasoning"], {"effort": "high"})
        self.assertEqual(result.reasoning_effort, "high")
        self.assertNotIn("tools", responses.kwargs)


class _Player:
    def __init__(self, player_id, team_id):
        self.id = player_id
        self.name = f"P{player_id}"
        self.team_id = team_id
        self.credits = self.metal = self.crystal = 10

    def is_allied_with(self, other):
        return other is not None and self.team_id == other.team_id


class _Commander:
    def __init__(self):
        self.current_order = None
        self.orders_queue = []
        self.stance = SimpleNamespace(value="do_nothing")
        self.clear_count = 0

    def clear_orders(self):
        self.clear_count += 1


def _unit(unit_id, owner):
    return SimpleNamespace(
        id=unit_id,
        name=f"U{unit_id}",
        owner=owner,
        in_system="Sol",
        in_hex=(0, 0),
        position=SimpleNamespace(x=0, y=0),
        hull_size=SimpleNamespace(value="small"),
        current_hit_points=10,
        max_hit_points=10,
        is_disabled=False,
        components={},
        antimatter_component=None,
        commander_component=_Commander(),
        engines_component=None,
        weapons_component=None,
        colony_component=None,
        constructor_component=None,
        repair_component=None,
        mining_component=None,
        harvester_component=None,
        hangar_component=None,
        strikecraft_bay_component=None,
        trade_component=None,
        inhibitor_component=None,
        cloaking_component=None,
        ability_component=None,
    )


class TestInformationBoundaryAndGateway(unittest.TestCase):
    def test_hidden_enemy_is_omitted_but_presence_is_retained(self):
        viewer = _Player(1, 1)
        enemy = _Player(2, 2)
        own_unit = _unit(10, viewer)
        hidden_unit = _unit(20, enemy)
        hex_obj = SimpleNamespace(
            celestial_bodies=[], units=[own_unit, hidden_unit], minefields=[]
        )
        system = SimpleNamespace(
            position=SimpleNamespace(x=1, y=2),
            radius=2,
            hexes={(0, 0): hex_obj},
        )
        galaxy = SimpleNamespace(systems={"Sol": system}, system_graph={"Sol": {}})
        game = SimpleNamespace(
            galaxy=galaxy,
            players=[viewer, enemy],
            turn_number=1,
        )
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(),
            presence_hexes={("Sol", (0, 0))},
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, viewer)
        self.assertEqual([unit["id"] for unit in observation["units"]], [10])
        self.assertEqual(
            observation["undetailed_enemy_presence"],
            [{"system_name": "Sol", "hex_coord": [0, 0]}],
        )

    def test_batch_preflight_is_all_or_nothing(self):
        player = _Player(1, 1)
        unit = _unit(10, player)

        class Galaxy:
            def get_unit_by_id(self, unit_id):
                return unit if unit_id == 10 else None

        game = SimpleNamespace(galaxy=Galaxy(), sidebar_needs_update=False)
        batch = CommandBatch(
            commands=(
                Command(type="cancel_orders", unit_ids=(10,)),
                Command(type="cancel_orders", unit_ids=(999,)),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch)
        self.assertFalse(result.accepted)
        self.assertEqual(unit.commander_component.clear_count, 0)


class TestCoordinator(unittest.TestCase):
    @staticmethod
    def _coordinator_fixture(repair_retries, plans):
        player = _Player(1, 1)
        player.is_human = False
        player.agent_id = "agent-1"
        player.ai_reasoning_effort = "medium"
        player.ai_repair_retries = repair_retries
        player.ai_memory = {}
        player.last_ai_report = {}
        ended = []
        game = SimpleNamespace(
            game_started=True,
            campaign_id="campaign-1",
            current_player=player,
            turn_number=3,
            galaxy=SimpleNamespace(),
            gui=None,
            end_turn=lambda: ended.append(True),
        )
        provider = FakePlanningProvider(plans)
        return player, game, ended, provider, AgentTurnCoordinator(
            game, provider=provider
        )

    @staticmethod
    def _finish_pending_request(coordinator):
        coordinator._future.result(timeout=2)
        coordinator.update()

    def test_fake_provider_completes_turn_and_persists_receipt(self):
        player = _Player(1, 1)
        player.is_human = False
        player.agent_id = "agent-1"
        player.ai_reasoning_effort = "low"
        player.ai_memory = {}
        player.last_ai_report = {}
        ended = []
        game = SimpleNamespace(
            game_started=True,
            campaign_id="campaign-1",
            current_player=player,
            turn_number=3,
            galaxy=SimpleNamespace(),
            gui=None,
            end_turn=lambda: ended.append(True),
        )
        plan = TurnPlan("Consolidate.", (), CommandBatch((), True), EMPTY_PATCH)
        provider = FakePlanningProvider([plan])
        coordinator = AgentTurnCoordinator(game, provider=provider)
        try:
            with patch("game_ai.coordinator.build_observation", return_value={}), patch.object(
                coordinator, "_write_memory"
            ), patch.object(coordinator, "_record_telemetry"):
                self.assertTrue(coordinator.start_current_turn())
                coordinator._future.result(timeout=2)
                coordinator.update()
            self.assertEqual(ended, [True])
            self.assertIn("No commands issued.", player.ai_memory["receipts"][-1])
            self.assertEqual(player.last_ai_report["summary"], "Consolidate.")
            self.assertEqual(player.last_ai_report["reasoning_effort"], "low")
            self.assertEqual(provider.runtime_configs[0].reasoning_effort, "low")
        finally:
            coordinator.shutdown()

    def test_configured_repairs_forward_latest_errors_and_can_recover(self):
        plan = TurnPlan("Retry.", (), CommandBatch((), True), EMPTY_PATCH)
        player, _game, ended, provider, coordinator = self._coordinator_fixture(
            2, [plan, plan, plan]
        )
        rejected_first = CommandResult(
            accepted=False,
            errors=(CommandError(0, "first_error", "First rejection"),),
        )
        rejected_second = CommandResult(
            accepted=False,
            errors=(CommandError(1, "second_error", "Second rejection"),),
        )
        accepted = CommandResult(accepted=True)
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch("game_ai.coordinator.CommandGateway") as gateway_class, patch.object(
                coordinator, "_write_memory"
            ), patch.object(coordinator, "_record_telemetry"):
                gateway_class.return_value.apply_batch.side_effect = [
                    rejected_first,
                    rejected_second,
                    accepted,
                ]
                self.assertTrue(coordinator.start_current_turn())
                self._finish_pending_request(coordinator)
                self._finish_pending_request(coordinator)
                self._finish_pending_request(coordinator)

            self.assertEqual(len(provider.requests), 3)
            self.assertEqual(
                provider.requests[1].observation["previous_command_errors"],
                [{
                    "command_index": 0,
                    "code": "first_error",
                    "message": "First rejection",
                }],
            )
            self.assertEqual(
                provider.requests[2].observation["previous_command_errors"],
                [{
                    "command_index": 1,
                    "code": "second_error",
                    "message": "Second rejection",
                }],
            )
            self.assertEqual(ended, [True])
            self.assertEqual(player.last_ai_report["summary"], "Retry.")
        finally:
            coordinator.shutdown()

    def test_retry_limit_is_snapshotted_and_exhaustion_returns_manual_control(self):
        plan = TurnPlan("Invalid.", (), CommandBatch((), True), EMPTY_PATCH)
        player, game, ended, provider, coordinator = self._coordinator_fixture(
            1, [plan, plan]
        )

        class Button:
            def __init__(self):
                self.enabled = False

            def enable(self):
                self.enabled = True

            def disable(self):
                self.enabled = False

        dialogs = []
        button = Button()
        game.gui = SimpleNamespace(
            end_turn_button=button,
            show_error_dialog=lambda message, title: dialogs.append((message, title)),
        )
        rejected = CommandResult(
            accepted=False,
            errors=(CommandError(0, "invalid", "Still invalid"),),
        )
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch("game_ai.coordinator.CommandGateway") as gateway_class, patch.object(
                coordinator, "_record_telemetry"
            ):
                gateway_class.return_value.apply_batch.side_effect = [
                    rejected,
                    rejected,
                ]
                self.assertTrue(coordinator.start_current_turn())
                player.ai_repair_retries = 5
                self._finish_pending_request(coordinator)
                self._finish_pending_request(coordinator)

            self.assertEqual(len(provider.requests), 2)
            self.assertEqual(coordinator.state, "error")
            self.assertTrue(button.enabled)
            self.assertEqual(ended, [])
            self.assertEqual(dialogs[0][1], "AI Turn Error")
            self.assertIn("end the turn manually", dialogs[0][0])

            provider._plans.extend([plan])
            with patch("game_ai.coordinator.build_observation", return_value={}):
                self.assertTrue(coordinator.start_current_turn())
            self.assertEqual(coordinator._max_repair_retries, 5)
        finally:
            coordinator.shutdown()

    def test_telemetry_records_reasoning_effort(self):
        import save_manager

        player = SimpleNamespace(agent_id="agent-1")
        game = SimpleNamespace(
            campaign_id="campaign-1",
            current_player=player,
            turn_number=4,
        )
        plan = TurnPlan("Wait.", (), CommandBatch((), True), EMPTY_PATCH)
        result = PlanningResult(
            plan=plan,
            provider="fake",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        coordinator = AgentTurnCoordinator(
            game,
            provider=FakePlanningProvider([]),
        )
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(
                save_manager, "SAVES_DIR", directory
            ):
                coordinator._record_telemetry(
                    result,
                    CommandResult(accepted=True),
                    status="accepted",
                )
                record = json.loads(
                    (Path(directory) / "ai_telemetry.jsonl").read_text(
                        encoding="utf-8"
                    )
                )
            self.assertEqual(record["model"], "gpt-5.6-luna")
            self.assertEqual(record["reasoning_effort"], "high")
        finally:
            coordinator.shutdown()


class TestEvaluation(unittest.TestCase):
    def test_fixture_score_tracks_required_and_forbidden_commands(self):
        request = PlanningRequest("c", "a", "AI", 1, {}, {})
        case = EvaluationCase(
            "opening",
            request,
            required_command_types=frozenset({"move"}),
            forbidden_command_types=frozenset({"attack"}),
        )
        plan = TurnPlan(
            "Scout",
            ("Scout",),
            CommandBatch((Command(type="move", unit_ids=(1,)),), True),
            {},
        )
        score = score_plan(case, plan)
        self.assertTrue(score.passed)
        self.assertEqual(score.required_coverage, 1.0)

    def test_evaluation_reports_effective_reasoning_effort(self):
        request = PlanningRequest("c", "a", "AI", 1, {}, {})
        case = EvaluationCase("wait", request)
        plan = TurnPlan("Wait", (), CommandBatch((), True), EMPTY_PATCH)
        provider = FakePlanningProvider([plan])

        report = run_evaluation(
            provider,
            [case],
            reasoning_effort="invalid",
        )

        self.assertEqual(report.reasoning_effort, "medium")
        self.assertEqual(report.to_dict()["reasoning_effort"], "medium")
        self.assertEqual(provider.runtime_configs[0].model, "gpt-5.6-luna")


if __name__ == "__main__":
    unittest.main()
