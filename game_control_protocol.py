"""Versioned localhost control protocol for Codex-driven players."""

from __future__ import annotations

import copy
import json
import logging
import os
import queue
import secrets
import socketserver
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, cast

from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch, ContractError
from game_ai.observation import build_observation
from game_settings import (GameSettings, PlayerConfig, PLAYER_COLOR_PALETTE,
                           SettingsValidationError, MIN_PLAYERS, MAX_PLAYERS)
from player_controller import PlayerController

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 4
SERVICE_NAME = "wormhole-control"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 47653
MAX_REQUEST_BYTES = 1024 * 1024
MAX_CACHE_ENTRIES = 256
MAX_COMMANDS = 40
MAX_WAIT_SECONDS = 600.0
MUTATING_ACTIONS = frozenset({"new_game", "command", "end_turn", "retry_ai_turn", "skip_failed_ai_turn", "save_game", "load_game", "return_to_menu"})


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"{value} is not valid JSON.")


class ProtocolError(ValueError):
    def __init__(self, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass
class _QueuedRequest:
    payload: dict[str, Any]
    future: Future
    protocol_error: ProtocolError | None = None


@dataclass
class _PendingWait:
    payload: dict[str, Any]
    future: Future
    deadline: float


class _ThreadingControlServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _ControlRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        service: ControlService = self.server.control_service  # type: ignore[attr-defined]
        raw = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            self._queue_error(service, "request_too_large", "Request exceeds 1 MiB.")
            return
        if not raw:
            self._queue_error(service, "empty_request", "Request body is empty.")
            return
        try:
            payload = json.loads(
                raw.decode("utf-8"), parse_constant=_reject_non_json_constant
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self._queue_error(service, "invalid_json", "Request must be one UTF-8 JSON object.")
            return
        if not isinstance(payload, dict):
            self._queue_error(service, "invalid_request", "Request must be a JSON object.")
            return

        future: Future = Future()
        service._requests.put(_QueuedRequest(payload, future))
        requested_wait = payload.get("timeout_seconds")
        timeout = 130.0
        if (
            payload.get("action") == "wait_for_turn"
            and isinstance(requested_wait, (int, float))
            and not isinstance(requested_wait, bool)
        ):
            timeout = min(MAX_WAIT_SECONDS, max(0.0, float(requested_wait))) + 10.0
        try:
            response = future.result(timeout=timeout)
        except FutureTimeoutError:
            response = service.envelope_error(
                str(payload.get("action", "unknown")),
                str(payload.get("request_id", "")),
                "server_timeout",
                "The game did not process the request before the server deadline.",
            )
        self._write(response)

    def _queue_error(self, service: ControlService, code: str, message: str) -> None:
        future: Future = Future()
        service._requests.put(
            _QueuedRequest({}, future, ProtocolError(code, message))
        )
        try:
            response = future.result(timeout=10.0)
        except FutureTimeoutError:
            response = service.envelope_error(
                "unknown", "", "server_timeout", "The game did not process the invalid request."
            )
        self._write(response)

    def _write(self, response: dict[str, Any]) -> None:
        encoded = json.dumps(response, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
        self.wfile.write(encoded)


class ControlService:
    """Own socket I/O off-thread and dispatch live game work from ``pump``."""

    def __init__(self, game: Any, *, host: str = DEFAULT_HOST, port: int | None = None):
        """Configure a loopback service; reject unsupported hosts before socket creation."""
        if host != DEFAULT_HOST:
            raise ValueError("Control host must be 127.0.0.1.")
        self.game = game
        self.host = DEFAULT_HOST
        configured = os.environ.get("WORMHOLE_CONTROL_PORT", "").strip()
        self.port = int(configured) if port is None and configured else (port if port is not None else DEFAULT_PORT)
        if not 0 <= self.port <= 65535:
            raise ValueError("Control port must be between 0 and 65535.")
        self._requests: queue.Queue[_QueuedRequest] = queue.Queue()
        self._waiters: list[_PendingWait] = []
        self._cache: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()
        self._token_identity: tuple[Any, ...] | None = None
        self._token_value: str | None = None
        self._requires_observation = False
        self._unobserved_created_ids = set()
        self._server: _ThreadingControlServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._server is not None

    def start(self) -> None:
        if self._server is not None:
            return
        server = _ThreadingControlServer((self.host, self.port), _ControlRequestHandler)
        server.control_service = self  # type: ignore[attr-defined]
        self.port = int(server.server_address[1])
        self._server = server
        self._thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="wormhole-control",
            daemon=True,
        )
        self._thread.start()
        logger.info("Codex control server listening on %s:%s", self.host, self.port)

    def pump(self, *, max_requests: int = 32) -> None:
        for _ in range(max_requests):
            try:
                queued = self._requests.get_nowait()
            except queue.Empty:
                break
            if queued.future.cancelled():
                continue
            try:
                if queued.protocol_error is not None:
                    response = self.envelope_error(
                        "unknown",
                        "",
                        queued.protocol_error.code,
                        str(queued.protocol_error),
                        queued.protocol_error.details,
                    )
                else:
                    response = self._dispatch_or_wait(queued.payload, queued.future)
            except ProtocolError as exc:
                response = self.envelope_error(
                    str(queued.payload.get("action", "unknown")),
                    str(queued.payload.get("request_id", "")),
                    exc.code,
                    str(exc),
                    exc.details,
                )
            except Exception:
                logger.exception("Unexpected Codex control request failure.")
                response = self.envelope_error(
                    str(queued.payload.get("action", "unknown")),
                    str(queued.payload.get("request_id", "")),
                    "internal_error",
                    "The game could not process the request.",
                )
            if response is not None and not queued.future.done():
                queued.future.set_result(response)
        self._resolve_waiters()

    def shutdown(self) -> None:
        response = self.envelope_error("unknown", "", "server_stopping", "The game is shutting down.")
        while True:
            try:
                queued = self._requests.get_nowait()
            except queue.Empty:
                break
            if not queued.future.done():
                queued.future.set_result(response)
        for waiter in self._waiters:
            if not waiter.future.done():
                waiter.future.set_result(response)
        self._waiters.clear()
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _dispatch_or_wait(self, payload: dict[str, Any], future: Future) -> dict[str, Any] | None:
        action, request_id = self._validate_envelope(payload)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        if action in MUTATING_ACTIONS:
            cached = self._cache.get(request_id)
            if cached is not None:
                cached_payload, cached_response = cached
                if cached_payload != canonical:
                    return self.envelope_error(
                        action,
                        request_id,
                        "request_id_conflict",
                        "This request_id was already used with a different payload.",
                    )
                self._cache.move_to_end(request_id)
                return copy.deepcopy(cached_response)

        if action == "wait_for_turn":
            response = self._begin_wait(payload, future)
        else:
            response = self._dispatch(action, request_id, payload)

        if response is not None and action in MUTATING_ACTIONS:
            self._cache[request_id] = (canonical, copy.deepcopy(response))
            self._cache.move_to_end(request_id)
            while len(self._cache) > MAX_CACHE_ENTRIES:
                self._cache.popitem(last=False)
        return response

    def _validate_envelope(self, payload: dict[str, Any]) -> tuple[str, str]:
        if type(payload.get("protocol_version")) is not int or payload["protocol_version"] != PROTOCOL_VERSION:
            raise ProtocolError("unsupported_protocol", f"Upgrade your client: protocol_version must be {PROTOCOL_VERSION}; legacy order observations are not supported.")
        action = payload.get("action")
        if action not in MUTATING_ACTIONS | {"status", "observe", "export_setup", "export_state", "list_saves", "wait_for_turn"}:
            raise ProtocolError("unknown_action", "Unknown control action.")
        request_id = payload.get("request_id", "")
        if not isinstance(request_id, str) or len(request_id) > 128:
            raise ProtocolError("invalid_request_id", "request_id must be a string of at most 128 characters.")
        if action in MUTATING_ACTIONS and not request_id:
            raise ProtocolError("request_id_required", "Mutating actions require request_id.")
        return action, request_id

    def _dispatch(self, action: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            if action == "status":
                return self._success(action, request_id, {"service": SERVICE_NAME})
            if action == "new_game":
                return self._new_game(action, request_id, payload)
            if action in {"observe", "export_state"}:
                player = self._require_codex_turn()
                data = self._observation_data(player)
                if action == "export_state":
                    data["setup"] = copy.deepcopy(getattr(self.game, "setup_metadata", None))
                return self._success(action, request_id, data)
            if action == "export_setup":
                if not getattr(self.game, "game_started", False):
                    raise ProtocolError("game_not_started", "Create or load a campaign first.")
                return self._success(action, request_id, {"setup": copy.deepcopy(getattr(self.game, "setup_metadata", None))})
            if action == "list_saves":
                return self._list_saves(action, request_id)
            if action in {"save_game", "load_game", "return_to_menu"}:
                return self._campaign_action(action, request_id, payload)
            if action == "command":
                return self._command(action, request_id, payload)
            if action == "end_turn":
                return self._end_turn(action, request_id, payload)
            if action in {"retry_ai_turn", "skip_failed_ai_turn"}:
                return self._recover_ai_turn(action, request_id, payload)
        except ProtocolError as exc:
            return self.envelope_error(action, request_id, exc.code, str(exc), exc.details)
        raise AssertionError(f"Unhandled action {action}")

    def _new_game(self, action: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if getattr(self.game, "game_started", False):
            raise ProtocolError("campaign_active", "Quit to the main menu before creating another campaign.")
        settings = _parse_new_game_settings(payload.get("settings"))
        if not self.game.start_new_game(settings=settings):
            raise ProtocolError("new_game_failed", getattr(self.game, 'last_setup_error', None) or "The game could not create the requested campaign.")
        return self._success(action, request_id, {"created": True})

    def _command(self, action: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        player = self._require_codex_turn()
        self._require_turn_token(payload, player)
        raw_commands = payload.get("commands")
        if not isinstance(raw_commands, list) or not 1 <= len(raw_commands) <= MAX_COMMANDS:
            raise ProtocolError("invalid_commands", f"commands must contain 1-{MAX_COMMANDS} objects.")
        commands, errors = [], []
        for index, raw in enumerate(raw_commands):
            try:
                command = Command.from_dict(raw)
                if command.target_id in self._unobserved_created_ids or any(uid in self._unobserved_created_ids for uid in command.unit_ids):
                    errors.append({'command_index': index, 'code': 'target_unavailable', 'message': 'The target is unavailable.'})
                commands.append(command)
            except ContractError as exc:
                errors.append({"command_index": index, "code": "invalid_command_contract", "message": str(exc)})
        if errors:
            error_code = "commands_rejected" if any(e["code"] == "target_unavailable" for e in errors) else "invalid_command_contract"
            return self.envelope_error(action, request_id, error_code, "The command batch was rejected.", errors,
                data={"accepted": False, "applied_count": 0, "failure_stage": "preflight", "retryable": True,
                      "receipts": [], "operation_results": [], "may_have_partial_effects": False,
                      "requires_observation": False, "turn_token": self._turn_token(player)})
        from campaign_graph import iter_objects
        galaxy = getattr(self.game, 'galaxy', None)
        before_ids = {obj.id for obj, _ in iter_objects(galaxy)} if galaxy else set()
        result = CommandGateway(self.game).apply_batch(player, CommandBatch(tuple(commands), end_turn=False))
        if galaxy:
            self._unobserved_created_ids.update({obj.id for obj, _ in iter_objects(galaxy)} - before_ids)
        if result.requires_observation:
            self._requires_observation = True
            self._token_value = secrets.token_urlsafe(24)
        data = {
            "accepted": result.accepted,
            "failure_stage": result.failure_stage,
            "retryable": result.retryable,
            "operation_results": list(result.operation_results),
            "may_have_partial_effects": result.may_have_partial_effects,
            "requires_observation": result.requires_observation,
            "applied_count": result.applied_count,
            "receipts": list(result.receipts),
            "turn_token": None if self._requires_observation else self._turn_token(player),
        }
        if result.accepted:
            return self._success(action, request_id, data)
        return self.envelope_error(
            action,
            request_id,
            "commands_rejected",
            "The command batch was rejected.",
            [
                {"command_index": error.command_index, "code": error.code, "message": error.message}
                for error in result.errors
            ],
            data=data,
        )

    def _end_turn(self, action: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        player = self._require_codex_turn()
        token = self._require_turn_token(payload, player)
        ended = {
            "turn_token": token,
            "turn_number": int(getattr(self.game, "turn_number", 1)),
            "player_id": int(player.id),
            "player_name": str(player.name),
        }
        self.game.end_turn()
        return self._success(action, request_id, {"ended_turn": ended})

    def _begin_wait(self, payload: dict[str, Any], future: Future) -> dict[str, Any] | None:
        action = "wait_for_turn"
        request_id = str(payload.get("request_id", ""))
        try:
            timeout = payload.get("timeout_seconds", 120)
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
                raise ProtocolError("invalid_timeout", "timeout_seconds must be a number from 1 to 600.")
            timeout = float(timeout)
            if not 1.0 <= timeout <= MAX_WAIT_SECONDS:
                raise ProtocolError("invalid_timeout", "timeout_seconds must be between 1 and 600.")
            if not getattr(self.game, "game_started", False):
                raise ProtocolError("game_not_started", "Create or load a campaign first.")
            if not any(player.controller == PlayerController.CODEX for player in self.game.players):
                raise ProtocolError("no_codex_player", "The campaign has no Codex-controlled player.")
            player = getattr(self.game, "current_player", None)
            if player is not None and player.controller == PlayerController.CODEX:
                return self._success(action, request_id, {"ready": True, **self._observation_data(player)})
            if self._public_state()["attention_required"]:
                return self._success(action, request_id, {"ready": False, "attention_required": True})
            self._waiters.append(_PendingWait(payload, future, time.monotonic() + timeout))
            return None
        except ProtocolError as exc:
            return self.envelope_error(action, request_id, exc.code, str(exc), exc.details)

    def _resolve_waiters(self) -> None:
        if not self._waiters:
            return
        now = time.monotonic()
        remaining: list[_PendingWait] = []
        for waiter in self._waiters:
            if waiter.future.done():
                continue
            request_id = str(waiter.payload.get("request_id", ""))
            if not getattr(self.game, "game_started", False):
                waiter.future.set_result(self.envelope_error("wait_for_turn", request_id, "game_not_started", "The campaign is no longer active."))
                continue
            player = getattr(self.game, "current_player", None)
            if player is not None and player.controller == PlayerController.CODEX:
                waiter.future.set_result(self._success("wait_for_turn", request_id, {"ready": True, **self._observation_data(player)}))
                continue
            if self._public_state()["attention_required"]:
                waiter.future.set_result(self._success("wait_for_turn", request_id, {"ready": False, "attention_required": True}))
                continue
            if now >= waiter.deadline:
                waiter.future.set_result(self._success("wait_for_turn", request_id, {"ready": False}))
                continue
            remaining.append(waiter)
        self._waiters = remaining

    def _recover_ai_turn(self, action, request_id, payload):
        if set(payload) - {"protocol_version", "action", "request_id", "recovery_token"}:
            raise ProtocolError("invalid_recovery", "Recovery accepts only the failed-turn recovery_token.")
        lifecycle = self._public_state()["ai_lifecycle"]
        if lifecycle is None or action not in lifecycle["recovery_actions"]:
            raise ProtocolError("ai_recovery_unavailable", "This action is available only for a failed AI turn; a partial commit cannot be retried automatically.")
        if payload.get("recovery_token") != lifecycle["recovery_token"]:
            raise ProtocolError("stale_recovery_token", "The recovery token is missing or stale.")
        coordinator = self.game.ai_coordinator
        self.game.pending_ai_turn_end_time = 0
        coordinator.reset()
        self._token_value = secrets.token_urlsafe(24)
        if action == "retry_ai_turn":
            if not coordinator.start_current_turn():
                raise ProtocolError("ai_recovery_unavailable", "The AI turn could not be restarted.")
            return self._success(action, request_id, {"retried": True})
        self.game.end_turn()
        return self._success(action, request_id, {"skipped": True})

    @staticmethod
    def _save_path(name):
        """A basename inside the configured save root, including after resolution."""
        import re
        from pathlib import Path
        import save_manager
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\.json", name):
            raise ProtocolError("invalid_save_name", "save_name must be a short ASCII basename ending in .json.")
        reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
        if name.split('.')[0].lower() in reserved:
            raise ProtocolError("invalid_save_name", "Reserved file names are not allowed.")
        try:
            root = Path(save_manager.SAVES_DIR).resolve()
            path = (root / name).resolve()
        except (OSError, RuntimeError) as exc:
            raise ProtocolError("invalid_save_name", "Save files must stay inside the configured save directory.") from exc
        if path.parent != root:
            raise ProtocolError("invalid_save_name", "Save files must stay inside the configured save directory.")
        return path

    def _list_saves(self, action, request_id):
        from pathlib import Path
        import save_manager
        root = Path(save_manager.SAVES_DIR)
        files = sorted(root.glob('*.json'), reverse=True) if root.exists() else []
        entries = []
        for file in files:
            try:
                path = self._save_path(file.name)
                raw = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(raw, dict) or not isinstance(raw.get('game_state'), dict):
                    continue
                turn = raw['game_state'].get('turn_number')
                entries.append({'save_name': file.name, 'compatible': raw.get('version') == save_manager.CURRENT_SAVE_VERSION,
                                'turn_number': turn if type(turn) is int and turn > 0 else None})
            except (ProtocolError, OSError, ValueError):
                continue
        return self._success(action, request_id, {'saves': entries[:64], 'omitted_count': max(0, len(entries) - 64)})

    def _campaign_action(self, action, request_id, payload):
        allowed = {"protocol_version", "action", "request_id", "campaign_token"}
        if action in {"save_game", "load_game"}:
            allowed.add("save_name")
        if action == "save_game":
            allowed.add("overwrite")
        if set(payload) - allowed:
            raise ProtocolError("invalid_lifecycle_request", "Unknown campaign lifecycle fields.")
        if action == "load_game":
            if getattr(self.game, "game_started", False):
                raise ProtocolError("campaign_active", "Return to the main menu before loading another campaign.")
            path = self._save_path(payload.get('save_name'))
            if not path.is_file() or not self.game.load_game(str(path)):
                raise ProtocolError("load_failed", "The selected save could not be loaded.")
            self._requires_observation = False
            self._unobserved_created_ids.clear()
            return self._success(action, request_id, {'loaded': True})
        player = getattr(self.game, 'current_player', None)
        if not getattr(self.game, 'game_started', False) or player is None:
            raise ProtocolError("game_not_started", "Create or load a campaign first.")
        if payload.get('campaign_token') != self._turn_token(player):
            raise ProtocolError("stale_campaign_token", "Use the current status campaign_token for this action.")
        if action == 'return_to_menu':
            self.game.quit_to_main_menu()
            self._requires_observation = False
            self._unobserved_created_ids.clear()
            return self._success(action, request_id, {'returned_to_menu': True})
        path = self._save_path(payload.get('save_name'))
        overwrite = payload.get('overwrite', False)
        if type(overwrite) is not bool:
            raise ProtocolError('invalid_lifecycle_request', 'overwrite must be a boolean.')
        if path.exists() and not overwrite:
            raise ProtocolError('save_exists', 'The save exists; choose another name or explicitly set overwrite=true.')
        if self.game.save_game(str(path)) is None:
            raise ProtocolError('save_failed', 'The campaign could not be saved.')
        return self._success(action, request_id, {'saved': True, 'save_name': path.name})

    def _require_codex_turn(self) -> Any:
        if not getattr(self.game, "game_started", False):
            raise ProtocolError("game_not_started", "Create or load a campaign first.")
        player = getattr(self.game, "current_player", None)
        if player is None or player.controller != PlayerController.CODEX:
            raise ProtocolError("not_codex_turn", "The active player is not controlled by Codex.")
        return player

    def _require_turn_token(self, payload: dict[str, Any], player: Any) -> str:
        if self._requires_observation:
            raise ProtocolError("observation_required", "A commit failed; successfully observe current state before another command or end_turn.")
        supplied = payload.get("turn_token")
        expected = self._turn_token(player)
        if not isinstance(supplied, str) or supplied != expected:
            raise ProtocolError("stale_turn_token", "The turn token is missing or stale.")
        return supplied

    def _turn_token(self, player: Any) -> str:
        identity = (
            str(getattr(self.game, "campaign_id", "")),
            int(getattr(self.game, "turn_number", 1)),
            int(player.id),
            str(player.agent_id),
            id(player),
        )
        if identity != self._token_identity:
            self._token_identity = identity
            self._token_value = secrets.token_urlsafe(24)
        return cast(str, self._token_value)

    def _observation_data(self, player: Any) -> dict[str, Any]:
        observation = build_observation(self.game, player)
        self._unobserved_created_ids.clear()
        self._requires_observation = False
        return {"turn_token": self._turn_token(player), "observation": observation}

    def _public_state(self) -> dict[str, Any]:
        started = bool(getattr(self.game, "game_started", False))
        player = getattr(self.game, "current_player", None) if started else None
        lifecycle = None
        attention = False
        if player is not None and player.controller == PlayerController.OPENAI:
            coordinator = getattr(self.game, "ai_coordinator", None)
            failed = getattr(coordinator, "failed_current_turn", None)
            attention = callable(failed) and failed() is True
            phase = {"thinking": "planning", "repairing": "repairing", "applying": "applying", "cancelling": "cancelling"}.get(getattr(coordinator, "state", None), "manual_recovery")
            if getattr(self.game, "pending_ai_turn_end_time", 0) > 0:
                phase = "scheduled"
            if attention:
                phase = "failed"
            from game_ai.provider_errors import MESSAGES
            category = getattr(coordinator, "last_error_category", None) if attention else None
            if category is not None and category not in {*MESSAGES, "invalid_output", "preflight", "commit"}:
                category = "provider_error"
            actions = (["skip_failed_ai_turn"] if category == "commit" else ["retry_ai_turn", "skip_failed_ai_turn"]) if attention else []
            def repair_count(name):
                value = getattr(coordinator, name, 0)
                return min(5, max(0, value)) if type(value) is int else 0
            lifecycle = {"phase": phase, "error_category": category,
                         "repair_attempt": repair_count("_repair_attempts_used"),
                         "repair_limit": repair_count("_max_repair_retries"),
                         "manual_recovery_available": attention, "recovery_actions": actions,
                         "recovery_token": self._turn_token(player) if attention else None}
        return {
            "game_started": started,
            "view_mode": str(getattr(self.game, "view_mode", "main_menu")),
            "campaign_id": str(getattr(self.game, "campaign_id", "")) if started else None,
            "campaign_token": self._turn_token(player) if player is not None else None,
            "turn_number": int(getattr(self.game, "turn_number", 1)) if started else None,
            "current_player": (
                {
                    "id": int(player.id),
                    "name": str(player.name),
                    "team_id": int(player.team_id),
                    "controller": player.controller.value,
                }
                if player is not None
                else None
            ),
            "codex_ready": bool(player is not None and player.controller == PlayerController.CODEX),
            "attention_required": attention,
            "ai_lifecycle": lifecycle,
        }

    def _success(self, action: str, request_id: str, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "service": SERVICE_NAME,
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "action": action,
            "ok": True,
            "state": self._public_state(),
            "data": data,
        }

    def envelope_error(
        self,
        action: str,
        request_id: str,
        code: str,
        message: str,
        details: Any = None,
        *,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        error = {"code": code, "message": message}
        if details is not None:
            error["details"] = details
        response = {
            "service": SERVICE_NAME,
            "protocol_version": PROTOCOL_VERSION,
            "request_id": request_id,
            "action": action,
            "ok": False,
            "state": None,
            "error": error,
        }
        # Only the main-thread dispatcher may read live public state.
        if threading.current_thread() is threading.main_thread():
            response["state"] = self._public_state()
        if data is not None:
            response["data"] = data
        return response


_SETTINGS_FIELDS = {
    "players",
    "num_systems",
    "min_system_distance",
    "max_system_distance",
    "wormhole_density",
    "system_radius_min",
    "system_radius_max",
    "starting_credits",
    "starting_metal",
    "starting_crystal",
    "starting_population",
    "spawn_profile",
    "home_system_assignment_mode",
    "seed",
}
_PLAYER_FIELDS = {"name", "controller", "team_id", "color", "ai_reasoning_effort", "ai_repair_retries", "home_system_name"}


def _parse_new_game_settings(raw: Any) -> GameSettings:
    if not isinstance(raw, dict):
        raise ProtocolError("invalid_settings", "settings must be an object.")
    unknown = sorted(set(raw) - _SETTINGS_FIELDS)
    if unknown:
        raise ProtocolError("unknown_settings", "Unknown game settings fields.", unknown)
    players_raw = raw.get("players")
    if not isinstance(players_raw, list) or not MIN_PLAYERS <= len(players_raw) <= MAX_PLAYERS:
        raise ProtocolError("invalid_players", "settings.players must contain 2-6 player objects.")
    players = [_parse_player_config(item, index) for index, item in enumerate(players_raw)]
    if sum(config.controller == PlayerController.CODEX for config in players) != 1:
        raise ProtocolError("invalid_codex_count", "A campaign must contain exactly one Codex player.")
    kwargs = {key: value for key, value in raw.items() if key != "players"}
    try:
        return GameSettings(player_configs=players, **kwargs)
    except SettingsValidationError as exc:
        raise ProtocolError(exc.issues[0].code, str(exc)) from exc


def _parse_player_config(raw: Any, index: int) -> PlayerConfig:
    if not isinstance(raw, dict):
        raise ProtocolError("invalid_player", f"settings.players[{index}] must be an object.")
    unknown = sorted(set(raw) - _PLAYER_FIELDS)
    if unknown:
        raise ProtocolError("unknown_player_fields", f"Unknown fields for player {index}.", unknown)
    missing = [field for field in ("name", "controller", "team_id") if field not in raw]
    if missing:
        raise ProtocolError("missing_player_fields", f"Player {index} is missing required fields.", missing)
    values = dict(raw)
    values.setdefault("color", PLAYER_COLOR_PALETTE[index % len(PLAYER_COLOR_PALETTE)][1])
    try:
        config = PlayerConfig(**values)
    except SettingsValidationError as exc:
        raise ProtocolError(exc.issues[0].code, str(exc)) from exc
    if config.controller != PlayerController.OPENAI and ({"ai_reasoning_effort", "ai_repair_retries"} & set(raw)):
        raise ProtocolError("irrelevant_ai_settings", f"Player {index} AI settings are only valid for openai controllers.")
    return config
