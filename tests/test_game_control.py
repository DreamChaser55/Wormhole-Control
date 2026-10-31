from __future__ import annotations
from game_actions.turn_presentation import ApplicationTurnPresentation
import io
import json
import os
from pathlib import Path
import socket
import socketserver
import subprocess
import sys
from threading import Thread
import time
import unittest
from concurrent.futures import Future
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import game_control
from game import Game
from game_ai.commands import CommandError, CommandResult
from game_ai.coordinator import AgentTurnCoordinator
from game_control_protocol import (
    MAX_REQUEST_BYTES,
    PROTOCOL_VERSION,
    ControlService,
    ProtocolError,
    _parse_new_game_settings,
)
from player_controller import PlayerController
from turn_processor import TurnProcessor
import pytest


class _Player:
    def __init__(self, player_id: int, name: str, controller: PlayerController, team_id: int):
        self.id = player_id
        self.name = name
        self.controller = controller
        self.team_id = team_id
        self.agent_id = f"agent-{player_id}"


class _Game:
    def __init__(self, controller: PlayerController = PlayerController.CODEX):
        self.game_started = True
        self.view_mode = "galaxy"
        self.campaign_id = "campaign"
        self.turn_number = 3
        self.players = [
            _Player(1, "Codex", controller, 1),
            _Player(2, "Opponent", PlayerController.HUMAN, 2),
        ]
        self.current_player_index = 0
        self.started_with = None

    @property
    def current_player(self):
        return self.players[self.current_player_index] if self.game_started else None

    def start_new_game(self, settings):
        self.started_with = settings
        self.game_started = True
        return True

    def end_turn(self):
        self.current_player_index = (self.current_player_index + 1) % len(self.players)


def _request(action: str, request_id: str = "request-1", **values):
    return {
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request_id,
        "action": action,
        **values,
    }


class ProtocolSettingsTests(unittest.TestCase):
    def test_new_game_defaults_and_controller_requirements(self):
        settings = _parse_new_game_settings(
            {
                "players": [
                    {"name": "Codex", "controller": "codex", "team_id": 1},
                    {"name": "Human", "controller": "human", "team_id": 2},
                ]
            }
        )
        self.assertEqual(settings.num_systems, 15)
        self.assertEqual(settings.player_configs[0].controller, PlayerController.CODEX)

        invalid_cases = (
            {"players": [{"name": "Only", "controller": "codex", "team_id": 1}]},
            {
                "players": [
                    {"name": "A", "controller": "human", "team_id": 1},
                    {"name": "B", "controller": "openai", "team_id": 2},
                ]
            },
            {
                "players": [
                    {"name": "A", "controller": "codex", "team_id": 1},
                    {"name": "B", "controller": "codex", "team_id": 2},
                ]
            },
            {
                "players": [
                    {"name": "A", "controller": "codex", "team_id": 1},
                    {"name": "B", "controller": "human", "team_id": 1},
                ]
            },
            {
                "players": [
                    {"name": "A", "controller": "codex", "team_id": 1, "unknown": True},
                    {"name": "B", "controller": "human", "team_id": 2},
                ]
            },
        )
        for raw in invalid_cases:
            with self.subTest(raw=raw), self.assertRaises(ProtocolError):
                _parse_new_game_settings(raw)

    def test_invalid_game_settings_are_rejected(self):
        players = [
            {"name": "A", "controller": "codex", "team_id": 1},
            {"name": "B", "controller": "human", "team_id": 2},
        ]
        for values in (
            {"unknown": 1},
            {"wormhole_density": 1.1},
            {"num_systems": 1},
            {"starting_credits": -1},
            {"min_system_distance": 400, "max_system_distance": 300},
        ):
            with self.subTest(values=values), self.assertRaises(ProtocolError):
                _parse_new_game_settings({"players": players, **values})


class ControlServiceTests(unittest.TestCase):
    def setUp(self):
        self.game = _Game()
        self.service = ControlService(self.game, port=0)

    @patch("game_control_protocol.build_observation", return_value={"visible": "state"})
    def test_observe_token_is_opaque_and_stale_tokens_are_rejected(self, _observation):
        observed = self.service._dispatch("observe", "observe-1", _request("observe"))
        token = observed["data"]["turn_token"]
        self.assertNotIn(self.game.campaign_id, token)
        self.assertEqual(observed["data"]["observation"], {"visible": "state"})

        stale = self.service._dispatch(
            "command",
            "command-1",
            _request("command", turn_token="stale", commands=[{"type": "cancel_orders", "unit_ids": [1]}]),
        )
        self.assertFalse(stale["ok"])
        self.assertEqual(stale["error"]["code"], "stale_turn_token")

    @patch("game_control_protocol.CommandGateway")
    def test_commands_are_incremental_and_mutating_retries_are_idempotent(self, gateway_type):
        gateway_type.return_value.apply_batch.return_value = CommandResult(
            accepted=True,
            applied_count=1,
            receipts=("queued",),
        )
        token = self.service._turn_token(self.game.current_player)
        payload = _request(
            "command",
            "stable-request",
            turn_token=token,
            commands=[{"type": "cancel_orders", "unit_ids": [1]}],
        )
        first = self.service._dispatch_or_wait(payload, Future())
        second = self.service._dispatch_or_wait(payload, Future())
        self.assertTrue(first["ok"])
        self.assertEqual(first, second)
        self.assertEqual(gateway_type.return_value.apply_batch.call_count, 1)
        batch = gateway_type.return_value.apply_batch.call_args.args[1]
        self.assertFalse(batch.end_turn)
        self.assertEqual(self.game.current_player_index, 0)

        conflict = self.service._dispatch_or_wait(
            {**payload, "commands": [{"type": "cancel_orders", "unit_ids": [2]}]},
            Future(),
        )
        self.assertEqual(conflict["error"]["code"], "request_id_conflict")

    @patch("game_control_protocol.CommandGateway")
    def test_rejected_batch_keeps_turn_active(self, gateway_type):
        gateway_type.return_value.apply_batch.return_value = CommandResult(
            accepted=False,
            errors=(CommandError(0, "hidden_target", "Target is unavailable."),),
        )
        token = self.service._turn_token(self.game.current_player)
        response = self.service._dispatch(
            "command",
            "bad-command",
            _request(
                "command",
                turn_token=token,
                commands=[{"type": "attack", "unit_ids": [1], "target_id": 99}],
            ),
        )
        self.assertFalse(response["ok"])
        self.assertEqual(response["data"]["applied_count"], 0)
        self.assertEqual(self.game.current_player_index, 0)

    @patch("game_control_protocol.build_observation", return_value={"visible": "state"})
    def test_end_turn_and_wait_for_next_codex_turn(self, _observation):
        token = self.service._turn_token(self.game.current_player)
        ended = self.service._dispatch(
            "end_turn",
            "end-1",
            _request("end_turn", turn_token=token),
        )
        self.assertTrue(ended["ok"])
        self.assertEqual(self.game.current_player.controller, PlayerController.HUMAN)

        future = Future()
        response = self.service._begin_wait(_request("wait_for_turn", timeout_seconds=1), future)
        self.assertIsNone(response)
        self.game.current_player_index = 0
        self.service._resolve_waiters()
        self.assertTrue(future.result()["data"]["ready"])

    def test_shutdown_resolves_concurrent_waits(self):
        self.game.current_player_index = 1
        futures = [Future(), Future()]
        for index, future in enumerate(futures):
            response = self.service._begin_wait(
                _request("wait_for_turn", f"wait-{index}", timeout_seconds=30),
                future,
            )
            self.assertIsNone(response)
        self.assertEqual(len(self.service._waiters), 2)
        self.service.shutdown()
        for future in futures:
            self.assertEqual(future.result()["error"]["code"], "server_stopping")

    def test_status_and_new_game_reject_active_campaign(self):
        status = self.service._dispatch("status", "status-1", _request("status"))
        self.assertTrue(status["ok"])
        self.assertEqual(status["state"]["current_player"]["controller"], "codex")
        response = self.service._dispatch(
            "new_game",
            "new-1",
            _request("new_game", settings={"players": []}),
        )
        self.assertEqual(response["error"]["code"], "campaign_active")

    def test_wait_timeout_is_validated_even_when_codex_is_ready(self):
        response = self.service._begin_wait(
            _request("wait_for_turn", timeout_seconds=0),
            Future(),
        )
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "invalid_timeout")

    def test_codex_input_lock_does_not_depend_on_openai_coordinator(self):
        fake = SimpleNamespace(
            game_started=True,
            current_player=self.game.current_player,
            pending_ai_turn_end_time=0,
            ai_coordinator=SimpleNamespace(is_busy=False),
        )
        self.assertTrue(Game.is_ai_input_locked(fake))
        fake.current_player.controller = PlayerController.OPENAI
        self.assertFalse(Game.is_ai_input_locked(fake))
        fake.ai_coordinator.is_busy = True
        self.assertTrue(Game.is_ai_input_locked(fake))

    def test_codex_never_starts_builtin_openai_coordinator_or_timer(self):
        from game_ai.adapters.base import PlanningProvider
        provider = MagicMock(spec=PlanningProvider)
        coordinator = AgentTurnCoordinator(self.game, provider=provider)
        try:
            self.assertFalse(coordinator.start_current_turn())
            provider.plan_turn.assert_not_called()
        finally:
            coordinator.shutdown()

        self.game.pending_ai_turn_end_time = 123
        TurnProcessor(self.game, presentation=ApplicationTurnPresentation(self.game)).check_and_schedule_ai_turn()
        self.assertEqual(self.game.pending_ai_turn_end_time, 0)

    def test_socket_dispatch_runs_through_pump_and_enforces_size_limit(self):
        from concurrent.futures import ThreadPoolExecutor

        self.service.start()

        def client(payload):
            with socket.create_connection(("127.0.0.1", self.service.port), timeout=5) as connection:
                connection.sendall(payload + b"\n")
                with connection.makefile("rb") as response:
                    return json.loads(response.readline())

        def exchange(payload):
            # Surface client exceptions directly and always join the worker.
            # The bound accommodates scheduling on loaded Windows CI hosts.
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(client, payload)
                deadline = time.monotonic() + 5
                while not result.done() and time.monotonic() < deadline:
                    self.service.pump()
                    time.sleep(0.005)
                return result.result(timeout=1)

        response = exchange(json.dumps(_request("status")).encode())
        self.assertTrue(response["ok"])
        oversized = exchange(b"{" + (b" " * MAX_REQUEST_BYTES))
        self.assertEqual(oversized["error"]["code"], "request_too_large")
        self.assertIsNotNone(oversized["state"])

    def tearDown(self):
        self.service.shutdown()


class ControlCliTests(unittest.TestCase):
    def _run(self, argv, stdin=""):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.object(game_control.sys, "stdin", io.StringIO(stdin)):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = game_control.main(argv)
        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        return code, json.loads(lines[0]), stderr.getvalue()

    @patch("game_control._send")
    def test_positional_and_stdin_requests_keep_stdout_json_only(self, send):
        send.return_value = {"service": "wormhole-control", "ok": True}
        code, response, _ = self._run(['{"action":"status"}', "--no-launch"])
        self.assertEqual(code, 0)
        self.assertTrue(response["ok"])
        sent = send.call_args.args[0]
        self.assertEqual(sent["protocol_version"], PROTOCOL_VERSION)
        self.assertTrue(sent["request_id"])

        code, response, _ = self._run(["-", "--no-launch"], '{"action":"status"}')
        self.assertEqual(code, 0)
        self.assertTrue(response["ok"])

    def test_malformed_input_exits_two(self):
        code, response, diagnostics = self._run(["not-json"])
        self.assertEqual(code, 2)
        self.assertEqual(response["error"]["code"], "invalid_cli_input")
        self.assertTrue(diagnostics)

    @patch("game_control._wait_for_server")
    @patch("game_control._launch_game")
    @patch("game_control._send")
    def test_connection_refusal_launches_then_retries(self, send, launch, wait):
        send.side_effect = [ConnectionRefusedError(), {"service": "wormhole-control", "ok": True}]
        process = MagicMock()
        launch.return_value = process
        code, response, diagnostics = self._run(['{"action":"status"}'])
        self.assertEqual(code, 0)
        self.assertTrue(response["ok"])
        launch.assert_called_once_with(47653)
        wait.assert_called_once_with(47653, 15.0, process)
        self.assertIn("Launching", diagnostics)

    @patch("game_control._wait_for_server")
    @patch("game_control._launch_game")
    @patch("game_control._send")
    def test_connection_timeout_preserves_identity_without_launching(self, send, launch, wait):
        send.side_effect = game_control.TransportError('connect', socket.timeout(), 1.01, 1.0)
        code, response, diagnostics = self._run(['{"action":"status"}'])
        self.assertEqual(code, 2)
        self.assertEqual(response['error']['code'], 'connect_timeout')
        self.assertEqual(response['error']['retry']['request_id'], response['request_id'])
        self.assertFalse(response['error']['execution_uncertain'])
        self.assertNotIn('No Wormhole Control server', diagnostics)
        launch.assert_not_called()
        wait.assert_not_called()

    @patch("game_control._send")
    def test_protocol_rejection_exits_one(self, send):
        send.return_value = {"service": "wormhole-control", "ok": False}
        code, response, _ = self._run(['{"action":"command"}', "--no-launch"])
        self.assertEqual(code, 1)
        self.assertFalse(response["ok"])

    @patch("game_control._launch_game")
    @patch("game_control._send", side_effect=game_control.ClientError("incompatible service"))
    def test_handshake_conflict_is_transport_failure_without_launch(self, _send, launch):
        code, response, diagnostics = self._run(['{"action":"status"}'])
        self.assertEqual(code, 2)
        self.assertEqual(response["error"]["code"], "transport_error")
        self.assertIn("incompatible service", diagnostics)
        launch.assert_not_called()

    @patch("game_control._send", side_effect=game_control.ClientError("Transport \u2013 \u0394 \ud800"))
    def test_unencodable_diagnostics_preserve_the_json_error_response(self, _send):
        with io.BytesIO() as output, io.BytesIO() as errors:
            with io.TextIOWrapper(output, encoding="cp1252") as stdout:
                with io.TextIOWrapper(errors, encoding="cp1252") as stderr:
                    with patch.object(game_control.sys, "stdin", io.StringIO()):
                        with redirect_stdout(stdout), redirect_stderr(stderr):
                            code = game_control.main(['{"action":"status"}', "--no-launch"])
                    stdout.flush()
                    stderr.flush()
                    response = json.loads(output.getvalue().decode("utf-8"))
                    diagnostics = errors.getvalue().decode("utf-8")
        self.assertEqual(code, 2)
        self.assertEqual(response["error"]["code"], "transport_error")
        self.assertEqual(response["error"]["message"], "Transport \u2013 \u0394 \ud800")
        self.assertIn("Transport \u2013 \u0394 \\ud800", diagnostics)


@pytest.fixture
def cli_stub_server():
    """Answer real CLI connections without launching a campaign or AI provider."""
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(5)
            payload = json.loads(self.rfile.readline(MAX_REQUEST_BYTES + 1).decode("utf-8"))
            self.server.requests.append(payload)
            response = {
                "service": "wormhole-control",
                "protocol_version": PROTOCOL_VERSION,
                "request_id": payload["request_id"],
                "action": payload["action"],
                "ok": self.server.ok,
                "state": None,
                "data": {"name": "PT Yard \u0394", "description": "Orders \u2013 move"},
            }
            if not self.server.ok:
                response["error"] = {"code": "invalid_state", "message": "Unavailable \u2013 \u0394"}
            raw = json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n"
            self.wfile.write(raw)

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        server.requests = []
        server.ok = True
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            thread.join(timeout=5)


@pytest.mark.parametrize('phase', ['connect', 'send', 'read'])
@pytest.mark.parametrize('cause', [TimeoutError, ConnectionResetError, ConnectionRefusedError])
def test_transport_errors_preserve_phase_and_exact_retry_request(phase, cause, monkeypatch, capsys):
    connection = MagicMock()
    connection.__enter__.return_value = connection
    stream = connection.makefile.return_value.__enter__.return_value
    create = MagicMock(return_value=connection)
    if phase == 'connect':
        create.side_effect = cause(10060, 'private exception detail')
    elif phase == 'send':
        connection.sendall.side_effect = cause(10060, 'private exception detail')
    else:
        stream.readline.side_effect = cause(10060, 'private exception detail')
    monkeypatch.setattr(game_control.socket, 'create_connection', create)
    launch = MagicMock()
    monkeypatch.setattr(game_control, '_launch_game', launch)
    request = {'action': 'end_turn', 'request_id': 'retry-identity', 'turn_token': 'private-token'}
    assert game_control.main([json.dumps(request), '--no-launch']) == 2
    output = capsys.readouterr()
    response = json.loads(output.out)
    error = response['error']
    assert error['transport']['phase'] == phase and error['transport']['cause'] == cause.__name__
    assert error['transport']['errno'] == 10060
    assert error['execution_uncertain'] == (phase != 'connect')
    assert error['retry']['request_id'] == 'retry-identity'
    assert 'private-token' not in output.out + output.err
    assert 'private exception detail' not in output.out + output.err
    launch.assert_not_called()


def test_launch_keeps_utf8_runtime_stderr_in_append_only_file(tmp_path, monkeypatch):
    monkeypatch.setattr(game_control, '__file__', str(tmp_path / 'game_control.py'))
    captured = []

    def popen(*args, **kwargs):
        assert kwargs['env']['PYTHONIOENCODING'] == 'utf-8'
        kwargs['stderr'].write('startup failure Δ\n'.encode('utf-8'))
        captured.append(kwargs['stderr'])
        return MagicMock()

    monkeypatch.setattr(game_control.subprocess, 'Popen', popen)
    game_control._launch_game(47653)
    game_control._launch_game(47653)
    assert all(handle.closed for handle in captured)
    assert (tmp_path / 'saves/control_stderr.log').read_text(encoding='utf-8') == 'startup failure Δ\n' * 2


def test_repeated_local_connections_preserve_matching_responses(cli_stub_server):
    port = cli_stub_server.server_address[1]
    for index in range(150):
        request = {'protocol_version': PROTOCOL_VERSION, 'action': 'status', 'request_id': f'stress-{index}'}
        response = game_control._send(request, port)
        assert response['ok'] and response['request_id'] == request['request_id']
    assert len(cli_stub_server.requests) == 150


def _run_redirected_cli(server, *arguments, stdin=b"", legacy_encoding="cp1252"):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "game_control.py"), "--no-launch",
         "--port", str(server.server_address[1]), *arguments],
        input=stdin,
        capture_output=True,
        env=dict(os.environ, PYTHONIOENCODING=legacy_encoding, PYTHONUTF8="0",
                 PYGAME_HIDE_SUPPORT_PROMPT="1"),
        timeout=20,
    )
    text = result.stdout.decode("utf-8")
    diagnostics = result.stderr.decode("utf-8")
    assert result.stdout.endswith(b"\n"), diagnostics
    assert len(text.splitlines()) == 1, diagnostics
    assert "Traceback" not in diagnostics
    return result, json.loads(text), diagnostics


@pytest.mark.parametrize("legacy_encoding", ["cp1252", "ascii"])
@pytest.mark.parametrize("request_source", ["positional", "stdin_dash", "stdin_default"])
@pytest.mark.parametrize("accepted", [True, False])
def test_redirected_cli_preserves_utf8_requests_and_responses(
    cli_stub_server, legacy_encoding, request_source, accepted,
):
    cli_stub_server.ok = accepted
    request = _request(
        "command", "rename-\u0394",
        commands=[{"type": "rename_unit", "unit_ids": [1], "new_name": "PT Yard \u0394"}],
    )
    raw = json.dumps(request, ensure_ascii=False)
    arguments = [raw] if request_source == "positional" else ["-"] if request_source == "stdin_dash" else []
    result, response, diagnostics = _run_redirected_cli(
        cli_stub_server, *arguments,
        stdin=b"" if request_source == "positional" else raw.encode("utf-8"),
        legacy_encoding=legacy_encoding,
    )
    assert result.returncode == (0 if accepted else 1)
    assert response["ok"] is accepted
    assert response["request_id"] == request["request_id"]
    assert response["data"] == {"name": "PT Yard \u0394", "description": "Orders \u2013 move"}
    assert "PT Yard \u0394".encode("utf-8") in result.stdout
    assert "Orders \u2013 move".encode("utf-8") in result.stdout
    assert cli_stub_server.requests == [request]
    assert not diagnostics


@pytest.mark.parametrize(("arguments", "stdin"), [
    (["-"], b'{"action":"status","name":"\xff"}'),
    (["-"], b'{"action":"status","name":"\\ud800"}'),
    (['{"action":"status","name":"\\ud800"}'], b""),
])
def test_redirected_cli_rejects_invalid_unicode_before_connecting(cli_stub_server, arguments, stdin):
    result, response, diagnostics = _run_redirected_cli(cli_stub_server, *arguments, stdin=stdin)
    assert result.returncode == 2
    assert response["error"]["code"] == "invalid_cli_input"
    assert diagnostics
    assert cli_stub_server.requests == []


@pytest.mark.parametrize(("arguments", "error_code"), [
    (["--unknown-\u0394"], "invalid_cli_arguments"),
    (["--port", "0", '{"action":"status"}'], "invalid_port"),
    (["not-json"], "invalid_cli_input"),
])
def test_redirected_cli_input_errors_keep_utf8_json_and_diagnostics(cli_stub_server, arguments, error_code):
    result, response, diagnostics = _run_redirected_cli(cli_stub_server, *arguments)
    assert result.returncode == 2
    assert response["error"]["code"] == error_code
    assert diagnostics
    if error_code == "invalid_cli_arguments":
        assert "\u0394".encode("utf-8") in result.stdout
        assert "\u0394" in diagnostics
    assert cli_stub_server.requests == []


@pytest.mark.parametrize('host', ['localhost', '0.0.0.0', '::1', '192.0.2.1', None])
def test_control_rejects_unsupported_hosts(host):
    with pytest.raises(ValueError, match='127.0.0.1'):
        ControlService(None, host=host, port=0)
    assert not ControlService(None, host='127.0.0.1', port=0).is_running
