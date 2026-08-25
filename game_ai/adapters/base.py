"""Planning provider interface; providers never receive live game objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from game_ai.contracts import TurnPlan
from game_ai.profiles import AgentProfile


@dataclass(frozen=True)
class PlanningRequest:
    campaign_id: str
    agent_id: str
    player_name: str
    turn_number: int
    observation: dict[str, Any]
    memory: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_id": self.campaign_id,
            "agent_id": self.agent_id,
            "player_name": self.player_name,
            "turn_number": self.turn_number,
            "observation": self.observation,
            "long_term_memory": self.memory,
        }


@dataclass(frozen=True)
class PlanningResult:
    plan: TurnPlan
    provider: str
    model: str
    response_id: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    latency_seconds: float = 0.0


class PlanningProvider(Protocol):
    def plan_turn(
        self,
        request: PlanningRequest,
        profile: AgentProfile,
    ) -> PlanningResult:
        ...
