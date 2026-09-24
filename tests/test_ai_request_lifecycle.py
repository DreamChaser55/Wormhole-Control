"""Exercise running requests, actual async SDK transport and process teardown offline."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, get_ident
from time import monotonic
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
from openai import AsyncOpenAI
import pytest

from game_ai.adapters.base import PlanningOutputError, PlanningRequest, PlanningResult
from game_ai.adapters.fake import FakePlanningProvider
from game_ai.adapters.openai_responses import OpenAIResponsesProvider
from game_ai.commands import CommandResult
from game_ai.contracts import CommandBatch, TurnPlan
from game_ai.coordinator import AgentTurnCoordinator
from game_ai.planning_runtime import AsyncPlanningRuntime, PlanningRetirementError
from game_ai.runtime import get_runtime_config
from player_controller import PlayerController
from tests.support.campaigns import campaign


def result(strategy="current"):
    return PlanningResult(TurnPlan((), CommandBatch((), True), {"strategy": strategy}),
                          "fake", "gpt-6-luna", "medium")


class RunningProvider(FakePlanningProvider):
    def __init__(self, *, hold_cleanup=False, outcome="cancel"):
        super().__init__([])
        self.hold_cleanup, self.outcome = hold_cleanup, outcome
        self.entered, self.cancelling, self.closed = Event(), Event(), Event()
        self.close_count = 0
        self.thread_ids = []

    async def plan_turn(self, request, config):
        self.requests.append(request)
        self.thread_ids.append(get_ident())
        if len(self.requests) != 1:
            return result()
        self.release = asyncio.Event()
        self.cleanup = asyncio.Event()
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelling.set()
            if self.hold_cleanup:
                await self.cleanup.wait()
            if self.outcome == "cancel":
                raise
        if self.outcome == "transport":
            raise RuntimeError("private obsolete provider payload")
        if self.outcome == "output":
            raise PlanningOutputError("invalid_json", "private obsolete provider payload",
                                      provider="fake", model="gpt-6-luna", reasoning_effort="medium")
        return result("obsolete")

    async def aclose(self):
        self.close_count += 1
        if hasattr(self, "cleanup"):
            self.cleanup.set()
        self.closed.set()


@pytest.fixture
def make_coordinator(monkeypatch):
    coordinators = []
    monkeypatch.setattr("game_ai.coordinator.build_observation", lambda *_: {})
    gateway = Mock()
    gateway.apply_batch.return_value = CommandResult(accepted=True)
    monkeypatch.setattr("game_ai.coordinator.CommandGateway", lambda *_: gateway)

    def make(provider):
        game = campaign()
        game.current_player = game.players[0]
        game.current_player.controller = PlayerController.OPENAI
        game.end_turn = Mock()
        game.gui = SimpleNamespace(end_turn_button=Mock(), show_error_dialog=Mock())
        coordinator = AgentTurnCoordinator(game, provider=provider)
        coordinator._write_memory = Mock()
        coordinator._record_telemetry = Mock()
        coordinator._record_transport_error = Mock()
        coordinator._record_output_error = Mock()
        coordinators.append(coordinator)
        return coordinator, game, gateway

    yield make
    for coordinator in coordinators:
        coordinator.shutdown()


def begin(coordinator, provider):
    assert coordinator.start_current_turn()
    assert provider.entered.wait(2), "provider must actually be running before reset"
    return coordinator._handle


def release_on_worker(coordinator, event):
    coordinator._runtime._loop.call_soon_threadsafe(event.set)


def test_reset_cancels_running_io_and_replacement_uses_same_worker(make_coordinator):
    provider = RunningProvider()
    coordinator, game, gateway = make_coordinator(provider)
    old = begin(coordinator, provider)
    worker = coordinator._runtime._thread
    coordinator.reset()
    assert coordinator.start_current_turn()
    coordinator._future.result(timeout=2)
    coordinator.update()
    assert provider.cancelling.is_set() and old.finished.is_set()
    assert not provider.release.is_set()  # The old request never completed normally.
    assert provider.thread_ids == [worker.ident, worker.ident]
    assert coordinator._runtime._thread is worker
    assert game.current_player.ai_memory["strategy"] == "current"
    gateway.apply_batch.assert_called_once()
    game.end_turn.assert_called_once()
    coordinator.shutdown()
    coordinator.shutdown()
    assert not worker.is_alive() and provider.close_count == 1
    assert not coordinator.start_current_turn()


def test_repeated_resets_keep_only_latest_pending_request_and_show_cancelling(make_coordinator):
    provider = RunningProvider(hold_cleanup=True)
    coordinator, game, _ = make_coordinator(provider)
    coordinator._runtime.retirement_timeout = 10  # No elapsed-time race in this queue test.
    old = begin(coordinator, provider)
    pending = []
    for _ in range(20):
        coordinator.reset()
        assert coordinator.start_current_turn()
        pending.append(coordinator._handle)
    assert pending[-1].waiting.wait(2)
    coordinator.update()
    assert coordinator.state == "cancelling" and coordinator.is_busy
    assert len(provider.requests) == 1
    assert old.result.cancelled() and not old.finished.is_set()
    assert all(handle.result.cancelled() and handle.finished.wait(2) for handle in pending[:-1])
    game.gui.end_turn_button.disable.assert_called()
    release_on_worker(coordinator, provider.cleanup)
    coordinator._future.result(timeout=2)
    coordinator.update()
    assert len(provider.requests) == 2
    assert coordinator.state == "idle"


def test_retirement_deadline_enters_manual_recovery_without_more_workers(make_coordinator):
    provider = RunningProvider(hold_cleanup=True)
    coordinator, game, gateway = make_coordinator(provider)
    coordinator._runtime.retirement_timeout = .03
    begin(coordinator, provider)
    worker = coordinator._runtime._thread
    coordinator.reset()
    assert coordinator.start_current_turn()
    assert isinstance(coordinator._future.exception(timeout=2), PlanningRetirementError)
    coordinator.update()
    assert coordinator.state == "error" and not coordinator.is_busy
    assert "cancellation deadline" in coordinator.last_error
    game.gui.end_turn_button.enable.assert_called()
    game.gui.show_error_dialog.assert_called_once()
    gateway.apply_batch.assert_not_called()
    # Retrying while the obsolete call is still retiring must not queue more I/O.
    assert coordinator.start_current_turn()
    assert isinstance(coordinator._future.exception(timeout=2), PlanningRetirementError)
    coordinator.update()
    assert len(provider.requests) == 1 and coordinator._runtime._thread is worker
    coordinator.shutdown()  # Provider closure releases its deliberately delayed cleanup.
    assert provider.close_count == 1 and not worker.is_alive()


@pytest.mark.parametrize("outcome", ["success", "transport", "output"])
def test_reset_generation_discards_late_success_and_errors_in_same_turn(make_coordinator, outcome, caplog):
    provider = RunningProvider(hold_cleanup=True, outcome=outcome)
    coordinator, game, gateway = make_coordinator(provider)
    old = begin(coordinator, provider)
    identity = coordinator._turn_token
    coordinator.reset()
    assert coordinator.start_current_turn()
    assert coordinator._turn_token == identity
    assert provider.cancelling.wait(2)
    release_on_worker(coordinator, provider.cleanup)
    coordinator._future.result(timeout=2)
    coordinator.update()
    assert old.finished.is_set()
    assert game.current_player.ai_memory["strategy"] == "current"
    gateway.apply_batch.assert_called_once()
    coordinator._record_telemetry.assert_called_once()
    coordinator._record_transport_error.assert_not_called()
    coordinator._record_output_error.assert_not_called()
    game.gui.show_error_dialog.assert_not_called()
    assert "private obsolete" not in caplog.text


def test_retirement_deadline_still_releases_ui_when_provider_blocks_event_loop(make_coordinator):
    class BlockingProvider(RunningProvider):
        unblock = Event()

        async def plan_turn(self, request, config):
            self.requests.append(request)
            self.entered.set()
            self.unblock.wait(2)  # Deliberately violates the async provider contract.
            return result("obsolete")

    provider = BlockingProvider()
    coordinator, game, gateway = make_coordinator(provider)
    coordinator._runtime.retirement_timeout = .03
    old = begin(coordinator, provider)
    try:
        coordinator.reset()
        assert coordinator.start_current_turn()
        coordinator.update()
        assert coordinator.state == "cancelling"
        Event().wait(.05)
        coordinator.update()
        assert coordinator.state == "error" and not coordinator.is_busy
        game.gui.end_turn_button.enable.assert_called()
        gateway.apply_batch.assert_not_called()
    finally:
        provider.unblock.set()
        assert old.finished.wait(2)
    coordinator.shutdown()
    assert len(provider.requests) == 1


@pytest.mark.parametrize("identity", ["campaign", "agent", "turn", "controller"])
@pytest.mark.parametrize("outcome", ["success", "transport", "output"])
def test_changed_turn_identity_discards_outcome_before_handling_errors(make_coordinator, identity, outcome):
    provider = RunningProvider(outcome=outcome)
    coordinator, game, gateway = make_coordinator(provider)
    handle = begin(coordinator, provider)
    if identity == "campaign":
        game.campaign_id = "replacement"
    elif identity == "agent":
        game.current_player.agent_id = "replacement"
    elif identity == "turn":
        game.turn_number += 1
    else:
        game.current_player.controller = PlayerController.HUMAN
    release_on_worker(coordinator, provider.release)
    assert handle.finished.wait(2)
    coordinator.update()
    assert coordinator.state == "idle"
    gateway.apply_batch.assert_not_called()
    coordinator._record_transport_error.assert_not_called()
    coordinator._record_output_error.assert_not_called()
    coordinator._write_memory.assert_not_called()
    game.end_turn.assert_not_called()
    game.gui.show_error_dialog.assert_not_called()


def test_game_observation_and_mutations_stay_on_main_thread(make_coordinator, monkeypatch):
    provider = RunningProvider()
    coordinator, _, gateway = make_coordinator(provider)
    main = get_ident()
    def observe(*_):
        assert get_ident() == main
        return {}
    def apply(*_):
        assert get_ident() == main
        return CommandResult(accepted=True)
    monkeypatch.setattr("game_ai.coordinator.build_observation", observe)
    gateway.apply_batch.side_effect = apply
    begin(coordinator, provider)
    release_on_worker(coordinator, provider.release)
    coordinator._future.result(timeout=2)
    coordinator.update()
    assert provider.thread_ids[0] != main


@pytest.mark.parametrize("stage", ["request", "response_body", "retry_backoff"])
def test_sdk_cancellation_interrupts_running_transport_without_retrying(monkeypatch, stage):
    async def exercise():
        entered, cancelled = asyncio.Event(), asyncio.Event()
        calls = []
        original_sleep = __import__("anyio").sleep
        class Body(httpx.AsyncByteStream):
            async def __aiter__(self):
                entered.set()
                await asyncio.Future()
                yield b""

            async def aclose(self):
                cancelled.set()

        async def backoff(delay):
            entered.set()
            try:
                await original_sleep(delay)
            finally:
                cancelled.set()
        async def transport(request):
            calls.append(request)
            if stage == "response_body":
                return httpx.Response(200, stream=Body())
            if stage == "retry_backoff":
                return httpx.Response(429, headers={"retry-after": "60"},
                                      json={"error": {"message": "offline rate limit", "type": "rate_limit_error"}})
            entered.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
        if stage == "retry_backoff":
            monkeypatch.setattr("openai._base_client.anyio.sleep", backoff)
        async with AsyncOpenAI(api_key="offline-test-key", max_retries=2,
                               http_client=httpx.AsyncClient(transport=httpx.MockTransport(transport))) as client:
            provider = OpenAIResponsesProvider(client=client)
            task = asyncio.create_task(provider.plan_turn(
                PlanningRequest("campaign", "agent", "AI", 1, {}, {}), get_runtime_config("medium")))
            # SDK lazy imports/platform discovery can be slow on mounted CI
            # filesystems. Measure cancellation only after I/O actually starts.
            await asyncio.wait_for(entered.wait(), 30)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, 2)
            assert cancelled.is_set() and len(calls) == 1
            await provider.aclose()
            assert not client.is_closed()  # Borrowed client belongs to this context.
    asyncio.run(exercise())


def test_owned_sdk_client_configuration_and_idempotent_close(monkeypatch):
    response = SimpleNamespace(id="offline", usage=None, output_text='{"plan":[],"commands":[],"memory_patch":'
        '{"strategy":null,"objectives":null,"commitments":null,"beliefs":null,"lessons":null,"misc":null},"end_turn":true}')
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(return_value=response)), close=AsyncMock())
    factory = Mock(return_value=client)
    monkeypatch.setattr("openai.AsyncOpenAI", factory)
    monkeypatch.setattr("game_ai.adapters.openai_responses.load_openai_api_key", lambda: "offline-test-key")
    async def exercise():
        provider = OpenAIResponsesProvider()
        await provider.plan_turn(PlanningRequest("campaign", "agent", "AI", 1, {}, {}), get_runtime_config("high"))
        await provider.aclose()
        await provider.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            await provider.plan_turn(PlanningRequest("campaign", "agent", "AI", 1, {}, {}), get_runtime_config("high"))
    asyncio.run(exercise())
    assert factory.call_args.kwargs == dict(api_key="offline-test-key", timeout=120, max_retries=2)
    client.close.assert_awaited_once()
    assert client.responses.create.call_args.kwargs["store"] is False
    assert "background" not in client.responses.create.call_args.kwargs


@pytest.mark.parametrize("failure", ["timeout", "exception"])
def test_shutdown_is_bounded_and_cleanup_failures_are_sanitized(failure, caplog):
    class Provider(FakePlanningProvider):
        close_count = 0
        cleanup = Event()

        async def aclose(self):
            self.close_count += 1
            try:
                if failure == "exception":
                    raise RuntimeError("private provider payload")
                await asyncio.Future()
            finally:
                self.cleanup.set()

    provider = Provider([])
    runtime = AsyncPlanningRuntime(provider)
    runtime.shutdown_timeout = .2
    started = monotonic()
    assert not runtime.shutdown()
    assert monotonic() - started < 1
    assert not runtime.shutdown()
    assert provider.close_count == 1 and provider.cleanup.is_set()
    assert not runtime._thread.is_alive()
    assert "cleanup" in caplog.text and "private provider payload" not in caplog.text


@pytest.mark.parametrize("cooperative", [True, False])
def test_process_exits_during_active_request(cooperative):
    code = '''
import asyncio
from threading import Event
from game_ai.adapters.fake import FakePlanningProvider
from game_ai.adapters.base import PlanningRequest
from game_ai.planning_runtime import AsyncPlanningRuntime
from game_ai.runtime import get_runtime_config
class Provider(FakePlanningProvider):
    entered = Event()
    closed = False
    async def plan_turn(self, request, config):
        self.entered.set()
        if COOPERATIVE:
            await asyncio.Future()
        else:
            Event().wait(60)
    async def aclose(self):
        self.closed = True
provider = Provider([])
runtime = AsyncPlanningRuntime(provider)
runtime.shutdown_timeout = .2
runtime.submit(PlanningRequest("campaign", "agent", "AI", 1, {}, {}), get_runtime_config("low"))
assert provider.entered.wait(2)
closed = runtime.shutdown()
assert closed == COOPERATIVE
assert provider.closed == COOPERATIVE
print("EXITED")
'''.replace("COOPERATIVE", repr(cooperative))
    completed = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                               env=dict(os.environ), capture_output=True, text=True, timeout=8)
    assert completed.returncode == 0, completed.stderr
    assert "EXITED" in completed.stdout
