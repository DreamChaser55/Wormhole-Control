"""Versioned command definitions shared by schemas, clients and validation."""
from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import math

CONTRACT_VERSION = 3
MAX_COMMANDS = 40
MAX_UNITS = 12
MAX_WAYPOINTS = 16
STANCE_VALUES = ["do_nothing", "attack_weapon_range", "attack_same_sector",
                 "attack_intra_system_jump_range", "attack_same_system"]


@dataclass(frozen=True)
class CommandSpec:
    description: str
    fields: tuple[str, ...] = ()
    required: tuple[str, ...] = ()
    queued: bool = True
    capability: tuple[str, ...] = ()
    player_level: bool = False
    single_unit: bool = False
    text_limit: int | None = None


DESTINATION = ("system_name", "hex_coord", "position")


def _spec(description, fields=(), required=None, **kwargs):
    return CommandSpec(description, tuple(fields), tuple(fields if required is None else required), **kwargs)


COMMAND_SPECS = {
    "cancel_orders": _spec("Stop all work, clear navigation/fire targets, and select Do Nothing.", queued=False),
    "clear_explicit_orders": _spec("Cancel explicit work, preserving the stance; it resumes when idle.", queued=False),
    "cancel_order": _spec("Cancel one current or queued explicit root, promoting the next order.", ("order_id",), queued=False, single_unit=True),
    "append_patrol_waypoints": _spec("Append waypoints to an existing explicit patrol without interrupting its leg.", ("order_id", "waypoints"), queued=False, single_unit=True),
    "move": _spec("Move to a destination. Explicit movement suspends stance combat.", DESTINATION, capability=("engines_component",)),
    "patrol": _spec("Loop through waypoints then return to the starting position. Queuing creates a separate loop.", (*DESTINATION, "waypoints"), (), capability=("engines_component",)),
    "attack": _spec("Attack a visible enemy, optionally selecting a publicly visible subsystem.", ("target_id", "target_component"), ("target_id",), capability=("weapons_component",)),
    "defend": _spec("Hold a destination or target location, engaging intruders within the guard radius.", (*DESTINATION, "target_id"), (), capability=("engines_component", "weapons_component")),
    "protect": _spec("Escort a friendly unit and engage nearby enemies.", ("target_id",), capability=("engines_component",)),
    "colonize": _spec("Colonize an unowned body; queue behind a required colonist load.", ("target_id",), capability=("colony_component",)),
    "load_colonists": _spec("Load a positive amount of colonists from a self-owned colony.", ("target_id", "amount"), capability=("colony_component",)),
    "construct": _spec("Construct a template at a position.", ("template_name", "position"), capability=("constructor_component",)),
    "repair": _spec("Repair a friendly unit.", ("target_id",), capability=("repair_component",)),
    "mine": _spec("Mine a body once.", ("target_id",), capability=("mining_component",)),
    "continuous_mine": _spec("Repeat mining and unloading indefinitely.", ("target_id",), capability=("mining_component",)),
    "unload_resources": _spec("Unload cargo at a friendly refinery.", ("target_id",), capability=("mining_component",)),
    "dock_in_hangar": _spec("Dock a tiny ship in a friendly hangar.", ("target_id",)),
    "dock_in_strikecraft_bay": _spec("Dock a wing in a friendly strikecraft bay.", ("target_id",)),
    "deploy_unit": _spec("Deploy the identified docked craft.", ("target_id",)),
    "deploy_all_wings": _spec("Deploy all docked wings.", capability=("strikecraft_bay_component",)),
    "transfer_antimatter": _spec("Transfer antimatter to a friendly unit.", ("target_id",), capability=("antimatter_component",)),
    "continuous_resupply": _spec("Repeat harvesting and friendly refuelling indefinitely.", ("target_id",), capability=("harvester_component", "antimatter_component")),
    "lay_minefield": _spec("Lay anti_ship (default) or anti_strikecraft mines.", ("minefield_type",), ()),
    "trade": _spec("Trade with a friendly active habitat.", ("target_id",), capability=("trade_component",)),
    "continuous_trade": _spec("Repeat trade routes indefinitely.", capability=("trade_component",)),
    "set_stance": _spec("Change standing policy without cancelling explicit work, even an explicit Attack.", ("stance",), queued=False),
    "toggle_inhibitor": _spec("Immediately flip the inhibitor; activation requires a valid non-overlapping field.", queued=False, capability=("inhibitor_component",)),
    "toggle_cloaking": _spec("Immediately flip a functioning cloak.", queued=False, capability=("cloaking_component",)),
    "infiltrate_unit": _spec("Deploy an agent onto a visible enemy unit.", ("target_id",), capability=("intelligence_component",)),
    "infiltrate_planet": _spec("Deploy an agent onto an exact enemy colony.", ("target_id",), capability=("intelligence_component",)),
    "extract_agent": _spec("Recover an owned embedded agent into this Intelligence ship.", ("agent_id",), capability=("intelligence_component",), single_unit=True),
    "ci_sweep": _spec("Immediately spend credits and antimatter to discover enemy agents on nearby friendly assets.", queued=False, capability=("intelligence_component",)),
    "eliminate_agent": _spec("Approach and eliminate a discovered enemy agent on a friendly asset.", ("agent_id",), capability=("intelligence_component",), single_unit=True),
    "sabotage": _spec("Immediately set an owned embedded agent's sabotage operation.", ("agent_id", "sabotage_type"), queued=False, player_level=True),
    "relocate_agent": _spec("Immediately relocate an owned embedded agent to a visible in-range enemy host.", ("agent_id", "target_id"), queued=False, player_level=True),
    "use_ability": _spec("Use an ability; target requirements are provided in ability options.", ("ability", "target_id", "position"), ("ability",), capability=("ability_component",)),
    "enter_gas_giant": _spec("Hide eligible ships in a gas giant atmosphere.", ("target_id",), capability=("engines_component",)),
    "leave_gas_giant": _spec("Order submerged ships to emerge from a gas giant atmosphere.", queued=False),
    "send_message": _spec("Send a message to player target_id.", ("target_id", "message"), queued=False, player_level=True, text_limit=500),
    "message_developer": _spec("Send developer feedback.", ("message",), queued=False, player_level=True, text_limit=2000),
}

NULLABLE_STRING = {"type": ["string", "null"]}
def _pair_schema(kind):
    return {"anyOf": [{"type": "array", "items": {"type": kind}, "minItems": 2, "maxItems": 2}, {"type": "null"}]}

WAYPOINT_SCHEMA = {"type": "object", "additionalProperties": False,
    "properties": {"system_name": {"type": "string"},
                   "hex_coord": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2},
                   "position": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}},
    "required": list(DESTINATION)}
COMMAND_PROPERTIES = {
    "type": {"type": "string", "enum": sorted(COMMAND_SPECS)},
    "unit_ids": {"type": "array", "items": {"type": "integer"}, "maxItems": MAX_UNITS},
    "target_id": {"type": ["integer", "null"]}, "system_name": NULLABLE_STRING,
    "hex_coord": _pair_schema("integer"), "position": _pair_schema("number"),
    "template_name": NULLABLE_STRING, "amount": {"type": ["number", "null"]},
    "stance": {"type": ["string", "null"], "enum": [None, *STANCE_VALUES]},
    "queue": {"type": "boolean"}, "ability": NULLABLE_STRING,
    "minefield_type": {"type": ["string", "null"], "enum": [None, "anti_ship", "anti_strikecraft"]},
    "target_component": NULLABLE_STRING, "message": NULLABLE_STRING, "order_id": NULLABLE_STRING,
    "agent_id": {"type": ["integer", "null"]},
    "sabotage_type": {"type": ["string", "null"], "enum": [None, "engines", "weapons", "defenses", "hyperdrive", "sensors", "antimatter", "economy", "growth"]},
    "waypoints": {"anyOf": [{"type": "array", "items": WAYPOINT_SCHEMA, "minItems": 1, "maxItems": MAX_WAYPOINTS}, {"type": "null"}]},
}


def validate_command(raw):
    """Validate JSON-shaped input without coercion or engine access."""
    from .contracts import ContractError
    from collections.abc import Mapping
    def require(condition, message):
        if not condition:
            raise ContractError(message)
    require(isinstance(raw, Mapping), "Each command must be an object.")
    require(not set(raw) - COMMAND_PROPERTIES.keys(), "Unknown command field.")
    kind = raw.get("type")
    require(isinstance(kind, str) and kind in COMMAND_SPECS, "Unsupported command type.")
    spec = COMMAND_SPECS[kind]
    ids = raw.get("unit_ids", [])
    require(isinstance(ids, (list, tuple)), "unit_ids must be an array.")
    require(all(type(i) is int and i >= 0 for i in ids), "unit_ids must contain nonnegative integers.")
    require(len(ids) <= MAX_UNITS and len(ids) == len(set(ids)), "unit_ids must be unique and contain at most 12 IDs.")
    require(not ids if spec.player_level else bool(ids), "Invalid unit selection for this command.")
    require(not spec.single_unit or len(ids) == 1, "This command requires exactly one unit.")
    queue = raw.get("queue", False)
    require(type(queue) is bool, "queue must be a boolean.")
    require(spec.queued or not queue, "Immediate commands require queue=false.")
    for field in COMMAND_PROPERTIES.keys() - {"type", "unit_ids", "queue"}:
        value = raw.get(field)
        require(value is None or field in spec.fields, f"{kind} does not use {field}.")
        if value is None:
            require(field not in spec.required, f"{kind} requires {field}.")
            continue
        if field in {"target_id", "agent_id"}:
            require(type(value) is int and value >= 0, f"{field} must be a nonnegative integer.")
        elif field == "amount":
            require(type(value) in (int, float) and _finite(value) and value > 0, "amount must be finite and positive.")
        elif field in ("hex_coord", "position"):
            _validate_pair(value, field, require)
        elif field == "waypoints":
            require(isinstance(value, (list, tuple)) and 1 <= len(value) <= MAX_WAYPOINTS, "waypoints requires 1-16 entries.")
            for wp in value:
                require(isinstance(wp, Mapping) and set(wp) == set(DESTINATION), "Invalid waypoint fields.")
                require(isinstance(wp["system_name"], str) and bool(wp["system_name"].strip()), "Invalid waypoint system_name.")
                _validate_pair(wp["hex_coord"], "hex_coord", require)
                _validate_pair(wp["position"], "position", require)
        else:
            require(isinstance(value, str) and bool(value.strip()), f"{field} must be a nonempty string.")
    require(spec.text_limit is None or len(raw.get("message") or "") <= spec.text_limit, "Message exceeds its length limit.")
    require(raw.get("stance") is None or raw["stance"] in STANCE_VALUES, "Unknown stance.")
    require(raw.get("minefield_type") in (None, "anti_ship", "anti_strikecraft"), "Unknown minefield_type.")
    require(raw.get("sabotage_type") in (None, "engines", "weapons", "defenses", "hyperdrive", "sensors", "antimatter", "economy", "growth"), "Unknown sabotage_type.")
    if kind in {"patrol", "defend"}:
        destination = [raw.get(f) is not None for f in DESTINATION]
        alternative = raw.get("waypoints" if kind == "patrol" else "target_id") is not None
        require((all(destination) and not alternative) or (not any(destination) and alternative), f"{kind} requires exactly one destination form.")


def _validate_pair(value, field, require):
    require(isinstance(value, (list, tuple)) and len(value) == 2, f"{field} must be a pair.")
    if field == "hex_coord":
        require(all(type(v) is int for v in value), "hex_coord requires integers.")
    else:
        require(all(type(v) in (int, float) and _finite(v) for v in value), "position requires finite numbers.")


def command_catalog():
    return {"version": CONTRACT_VERSION, "max_commands": MAX_COMMANDS, "max_units": MAX_UNITS,
        "fields": deepcopy(COMMAND_PROPERTIES),
        "commands": {kind: {"description": s.description, "fields": list(s.fields), "required": list(s.required),
                            "queue": "append_or_replace" if s.queued else "must_be_false",
                            "unit_selection": "none" if s.player_level else "one" if s.single_unit else "owned",
                            "capabilities": list(s.capability), "message_max_length": s.text_limit} for kind, s in COMMAND_SPECS.items()},
        "defaults": {"queue": False, "unit_ids": [], "optional_fields": None},
        "command_defaults": {"lay_minefield": {"minefield_type": "anti_ship"}},
        "destination_forms": {"patrol": [list(DESTINATION), ["waypoints"]], "defend": [list(DESTINATION), ["target_id"]]}}


def _finite(value):
    try:
        return math.isfinite(value)
    except (ValueError, OverflowError):
        return False
