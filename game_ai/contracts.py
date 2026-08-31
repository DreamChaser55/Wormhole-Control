"""Provider-independent contracts exchanged by game AI components."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


from .command_spec import COMMAND_SPECS, COMMAND_PROPERTIES, validate_command

SUPPORTED_COMMANDS = frozenset(COMMAND_SPECS)

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
    target_component: str | None = None
    message: str | None = None

    order_id: str | None = None
    waypoints: tuple[dict[str, Any], ...] | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Command":
        validate_command(raw)
        values = {key: raw[key] for key in COMMAND_PROPERTIES if key in raw}
        values["unit_ids"] = tuple(raw.get("unit_ids", []))
        for key in ("hex_coord", "position"):
            if values.get(key) is not None:
                values[key] = tuple(values[key])
        if values.get("waypoints") is not None:
            values["waypoints"] = tuple({"system_name": w["system_name"], "hex_coord": tuple(w["hex_coord"]), "position": tuple(w["position"])} for w in values["waypoints"])
        return cls(**values)

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
            "target_component": self.target_component,
            "message": self.message,
            "order_id": self.order_id,
            "waypoints": [{"system_name": w["system_name"], "hex_coord": list(w["hex_coord"]), "position": list(w["position"])} for w in self.waypoints] if self.waypoints is not None else None,
        }


@dataclass(frozen=True)
class CommandBatch:
    commands: tuple[Command, ...] = ()
    end_turn: bool = True


@dataclass(frozen=True)
class TurnPlan:
    """Strict output expected from a planning provider."""

    plan: tuple[str, ...]
    batch: CommandBatch
    memory_patch: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, max_commands: int = 40, strict: bool = False) -> "TurnPlan":
        if not isinstance(raw, Mapping):
            raise ContractError("Turn response must be an object.")
        if set(raw) != {"plan", "commands", "memory_patch", "end_turn"}:
            raise ContractError("Turn response requires plan, commands, memory_patch and end_turn only.")
        plan_raw = raw.get("plan", [])
        if not isinstance(plan_raw, list) or not all(isinstance(x, str) for x in plan_raw):
            raise ContractError("plan must be an array of strings.")
        commands_raw = raw.get("commands", [])
        if not isinstance(commands_raw, list):
            raise ContractError("commands must be an array.")
        if len(commands_raw) > max_commands:
            raise ContractError(f"A turn may contain at most {max_commands} commands.")
        patch = raw.get("memory_patch", {})
        if len(plan_raw) > 12 or any(len(item) > 500 for item in plan_raw):
            raise ContractError("plan exceeds its limits.")
        if not isinstance(patch, dict):
            raise ContractError("memory_patch must be an object.")
        limits = {"strategy": 3000, "objectives": 12, "commitments": 12, "beliefs": 16, "lessons": 16, "misc": 16}
        if set(patch) - limits.keys():
            raise ContractError("Unknown memory field.")
        for key, value in patch.items():
            if value is None:
                continue
            valid = isinstance(value, str) and len(value) <= 3000 if key == "strategy" else isinstance(value, list) and len(value) <= limits[key] and all(isinstance(v, str) and len(v) <= 500 for v in value)
            if not valid:
                raise ContractError("Invalid memory patch.")
        end_turn = raw.get("end_turn", True)
        if end_turn is not True:
            raise ContractError("end_turn must be true.")
        if strict:
            if set(patch) != set(limits):
                raise ContractError("All memory patch fields are required; use null for unchanged fields.")
            if any(not isinstance(command, Mapping) or set(command) != set(COMMAND_PROPERTIES) for command in commands_raw):
                raise ContractError("All command fields are required; use null for unused fields.")
        return cls(
            plan=tuple(item.strip()[:500] for item in plan_raw[:12]),
            batch=CommandBatch(
                commands=tuple(Command.from_dict(command) for command in commands_raw),
                end_turn=end_turn,
            ),
            memory_patch=patch,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": list(self.plan),
            "commands": [command.to_dict() for command in self.batch.commands],
            "memory_patch": self.memory_patch,
            "end_turn": self.batch.end_turn,
        }
