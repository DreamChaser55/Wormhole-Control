"""Versioned localhost control protocol for Codex-driven players."""

from __future__ import annotations

import copy
import json
import logging
import math
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
from game_ai.runtime import MAX_REPAIR_RETRIES, MIN_REPAIR_RETRIES
from game_settings import GameSettings, PlayerConfig, PLAYER_COLOR_PALETTE
from player_controller import PlayerController

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
SERVICE_NAME = "wormhole-control"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 47653
MAX_REQUEST_BYTES = 1024 * 1024
MAX_CACHE_ENTRIES = 256
MAX_COMMANDS = 40
MAX_WAIT_SECONDS = 600.0
MUTATING_ACTIONS = frozenset({"new_game", "command", "end_turn"})


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
        if payload.get("protocol_version") != PROTOCOL_VERSION:
            raise ProtocolError("unsupported_protocol", f"protocol_version must be {PROTOCOL_VERSION}.")
        action = payload.get("action")
        if action not in {"status", "new_game", "observe", "command", "end_turn", "wait_for_turn"}:
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
            if action == "observe":
                player = self._require_codex_turn()
                return self._success(action, request_id, self._observation_data(player))
            if action == "command":
                return self._command(action, request_id, payload)
            if action == "end_turn":
                return self._end_turn(action, request_id, payload)
        except ProtocolError as exc:
            return self.envelope_error(action, request_id, exc.code, str(exc), exc.details)
        raise AssertionError(f"Unhandled action {action}")

    def _new_game(self, action: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if getattr(self.game, "game_started", False):
            raise ProtocolError("campaign_active", "Quit to the main menu before creating another campaign.")
        settings = _parse_new_game_settings(payload.get("settings"))
        if not self.game.start_new_game(settings=settings):
            raise ProtocolError("new_game_failed", "The game could not create the requested campaign.")
        return self._success(action, request_id, {"created": True})

    def _command(self, action: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        player = self._require_codex_turn()
        self._require_turn_token(payload, player)
        raw_commands = payload.get("commands")
        if not isinstance(raw_commands, list) or not 1 <= len(raw_commands) <= MAX_COMMANDS:
            raise ProtocolError("invalid_commands", f"commands must contain 1-{MAX_COMMANDS} objects.")
        try:
            commands = tuple(Command.from_dict(raw) for raw in raw_commands)
        except ContractError as exc:
            raise ProtocolError("invalid_command_contract", str(exc)) from exc
        result = CommandGateway(self.game).apply_batch(player, CommandBatch(commands, end_turn=False))
        data = {
            "accepted": result.accepted,
            "applied_count": result.applied_count,
            "receipts": list(result.receipts),
            "turn_token": self._turn_token(player),
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
            if now >= waiter.deadline:
                waiter.future.set_result(self._success("wait_for_turn", request_id, {"ready": False}))
                continue
            remaining.append(waiter)
        self._waiters = remaining

    def _require_codex_turn(self) -> Any:
        if not getattr(self.game, "game_started", False):
            raise ProtocolError("game_not_started", "Create or load a campaign first.")
        player = getattr(self.game, "current_player", None)
        if player is None or player.controller != PlayerController.CODEX:
            raise ProtocolError("not_codex_turn", "The active player is not controlled by Codex.")
        return player

    def _require_turn_token(self, payload: dict[str, Any], player: Any) -> str:
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
        return {"turn_token": self._turn_token(player), "observation": build_observation(self.game, player)}

    def _public_state(self) -> dict[str, Any]:
        started = bool(getattr(self.game, "game_started", False))
        player = getattr(self.game, "current_player", None) if started else None
        return {
            "game_started": started,
            "view_mode": str(getattr(self.game, "view_mode", "main_menu")),
            "campaign_id": str(getattr(self.game, "campaign_id", "")) if started else None,
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
}
_PLAYER_FIELDS = {"name", "controller", "team_id", "color", "ai_reasoning_effort", "ai_repair_retries"}


def _parse_new_game_settings(raw: Any) -> GameSettings:
    if not isinstance(raw, dict):
        raise ProtocolError("invalid_settings", "settings must be an object.")
    unknown = sorted(set(raw) - _SETTINGS_FIELDS)
    if unknown:
        raise ProtocolError("unknown_settings", "Unknown game settings fields.", unknown)
    players_raw = raw.get("players")
    if not isinstance(players_raw, list) or not 2 <= len(players_raw) <= 6:
        raise ProtocolError("invalid_players", "settings.players must contain 2-6 player objects.")
    players = [_parse_player_config(item, index) for index, item in enumerate(players_raw)]
    if sum(config.controller == PlayerController.CODEX for config in players) != 1:
        raise ProtocolError("invalid_codex_count", "A campaign must contain exactly one Codex player.")
    if len({config.team_id for config in players}) < 2:
        raise ProtocolError("invalid_teams", "Players must belong to at least two teams.")

    kwargs: dict[str, Any] = {"player_configs": players}
    integer_fields = {"num_systems", "system_radius_min", "system_radius_max", "starting_population"}
    number_fields = {
        "min_system_distance",
        "max_system_distance",
        "wormhole_density",
        "starting_credits",
        "starting_metal",
        "starting_crystal",
    }
    for field in integer_fields:
        if field in raw:
            value = raw[field]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ProtocolError("invalid_settings", f"settings.{field} must be an integer.")
            kwargs[field] = value
    for field in number_fields:
        if field in raw:
            value = raw[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProtocolError("invalid_settings", f"settings.{field} must be a number.")
            if not math.isfinite(float(value)):
                raise ProtocolError("invalid_settings", f"settings.{field} must be finite.")
            kwargs[field] = float(value)

    num_systems = kwargs.get("num_systems", GameSettings.num_systems)
    radius_min = kwargs.get("system_radius_min", GameSettings.system_radius_min)
    radius_max = kwargs.get("system_radius_max", GameSettings.system_radius_max)
    population = kwargs.get("starting_population", GameSettings.starting_population)
    if not 5 <= num_systems <= 30:
        raise ProtocolError("invalid_settings", "settings.num_systems must be between 5 and 30.")
    if not 3 <= radius_min <= 10 or not 3 <= radius_max <= 10:
        raise ProtocolError("invalid_settings", "System radii must be between 3 and 10.")
    if population < 0:
        raise ProtocolError("invalid_settings", "settings.starting_population cannot be negative.")
    density = kwargs.get("wormhole_density", GameSettings.wormhole_density)
    if not 0.0 <= density <= 1.0:
        raise ProtocolError("invalid_settings", "settings.wormhole_density must be between 0 and 1.")
    for field in ("min_system_distance", "max_system_distance"):
        if kwargs.get(field, getattr(GameSettings, field)) <= 0:
            raise ProtocolError("invalid_settings", f"settings.{field} must be positive.")
    for field in ("starting_credits", "starting_metal", "starting_crystal"):
        if kwargs.get(field, getattr(GameSettings, field)) < 0:
            raise ProtocolError("invalid_settings", f"settings.{field} cannot be negative.")
    try:
        return GameSettings(**kwargs)
    except ValueError as exc:
        raise ProtocolError("invalid_settings", str(exc)) from exc


def _parse_player_config(raw: Any, index: int) -> PlayerConfig:
    if not isinstance(raw, dict):
        raise ProtocolError("invalid_player", f"settings.players[{index}] must be an object.")
    unknown = sorted(set(raw) - _PLAYER_FIELDS)
    if unknown:
        raise ProtocolError("unknown_player_fields", f"Unknown fields for player {index}.", unknown)
    missing = [field for field in ("name", "controller", "team_id") if field not in raw]
    if missing:
        raise ProtocolError("missing_player_fields", f"Player {index} is missing required fields.", missing)
    name = raw["name"]
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        raise ProtocolError("invalid_player_name", f"Player {index} name must contain 1-80 characters.")
    try:
        controller = PlayerController(raw["controller"])
    except (TypeError, ValueError) as exc:
        raise ProtocolError("invalid_controller", f"Player {index} controller must be human, openai, or codex.") from exc
    team_id = raw["team_id"]
    if isinstance(team_id, bool) or not isinstance(team_id, int) or team_id < 1:
        raise ProtocolError("invalid_team", f"Player {index} team_id must be a positive integer.")
    color = raw.get("color", PLAYER_COLOR_PALETTE[index % len(PLAYER_COLOR_PALETTE)][1])
    if (
        not isinstance(color, (list, tuple))
        or len(color) != 3
        or any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 255 for value in color)
    ):
        raise ProtocolError("invalid_color", f"Player {index} color must be three integers from 0 to 255.")
    effort = raw.get("ai_reasoning_effort", "medium")
    retries = raw.get("ai_repair_retries", 2)
    if controller != PlayerController.OPENAI and ({"ai_reasoning_effort", "ai_repair_retries"} & set(raw)):
        raise ProtocolError("irrelevant_ai_settings", f"Player {index} AI settings are only valid for openai controllers.")
    if effort not in {"low", "medium", "high"}:
        raise ProtocolError("invalid_reasoning_effort", f"Player {index} ai_reasoning_effort must be low, medium, or high.")
    if isinstance(retries, bool) or not isinstance(retries, int) or not MIN_REPAIR_RETRIES <= retries <= MAX_REPAIR_RETRIES:
        raise ProtocolError(
            "invalid_repair_retries",
            f"Player {index} ai_repair_retries must be between {MIN_REPAIR_RETRIES} and {MAX_REPAIR_RETRIES}.",
        )
    return PlayerConfig(
        name=name.strip(),
        color=tuple(color),
        controller=controller,
        team_id=team_id,
        ai_reasoning_effort=effort,
        ai_repair_retries=retries,
    )
