"""Provider-independent fixtures and metrics for AI quality/balance evaluation."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from types import SimpleNamespace
from typing import Any, Callable, Iterable

from .adapters.base import (
    PlanningOutputError,
    PlanningProvider,
    PlanningRequest,
    RepairContext,
    RepairIssue,
)
from .commands import CommandGateway, CommandResult
from .contracts import TurnPlan
from .command_spec import command_catalog
from geometry import Position
from .runtime import get_runtime_config


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
    reasoning_effort: str
    scores: list[CaseScore] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return mean([float(score.passed) for score in self.scores]) if self.scores else 0.0

    @property
    def average_latency(self) -> float:
        return mean([score.latency_seconds for score in self.scores]) if self.scores else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoning_effort": self.reasoning_effort,
            "pass_rate": self.pass_rate,
            "average_latency_seconds": self.average_latency,
            "scores": [score.__dict__ for score in self.scores],
        }


@dataclass(frozen=True)
class GatewayEvaluationCase:
    """A fresh deterministic game/request pair for semantic acceptance evaluation."""

    name: str
    build: Callable[
        [], tuple[PlanningRequest, Callable[[TurnPlan], CommandResult]]
    ]
    maximum_retries: int = 2


@dataclass(frozen=True)
class GatewayCaseScore:
    name: str
    accepted: bool
    attempts: int
    retries_used: int
    latency_seconds: float
    input_tokens: int
    output_tokens: int
    final_error_codes: tuple[str, ...] = ()


@dataclass
class GatewayEvaluationReport:
    reasoning_effort: str
    scores: list[GatewayCaseScore] = field(default_factory=list)

    @property
    def acceptance_rate(self) -> float:
        return mean([float(score.accepted) for score in self.scores]) if self.scores else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoning_effort": self.reasoning_effort,
            "acceptance_rate": self.acceptance_rate,
            "scores": [score.__dict__ for score in self.scores],
        }


def run_evaluation(
    provider: PlanningProvider,
    cases: Iterable[EvaluationCase],
    *,
    reasoning_effort: str = "medium",
    seed: int = 0,
) -> EvaluationReport:
    """Run deterministic fixture cases. Live OpenAI use is opt-in via provider choice."""
    random.seed(seed)
    runtime_config = get_runtime_config(reasoning_effort)
    report = EvaluationReport(reasoning_effort=runtime_config.reasoning_effort)
    for case in cases:
        result = provider.plan_turn(case.request, runtime_config)
        report.scores.append(score_plan(case, result.plan, result.latency_seconds, result.usage))
    return report


def compare_reasoning_efforts(
    provider: PlanningProvider,
    cases: Iterable[EvaluationCase],
    *,
    efforts: tuple[str, ...] = ("low", "medium", "high"),
    seed: int = 0,
) -> dict[str, EvaluationReport]:
    """Run the same fixed cases at each reasoning effort; live use is opt-in."""

    fixed_cases = tuple(cases)
    return {
        effort: run_evaluation(
            provider,
            fixed_cases,
            reasoning_effort=effort,
            seed=seed,
        )
        for effort in efforts
    }


def compare_gateway_reasoning_efforts(
    provider: PlanningProvider,
    cases: Iterable[GatewayEvaluationCase],
    *,
    efforts: tuple[str, ...] = ("low", "medium", "high"),
) -> dict[str, GatewayEvaluationReport]:
    """Opt-in live comparison using the real repair contract and gateway verdicts."""

    fixed_cases = tuple(cases)
    reports = {}
    for effort in efforts:
        runtime_config = get_runtime_config(effort)
        report = GatewayEvaluationReport(runtime_config.reasoning_effort)
        for case in fixed_cases:
            report.scores.append(
                _run_gateway_case(provider, case, runtime_config)
            )
        reports[effort] = report
    return reports


def colony_opening_case() -> EvaluationCase:
    """Minimal regression fixture for the observed zero-cargo colony opening."""

    observation = {
        "schema_version": 4,
        "command_catalog": command_catalog(),
        "turn_number": 1,
        "active_player": {
            "id": 1,
            "name": "AI",
            "team_id": 1,
            "resources": {"credits": 1000, "metal": 0, "crystal": 0},
        },
        "systems": [
            {
                "name": "Sol",
                "connections": [],
                "navigation_anchor": {
                    "body_id": 200,
                    "hex_coord": [0, 0],
                    "position": [0, 0],
                },
                "detail_level": "full",
                "celestial_bodies": [
                    {
                        "id": 201,
                        "type": "Planet",
                        "name": "Home",
                        "hex_coord": [0, 0],
                        "position": [0, 0],
                        "owner_id": 1,
                        "owner_relation": "self",
                        "population": 50,
                        "max_population": 100,
                    },
                    {
                        "id": 202,
                        "type": "Moon",
                        "name": "Frontier",
                        "hex_coord": [1, 0],
                        "position": [0, 0],
                        "owner_id": None,
                        "owner_relation": "neutral",
                        "population": 0,
                        "max_population": 50,
                    },
                ],
            }
        ],
        "units": [
            {
                "id": 101,
                "name": "Colony Ship",
                "owner_id": 1,
                "relation": "self",
                "system_name": "Sol",
                "hex_coord": [0, 0],
                "position": [0, 0],
                "supported_commands": ["colonize", "load_colonists"],
                "legal_commands": ["load_colonists"],
                "command_options": {
                    "load_colonists": {
                        "targets": [{"target_id": 201, "maximum_amount": 50}]
                    },
                    "colonize": {"target_ids": [202]},
                },
                "conditional_commands": [
                    {
                        "type": "colonize",
                        "requires_prior_command": "load_colonists",
                        "same_unit": True,
                        "queue": True,
                    }
                ],
                "capability_details": {
                    "colony": {"population_cargo": 0, "maximum_cargo": 100}
                },
            }
        ],
        "action_catalogs": {
            "colonization_target_ids": [202],
            "colonist_sources": [
                {"target_id": 201, "available_population": 50}
            ],
        },
    }
    return EvaluationCase(
        "colony-opening-repair",
        PlanningRequest("evaluation", "colony-agent", "AI", 1, observation, {}),
        required_command_types=frozenset({"load_colonists"}),
        maximum_commands=6,
    )


def colony_opening_gateway_case() -> GatewayEvaluationCase:
    """Executable version of the zero-cargo colony opening regression."""

    def build():
        from entities import Moon, Planet, PlanetType

        class Player:
            id = 1
            name = "AI"
            team_id = 1
            credits = 1000

            @staticmethod
            def is_allied_with(other):
                return other is not None and getattr(other, "team_id", None) == 1

        class Commander:
            def __init__(self):
                self.current_order = None
                self.orders_queue = []

            def clear_orders(self):
                self.current_order = None
                self.orders_queue.clear()

            def add_order(self, order):
                self.orders_queue.append(order)

        player = Player()
        unit = SimpleNamespace(
            id=101,
            in_system="Sol", in_hex=(0, 0), position=Position(2000, 0),
            name="Colony Ship",
            owner=player,
            colony_component=SimpleNamespace(population_cargo=0, max_cargo=100),
            commander_component=Commander(),
            components={},
            engines_component=None,
            weapons_component=None,
            constructor_component=None,
            repair_component=None,
            mining_component=None,
            harvester_component=None,
            antimatter_component=None,
            hangar_component=None,
            strikecraft_bay_component=None,
            trade_component=None,
            inhibitor_component=None,
            cloaking_component=None,
            ability_component=None,
            hull_size=SimpleNamespace(name="SMALL"),
        )
        source = Planet((0, 0), "Sol", next(iter(PlanetType)))
        source.id = 201
        source.owner = player
        source.population = 50
        target = Moon((1, 0), "Sol")
        target.id = 202

        class Galaxy:
            def get_unit_by_id(self, unit_id):
                return unit if unit_id == unit.id else None

            def get_celestial_body_by_id(self, body_id):
                return {source.id: source, target.id: target}.get(body_id)

        game = SimpleNamespace(
            galaxy=Galaxy(), sidebar_needs_update=False, visibility_dirty=False
        )
        request = colony_opening_case().request
        gateway = CommandGateway(game)
        return request, lambda plan: gateway.apply_batch(player, plan.batch)

    return GatewayEvaluationCase("colony-opening-gateway", build)


def inhibitor_overlap_case() -> EvaluationCase:
    """Regression fixture for an inhibitor blocked by an existing field."""

    observation = {
        "schema_version": 4,
        "command_catalog": command_catalog(),
        "turn_number": 3,
        "active_player": {
            "id": 1,
            "name": "AI",
            "team_id": 1,
            "resources": {"credits": 1000, "metal": 0, "crystal": 0},
        },
        "systems": [],
        "units": [
            {
                "id": 625,
                "name": "Inhibitor Station",
                "owner_id": 1,
                "relation": "self",
                "system_name": "Sol",
                "hex_coord": [0, 0],
                "position": [0, 0],
                "supported_commands": ["cancel_orders", "toggle_inhibitor"],
                "legal_commands": ["cancel_orders"],
                "command_options": {
                    "toggle_inhibitor": {
                        "current_state": "inactive",
                        "resulting_state": "active",
                        "available": False,
                        "unavailable_reason": "inhibitor_overlap",
                    }
                },
                "conditional_commands": [],
                "capability_details": {
                    "inhibitor": {
                        "is_active": False,
                        "radius": 100,
                        "antimatter_cost_per_turn": 2,
                        "can_activate": False,
                        "activation_blocker": "inhibitor_overlap",
                    }
                },
            }
        ],
    }
    return EvaluationCase(
        "inhibitor-overlap",
        PlanningRequest("evaluation", "inhibitor-agent", "AI", 3, observation, {}),
        forbidden_command_types=frozenset({"toggle_inhibitor"}),
        maximum_commands=4,
    )


def order_control_cases() -> tuple[EvaluationCase, ...]:
    """Deterministic contract fixtures for preserving work, stance and patrol choices."""
    from copy import deepcopy

    base = {
        "schema_version": 4, "command_catalog": command_catalog(), "turn_number": 1,
        "active_player": {"id": 1, "name": "AI", "team_id": 1},
        "systems": [{"name": "Sol", "navigation_anchor": {"hex_coord": [0, 0], "position": [0, 0]}}],
        "units": [{"id": 101, "relation": "self", "system_name": "Sol", "hex_coord": [0, 0],
            "position": [0, 0], "standing_order": {"stance": "do_nothing", "suspended": False, "engagement": None},
            "current_order": None, "queued_orders": [],
            "supported_commands": ["patrol", "set_stance", "clear_explicit_orders", "cancel_orders"],
            "legal_commands": ["patrol", "set_stance", "clear_explicit_orders", "cancel_orders"],
            "command_options": {"set_stance": {"values": ["do_nothing", "attack_weapon_range", "attack_same_sector"]}}}],
        "order_history": {"events": [], "latest_event_id": 0, "oldest_event_id": None, "omitted_count": 0},
    }
    preserve = deepcopy(base)
    preserve["units"][0]["current_order"] = {
        "order_id": "00000000000000000000000000000001", "type": "patrol", "status": "in_progress",
        "origin": "explicit", "cancellable": True, "editable": True,
        "parameters": {"waypoints": [{"system_name": "Sol", "hex_coord": [0, 0], "position": [500, 0]}]},
    }
    preserve["units"][0]["standing_order"]["suspended"] = True
    return (
        EvaluationCase("preserve-useful-patrol", PlanningRequest("evaluation", "orders", "AI", 1, preserve, {}),
                       forbidden_command_types=frozenset({"cancel_orders", "clear_explicit_orders", "cancel_order", "move", "patrol"})),
        EvaluationCase("select-stance", PlanningRequest("evaluation", "orders", "AI", 1, deepcopy(base), {}),
                       required_command_types=frozenset({"set_stance"})),
        EvaluationCase("construct-patrol-route", PlanningRequest("evaluation", "orders", "AI", 1, deepcopy(base), {}),
                       required_command_types=frozenset({"patrol"})),
    )


def _run_gateway_case(provider, case, runtime_config) -> GatewayCaseScore:
    base, validate = case.build()
    request = base
    attempts = 0
    latency = 0.0
    input_tokens = 0
    output_tokens = 0
    final_errors: tuple[str, ...] = ()
    accepted = False

    for attempt_index in range(case.maximum_retries + 1):
        attempts += 1
        try:
            result = provider.plan_turn(request, runtime_config)
        except PlanningOutputError as error:
            latency += error.latency_seconds
            input_tokens += error.usage.get("input_tokens", 0)
            output_tokens += error.usage.get("output_tokens", 0)
            final_errors = (error.code,)
            if attempt_index >= case.maximum_retries:
                break
            request = _evaluation_repair_request(
                base,
                RepairContext(
                    None, (RepairIssue(None, error.code, str(error)),)
                ),
            )
            continue
        except Exception as error:
            final_errors = (error.__class__.__name__,)
            break

        latency += result.latency_seconds
        input_tokens += result.usage.get("input_tokens", 0)
        output_tokens += result.usage.get("output_tokens", 0)
        verdict = validate(result.plan)
        if verdict.accepted:
            accepted = True
            final_errors = ()
            break
        final_errors = tuple(error.code for error in verdict.errors)
        if not verdict.retryable or attempt_index >= case.maximum_retries:
            break
        request = _evaluation_repair_request(
            base,
            RepairContext(
                result.plan,
                tuple(
                    RepairIssue(error.command_index, error.code, error.message)
                    for error in verdict.errors
                ),
            ),
        )

    return GatewayCaseScore(
        name=case.name,
        accepted=accepted,
        attempts=attempts,
        retries_used=max(0, attempts - 1),
        latency_seconds=latency,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        final_error_codes=final_errors,
    )


def _evaluation_repair_request(
    base: PlanningRequest, context: RepairContext
) -> PlanningRequest:
    return PlanningRequest(
        campaign_id=base.campaign_id,
        agent_id=base.agent_id,
        player_name=base.player_name,
        turn_number=base.turn_number,
        observation=base.observation,
        memory=base.memory,
        repair_context=context,
    )


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
