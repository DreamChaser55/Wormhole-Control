"""Transient, immutable AI progress. No plans, game objects or provider payloads."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping

from .runtime import MAX_REPAIR_RETRIES


USAGE_FIELDS = (
    "input_tokens", "output_tokens", "total_tokens", "cached_input_tokens",
    "uncached_input_tokens", "reasoning_tokens",
)
TURN_PHASES = (
    ("scheduled", "Scheduled"),
    ("preparing", "Preparing observation"),
    ("requesting", "Requesting AI plan"),
    ("checking", "Checking and applying orders"),
    ("resolving", "Resolving turn"),
    ("complete", "Complete"),
)
SAFE_ERRORS = {
    "certificate_trust": "The connection certificate could not be verified.",
    "certificate_configuration": "The connection certificate settings could not be loaded.",
    "timeout": "The AI request timed out.",
    "authentication": "The AI service rejected the configured credentials.",
    "quota": "The AI service quota is exhausted.",
    "rate_limit": "The AI service rate limit was reached.",
    "connection": "The AI service could not be reached.",
    "cancellation_timeout": "The previous AI request has not finished cancelling.",
    "invalid_output": "The AI response could not be validated after the available repairs.",
    "preflight": "The AI orders could not be validated after the available repairs.",
    "commit": "The turn needs review; some actions may already have taken effect.",
}


@dataclass(frozen=True)
class AIAttemptStatistics:
    """An ended initial request or semantic repair; usage is an immutable allowlist."""

    attempt_index: int
    started_at: float
    finished_at: float
    latency_seconds: float
    status: str
    usage: tuple[tuple[str, int], ...] = ()

    @classmethod
    def from_usage(
        cls, *, attempt_index: int, started_at: float, finished_at: float,
        latency_seconds: float, status: str, usage: Mapping[str, int],
    ) -> AIAttemptStatistics:
        values = tuple((key, usage[key]) for key in USAGE_FIELDS
                       if type(usage.get(key)) is int and usage[key] >= 0)
        latency = (float(latency_seconds) if type(latency_seconds) in (int, float)
                   and math.isfinite(latency_seconds) and latency_seconds >= 0
                   else max(0.0, finished_at - started_at))
        return cls(attempt_index, started_at, finished_at, latency, status, values)

    def token_count(self, field: str) -> int | None:
        return dict(self.usage).get(field)


@dataclass(frozen=True)
class AITurnProgress:
    campaign_id: str
    agent_id: str
    generation: int
    player_name: str
    turn_number: int
    model: str
    reasoning_effort: str
    phase: str
    turn_started_at: float
    phase_started_at: float
    sampled_at: float
    repair_attempt: int = 0
    repair_limit: int = 0
    phase_durations: tuple[tuple[str, float], ...] = ()
    attempts: tuple[AIAttemptStatistics, ...] = ()
    error_category: str | None = None

    @property
    def identity(self) -> tuple[str, str, int]:
        return self.campaign_id, self.agent_id, self.turn_number

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, self.sampled_at - self.turn_started_at)

    @property
    def phase_elapsed_seconds(self) -> float:
        return max(0.0, self.sampled_at - self.phase_started_at)

    @property
    def phase_label(self) -> str:
        if self.phase == "requesting" and self.repair_attempt:
            return f"Revising — retry {self.repair_attempt}/{self.repair_limit}"
        return dict(TURN_PHASES).get(self.phase, {
            "cancelling": "Cancelling previous request",
            "error": "Needs attention",
            "waiting_for_codex": "Waiting for Codex",
        }.get(self.phase, "AI turn in progress"))

    @property
    def safe_error(self) -> str:
        return SAFE_ERRORS.get(self.error_category or "", "The AI turn could not be completed.")

    def sample(self, now: float) -> AITurnProgress:
        return self if self.phase in {"complete", "error"} else replace(self, sampled_at=now)

    def transition(
        self, phase: str, now: float, *, repair_attempt: int | None = None,
        repair_limit: int | None = None, error_category: str | None = None,
    ) -> AITurnProgress:
        durations = dict(self.phase_durations)
        if phase != self.phase:
            durations[self.phase] = durations.get(self.phase, 0.0) + max(0.0, now - self.phase_started_at)
        return replace(
            self, phase=phase, sampled_at=now,
            phase_started_at=self.phase_started_at if phase == self.phase else now,
            repair_attempt=self.repair_attempt if repair_attempt is None else repair_attempt,
            repair_limit=self.repair_limit if repair_limit is None else repair_limit,
            error_category=error_category, phase_durations=tuple(durations.items()),
        )

    def with_attempt(self, attempt: AIAttemptStatistics) -> AITurnProgress:
        # Each request contributes once, even if validation subsequently fails.
        attempts = tuple(item for item in self.attempts if item.attempt_index != attempt.attempt_index)
        return replace(self, attempts=(*attempts, attempt)[-(MAX_REPAIR_RETRIES + 1):])

    def reported_total(self, field: str) -> tuple[int | None, bool]:
        values = [item.token_count(field) for item in self.attempts]
        known = [value for value in values if value is not None]
        return (sum(known), len(known) != len(values)) if known else (None, False)
