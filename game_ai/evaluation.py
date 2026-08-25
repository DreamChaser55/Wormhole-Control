"""Provider-independent fixtures and metrics for AI quality/balance evaluation."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .adapters.base import PlanningProvider, PlanningRequest
from .contracts import TurnPlan
from .profiles import get_profile


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    request: PlanningRequest
    required_command_types: frozenset[str] = frozenset()
    forbidden_command_types: frozenset[str] = frozenset()
    maximum_commands: int = 32

    @classmethod
    def from_json(cls, path: Path) -> "EvaluationCase":
        raw = json.loads(path.read_text(encoding="utf-8"))
        request = PlanningRequest(**raw["request"])
        return cls(
            name=raw["name"],
            request=request,
            required_command_types=frozenset(raw.get("required_command_types", [])),
            forbidden_command_types=frozenset(raw.get("forbidden_command_types", [])),
            maximum_commands=int(raw.get("maximum_commands", 32)),
        )


@dataclass(frozen=True)
class CaseScore:
    name: str
    passed: bool
    schema_valid: bool
    required_coverage: float
    forbidden_count: int
    command_count: int
    latency_seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    notes: tuple[str, ...] = ()


@dataclass
class EvaluationReport:
    profile_id: str
    scores: list[CaseScore] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return mean([float(score.passed) for score in self.scores]) if self.scores else 0.0

    @property
    def average_latency(self) -> float:
        return mean([score.latency_seconds for score in self.scores]) if self.scores else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "pass_rate": self.pass_rate,
            "average_latency_seconds": self.average_latency,
            "scores": [score.__dict__ for score in self.scores],
        }


def run_evaluation(
    provider: PlanningProvider,
    cases: Iterable[EvaluationCase],
    *,
    profile_id: str = "balanced",
    seed: int = 0,
) -> EvaluationReport:
    """Run deterministic fixture cases. Live OpenAI use is opt-in via provider choice."""
    random.seed(seed)
    profile = get_profile(profile_id)
    report = EvaluationReport(profile_id=profile.id)
    for case in cases:
        result = provider.plan_turn(case.request, profile)
        report.scores.append(score_plan(case, result.plan, result.latency_seconds, result.usage))
    return report


def score_plan(
    case: EvaluationCase,
    plan: TurnPlan,
    latency_seconds: float = 0.0,
    usage: dict[str, int] | None = None,
) -> CaseScore:
    usage = usage or {}
    command_types = [command.type for command in plan.batch.commands]
    present = set(command_types)
    required_found = len(case.required_command_types & present)
    required_total = len(case.required_command_types)
    coverage = required_found / required_total if required_total else 1.0
    forbidden_count = len([name for name in command_types if name in case.forbidden_command_types])
    notes = []
    if coverage < 1.0:
        notes.append("Missing one or more required command types.")
    if forbidden_count:
        notes.append("Issued a forbidden command type.")
    if len(command_types) > case.maximum_commands:
        notes.append("Exceeded the case command budget.")
    passed = not notes and plan.batch.end_turn
    if not plan.batch.end_turn:
        notes.append("Did not end the turn.")
    return CaseScore(
        name=case.name,
        passed=passed,
        schema_valid=True,
        required_coverage=coverage,
        forbidden_count=forbidden_count,
        command_count=len(command_types),
        latency_seconds=latency_seconds,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        notes=tuple(notes),
    )
