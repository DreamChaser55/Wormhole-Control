"""Player-scoped, JSON-safe observations for planning agents."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .rules import (
    ability_states,
    command_guidance,
    is_colonizable_body,
    is_mining_target,
    is_self_owned,
    is_star,
    supported_commands,
)


COMMAND_HELP = {
    "cancel_orders": "Clear current and queued orders.",
    "move": "Move to system_name, hex_coord, and position.",
    "patrol": "Patrol toward system_name, hex_coord, and position.",
    "attack": "Attack visible enemy target_id (optional target_component to focus fire on a specific subsystem).",
    "defend": "Move to and defend system_name, hex_coord, position, or target_id against hostile intruders.",
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
    "toggle_inhibitor": (
        "Flip the unit's hyperspace inhibitor to the resulting_state listed in "
        "command_options; activation is legal only when its field fits and does not overlap."
    ),
    "toggle_cloaking": "Toggle the unit's cloaking device.",
    "use_ability": "Use ability; target_id and/or position depend on ability.",
    "send_message": "Send a text message to player target_id with message text.",
    "message_developer": "Send feedback, suggestions, or bug reports to the game developer with message text.",
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
    visible_unit_objects = []
    bodies_by_system: dict[str, list[Any]] = {}
    minefields = []

    for system_name in sorted(galaxy.systems):
        system = galaxy.systems[system_name]
        system_bodies = []
        for hex_coord, hex_obj in sorted(system.hexes.items()):
            for body in getattr(hex_obj, "celestial_bodies", []):
                system_bodies.append(body)
            for unit in getattr(hex_obj, "units", []):
                relation = _relation(player, getattr(unit, "owner", None))
                if relation != "enemy" or unit.id in visibility.visible_enemy_unit_ids:
                    visible_unit_objects.append(unit)
            for minefield in getattr(hex_obj, "minefields", []):
                if is_minefield_visible(visibility, minefield):
                    minefields.append(_minefield_view(minefield, player))
        bodies_by_system[system_name] = system_bodies

    presences = [
        {"system_name": system_name, "hex_coord": list(hex_coord)}
        for system_name, hex_coord in sorted(visibility.presence_hexes)
    ]
    friendly_systems = {
        str(unit.in_system)
        for unit in visible_unit_objects
        if _relation(player, getattr(unit, "owner", None)) in {"self", "ally"}
    }
    detailed_systems = set(friendly_systems)
    for system_name in friendly_systems:
        detailed_systems.update(
            getattr(galaxy, "system_graph", {}).get(system_name, {}).keys()
        )
    detailed_systems.update(
        str(unit.in_system)
        for unit in visible_unit_objects
        if _relation(player, getattr(unit, "owner", None)) == "enemy"
    )
    detailed_systems.update(system_name for system_name, _hex in visibility.presence_hexes)

    exact_bodies = []
    for system_name in sorted(galaxy.systems):
        system = galaxy.systems[system_name]
        system_bodies = bodies_by_system[system_name]
        detailed = system_name in detailed_systems
        exact_for_system = (
            list(system_bodies)
            if detailed
            else [
                body
                for body in system_bodies
                if is_star(body) or getattr(body, "owner", None) is not None
            ]
        )
        exact_bodies.extend(exact_for_system)
        system_data = {
            "name": system_name,
            "position": _position(getattr(system, "position", None)),
            "radius": int(getattr(system, "radius", 0)),
            "connections": [
                {
                    "system_name": destination,
                    "maximum_hull": _enum_value(maximum_hull),
                }
                for destination, maximum_hull in sorted(
                    getattr(galaxy, "system_graph", {}).get(system_name, {}).items()
                )
            ],
            "navigation_anchor": _navigation_anchor(system, system_bodies),
            "detail_level": "full" if detailed else "summary",
        }
        if detailed:
            system_data["celestial_bodies"] = [
                _body_view(body, player, include_system=False)
                for body in exact_for_system
            ]
        else:
            system_data["notable_bodies"] = [
                _body_view(body, player, include_system=False)
                for body in exact_for_system
            ]
            system_data["body_summary"] = _body_summary(system_bodies, player)
        systems.append(system_data)

    units = [
        _unit_view(
            unit,
            _relation(player, getattr(unit, "owner", None)),
            include_capabilities=_relation(player, getattr(unit, "owner", None)) == "self",
            game=game,
            player=player,
            exact_bodies=exact_bodies,
            visible_units=visible_unit_objects,
        )
        for unit in visible_unit_objects
    ]
    construction_templates = _construction_catalog(visible_unit_objects, player)
    memory_note = (
        "Presence signatures intentionally contain no unit count, identity, owner, or strength."
    )
    return {
        "schema_version": 3,
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
        "conversations": [
            {
                "partner_id": int(conv.get_partner_id(getattr(player, "id", None))),
                "partner_name": str(
                    getattr(
                        game.get_player_by_id(conv.get_partner_id(getattr(player, "id", None))),
                        "name",
                        f"Player {conv.get_partner_id(getattr(player, 'id', None))}",
                    )
                ),
                "messages": [
                    {
                        "sender_id": int(m.sender_id),
                        "sender_name": str(m.sender_name),
                        "turn_sent": int(m.turn_sent),
                        "text": str(m.text),
                    }
                    for m in conv.messages
                    if getattr(m, "turn_sent", 1) < turn
                ],
            }
            for conv in (
                game.get_conversations_for_player(getattr(player, "id", None))
                if hasattr(game, "get_conversations_for_player")
                else []
            )
            if any(getattr(m, "turn_sent", 1) < turn for m in conv.messages)
        ],
        "systems": systems,
        "units": units,
        "visible_minefields": minefields,
        "undetailed_enemy_presence": presences,
        "visibility_note": memory_note,
        "command_reference": COMMAND_HELP,
        "action_catalogs": {
            "colonization_target_ids": [
                int(body.id)
                for body in exact_bodies
                if is_colonizable_body(body) and getattr(body, "owner", None) is None
            ],
            "colonist_sources": [
                {
                    "target_id": int(body.id),
                    "available_population": _rounded(getattr(body, "population", 0)),
                }
                for body in exact_bodies
                if is_colonizable_body(body)
                and is_self_owned(player, getattr(body, "owner", None))
                and float(getattr(body, "population", 0)) > 0
            ],
            "mining_target_ids": [
                int(body.id) for body in exact_bodies if is_mining_target(body)
            ],
            "antimatter_source_ids": [
                int(body.id) for body in exact_bodies if is_star(body)
            ],
            "construction_templates": construction_templates,
        },
    }


def _unit_view(
    unit: Any,
    relation: str,
    *,
    include_capabilities: bool,
    game: Any,
    player: Any,
    exact_bodies: list[Any],
    visible_units: list[Any],
) -> dict[str, Any]:
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
        legal, options, conditional = command_guidance(
            game,
            player,
            unit,
            exact_bodies=exact_bodies,
            visible_units=visible_units,
        )
        data["supported_commands"] = supported_commands(unit)
        data["legal_commands"] = legal
        data["command_options"] = options
        data["conditional_commands"] = conditional
        data["ability_states"] = ability_states(unit)
        data["capability_details"] = _capability_details(unit, game)
    return data


def _body_view(
    body: Any, viewer: Any, *, include_system: bool = True
) -> dict[str, Any]:
    owner = getattr(body, "owner", None)
    data = {
        "id": int(body.id),
        "type": body.__class__.__name__,
        "name": str(getattr(body, "name", body.__class__.__name__)),
        "hex_coord": list(body.in_hex),
        "position": _position(body.position),
        "owner_id": int(owner.id) if owner is not None else None,
        "owner_relation": _relation(viewer, owner) if owner is not None else "neutral",
    }
    if include_system:
        data["system_name"] = str(body.in_system)
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


def _capability_details(unit: Any, game: Any) -> dict[str, Any]:
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
            "maximum_cargo": _rounded(getattr(colony, "max_cargo", 0)),
        }
    mining = getattr(unit, "mining_component", None)
    if mining is not None:
        details["mining"] = {
            "raw_metal_cargo": _rounded(getattr(mining, "raw_metal_cargo", 0)),
            "raw_crystal_cargo": _rounded(getattr(mining, "raw_crystal_cargo", 0)),
            "cargo_capacity": _rounded(getattr(mining, "max_cargo", 0)),
        }
    constructor = getattr(unit, "constructor_component", None)
    if constructor is not None:
        details["construction"] = {
            "buildable_template_names": [
                buildable.unit_template_name
                for buildable in getattr(constructor, "buildable_units", [])
            ]
        }
    inhibitor = getattr(unit, "inhibitor_component", None)
    if inhibitor is not None:
        is_active = bool(getattr(inhibitor, "is_active", False))
        activation_check = (
            None
            if is_active
            else inhibitor.check_state_change(True, game.galaxy)
        )
        details["inhibitor"] = {
            "is_active": is_active,
            "radius": _rounded(getattr(inhibitor, "radius", 0)),
            "antimatter_cost_per_turn": _rounded(
                inhibitor.get_antimatter_cost_per_turn()
            ),
            "can_activate": not is_active and bool(activation_check.allowed),
            "activation_blocker": (
                None if is_active or activation_check.allowed else activation_check.code
            ),
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


def _navigation_anchor(system: Any, bodies: list[Any]) -> dict[str, Any]:
    anchor = next((body for body in bodies if is_star(body)), None)
    if anchor is not None:
        return {
            "body_id": int(anchor.id),
            "hex_coord": list(anchor.in_hex),
            "position": _position(anchor.position),
        }
    hexes = sorted(getattr(system, "hexes", {}))
    return {
        "body_id": None,
        "hex_coord": list(hexes[0]) if hexes else [0, 0],
        "position": [0.0, 0.0],
    }


def _body_summary(bodies: list[Any], viewer: Any) -> dict[str, Any]:
    type_counts = Counter(body.__class__.__name__ for body in bodies)
    relation_counts = Counter(
        _relation(viewer, getattr(body, "owner", None)) for body in bodies
    )
    neutral_colonizable = [
        body
        for body in bodies
        if is_colonizable_body(body) and getattr(body, "owner", None) is None
    ]
    mining_counts = Counter()
    for body in bodies:
        if not is_mining_target(body):
            continue
        body_type = body.__class__.__name__
        mining_counts["crystal" if body_type == "Comet" else "metal"] += 1
    hazard_names = {"Nebula", "Storm", "DebrisField", "IceField"}
    return {
        "counts_by_type": dict(sorted(type_counts.items())),
        "counts_by_owner_relation": dict(sorted(relation_counts.items())),
        "neutral_colonizable_count": len(neutral_colonizable),
        "neutral_colonizable_capacity": _rounded(
            sum(float(getattr(body, "max_population", 0)) for body in neutral_colonizable)
        ),
        "mining_targets": dict(sorted(mining_counts.items())),
        "hazards": {
            name: type_counts[name]
            for name in sorted(hazard_names)
            if type_counts[name]
        },
    }


def _construction_catalog(units: list[Any], player: Any) -> list[dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for unit in units:
        if not is_self_owned(player, getattr(unit, "owner", None)):
            continue
        constructor = getattr(unit, "constructor_component", None)
        for buildable in getattr(constructor, "buildable_units", []) if constructor else []:
            catalog[buildable.unit_template_name] = {
                "template_name": buildable.unit_template_name,
                "credit_cost": int(buildable.cost_credits),
                "turns": int(buildable.time_to_build),
            }
    return [catalog[name] for name in sorted(catalog)]


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
