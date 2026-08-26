"""Planning provider interface; providers never receive live game objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from game_ai.contracts import TurnPlan
from game_ai.runtime import AgentRuntimeConfig


@dataclass(frozen=True)
class RepairIssue:
    """One model-output or command-validation problem supplied for repair."""

    command_index: int | None
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_index": self.command_index,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class RepairContext:
    """The immediately preceding rejected output and its validation errors."""

    rejected_plan: TurnPlan | None
    errors: tuple[RepairIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rejected_plan": (
                self.rejected_plan.to_dict() if self.rejected_plan is not None else None
            ),
            "validation_errors": [error.to_dict() for error in self.errors],
        }


class PlanningOutputError(RuntimeError):
    """A retryable failure caused by malformed model output, not transport."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider: str,
        model: str,
        reasoning_effort: str,
        response_id: str | None = None,
        usage: dict[str, int] | None = None,
        latency_seconds: float = 0.0,
    ):
        super().__init__(message)
        self.code = code
        self.provider = provider
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.response_id = response_id
        self.usage = usage or {}
        self.latency_seconds = latency_seconds


@dataclass(frozen=True)
class PlanningRequest:
    campaign_id: str
    agent_id: str
    player_name: str
    turn_number: int
    observation: dict[str, Any]
    memory: dict[str, Any]
    repair_context: RepairContext | None = None

    def to_dict(self) -> dict[str, Any]:
        result = {
            "campaign_id": self.campaign_id,
            "agent_id": self.agent_id,
            "player_name": self.player_name,
            "turn_number": self.turn_number,
            "observation": self.observation,
            "long_term_memory": self.memory,
        }
        if self.repair_context is not None:
            result["repair_context"] = self.repair_context.to_dict()
        return result


@dataclass(frozen=True)
class PlanningResult:
    plan: TurnPlan
    provider: str
    model: str
    reasoning_effort: str
    response_id: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    latency_seconds: float = 0.0


class PlanningProvider(Protocol):
    def plan_turn(
        self,
        request: PlanningRequest,
        runtime_config: AgentRuntimeConfig,
    ) -> PlanningResult:
        ...
