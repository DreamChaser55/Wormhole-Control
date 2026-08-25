"""Player-scoped, JSON-safe observations for planning agents."""

from __future__ import annotations

from typing import Any


COMMAND_HELP = {
    "cancel_orders": "Clear current and queued orders.",
    "move": "Move to system_name, hex_coord, and position.",
    "patrol": "Patrol toward system_name, hex_coord, and position.",
    "attack": "Attack visible enemy target_id.",
    "protect": "Protect friendly target_id.",
    "colonize": "Colonize unowned body target_id with carried population.",
    "load_colonists": "Load amount colonists from friendly body target_id.",
    "construct": "Construct template_name at position.",
    "repair": "Repair friendly unit target_id.",
    "mine": "Mine body target_id once.",
    "continuous_mine": "Repeatedly mine body target_id and unload.",
    "unload_resources": "Unload raw cargo into friendly refinery target_id.",
    "dock": "Dock a tiny/small unit into friendly carrier target_id.",
    "deploy_unit": "Carrier deploys docked unit target_id.",
    "deploy_all_wings": "Carrier deploys all docked strikecraft wings.",
    "transfer_antimatter": "Transfer antimatter to friendly unit target_id.",
    "continuous_resupply": "Repeatedly harvest antimatter from star target_id.",
    "lay_minefield": "Lay anti_ship or anti_strikecraft minefield.",
    "trade": "Trade once with active habitat unit target_id.",
    "continuous_trade": "Autonomously repeat trade routes.",
    "set_stance": "Set one of the listed stance values.",
    "toggle_inhibitor": "Toggle the unit's hyperspace inhibitor.",
    "toggle_cloaking": "Toggle the unit's cloaking device.",
    "use_ability": "Use ability; target_id and/or position depend on ability.",
}


def build_observation(game: Any, player: Any) -> dict[str, Any]:
    """Create a fair observation without references to live game objects."""
    galaxy = getattr(game, "galaxy", None)
    turn = int(getattr(game, "turn_number", 1))
    if galaxy is None:
        raise ValueError("Cannot observe a game without a galaxy.")

    from visibility import VisibilityService, is_minefield_visible

    visibility = VisibilityService.compute(galaxy, player, turn_number=turn)
    systems = []
    units = []
    bodies = []
    minefields = []

    for system_name in sorted(galaxy.systems):
        system = galaxy.systems[system_name]
        connections = []
        for destination, maximum_hull in sorted(
            getattr(galaxy, "system_graph", {}).get(system_name, {}).items()
        ):
            connections.append(
                {
                    "system_name": destination,
                    "maximum_hull": _enum_value(maximum_hull),
                }
            )
        systems.append(
            {
                "name": system_name,
                "position": _position(getattr(system, "position", None)),
                "radius": int(getattr(system, "radius", 0)),
                "connections": connections,
            }
        )
        for hex_coord, hex_obj in sorted(system.hexes.items()):
            for body in getattr(hex_obj, "celestial_bodies", []):
                bodies.append(_body_view(body, player))
            for unit in getattr(hex_obj, "units", []):
                relation = _relation(player, getattr(unit, "owner", None))
                if relation != "enemy" or unit.id in visibility.visible_enemy_unit_ids:
                    units.append(_unit_view(unit, relation, include_capabilities=relation == "self"))
            for minefield in getattr(hex_obj, "minefields", []):
                if is_minefield_visible(visibility, minefield):
                    minefields.append(_minefield_view(minefield, player))

    presences = [
        {"system_name": system_name, "hex_coord": list(hex_coord)}
        for system_name, hex_coord in sorted(visibility.presence_hexes)
    ]
    memory_note = (
        "Presence signatures intentionally contain no unit count, identity, owner, or strength."
    )
    return {
        "schema_version": 1,
        "turn_number": turn,
        "active_player": {
            "id": int(player.id),
            "name": str(player.name),
            "team_id": int(player.team_id),
            "resources": {
                "credits": _rounded(player.credits),
                "metal": _rounded(player.metal),
                "crystal": _rounded(player.crystal),
                "income": _safe_game_metric(game, "get_player_income", player),
                "upkeep": _safe_game_metric(game, "get_player_upkeep", player),
            },
        },
        "players": [
            {
                "id": int(other.id),
                "name": str(other.name),
                "team_id": int(other.team_id),
                "relation": _relation(player, other),
            }
            for other in getattr(game, "players", [])
        ],
        "systems": systems,
        "celestial_bodies": bodies,
        "units": units,
        "visible_minefields": minefields,
        "undetailed_enemy_presence": presences,
        "visibility_note": memory_note,
        "command_reference": COMMAND_HELP,
    }


def _unit_view(unit: Any, relation: str, *, include_capabilities: bool) -> dict[str, Any]:
    commander = getattr(unit, "commander_component", None)
    components = sorted(
        component.__class__.__name__ for component in getattr(unit, "components", {}).values()
    )
    data = {
        "id": int(unit.id),
        "name": str(unit.name),
        "owner_id": int(unit.owner.id),
        "relation": relation,
        "system_name": str(unit.in_system),
        "hex_coord": list(unit.in_hex),
        "position": _position(unit.position),
        "hull_size": _enum_value(unit.hull_size),
        "hit_points": {
            "current": int(unit.current_hit_points),
            "maximum": int(unit.max_hit_points),
        },
        "disabled": bool(getattr(unit, "is_disabled", False)),
        "components": components,
        "antimatter": _component_amount(getattr(unit, "antimatter_component", None)),
        "orders": _orders(commander),
        "stance": _enum_value(getattr(commander, "stance", None)),
    }
    if include_capabilities:
        data["available_commands"] = _available_commands(unit)
        data["ability_states"] = _ability_states(unit)
        data["capability_details"] = _capability_details(unit)
    return data


def _body_view(body: Any, viewer: Any) -> dict[str, Any]:
    owner = getattr(body, "owner", None)
    data = {
        "id": int(body.id),
        "type": body.__class__.__name__,
        "name": str(getattr(body, "name", body.__class__.__name__)),
        "system_name": str(body.in_system),
        "hex_coord": list(body.in_hex),
        "position": _position(body.position),
        "owner_id": int(owner.id) if owner is not None else None,
        "owner_relation": _relation(viewer, owner) if owner is not None else "neutral",
    }
    for name in (
        "population",
        "max_population",
        "metal_yield",
        "crystal_yield",
        "stability",
    ):
        if hasattr(body, name):
            data[name] = _rounded(getattr(body, name))
    if hasattr(body, "exit_system_name"):
        data["exit_system_name"] = str(body.exit_system_name)
    return data


def _minefield_view(minefield: Any, viewer: Any) -> dict[str, Any]:
    return {
        "id": int(minefield.id),
        "owner_id": int(minefield.owner.id),
        "owner_relation": _relation(viewer, minefield.owner),
        "system_name": str(minefield.in_system),
        "hex_coord": list(minefield.in_hex),
        "position": _position(minefield.position),
        "type": _enum_value(minefield.minefield_type),
        "mines_remaining": int(minefield.mines_remaining),
    }


def _available_commands(unit: Any) -> list[str]:
    commands = ["cancel_orders", "set_stance"]
    if getattr(unit, "engines_component", None):
        commands.extend(["move", "patrol", "protect"])
    if getattr(unit, "weapons_component", None):
        commands.append("attack")
    if getattr(unit, "colony_component", None):
        commands.extend(["colonize", "load_colonists"])
    if getattr(unit, "constructor_component", None):
        commands.append("construct")
    if getattr(unit, "repair_component", None):
        commands.append("repair")
    if getattr(unit, "mining_component", None):
        commands.extend(["mine", "continuous_mine", "unload_resources"])
    if getattr(unit, "harvester_component", None):
        commands.extend(["transfer_antimatter", "continuous_resupply"])
    hull_name = str(getattr(getattr(unit, "hull_size", None), "name", "")).lower()
    if hull_name in {"tiny", "small", "strikecraft_wing"}:
        commands.append("dock")
    if getattr(unit, "hangar_component", None):
        commands.append("deploy_unit")
    if getattr(unit, "strikecraft_bay_component", None):
        commands.extend(["deploy_unit", "deploy_all_wings"])
    if getattr(unit, "trade_component", None):
        commands.extend(["trade", "continuous_trade"])
    if getattr(unit, "inhibitor_component", None):
        commands.append("toggle_inhibitor")
    if getattr(unit, "cloaking_component", None):
        commands.append("toggle_cloaking")
    if getattr(unit, "ability_component", None):
        commands.append("use_ability")
    if _component_by_name(unit, "MinelayerComponent") is not None:
        commands.append("lay_minefield")
    return sorted(set(commands))


def _ability_states(unit: Any) -> list[dict[str, Any]]:
    component = getattr(unit, "ability_component", None)
    result = []
    for ability_type, instance in getattr(component, "abilities", {}).items():
        definition = getattr(instance, "definition", None)
        result.append(
            {
                "ability": _enum_value(ability_type),
                "ready": bool(getattr(instance, "is_ready", False)),
                "requires_target_unit": bool(
                    getattr(definition, "requires_target_unit", False)
                ),
                "requires_target_position": bool(
                    getattr(definition, "requires_target_position", False)
                ),
            }
        )
    return result


def _capability_details(unit: Any) -> dict[str, Any]:
    commander = getattr(unit, "commander_component", None)
    details: dict[str, Any] = {
        "allowed_stances": [
            _enum_value(stance)
            for stance in (
                commander.get_allowed_stances()
                if commander and hasattr(commander, "get_allowed_stances")
                else []
            )
        ]
    }
    engines = getattr(unit, "engines_component", None)
    if engines is not None:
        details["engines"] = {"speed": _rounded(getattr(engines, "speed", 0))}
    hyperdrive = getattr(unit, "hyperdrive_component", None)
    if hyperdrive is not None:
        details["hyperdrive"] = {
            "type": _enum_value(getattr(hyperdrive, "drive_type", None)),
            "jump_range": _rounded(getattr(hyperdrive, "jump_range", 0)),
            "status": _enum_value(getattr(hyperdrive, "jump_status", None)),
        }
    colony = getattr(unit, "colony_component", None)
    if colony is not None:
        details["colony"] = {
            "population_cargo": _rounded(getattr(colony, "population_cargo", 0)),
            "maximum_cargo": _rounded(
                getattr(colony, "max_population_cargo", getattr(colony, "capacity", 0))
            ),
        }
    mining = getattr(unit, "mining_component", None)
    if mining is not None:
        details["mining"] = {
            "raw_metal_cargo": _rounded(getattr(mining, "raw_metal_cargo", 0)),
            "raw_crystal_cargo": _rounded(getattr(mining, "raw_crystal_cargo", 0)),
            "cargo_capacity": _rounded(getattr(mining, "cargo_capacity", 0)),
        }
    constructor = getattr(unit, "constructor_component", None)
    if constructor is not None:
        details["construction"] = {
            "buildable_templates": [
                {
                    "template_name": buildable.unit_template_name,
                    "credit_cost": int(buildable.cost_credits),
                    "turns": int(buildable.time_to_build),
                }
                for buildable in getattr(constructor, "buildable_units", [])
            ]
        }
    for name, component_name in (
        ("repair", "repair_component"),
        ("antimatter_harvester", "harvester_component"),
        ("trade", "trade_component"),
        ("intelligence", "intelligence_component"),
    ):
        component = getattr(unit, component_name, None)
        if component is not None:
            details[name] = _public_scalar_attributes(component)
    for name, component_name in (
        ("hangar", "hangar_component"),
        ("strikecraft_bay", "strikecraft_bay_component"),
    ):
        component = getattr(unit, component_name, None)
        if component is not None:
            details[name] = {
                "docked_units": [
                    {"id": int(docked.id), "name": str(docked.name)}
                    for docked in getattr(component, "docked_units", [])
                ],
                "maximum_slots": int(getattr(component, "max_slots", 0)),
            }
    return details


def _public_scalar_attributes(component: Any) -> dict[str, Any]:
    allowed = (
        "repair_amount",
        "harvest_rate",
        "trade_revenue_multiplier",
        "available_agents",
        "max_agents",
        "has_counter_intelligence",
        "ci_cooldown_remaining",
    )
    result = {}
    for name in allowed:
        value = getattr(component, name, None)
        if isinstance(value, bool):
            result[name] = value
        elif isinstance(value, (int, float)):
            result[name] = _rounded(value)
    return result


def _orders(commander: Any) -> list[dict[str, Any]]:
    if commander is None:
        return []
    active = getattr(commander, "current_order", None)
    queued = list(getattr(commander, "orders_queue", []) or [])
    result = []
    for state, order in ([("active", active)] if active is not None else []) + [
        ("queued", order) for order in queued
    ]:
        result.append(
            {
                "state": state,
                "type": _enum_value(getattr(order, "order_type", None)),
                "status": _enum_value(getattr(order, "status", None)),
            }
        )
    return result


def _component_by_name(unit: Any, name: str) -> Any | None:
    for component in getattr(unit, "components", {}).values():
        if component.__class__.__name__ == name:
            return component
    return None


def _component_amount(component: Any) -> dict[str, float] | None:
    if component is None:
        return None
    return {
        "current": _rounded(getattr(component, "current_amount", 0.0)),
        "maximum": _rounded(
            getattr(component, "max_capacity", getattr(component, "capacity", 0.0))
        ),
    }


def _relation(viewer: Any, owner: Any) -> str:
    if owner is None:
        return "neutral"
    if owner is viewer or getattr(owner, "id", None) == getattr(viewer, "id", None):
        return "self"
    if hasattr(viewer, "is_allied_with") and viewer.is_allied_with(owner):
        return "ally"
    return "enemy"


def _safe_game_metric(game: Any, name: str, player: Any) -> float | None:
    method = getattr(game, name, None)
    if not callable(method):
        return None
    try:
        return _rounded(method(player))
    except Exception:
        return None


def _position(position: Any) -> list[float]:
    return [_rounded(getattr(position, "x", 0.0)), _rounded(getattr(position, "y", 0.0))]


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


def _rounded(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0
