"""Deterministic provider for tests, demos, and offline evaluation."""

from __future__ import annotations

from collections import deque
from time import perf_counter
from typing import Iterable

from game_ai.contracts import TurnPlan
from game_ai.profiles import AgentProfile

from .base import PlanningRequest, PlanningResult


class FakePlanningProvider:
    def __init__(self, plans: Iterable[TurnPlan]):
        self._plans = deque(plans)
        self.requests: list[PlanningRequest] = []

    def plan_turn(
        self,
        request: PlanningRequest,
        profile: AgentProfile,
    ) -> PlanningResult:
        started = perf_counter()
        self.requests.append(request)
        if not self._plans:
            raise RuntimeError("FakePlanningProvider has no queued plan.")
        return PlanningResult(
            plan=self._plans.popleft(),
            provider="fake",
            model=profile.model,
            latency_seconds=perf_counter() - started,
        )
