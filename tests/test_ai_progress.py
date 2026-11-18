"""Progress follows actual attempts and preserves the authoritative turn lifecycle."""

import asyncio
from dataclasses import FrozenInstanceError
from threading import Event, get_ident
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from game_ai.adapters.base import PlanningOutputError, PlanningResult
from game_ai.adapters.fake import FakePlanningProvider
from game_ai.adapters.openai_responses import _usage_dict
from game_ai.commands import CommandError, CommandResult
from game_ai.contracts import CommandBatch, TurnPlan
from game_ai.coordinator import AgentTurnCoordinator
from game_ai.progress import AIAttemptStatistics, AITurnProgress, USAGE_FIELDS
from player_controller import PlayerController
from tests.support.ai import EMPTY_PATCH


def result(usage=None, latency=1.5):
    return PlanningResult(TurnPlan(("private strategy",), CommandBatch((), True), EMPTY_PATCH),
                          "fake", "gpt-6-luna", "medium", usage=usage or {}, latency_seconds=latency)


class Responses(FakePlanningProvider):
    def __init__(self, outputs):
        super().__init__([])
        self.outputs = iter(outputs)

    async def plan_turn(self, request, config):
        self.requests.append(request)
        output = next(self.outputs)
        if isinstance(output, Exception):
            raise output
        return output


@pytest.fixture
def make_progress_coordinator(monkeypatch):
    coordinators = []
    monkeypatch.setattr("game_ai.coordinator.build_observation", lambda *_: {"private": "secret observation"})

    def make(outputs, *, outcomes=None, on_progress=None, provider=None):
        clock = Mock(return_value=10.0)
        player = SimpleNamespace(name="AI One", controller=PlayerController.OPENAI, agent_id="agent",
                                 ai_memory={}, ai_repair_retries=2, ai_reasoning_effort="medium")
        human = SimpleNamespace(name="Human", controller=PlayerController.HUMAN, agent_id="human")
        game = SimpleNamespace(game_started=True, campaign_id="campaign", turn_number=4,
                               current_player=player, gui=None)
        game.end_turn = Mock(side_effect=lambda: setattr(game, "current_player", human))
        events = []

        def changed(progress):
            events.append((get_ident(), progress))
            if on_progress:
                on_progress(progress)

        provider = provider or Responses(outputs)
        coordinator = AgentTurnCoordinator(game, provider=provider, clock=clock, on_progress=changed)
        coordinator._write_memory = Mock()
        coordinator._append_telemetry = Mock()
        gateway = Mock()
        gateway.apply_batch.side_effect = outcomes or [CommandResult(accepted=True)]
        monkeypatch.setattr("game_ai.coordinator.CommandGateway", lambda *_: gateway)
        coordinators.append(coordinator)
        return coordinator, game, provider, gateway, clock, events

    yield make
    for coordinator in coordinators:
        coordinator.shutdown()


def finish(coordinator):
    try:
        coordinator._future.result(timeout=2)
    except (PlanningOutputError, RuntimeError, TimeoutError):
        pass
    coordinator.update()


def completed(events):
    return [progress for _, progress in events if progress is not None and progress.phase == "complete"]


def test_phases_paint_before_work_and_completion_follows_resolution(make_progress_coordinator, monkeypatch):
    coordinator, game, _, gateway, clock, events = make_progress_coordinator([
        result({"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})])
    phases_at_work = []

    def observe(*_):
        phases_at_work.append(coordinator.progress_snapshot().phase)
        clock.return_value += .25
        return {}

    def apply(*_):
        phases_at_work.append(coordinator.progress_snapshot().phase)
        clock.return_value += .5
        return CommandResult(accepted=True)

    def resolve():
        phases_at_work.append(coordinator.progress_snapshot().phase)
        assert not completed(events)
        clock.return_value += .75

    monkeypatch.setattr("game_ai.coordinator.build_observation", observe)
    gateway.apply_batch.side_effect = apply
    game.end_turn.side_effect = resolve
    coordinator.schedule_current_turn()
    clock.return_value = 10.5
    assert coordinator.progress_snapshot().phase == "scheduled"
    assert coordinator.start_current_turn()
    assert coordinator.progress_snapshot().phase == "requesting"
    clock.return_value = 13.0
    finish(coordinator)
    assert phases_at_work == ["preparing", "checking", "resolving"]
    assert game.end_turn.call_count == 1 and gateway.apply_batch.call_count == 1
    snapshot, = completed(events)
    assert snapshot.elapsed_seconds == 4.25
    assert dict(snapshot.phase_durations) == {
        "scheduled": .5, "preparing": .25, "requesting": 2.25, "checking": .5, "resolving": .75}
    assert snapshot.attempts[0].latency_seconds == 1.5
    assert snapshot.reported_total("total_tokens") == (120, False)
    assert "private strategy" not in repr(snapshot)
    assert {thread for thread, _ in events} == {get_ident()}
    clock.return_value = 50
    coordinator.update()
    assert snapshot.elapsed_seconds == 4.25 and game.end_turn.call_count == 1
    assert coordinator.progress_snapshot() is None


def test_repairs_keep_every_completed_response_and_mark_partial_totals(make_progress_coordinator):
    usage = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
             "cached_input_tokens": 80, "uncached_input_tokens": 20, "reasoning_tokens": 10}
    malformed = PlanningOutputError("invalid_json", "secret response", provider="fake", model="gpt-6-luna",
                                    reasoning_effort="medium", usage=usage, latency_seconds=2)
    rejection = CommandResult(False, errors=(CommandError(0, "invalid_state", "secret command"),))
    coordinator, game, provider, _, clock, events = make_progress_coordinator(
        [result(usage), malformed, result({"input_tokens": 200})],
        outcomes=[rejection, CommandResult(accepted=True)])
    assert coordinator.start_current_turn()
    finish(coordinator)
    first = coordinator.progress_snapshot()
    assert first.phase_label == "Revising — retry 1/2"
    assert len(first.attempts) == 1 and first.attempts[0].status == "rejected"
    clock.return_value = 14
    finish(coordinator)
    second = coordinator.progress_snapshot()
    assert second.phase_label == "Revising — retry 2/2"
    assert [item.status for item in second.attempts] == ["rejected", "invalid_output"]
    clock.return_value = 17
    finish(coordinator)
    final, = completed(events)
    assert [item.attempt_index for item in final.attempts] == [0, 1, 2]
    assert final.reported_total("input_tokens") == (400, False)
    assert final.reported_total("total_tokens") == (240, True)
    assert final.reported_total("cached_input_tokens") == (160, True)
    assert final.reported_total("reasoning_tokens") == (20, True)
    assert len(provider.requests) == 3 and game.end_turn.call_count == 1
    assert all(secret not in repr(final) for secret in ("secret response", "secret command", "secret observation"))


@pytest.mark.parametrize("category", ["transport", "commit", "invalid_output"])
def test_failed_turn_retains_statistics_and_safe_error(make_progress_coordinator, category):
    usage = {"input_tokens": 70, "output_tokens": 10, "total_tokens": 80}
    failure = PlanningOutputError("invalid_json", "secret output", provider="fake", model="gpt-6-luna",
                                  reasoning_effort="medium", usage=usage, latency_seconds=3)
    outputs = [TimeoutError("secret transport")] if category == "transport" else (
        [failure, failure] if category == "invalid_output" else [result(usage)])
    outcomes = [CommandResult(False, failure_stage="commit", retryable=False,
                              errors=(CommandError(0, "commit_failed", "secret unit"),), may_have_partial_effects=True)]
    coordinator, game, _, _, clock, events = make_progress_coordinator(outputs, outcomes=outcomes)
    game.current_player.ai_repair_retries = 1
    assert coordinator.start_current_turn()
    clock.return_value = 13
    finish(coordinator)
    if category == "invalid_output":
        clock.return_value = 16
        finish(coordinator)
    snapshot = coordinator.progress_snapshot()
    assert snapshot.phase == "error" and coordinator.failed_current_turn()
    assert not completed(events) and not game.end_turn.called
    assert snapshot.attempts and "secret" not in repr(snapshot) + snapshot.safe_error
    if category == "transport":
        assert snapshot.attempts[0].latency_seconds == 3
        assert snapshot.reported_total("input_tokens") == (None, False)
    else:
        assert snapshot.reported_total("input_tokens") == (140 if category == "invalid_output" else 70, False)
    elapsed = snapshot.elapsed_seconds
    clock.return_value = 100
    assert coordinator.progress_snapshot().elapsed_seconds == elapsed


def test_preparation_failure_is_attention_and_does_not_trigger_skip(make_progress_coordinator, monkeypatch):
    coordinator, game, _, _, _, _ = make_progress_coordinator([])
    monkeypatch.setattr("game_ai.coordinator.build_observation", Mock(side_effect=RuntimeError("secret observation")))
    assert coordinator.start_current_turn()
    snapshot = coordinator.progress_snapshot()
    assert snapshot.phase == "error" and not snapshot.attempts
    assert not game.end_turn.called and coordinator._future is None
    assert "secret" not in snapshot.safe_error


def test_resolution_failure_never_reports_completion_or_resolves_twice(make_progress_coordinator):
    coordinator, game, _, _, _, events = make_progress_coordinator([result()])
    game.end_turn.side_effect = RuntimeError("secret resolution")
    assert coordinator.start_current_turn()
    finish(coordinator)
    assert coordinator.failed_current_turn() and coordinator.last_error_category == "commit"
    assert not completed(events)
    coordinator.update()
    assert game.end_turn.call_count == 1


@pytest.mark.parametrize("outcome", ["success", "error"])
def test_reset_discards_late_progress_as_well_as_plan(make_progress_coordinator, outcome):
    class LateProvider(Responses):
        entered = Event()

        async def plan_turn(self, request, config):
            self.entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if outcome == "error":
                    raise PlanningOutputError("invalid_json", "secret stale response", provider="fake",
                                              model="gpt-6-luna", reasoning_effort="medium")
                return result({"input_tokens": 999})

    provider = LateProvider([])
    coordinator, game, _, gateway, _, events = make_progress_coordinator([], provider=provider)
    assert coordinator.start_current_turn() and provider.entered.wait(2)
    handle = coordinator._handle
    coordinator.reset()
    assert handle.finished.wait(2)
    coordinator.update()
    assert coordinator.progress_snapshot() is None and events[-1][1] is None
    assert not completed(events) and not gateway.apply_batch.called and not game.end_turn.called


def test_progress_is_scoped_to_campaign_agent_round_and_controller(make_progress_coordinator):
    coordinator, game, _, _, _, _ = make_progress_coordinator([result()])
    coordinator.schedule_current_turn()
    original = coordinator.progress_snapshot()
    for obj, field, value in ((game, "campaign_id", "other"), (game, "turn_number", 5),
                              (game.current_player, "agent_id", "other"),
                              (game.current_player, "controller", PlayerController.HUMAN)):
        previous = getattr(obj, field)
        setattr(obj, field, value)
        assert coordinator.progress_snapshot() is None
        setattr(obj, field, previous)
    assert coordinator.progress_snapshot().identity == original.identity


def test_usage_is_optional_immutable_bounded_and_not_double_counted():
    snapshot = AITurnProgress("campaign", "agent", 0, "AI", 1, "model", "medium", "requesting", 0, 0, 0)
    for index in range(8):
        attempt = AIAttemptStatistics.from_usage(
            attempt_index=index, started_at=0, finished_at=2, latency_seconds=float("nan"),
            status="accepted", usage={"input_tokens": 10, "output_tokens": 8, "total_tokens": 18,
                                      "reasoning_tokens": 5, "cached_input_tokens": True,
                                      "uncached_input_tokens": -1, "secret": "payload"})
        snapshot = snapshot.with_attempt(attempt).with_attempt(attempt)
    assert len(snapshot.attempts) == 6
    assert snapshot.reported_total("total_tokens") == (108, False)
    assert snapshot.reported_total("reasoning_tokens") == (30, False)
    assert snapshot.reported_total("cached_input_tokens") == (None, False)
    assert snapshot.attempts[0].latency_seconds == 2
    with pytest.raises(FrozenInstanceError):
        snapshot.phase = "other"
    with pytest.raises(FrozenInstanceError):
        snapshot.attempts[0].usage = ()
    assert all(field in USAGE_FIELDS for field, _ in snapshot.attempts[0].usage)


@pytest.mark.parametrize("reasoning", [0, 7, None, -1, True, "7"])
def test_adapter_reasoning_counts_remain_an_output_subset(reasoning):
    usage = _usage_dict(SimpleNamespace(input_tokens=100, output_tokens=10, total_tokens=110,
        input_tokens_details=SimpleNamespace(cached_tokens=80),
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning)))
    assert usage["total_tokens"] == 110 and usage["output_tokens"] == 10
    assert usage["uncached_input_tokens"] == 20
    assert usage.get("reasoning_tokens") == (reasoning if type(reasoning) is int and reasoning >= 0 else None)
