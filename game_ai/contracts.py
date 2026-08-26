"""Provider-independent contracts exchanged by game AI components."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


SUPPORTED_COMMANDS = frozenset(
    {
        "cancel_orders",
        "move",
        "patrol",
        "attack",
        "protect",
        "colonize",
        "load_colonists",
        "construct",
        "repair",
        "mine",
        "continuous_mine",
        "unload_resources",
        "dock",
        "deploy_unit",
        "deploy_all_wings",
        "transfer_antimatter",
        "continuous_resupply",
        "lay_minefield",
        "trade",
        "continuous_trade",
        "set_stance",
        "toggle_inhibitor",
        "toggle_cloaking",
        "use_ability",
    }
)


class ContractError(ValueError):
    """Raised when an AI payload violates the turn contract."""


@dataclass(frozen=True)
class Command:
    """One requested game command using a strict, schema-friendly shape."""

    type: str
    unit_ids: tuple[int, ...] = ()
    target_id: int | None = None
    system_name: str | None = None
    hex_coord: tuple[int, int] | None = None
    position: tuple[float, float] | None = None
    template_name: str | None = None
    amount: float | None = None
    stance: str | None = None
    queue: bool = False
    ability: str | None = None
    minefield_type: str | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Command":
        if not isinstance(raw, Mapping):
            raise ContractError("Each command must be an object.")
        command_type = raw.get("type")
        if command_type not in SUPPORTED_COMMANDS:
            raise ContractError("Unsupported command type.")

        ids = raw.get("unit_ids") or []
        if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)):
            raise ContractError("command.unit_ids must be an array of integer IDs.")
        try:
            unit_ids = tuple(int(value) for value in ids)
        except (TypeError, ValueError) as exc:
            raise ContractError("command.unit_ids must contain only integer IDs.") from exc

        return cls(
            type=str(command_type),
            unit_ids=unit_ids,
            target_id=_optional_int(raw.get("target_id"), "target_id"),
            system_name=_optional_str(raw.get("system_name"), "system_name"),
            hex_coord=_optional_pair(raw.get("hex_coord"), int, "hex_coord"),
            position=_optional_pair(raw.get("position"), float, "position"),
            template_name=_optional_str(raw.get("template_name"), "template_name"),
            amount=_optional_float(raw.get("amount"), "amount"),
            stance=_optional_str(raw.get("stance"), "stance"),
            queue=bool(raw.get("queue", False)),
            ability=_optional_str(raw.get("ability"), "ability"),
            minefield_type=_optional_str(raw.get("minefield_type"), "minefield_type"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "unit_ids": list(self.unit_ids),
            "target_id": self.target_id,
            "system_name": self.system_name,
            "hex_coord": list(self.hex_coord) if self.hex_coord is not None else None,
            "position": list(self.position) if self.position is not None else None,
            "template_name": self.template_name,
            "amount": self.amount,
            "stance": self.stance,
            "queue": self.queue,
            "ability": self.ability,
            "minefield_type": self.minefield_type,
        }


@dataclass(frozen=True)
class CommandBatch:
    commands: tuple[Command, ...] = ()
    end_turn: bool = True


@dataclass(frozen=True)
class TurnPlan:
    """Strict output expected from a planning provider."""

    analysis_summary: str
    plan: tuple[str, ...]
    batch: CommandBatch
    memory_patch: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, max_commands: int = 32) -> "TurnPlan":
        if not isinstance(raw, Mapping):
            raise ContractError("Turn response must be an object.")
        summary = raw.get("analysis_summary", "")
        if not isinstance(summary, str):
            raise ContractError("analysis_summary must be a string.")
        plan_raw = raw.get("plan", [])
        if not isinstance(plan_raw, list) or not all(isinstance(x, str) for x in plan_raw):
            raise ContractError("plan must be an array of strings.")
        commands_raw = raw.get("commands", [])
        if not isinstance(commands_raw, list):
            raise ContractError("commands must be an array.")
        if len(commands_raw) > max_commands:
            raise ContractError(f"A turn may contain at most {max_commands} commands.")
        patch = raw.get("memory_patch", {})
        if not isinstance(patch, dict):
            raise ContractError("memory_patch must be an object.")
        end_turn = raw.get("end_turn", True)
        if not isinstance(end_turn, bool):
            raise ContractError("end_turn must be a boolean.")
        return cls(
            analysis_summary=summary.strip()[:2000],
            plan=tuple(item.strip()[:500] for item in plan_raw[:12]),
            batch=CommandBatch(
                commands=tuple(Command.from_dict(command) for command in commands_raw),
                end_turn=end_turn,
            ),
            memory_patch=patch,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_summary": self.analysis_summary,
            "plan": list(self.plan),
            "commands": [command.to_dict() for command in self.batch.commands],
            "memory_patch": self.memory_patch,
            "end_turn": self.batch.end_turn,
        }


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ContractError(f"command.{field_name} must be an integer or null.")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"command.{field_name} must be an integer or null.") from exc


def _optional_float(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ContractError(f"command.{field_name} must be a number or null.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"command.{field_name} must be a number or null.") from exc


def _optional_str(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractError(f"command.{field_name} must be a string or null.")
    return value


def _optional_pair(value: Any, cast: type, field_name: str):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ContractError(f"command.{field_name} must be a two-item array or null.")
    try:
        return cast(value[0]), cast(value[1])
    except (TypeError, ValueError) as exc:
        raise ContractError(f"command.{field_name} contains invalid values.") from exc
