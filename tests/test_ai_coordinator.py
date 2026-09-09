

from player_controller import PlayerController
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from game_ai.adapters.base import (
    PlanningOutputError,
    PlanningRequest,
    PlanningResult,
)
from game_ai.adapters.fake import FakePlanningProvider
from game_ai.adapters.openai_responses import OpenAIResponsesProvider
from game_ai.commands import CommandError, CommandResult
from game_ai.coordinator import AgentTurnCoordinator
from game_ai.contracts import Command, CommandBatch, TurnPlan
from game_ai.evaluation import (
    EvaluationCase,
    colony_opening_case,
    colony_opening_gateway_case,
    compare_gateway_reasoning_efforts,
    compare_reasoning_efforts,
    inhibitor_overlap_case,
    run_evaluation,
    score_plan,
)
from game_ai.runtime import (
    get_runtime_config,
)
from tests.support.ai import EMPTY_PATCH, _Player


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
        self.assertEqual(responses.kwargs["prompt_cache_key"], "wormhole-control-turn-v4")
        self.assertNotIn("previous_response_id", responses.kwargs)

    def test_responses_adapter_classifies_invalid_output_as_repairable(self):
        responses = _FakeResponses(None)
        provider = OpenAIResponsesProvider(
            client=SimpleNamespace(responses=responses)
        )
        with self.assertRaises(PlanningOutputError) as caught:
            provider.plan_turn(
                PlanningRequest("campaign", "agent", "AI", 1, {}, {}),
                get_runtime_config("low"),
            )
        self.assertEqual(caught.exception.code, "invalid_contract")
        self.assertEqual(caught.exception.reasoning_effort, "low")


class TestCoordinator(unittest.TestCase):
    @staticmethod
    def _coordinator_fixture(repair_retries, plans):
        player = _Player(1, 1)
        player.controller = PlayerController.OPENAI
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
        player.controller = PlayerController.OPENAI
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
        plan = TurnPlan(("Consolidate.",), CommandBatch((), True), EMPTY_PATCH)
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
            self.assertEqual(player.last_ai_report["plan"], ["Consolidate."])
            self.assertEqual(player.last_ai_report["reasoning_effort"], "low")
            self.assertEqual(provider.runtime_configs[0].reasoning_effort, "low")
        finally:
            coordinator.shutdown()

    def test_configured_repairs_forward_latest_errors_and_can_recover(self):
        first_plan = TurnPlan(("First.",), CommandBatch((), True), EMPTY_PATCH)
        second_plan = TurnPlan(("Second.",), CommandBatch((), True), EMPTY_PATCH)
        accepted_plan = TurnPlan(("Recovered.",), CommandBatch((), True), EMPTY_PATCH)
        player, _game, ended, provider, coordinator = self._coordinator_fixture(
            2, [first_plan, second_plan, accepted_plan]
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
                self.assertEqual(coordinator.status_message, "thinking…")
                self._finish_pending_request(coordinator)
                self.assertEqual(coordinator.status_message, "revising... retry 1/2")
                self._finish_pending_request(coordinator)
                self.assertEqual(coordinator.status_message, "revising... retry 2/2")
                self._finish_pending_request(coordinator)

            self.assertEqual(len(provider.requests), 3)
            self.assertEqual(
                provider.requests[1].repair_context.to_dict()["validation_errors"],
                [{
                    "command_index": 0,
                    "code": "first_error",
                    "message": "First rejection",
                }],
            )
            self.assertEqual(
                provider.requests[1].repair_context.rejected_plan,
                first_plan,
            )
            self.assertEqual(provider.requests[1].observation, {})
            self.assertEqual(
                provider.requests[2].repair_context.to_dict()["validation_errors"],
                [{
                    "command_index": 1,
                    "code": "second_error",
                    "message": "Second rejection",
                }],
            )
            self.assertEqual(
                provider.requests[2].repair_context.rejected_plan,
                second_plan,
            )
            self.assertEqual(ended, [True])
            self.assertEqual(player.last_ai_report["plan"], ["Recovered."])
        finally:
            coordinator.shutdown()

    def test_retry_limit_is_snapshotted_and_exhaustion_returns_manual_control(self):
        plan = TurnPlan(("Invalid.",), CommandBatch((), True), EMPTY_PATCH)
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

    def test_invalid_model_output_uses_repair_context_and_same_reasoning(self):
        plan = TurnPlan(("Recovered.",), CommandBatch((), True), EMPTY_PATCH)
        player, _game, ended, _provider, coordinator = self._coordinator_fixture(
            1, []
        )

        class Provider:
            def __init__(self):
                self.requests = []
                self.runtime_configs = []

            def plan_turn(self, request, runtime_config):
                self.requests.append(request)
                self.runtime_configs.append(runtime_config)
                if len(self.requests) == 1:
                    raise PlanningOutputError(
                        "invalid_json",
                        "Invalid JSON.",
                        provider="fake",
                        model=runtime_config.model,
                        reasoning_effort=runtime_config.reasoning_effort,
                    )
                return PlanningResult(
                    plan=plan,
                    provider="fake",
                    model=runtime_config.model,
                    reasoning_effort=runtime_config.reasoning_effort,
                )

        provider = Provider()
        coordinator.provider = provider
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={"schema_version": 2}
            ), patch("game_ai.coordinator.CommandGateway") as gateway_class, patch.object(
                coordinator, "_write_memory"
            ), patch.object(coordinator, "_record_output_error"), patch.object(
                coordinator, "_record_telemetry"
            ):
                gateway_class.return_value.apply_batch.return_value = CommandResult(
                    accepted=True
                )
                self.assertTrue(coordinator.start_current_turn())
                coordinator._future.exception(timeout=2)
                coordinator.update()
                self._finish_pending_request(coordinator)

            self.assertEqual(ended, [True])
            self.assertEqual(len(provider.requests), 2)
            repair = provider.requests[1].repair_context
            self.assertIsNone(repair.rejected_plan)
            self.assertEqual(repair.errors[0].code, "invalid_json")
            self.assertEqual(provider.requests[1].observation, {"schema_version": 2})
            self.assertEqual(
                [config.reasoning_effort for config in provider.runtime_configs],
                ["medium", "medium"],
            )
        finally:
            coordinator.shutdown()

    def test_malformed_output_exhausts_exact_semantic_retry_budget(self):
        _player, _game, ended, _provider, coordinator = self._coordinator_fixture(
            1, []
        )

        class InvalidProvider:
            def __init__(self):
                self.requests = []

            def plan_turn(self, request, runtime_config):
                self.requests.append(request)
                raise PlanningOutputError(
                    "invalid_contract",
                    "The turn output violated its contract.",
                    provider="fake",
                    model=runtime_config.model,
                    reasoning_effort=runtime_config.reasoning_effort,
                )

        provider = InvalidProvider()
        coordinator.provider = provider
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch.object(coordinator, "_record_output_error"):
                self.assertTrue(coordinator.start_current_turn())
                coordinator._future.exception(timeout=2)
                coordinator.update()
                coordinator._future.exception(timeout=2)
                coordinator.update()
            self.assertEqual(len(provider.requests), 2)
            self.assertIsNotNone(provider.requests[1].repair_context)
            self.assertEqual(coordinator.state, "error")
            self.assertEqual(ended, [])
        finally:
            coordinator.shutdown()

    def test_transport_failure_does_not_use_semantic_retry(self):
        _player, _game, ended, _provider, coordinator = self._coordinator_fixture(
            3, []
        )

        class TransportProvider:
            def __init__(self):
                self.calls = 0

            def plan_turn(self, request, runtime_config):
                self.calls += 1
                raise TimeoutError("provider timeout")

        provider = TransportProvider()
        coordinator.provider = provider
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch.object(coordinator, "_record_transport_error"):
                self.assertTrue(coordinator.start_current_turn())
                coordinator._future.exception(timeout=2)
                coordinator.update()
            self.assertEqual(provider.calls, 1)
            self.assertEqual(coordinator.state, "error")
            self.assertNotIn("provider timeout", coordinator.last_error)
            self.assertEqual(ended, [])
        finally:
            coordinator.shutdown()

    def test_commit_failure_is_not_retried(self):
        plan = TurnPlan(("Commit.",), CommandBatch((), True), EMPTY_PATCH)
        _player, _game, ended, provider, coordinator = self._coordinator_fixture(
            3, [plan]
        )
        commit_failure = CommandResult(
            accepted=False,
            errors=(CommandError(-1, "commit_failed", "Commit failed"),),
            failure_stage="commit",
            retryable=False,
        )
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch("game_ai.coordinator.CommandGateway") as gateway_class, patch.object(
                coordinator, "_record_telemetry"
            ):
                gateway_class.return_value.apply_batch.return_value = commit_failure
                self.assertTrue(coordinator.start_current_turn())
                self._finish_pending_request(coordinator)
            self.assertEqual(len(provider.requests), 1)
            self.assertEqual(ended, [])
            self.assertEqual(coordinator.state, "error")
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
        plan = TurnPlan(("Wait.",), CommandBatch((), True), EMPTY_PATCH)
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
            self.assertEqual(record["attempt_index"], 0)
            self.assertFalse(record["is_repair"])
            self.assertEqual(record["command_summaries"], [])
            self.assertFalse(record["will_retry"])
        finally:
            coordinator.shutdown()

    def test_telemetry_records_every_rejected_and_accepted_attempt(self):
        import save_manager

        command = Command(type="cancel_orders", unit_ids=(1,))
        plan = TurnPlan(
            (), CommandBatch((command,), True), EMPTY_PATCH
        )
        _player, _game, ended, _provider, coordinator = self._coordinator_fixture(
            2, [plan, plan, plan]
        )
        rejected = CommandResult(
            accepted=False,
            errors=(CommandError(0, "invalid", "Try again."),),
        )
        accepted = CommandResult(accepted=True, applied_count=1)
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(
                save_manager, "SAVES_DIR", directory
            ), patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch("game_ai.coordinator.CommandGateway") as gateway_class, patch.object(
                coordinator, "_write_memory"
            ):
                gateway_class.return_value.apply_batch.side_effect = [
                    rejected,
                    rejected,
                    accepted,
                ]
                self.assertTrue(coordinator.start_current_turn())
                self._finish_pending_request(coordinator)
                self._finish_pending_request(coordinator)
                self._finish_pending_request(coordinator)
                records = [
                    json.loads(line)
                    for line in (
                        Path(directory) / "ai_telemetry.jsonl"
                    ).read_text(encoding="utf-8").splitlines()
                ]
            self.assertEqual(ended, [True])
            self.assertEqual([record["attempt_index"] for record in records], [0, 1, 2])
            self.assertEqual([record["will_retry"] for record in records], [True, True, False])
            self.assertEqual([record["status"] for record in records], ["rejected", "rejected", "accepted"])
            self.assertEqual(records[0]["command_summaries"][0]["type"], "cancel_orders")
            self.assertEqual(records[0]["error_details"][0]["command_index"], 0)
            self.assertNotIn("plan", records[0])
            self.assertNotIn("observation", records[0])
        finally:
            coordinator.shutdown()


class TestLogging(unittest.TestCase):
    def test_third_party_http_clients_cannot_emit_debug_request_bodies(self):
        import logging

        from game_logging import THIRD_PARTY_LOGGERS, setup_logging

        setup_logging(log_to_file=False)
        for logger_name in THIRD_PARTY_LOGGERS:
            self.assertGreaterEqual(
                logging.getLogger(logger_name).getEffectiveLevel(), logging.WARNING
            )
        record = logging.LogRecord(
            "openai._base_client.responses",
            logging.DEBUG,
            __file__,
            1,
            "request body: secret",
            (),
            None,
        )
        self.assertTrue(
            all(not handler.filter(record) for handler in logging.getLogger().handlers)
        )


class TestEvaluation(unittest.TestCase):
    def test_colony_opening_fixture_and_reasoning_comparison_are_opt_in(self):
        case = colony_opening_case()
        command = Command(
            type="load_colonists",
            unit_ids=(101,),
            target_id=201,
            amount=50,
        )
        plan = TurnPlan(
            ("Load first.",), CommandBatch((command,), True), EMPTY_PATCH
        )
        provider = FakePlanningProvider([plan, plan, plan])
        reports = compare_reasoning_efforts(provider, [case])
        self.assertEqual(set(reports), {"low", "medium", "high"})
        self.assertTrue(all(report.pass_rate == 1.0 for report in reports.values()))
        self.assertEqual(
            [config.reasoning_effort for config in provider.runtime_configs],
            ["low", "medium", "high"],
        )

    def test_inhibitor_overlap_fixture_forbids_invalid_busywork(self):
        case = inhibitor_overlap_case()
        wait_plan = TurnPlan(("Hold position.",), CommandBatch((), True), EMPTY_PATCH)
        invalid_plan = TurnPlan(
            ("Activate defenses.",),
            CommandBatch(
                (Command(type="toggle_inhibitor", unit_ids=(625,)),), True
            ),
            EMPTY_PATCH,
        )

        self.assertTrue(score_plan(case, wait_plan).passed)
        invalid_score = score_plan(case, invalid_plan)
        self.assertFalse(invalid_score.passed)
        self.assertEqual(invalid_score.forbidden_count, 1)

    def test_gateway_reasoning_comparison_tracks_repairs_and_acceptance(self):
        invalid = TurnPlan(
            ("Colonize immediately.",),
            CommandBatch(
                (
                    Command(
                        type="colonize", unit_ids=(101,), target_id=202, queue=True
                    ),
                ),
                True,
            ),
            EMPTY_PATCH,
        )
        repaired = TurnPlan(
            ("Load before colonizing.",),
            CommandBatch(
                (
                    Command(
                        type="load_colonists",
                        unit_ids=(101,),
                        target_id=201,
                        amount=50,
                    ),
                    Command(
                        type="colonize", unit_ids=(101,), target_id=202, queue=True
                    ),
                ),
                True,
            ),
            EMPTY_PATCH,
        )

        class RepairAwareProvider:
            def __init__(self):
                self.requests = []

            def plan_turn(self, request, runtime_config):
                self.requests.append(request)
                plan = repaired if request.repair_context else invalid
                return PlanningResult(
                    plan=plan,
                    provider="fake",
                    model=runtime_config.model,
                    reasoning_effort=runtime_config.reasoning_effort,
                    usage={"input_tokens": 10, "output_tokens": 5},
                    latency_seconds=0.25,
                )

        provider = RepairAwareProvider()
        reports = compare_gateway_reasoning_efforts(
            provider, [colony_opening_gateway_case()]
        )
        for report in reports.values():
            self.assertEqual(report.acceptance_rate, 1.0)
            self.assertEqual(report.scores[0].attempts, 2)
            self.assertEqual(report.scores[0].retries_used, 1)
            self.assertEqual(report.scores[0].input_tokens, 20)
            self.assertEqual(report.scores[0].output_tokens, 10)
            self.assertEqual(report.scores[0].latency_seconds, 0.5)
        self.assertTrue(all(request.repair_context for request in provider.requests[1::2]))

    def test_fixture_score_tracks_required_and_forbidden_commands(self):
        request = PlanningRequest("c", "a", "AI", 1, {}, {})
        case = EvaluationCase(
            "opening",
            request,
            required_command_types=frozenset({"move"}),
            forbidden_command_types=frozenset({"attack"}),
        )
        plan = TurnPlan(
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
        plan = TurnPlan(("Wait",), CommandBatch((), True), EMPTY_PATCH)
        provider = FakePlanningProvider([plan])

        report = run_evaluation(
            provider,
            [case],
            reasoning_effort="invalid",
        )

        self.assertEqual(report.reasoning_effort, "medium")
        self.assertEqual(report.to_dict()["reasoning_effort"], "medium")
        self.assertEqual(provider.runtime_configs[0].model, "gpt-5.6-luna")
