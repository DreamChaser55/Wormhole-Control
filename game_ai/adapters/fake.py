"""Deterministic provider for tests, demos, and offline evaluation."""

from __future__ import annotations

from collections import deque
from time import perf_counter
from typing import Iterable

from game_ai.contracts import TurnPlan
from game_ai.runtime import AgentRuntimeConfig

from .base import PlanningRequest, PlanningResult


class FakePlanningProvider:
    def __init__(self, plans: Iterable[TurnPlan]):
        self._plans = deque(plans)
        self.requests: list[PlanningRequest] = []
        self.runtime_configs: list[AgentRuntimeConfig] = []

    def plan_turn(
        self,
        request: PlanningRequest,
        runtime_config: AgentRuntimeConfig,
    ) -> PlanningResult:
        started = perf_counter()
        self.requests.append(request)
        self.runtime_configs.append(runtime_config)
        if not self._plans:
            raise RuntimeError("FakePlanningProvider has no queued plan.")
        return PlanningResult(
            plan=self._plans.popleft(),
            provider="fake",
            model=runtime_config.model,
            reasoning_effort=runtime_config.reasoning_effort,
            latency_seconds=perf_counter() - started,
        )
