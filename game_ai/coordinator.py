"""Non-blocking orchestration of one complete AI player turn."""

from __future__ import annotations

import json
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .adapters.base import (
    PlanningOutputError,
    PlanningRequest,
    PlanningResult,
    RepairContext,
    RepairIssue,
)
from .adapters.openai_responses import OpenAIResponsesProvider
from .commands import CommandGateway, CommandResult
from .memory import AgentMemory, write_memory_sidecar
from .observation import build_observation
from .runtime import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_REPAIR_RETRIES,
    get_runtime_config,
    normalize_repair_retries,
)

logger = logging.getLogger(__name__)


class AgentTurnCoordinator:
    """Owns background planning while keeping all game mutations on the main thread."""

    def __init__(
        self,
        game: Any,
        *,
        provider: Any | None = None,
        executor: ThreadPoolExecutor | None = None,
    ):
        self.game = game
        self.provider = provider or OpenAIResponsesProvider()
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="wormhole-ai"
        )
        self._owns_executor = executor is None
        self._future: Future | None = None
        self._request: PlanningRequest | None = None
        self._base_request: PlanningRequest | None = None
        self._turn_token: tuple[str, str, int] | None = None
        self._repair_attempts_used = 0
        self._max_repair_retries = DEFAULT_REPAIR_RETRIES
        self.state = "idle"
        self.status_message = ""
        self.last_error = ""

    @property
    def is_busy(self) -> bool:
        return self.state in {"thinking", "repairing", "applying"}

    def start_current_turn(self) -> bool:
        if self._future is not None or not getattr(self.game, "game_started", False):
            return False
        player = getattr(self.game, "current_player", None)
        if player is None or getattr(player, "is_human", True):
            return False
        observation = build_observation(self.game, player)
        memory = AgentMemory.from_dict(getattr(player, "ai_memory", None))
        request = PlanningRequest(
            campaign_id=str(getattr(self.game, "campaign_id", "legacy-campaign")),
            agent_id=str(getattr(player, "agent_id", f"legacy-player-{player.id}")),
            player_name=str(player.name),
            turn_number=int(getattr(self.game, "turn_number", 1)),
            observation=observation,
            memory=memory.to_dict(),
        )
        self._base_request = request
        self._repair_attempts_used = 0
        self._max_repair_retries = normalize_repair_retries(
            getattr(player, "ai_repair_retries", DEFAULT_REPAIR_RETRIES)
        )
        self._submit(request, repairing=False)
        return True

    def update(self) -> None:
        future = self._future
        if future is None or not future.done():
            return
        self._future = None
        try:
            result = future.result()
        except PlanningOutputError as exc:
            logger.warning("AI output was invalid: %s", exc)
            self._handle_output_error(exc)
            return
        except Exception as exc:
            logger.error("AI planning provider failed: %s", exc.__class__.__name__)
            self._record_transport_error(exc)
            self._fail(
                f"AI planning provider failed ({exc.__class__.__name__})."
            )
            return
        if not self._turn_is_current():
            self._discard_stale_result()
            return
        self._apply_result(result)

    def reset(self) -> None:
        """Forget in-flight work; completed stale responses will be discarded."""
        if self._future is not None:
            self._future.cancel()
        self._future = None
        self._request = None
        self._base_request = None
        self._turn_token = None
        self._repair_attempts_used = 0
        self._max_repair_retries = DEFAULT_REPAIR_RETRIES
        self.state = "idle"
        self.status_message = ""
        self.last_error = ""
        self._set_end_turn_enabled(True)

    def shutdown(self) -> None:
        self.reset()
        if self._owns_executor:
            self._executor.shutdown(wait=False, cancel_futures=True)

    def _submit(self, request: PlanningRequest, *, repairing: bool) -> None:
        player = self.game.current_player
        runtime_config = get_runtime_config(
            getattr(player, "ai_reasoning_effort", DEFAULT_REASONING_EFFORT)
        )
        self._request = request
        self._turn_token = (
            request.campaign_id,
            request.agent_id,
            request.turn_number,
        )
        self.state = "repairing" if repairing else "thinking"
        self.status_message = "revising…" if repairing else "thinking…"
        self.last_error = ""
        self._set_end_turn_enabled(False)
        self._future = self._executor.submit(
            self.provider.plan_turn, request, runtime_config
        )

    def _apply_result(self, result: PlanningResult) -> None:
        player = self.game.current_player
        self.state = "applying"
        self.status_message = "issuing…"
        command_result = CommandGateway(self.game).apply_batch(player, result.plan.batch)
        if not command_result.accepted:
            will_retry = bool(
                command_result.retryable
                and self._repair_attempts_used < self._max_repair_retries
                and self._base_request is not None
            )
            self._record_telemetry(
                result,
                command_result,
                status="rejected",
                will_retry=will_retry,
            )
            if will_retry:
                self._repair_attempts_used += 1
                repair_context = RepairContext(
                    rejected_plan=result.plan,
                    errors=tuple(
                        RepairIssue(
                            command_index=error.command_index,
                            code=error.code,
                            message=error.message,
                        )
                        for error in command_result.errors
                    ),
                )
                self._submit(self._repair_request(repair_context), repairing=True)
                return
            messages = "; ".join(error.message for error in command_result.errors)
            self._fail(f"AI commands were rejected: {messages}")
            return

        memory = AgentMemory.from_dict(getattr(player, "ai_memory", None))
        memory.apply_patch(
            result.plan.memory_patch,
            turn=int(getattr(self.game, "turn_number", 1)),
        )
        receipt = (
            "; ".join(command_result.receipts)
            if command_result.receipts
            else "No commands issued."
        )
        memory.add_receipt(receipt, turn=int(getattr(self.game, "turn_number", 1)))
        player.ai_memory = memory.to_dict()
        player.last_ai_report = {
            "plan": list(result.plan.plan),
            "receipts": list(command_result.receipts),
            "model": result.model,
            "reasoning_effort": result.reasoning_effort,
            "usage": result.usage,
            "latency_seconds": round(result.latency_seconds, 3),
        }
        self._write_memory(player, memory)
        self._record_telemetry(
            result, command_result, status="accepted", will_retry=False
        )
        self.state = "idle"
        self.status_message = ""
        self._request = None
        self._base_request = None
        self._turn_token = None
        self._set_end_turn_enabled(True)
        if result.plan.batch.end_turn:
            self.game.end_turn()
        else:
            self._fail("The AI returned control without ending its turn.")

    def _handle_output_error(self, error: PlanningOutputError) -> None:
        if not self._turn_is_current():
            self._discard_stale_result()
            return
        will_retry = bool(
                self._repair_attempts_used < self._max_repair_retries
                and self._base_request is not None
        )
        self._record_output_error(error, will_retry=will_retry)
        if will_retry:
            self._repair_attempts_used += 1
            context = RepairContext(
                rejected_plan=None,
                errors=(RepairIssue(None, error.code, str(error)),),
            )
            self._submit(self._repair_request(context), repairing=True)
            return
        self._fail(f"AI planning output was invalid: {error}")

    def _repair_request(self, context: RepairContext) -> PlanningRequest:
        base = self._base_request
        if base is None:
            raise RuntimeError("Cannot create a repair request without a base request.")
        return PlanningRequest(
            campaign_id=base.campaign_id,
            agent_id=base.agent_id,
            player_name=base.player_name,
            turn_number=base.turn_number,
            observation=base.observation,
            memory=base.memory,
            repair_context=context,
        )

    def _turn_is_current(self) -> bool:
        player = getattr(self.game, "current_player", None)
        if player is None or self._turn_token is None:
            return False
        current = (
            str(getattr(self.game, "campaign_id", "legacy-campaign")),
            str(getattr(player, "agent_id", f"legacy-player-{player.id}")),
            int(getattr(self.game, "turn_number", 1)),
        )
        return current == self._turn_token and not getattr(player, "is_human", True)

    def _write_memory(self, player: Any, memory: AgentMemory) -> None:
        try:
            import save_manager

            write_memory_sidecar(
                Path(save_manager.SAVES_DIR),
                campaign_id=str(self.game.campaign_id),
                agent_id=str(player.agent_id),
                player_name=str(player.name),
                memory=memory,
            )
        except Exception:
            logger.warning("Could not write AI memory sidecar.", exc_info=True)

    def _record_telemetry(
        self,
        result: PlanningResult,
        command_result: CommandResult,
        *,
        status: str,
        will_retry: bool = False,
    ) -> None:
        record = {
            "campaign_id": getattr(self.game, "campaign_id", None),
            "agent_id": getattr(self.game.current_player, "agent_id", None),
            "turn": getattr(self.game, "turn_number", None),
            "attempt_index": self._repair_attempts_used,
            "is_repair": self._repair_attempts_used > 0,
            "provider": result.provider,
            "model": result.model,
            "reasoning_effort": result.reasoning_effort,
            "response_id": result.response_id,
            "usage": result.usage,
            "latency_seconds": round(result.latency_seconds, 3),
            "status": status,
            "commands": len(result.plan.batch.commands),
            "command_summaries": [
                {
                    "index": index,
                    "type": command.type,
                    "unit_ids": list(command.unit_ids),
                    "target_id": command.target_id,
                    "queue": command.queue,
                }
                for index, command in enumerate(result.plan.batch.commands)
            ],
            "applied_operations": command_result.applied_count,
            "errors": [error.code for error in command_result.errors],
            "error_details": [
                {
                    "command_index": error.command_index,
                    "code": error.code,
                    "message": _bounded_text(error.message),
                }
                for error in command_result.errors
            ],
            "will_retry": will_retry,
        }
        self._append_telemetry(record)
        logger.info(
            "AI attempt completed: turn=%s attempt=%s status=%s commands=%s errors=%s",
            record["turn"],
            record["attempt_index"],
            status,
            record["commands"],
            record["errors"],
        )

    def _record_output_error(
        self, error: PlanningOutputError, *, will_retry: bool
    ) -> None:
        record = {
            "campaign_id": getattr(self.game, "campaign_id", None),
            "agent_id": getattr(self.game.current_player, "agent_id", None),
            "turn": getattr(self.game, "turn_number", None),
            "attempt_index": self._repair_attempts_used,
            "is_repair": self._repair_attempts_used > 0,
            "provider": error.provider,
            "model": error.model,
            "reasoning_effort": error.reasoning_effort,
            "response_id": error.response_id,
            "usage": error.usage,
            "latency_seconds": round(error.latency_seconds, 3),
            "status": "invalid_output",
            "commands": 0,
            "command_summaries": [],
            "applied_operations": 0,
            "errors": [error.code],
            "error_details": [
                {
                    "command_index": None,
                    "code": error.code,
                    "message": _bounded_text(error),
                }
            ],
            "will_retry": will_retry,
        }
        self._append_telemetry(record)
        logger.info(
            "AI attempt completed: turn=%s attempt=%s status=invalid_output errors=%s",
            record["turn"],
            record["attempt_index"],
            record["errors"],
        )

    def _record_transport_error(self, error: Exception) -> None:
        player = getattr(self.game, "current_player", None)
        runtime_config = get_runtime_config(
            getattr(player, "ai_reasoning_effort", DEFAULT_REASONING_EFFORT)
        )
        record = {
            "campaign_id": getattr(self.game, "campaign_id", None),
            "agent_id": getattr(player, "agent_id", None),
            "turn": getattr(self.game, "turn_number", None),
            "attempt_index": self._repair_attempts_used,
            "is_repair": self._repair_attempts_used > 0,
            "provider": self.provider.__class__.__name__,
            "model": runtime_config.model,
            "reasoning_effort": runtime_config.reasoning_effort,
            "response_id": None,
            "usage": {},
            "latency_seconds": 0.0,
            "status": "transport_error",
            "commands": 0,
            "command_summaries": [],
            "applied_operations": 0,
            "errors": [error.__class__.__name__],
            "error_details": [
                {
                    "command_index": None,
                    "code": error.__class__.__name__,
                    "message": "The planning provider request failed.",
                }
            ],
            "will_retry": False,
        }
        self._append_telemetry(record)
        logger.info(
            "AI attempt completed: turn=%s attempt=%s status=transport_error errors=%s",
            record["turn"],
            record["attempt_index"],
            record["errors"],
        )

    @staticmethod
    def _append_telemetry(record: dict[str, Any]) -> None:
        try:
            import save_manager

            path = Path(save_manager.SAVES_DIR) / "ai_telemetry.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
        except Exception:
            logger.warning("Could not write AI telemetry.", exc_info=True)

    def _fail(self, message: str) -> None:
        self.state = "error"
        self.status_message = "attention"
        self.last_error = message
        self._request = None
        self._base_request = None
        self._turn_token = None
        self._set_end_turn_enabled(True)
        gui = getattr(self.game, "gui", None)
        if gui and hasattr(gui, "show_error_dialog"):
            gui.show_error_dialog(
                message + "<br><br>You can end the turn manually.",
                title="AI Turn Error",
            )

    def _discard_stale_result(self) -> None:
        self.state = "idle"
        self.status_message = ""
        self._request = None
        self._base_request = None
        self._turn_token = None
        self._set_end_turn_enabled(True)

    def _set_end_turn_enabled(self, enabled: bool) -> None:
        gui = getattr(self.game, "gui", None)
        button = getattr(gui, "end_turn_button", None)
        if button is not None:
            if enabled:
                button.enable()
            else:
                button.disable()


def _bounded_text(value: Any, limit: int = 500) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"
