"""Small JSON CLI for controlling a running Wormhole Control game."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
from typing import Any

from game_control_protocol import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    MAX_REQUEST_BYTES,
    PROTOCOL_VERSION,
    SERVICE_NAME,
)

MAX_RESPONSE_BYTES = 32 * 1024 * 1024


class ClientError(RuntimeError):
    pass


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"{value} is not valid JSON.")


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ClientError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        description=f"Send one protocol v{PROTOCOL_VERSION} JSON control request to Wormhole Control.",
        epilog="Pass '-' or omit REQUEST_JSON to read the request from stdin.",
    )
    parser.add_argument("request_json", nargs="?", help="JSON request object, or '-' for stdin")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"localhost control port (default: {DEFAULT_PORT})",
    )
    parser.add_argument("--startup-timeout", type=float, default=15.0)
    parser.add_argument("--no-launch", action="store_true", help="fail instead of launching game.py")
    return parser


def _read_request(raw_argument: str | None) -> dict[str, Any]:
    raw = sys.stdin.read() if raw_argument in (None, "-") else raw_argument
    if not raw.strip():
        raise ClientError("Request JSON is empty.")
    try:
        payload = json.loads(raw, parse_constant=_reject_non_json_constant)
    except json.JSONDecodeError as exc:
        raise ClientError(f"Invalid JSON: {exc.msg}.") from exc
    except ValueError as exc:
        raise ClientError(f"Invalid JSON: {exc}.") from exc
    if not isinstance(payload, dict):
        raise ClientError("Request JSON must be an object.")
    payload.setdefault("protocol_version", PROTOCOL_VERSION)
    payload.setdefault("request_id", uuid.uuid4().hex)
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ClientError("Request exceeds 1 MiB.")
    return payload


def _response_timeout(payload: dict[str, Any]) -> float:
    if payload.get("action") == "wait_for_turn":
        wait = payload.get("timeout_seconds", 120)
        if isinstance(wait, (int, float)) and not isinstance(wait, bool):
            return min(600.0, max(1.0, float(wait))) + 10.0
    if payload.get("action") == "new_game":
        return 120.0
    return 30.0


def _send(payload: dict[str, Any], port: int, *, connect_timeout: float = 1.0) -> dict[str, Any]:
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
    with socket.create_connection((DEFAULT_HOST, port), timeout=connect_timeout) as connection:
        connection.settimeout(_response_timeout(payload))
        connection.sendall(encoded)
        stream = connection.makefile("rb")
        raw = stream.readline(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ClientError("Server response exceeds 32 MiB.")
    if not raw:
        raise ClientError("Server closed the connection without a response.")
    try:
        response = json.loads(
            raw.decode("utf-8"), parse_constant=_reject_non_json_constant
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ClientError("The listening service did not return Wormhole Control JSON.") from exc
    if isinstance(response, dict) and response.get("service") == SERVICE_NAME and response.get("protocol_version") != PROTOCOL_VERSION:
        raise ClientError(f"Protocol mismatch: update both game and controller to protocol {PROTOCOL_VERSION}.")
    if (
        not isinstance(response, dict)
        or response.get("service") != SERVICE_NAME
        or response.get("protocol_version") != PROTOCOL_VERSION
    ):
        raise ClientError("The configured port belongs to an incompatible service.")
    if response.get("request_id") != payload.get("request_id") or response.get("action") != payload.get("action"):
        raise ClientError("The control response does not match the request.")
    return response


def _launch_game(port: int) -> subprocess.Popen:
    root = Path(__file__).resolve().parent
    environment = os.environ.copy()
    environment["WORMHOLE_CONTROL_PORT"] = str(port)
    kwargs: dict[str, Any] = {
        "cwd": str(root),
        "env": environment,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        [sys.executable, str(root / "game.py"), "--port", str(port)],
        **kwargs,
    )


def _wait_for_server(port: int, timeout: float, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + max(0.1, timeout)
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ClientError(f"game.py exited during startup with code {process.returncode}.")
        probe = {
            "protocol_version": PROTOCOL_VERSION,
            "request_id": uuid.uuid4().hex,
            "action": "status",
        }
        try:
            _send(probe, port, connect_timeout=0.25)
            return
        except (ConnectionRefusedError, TimeoutError, socket.timeout, OSError) as exc:
            last_error = exc
            time.sleep(0.1)
        except ClientError:
            raise
    message = "Timed out waiting for game.py to start its control server."
    if last_error is not None:
        message += f" Last connection error: {last_error.__class__.__name__}."
    raise ClientError(message)


def _client_error_response(payload: dict[str, Any] | None, code: str, message: str) -> dict[str, Any]:
    payload = payload or {}
    return {
        "service": SERVICE_NAME,
        "protocol_version": PROTOCOL_VERSION,
        "request_id": str(payload.get("request_id", "")),
        "action": str(payload.get("action", "unknown")),
        "ok": False,
        "state": None,
        "error": {"code": code, "message": message},
    }


def main(argv: list[str] | None = None) -> int:
    payload: dict[str, Any] | None = None
    try:
        args = _parser().parse_args(argv)
    except ClientError as exc:
        response = _client_error_response(None, "invalid_cli_arguments", str(exc))
        print(json.dumps(response, separators=(",", ":")))
        print(str(exc), file=sys.stderr)
        return 2
    try:
        port = args.port
        if port is None:
            port = int(os.environ.get("WORMHOLE_CONTROL_PORT", DEFAULT_PORT))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        response = _client_error_response(None, "invalid_port", "Port must be an integer from 1 to 65535.")
        print(json.dumps(response, separators=(",", ":")))
        print("Invalid control port.", file=sys.stderr)
        return 2
    try:
        payload = _read_request(args.request_json)
    except ClientError as exc:
        print(json.dumps(_client_error_response(payload, "invalid_cli_input", str(exc)), separators=(",", ":")))
        print(str(exc), file=sys.stderr)
        return 2

    try:
        response = _send(payload, port)
    except (ConnectionRefusedError, TimeoutError, socket.timeout):
        if args.no_launch:
            response = _client_error_response(payload, "connection_failed", "No Wormhole Control server is listening.")
            print(json.dumps(response, separators=(",", ":"), ensure_ascii=False))
            print(response["error"]["message"], file=sys.stderr)
            return 2
        try:
            print(f"Launching game.py with control port {port}...", file=sys.stderr)
            process = _launch_game(port)
            _wait_for_server(port, args.startup_timeout, process)
            response = _send(payload, port)
        except (ClientError, OSError, socket.timeout) as exc:
            response = _client_error_response(payload, "launch_failed", str(exc))
            print(json.dumps(response, separators=(",", ":"), ensure_ascii=False))
            print(str(exc), file=sys.stderr)
            return 2
    except (ClientError, OSError, socket.timeout) as exc:
        response = _client_error_response(payload, "transport_error", str(exc))
        print(json.dumps(response, separators=(",", ":"), ensure_ascii=False))
        print(str(exc), file=sys.stderr)
        return 2

    print(json.dumps(response, separators=(",", ":"), ensure_ascii=False))
    return 0 if response.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
