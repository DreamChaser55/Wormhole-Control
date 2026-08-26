"""Non-blocking orchestration of one complete AI player turn."""

from __future__ import annotations

import json
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .adapters.base import PlanningRequest, PlanningResult
from .adapters.openai_responses import OpenAIResponsesProvider
from .commands import CommandGateway, CommandResult
from .memory import AgentMemory, write_memory_sidecar
from .observation import build_observation
from .runtime import DEFAULT_REASONING_EFFORT, get_runtime_config

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
        self._turn_token: tuple[str, str, int] | None = None
        self._repair_attempted = False
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
        self._repair_attempted = False
        self._submit(request, repairing=False)
        return True

    def update(self) -> None:
        future = self._future
        if future is None or not future.done():
            return
        self._future = None
        try:
            result = future.result()
        except Exception as exc:
            logger.error("AI planning failed: %s", exc, exc_info=True)
            self._fail(f"AI planning failed: {exc}")
            return
        if not self._turn_is_current():
            self.state = "idle"
            self.status_message = ""
            return
        self._apply_result(result)

    def reset(self) -> None:
        """Forget in-flight work; completed stale responses will be discarded."""
        if self._future is not None:
            self._future.cancel()
        self._future = None
        self._request = None
        self._turn_token = None
        self._repair_attempted = False
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
            if not self._repair_attempted and self._request is not None:
                self._repair_attempted = True
                repaired_observation = dict(self._request.observation)
                repaired_observation["previous_command_errors"] = [
                    {
                        "command_index": error.command_index,
                        "code": error.code,
                        "message": error.message,
                    }
                    for error in command_result.errors
                ]
                repaired_request = PlanningRequest(
                    campaign_id=self._request.campaign_id,
                    agent_id=self._request.agent_id,
                    player_name=self._request.player_name,
                    turn_number=self._request.turn_number,
                    observation=repaired_observation,
                    memory=self._request.memory,
                )
                self._submit(repaired_request, repairing=True)
                return
            messages = "; ".join(error.message for error in command_result.errors)
            self._record_telemetry(result, command_result, status="rejected")
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
            "summary": result.plan.analysis_summary,
            "plan": list(result.plan.plan),
            "receipts": list(command_result.receipts),
            "model": result.model,
            "reasoning_effort": result.reasoning_effort,
            "usage": result.usage,
            "latency_seconds": round(result.latency_seconds, 3),
        }
        self._write_memory(player, memory)
        self._record_telemetry(result, command_result, status="accepted")
        self.state = "idle"
        self.status_message = ""
        self._request = None
        self._turn_token = None
        self._set_end_turn_enabled(True)
        if result.plan.batch.end_turn:
            self.game.end_turn()
        else:
            self._fail("The AI returned control without ending its turn.")

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
    ) -> None:
        try:
            import save_manager

            path = Path(save_manager.SAVES_DIR) / "ai_telemetry.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "campaign_id": getattr(self.game, "campaign_id", None),
                "agent_id": getattr(self.game.current_player, "agent_id", None),
                "turn": getattr(self.game, "turn_number", None),
                "provider": result.provider,
                "model": result.model,
                "reasoning_effort": result.reasoning_effort,
                "response_id": result.response_id,
                "usage": result.usage,
                "latency_seconds": round(result.latency_seconds, 3),
                "status": status,
                "commands": len(result.plan.batch.commands),
                "applied_operations": command_result.applied_count,
                "errors": [error.code for error in command_result.errors],
            }
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, sort_keys=True) + "\n")
        except Exception:
            logger.warning("Could not write AI telemetry.", exc_info=True)

    def _fail(self, message: str) -> None:
        self.state = "error"
        self.status_message = "attention"
        self.last_error = message
        self._request = None
        self._turn_token = None
        self._set_end_turn_enabled(True)
        gui = getattr(self.game, "gui", None)
        if gui and hasattr(gui, "show_error_dialog"):
            gui.show_error_dialog(
                message + "<br><br>You can end the turn manually.",
                title="AI Turn Error",
            )

    def _set_end_turn_enabled(self, enabled: bool) -> None:
        gui = getattr(self.game, "gui", None)
        button = getattr(gui, "end_turn_button", None)
        if button is not None:
            if enabled:
                button.enable()
            else:
                button.disable()
