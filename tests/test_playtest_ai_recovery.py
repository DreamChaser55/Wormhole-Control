"""Offline TLS, telemetry and failed-turn recovery regressions."""
import asyncio
import json
import ssl
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError

from display_config import DisplayConfig
from game_ai.adapters.fake import FakePlanningProvider
from game_ai.adapters.openai_responses import _tls_context, _usage_dict
from game_ai.commands import CommandResult
from game_ai.contracts import CommandBatch, TurnPlan
from game_ai.coordinator import AgentTurnCoordinator
from game_ai.provider_errors import CertificateConfigurationError, classify_provider_error
from game_control_protocol import ControlService, PROTOCOL_VERSION
from player_controller import PlayerController
from tests.support.ai import EMPTY_PATCH


def certificate_error():
    request = httpx.Request("POST", "https://private.example/private-payload")
    error = APIConnectionError(request=request, message="private credential and body")
    error.__cause__ = httpx.ConnectError("private proxy details", request=request)
    error.__cause__.__cause__ = ssl.SSLCertVerificationError("private certificate details")
    return error


@pytest.mark.parametrize("override", [None, "SSL_CERT_FILE", "SSL_CERT_DIR"])
def test_tls_combines_system_trust_and_bundle_unless_explicitly_overridden(monkeypatch, override):
    for key in ("SSL_CERT_FILE", "SSL_CERT_DIR"):
        monkeypatch.delenv(key, raising=False)
    if override:
        monkeypatch.setenv(override, "configured-ca")
    context = Mock()
    with patch("ssl.create_default_context", return_value=context) as factory:
        assert _tls_context() is context
    if override:
        factory.assert_called_once_with(**{"cafile" if override == "SSL_CERT_FILE" else "capath": "configured-ca"})
        context.load_default_certs.assert_not_called()
    else:
        import certifi
        factory.assert_called_once_with(cafile=certifi.where())
        context.load_default_certs.assert_called_once_with(ssl.Purpose.SERVER_AUTH)


def test_ca_configuration_failure_is_safe_and_actionable(monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", "missing-private-ca-bundle")
    with pytest.raises(CertificateConfigurationError) as failure:
        _tls_context()
    assert "private" not in str(failure.value)
    assert classify_provider_error(failure.value) == "certificate_configuration"


def test_provider_error_categories_use_types_and_bounded_chains():
    request = httpx.Request("POST", "https://private.example")
    response = httpx.Response(429, request=request)
    assert classify_provider_error(certificate_error()) == "certificate_trust"
    assert classify_provider_error(APITimeoutError(request)) == "timeout"
    assert classify_provider_error(AuthenticationError("private", response=response, body=None)) == "authentication"
    assert classify_provider_error(RateLimitError("private", response=response, body={"code": "insufficient_quota"})) == "quota"
    assert classify_provider_error(RateLimitError("private", response=response, body=None)) == "rate_limit"
    cycle = RuntimeError("SSL certificate verification failed, private")
    cycle.__cause__ = cycle
    assert classify_provider_error(cycle) == "provider_error"  # Message text cannot select a category.


def test_cached_and_uncached_usage_are_reported_separately():
    assert _usage_dict(SimpleNamespace(input_tokens=100, output_tokens=5, total_tokens=105,
        input_tokens_details=SimpleNamespace(cached_tokens=80))) == {
            "input_tokens": 100, "output_tokens": 5, "total_tokens": 105,
            "cached_input_tokens": 80, "uncached_input_tokens": 20}


@pytest.fixture
def failed_turn():
    class Provider(FakePlanningProvider):
        attempts = 0

        async def plan_turn(self, request, config):
            self.attempts += 1
            if self.attempts == 1:
                await asyncio.sleep(.01)
                raise certificate_error()
            return await super().plan_turn(request, config)

    ai = SimpleNamespace(id=1, name="AI", agent_id="ai", team_id=1, controller=PlayerController.OPENAI,
                         ai_memory={}, ai_repair_retries=0)
    codex = SimpleNamespace(id=2, name="Codex", agent_id="codex", team_id=2, controller=PlayerController.CODEX)
    game = SimpleNamespace(game_started=True, campaign_id="campaign", turn_number=1, current_player=ai,
                           players=[ai, codex], gui=None, view_mode="galaxy", display_config=DisplayConfig(),
                           pending_ai_turn_end_time=0)
    game.end_turn = Mock(side_effect=lambda: setattr(game, "current_player", codex))
    provider = Provider([TurnPlan((), CommandBatch((), True), EMPTY_PATCH)])
    coordinator = game.ai_coordinator = AgentTurnCoordinator(game, provider=provider)
    with patch("game_ai.coordinator.build_observation", return_value={"units": []}), \
         patch.object(coordinator, "_append_telemetry") as telemetry, \
         patch.object(coordinator, "_write_memory"), \
         patch("game_ai.coordinator.CommandGateway") as gateway:
        gateway.return_value.apply_batch.return_value = CommandResult(accepted=True)
        yield game, coordinator, provider, telemetry, ControlService(game, port=0)
    coordinator.shutdown()


def fail_request(coordinator):
    assert coordinator.start_current_turn()
    with pytest.raises(APIConnectionError):
        coordinator._future.result(timeout=2)
    coordinator.update()


def request(action, **fields):
    return {"protocol_version": PROTOCOL_VERSION, "action": action, "request_id": action, **fields}


def test_failure_latency_status_waiters_and_retry_are_scoped_and_idempotent(failed_turn, caplog):
    game, coordinator, provider, telemetry, service = failed_turn
    game.pending_ai_turn_end_time = 10
    assert service._public_state()["ai_lifecycle"]["phase"] == "scheduled"
    game.pending_ai_turn_end_time = 0
    assert coordinator.start_current_turn()
    assert service._public_state()["ai_lifecycle"]["phase"] == "planning"
    waiting = Future()
    assert service._begin_wait(request("wait_for_turn"), waiting) is None
    with pytest.raises(APIConnectionError):
        coordinator._future.result(timeout=2)
    with patch("game_ai.coordinator.perf_counter", return_value=coordinator._attempt_started + 9.75):
        coordinator.update()
    record = telemetry.call_args.args[0]
    assert record["latency_seconds"] == 9.75 and record["error_category"] == "certificate_trust"
    state = service._public_state()
    assert state["attention_required"] and state["ai_lifecycle"]["phase"] == "failed"
    assert state["ai_lifecycle"]["error_category"] == "certificate_trust"
    assert "private" not in json.dumps(record) + json.dumps(state) + coordinator.last_error + caplog.text
    service._resolve_waiters()
    assert waiting.result()["data"] == {"ready": False, "attention_required": True}
    immediate = service._begin_wait(request("wait_for_turn"), Future())
    assert immediate["data"]["attention_required"]
    token = state["ai_lifecycle"]["recovery_token"]
    stale = service._dispatch_or_wait(request("retry_ai_turn", recovery_token="stale"), Future())
    assert stale["error"]["code"] == "stale_recovery_token"
    payload = request("retry_ai_turn", request_id="retry-valid", recovery_token=token)
    retried = service._dispatch_or_wait(payload, Future())
    assert retried["ok"] and retried["data"]["retried"]
    assert service._dispatch_or_wait(payload, Future()) == retried
    coordinator._future.result(timeout=2)
    coordinator.update()
    assert provider.attempts == 2 and game.end_turn.call_count == 1
    assert service._public_state()["ai_lifecycle"] is None


def test_partial_commit_cannot_retry_and_skipping_is_explicit(failed_turn):
    game, coordinator, provider, _, service = failed_turn
    coordinator._fail("Command commit failed.", category="commit")
    lifecycle = service._public_state()["ai_lifecycle"]
    assert lifecycle["recovery_actions"] == ["skip_failed_ai_turn"]
    rejected = service._dispatch_or_wait(request("retry_ai_turn", recovery_token=lifecycle["recovery_token"]), Future())
    assert rejected["error"]["code"] == "ai_recovery_unavailable" and provider.attempts == 0
    payload = request("skip_failed_ai_turn", recovery_token=lifecycle["recovery_token"])
    skipped = service._dispatch_or_wait(payload, Future())
    assert skipped["ok"] and skipped["data"]["skipped"]
    assert service._dispatch_or_wait(payload, Future()) == skipped
    assert game.end_turn.call_count == 1
    assert service._dispatch_or_wait({**payload, "request_id": "again"}, Future())["error"]["code"] == "ai_recovery_unavailable"


def test_old_failure_cannot_recover_a_different_turn(failed_turn):
    game, coordinator, _, _, service = failed_turn
    fail_request(coordinator)
    token = service._public_state()["ai_lifecycle"]["recovery_token"]
    game.turn_number += 1
    assert not service._public_state()["attention_required"]
    rejected = service._dispatch_or_wait(request("skip_failed_ai_turn", recovery_token=token), Future())
    assert rejected["error"]["code"] == "ai_recovery_unavailable"
