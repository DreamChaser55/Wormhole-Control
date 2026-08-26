"""Side-effect-free legality helpers shared by AI observation and validation."""

from __future__ import annotations

from typing import Any, Iterable


def is_colonizable_body(body: Any) -> bool:
    from entities import ColonizableAsteroid, Moon, Planet

    return isinstance(body, (Planet, Moon, ColonizableAsteroid))


def is_mining_target(body: Any) -> bool:
    from entities import AsteroidField, Comet, MetalAsteroid

    return isinstance(body, (MetalAsteroid, AsteroidField, Comet))


def is_star(body: Any) -> bool:
    from entities import Star

    return isinstance(body, Star)


def compatible_docking_component(unit: Any, target: Any) -> Any | None:
    if _hull_name(unit) == "strikecraft_wing":
        component = getattr(target, "strikecraft_bay_component", None)
    else:
        component = getattr(target, "hangar_component", None)
    if component is None or not hasattr(component, "can_dock"):
        return None
    return component if component.can_dock(unit) else None


def is_self_owned(player: Any, owner: Any) -> bool:
    return owner is player or (
        owner is not None and getattr(owner, "id", None) == getattr(player, "id", None)
    )


def relation(player: Any, owner: Any) -> str:
    if owner is None:
        return "neutral"
    if is_self_owned(player, owner):
        return "self"
    if hasattr(player, "is_allied_with") and player.is_allied_with(owner):
        return "ally"
    return "enemy"


def supported_commands(unit: Any) -> list[str]:
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
    if getattr(unit, "antimatter_component", None):
        commands.append("transfer_antimatter")
    if getattr(unit, "harvester_component", None) and getattr(
        unit, "antimatter_component", None
    ):
        commands.append("continuous_resupply")
    if _hull_name(unit) in {"tiny", "strikecraft_wing"}:
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


def command_guidance(
    game: Any,
    player: Any,
    unit: Any,
    *,
    exact_bodies: Iterable[Any],
    visible_units: Iterable[Any],
) -> tuple[list[str], dict[str, Any], list[dict[str, Any]]]:
    """Return standalone legal commands, bounded options, and conditional actions."""

    supported = supported_commands(unit)
    exact_bodies = list(exact_bodies)
    visible_units = list(visible_units)
    legal: set[str] = set()
    options: dict[str, Any] = {}
    conditional: list[dict[str, Any]] = []

    if "cancel_orders" in supported:
        legal.add("cancel_orders")
    if "move" in supported:
        legal.update({"move", "patrol"})

    commander = getattr(unit, "commander_component", None)
    stances = [
        _enum_value(stance)
        for stance in (
            commander.get_allowed_stances()
            if commander and hasattr(commander, "get_allowed_stances")
            else []
        )
    ]
    options["set_stance"] = {"values": stances}
    if stances:
        legal.add("set_stance")

    friendly_units = [
        candidate
        for candidate in visible_units
        if relation(player, getattr(candidate, "owner", None)) in {"self", "ally"}
    ]
    enemy_units = [
        candidate
        for candidate in visible_units
        if relation(player, getattr(candidate, "owner", None)) == "enemy"
    ]

    target_options = {
        "attack": [candidate.id for candidate in enemy_units],
        "protect": [candidate.id for candidate in friendly_units],
        "repair": [candidate.id for candidate in friendly_units],
        "unload_resources": [
            candidate.id
            for candidate in friendly_units
            if getattr(candidate, "metal_refinery_component", None)
            or getattr(candidate, "crystal_refinery_component", None)
        ],
        "dock": [
            candidate.id
            for candidate in friendly_units
            if candidate is not unit
            and compatible_docking_component(unit, candidate) is not None
        ],
        "transfer_antimatter": [
            candidate.id
            for candidate in friendly_units
            if candidate is not unit
            and getattr(candidate, "antimatter_component", None) is not None
            and float(
                getattr(candidate.antimatter_component, "current_amount", 0)
            )
            < float(getattr(candidate.antimatter_component, "max_capacity", 0))
        ],
        "trade": [
            candidate.id
            for candidate in friendly_units
            if getattr(candidate, "civilian_habitat_component", None)
        ],
    }
    for command_type, target_ids in target_options.items():
        if command_type in supported:
            options[command_type] = {"target_ids": target_ids}
            if target_ids:
                legal.add(command_type)

    colony = getattr(unit, "colony_component", None)
    if colony is not None:
        cargo = float(getattr(colony, "population_cargo", 0))
        maximum = float(getattr(colony, "max_cargo", 0))
        remaining = max(0.0, maximum - cargo)
        colony_targets = [
            body.id
            for body in exact_bodies
            if is_colonizable_body(body) and getattr(body, "owner", None) is None
        ]
        sources = [
            {
                "target_id": body.id,
                "maximum_amount": min(
                    float(getattr(body, "population", 0)), remaining
                ),
            }
            for body in exact_bodies
            if is_colonizable_body(body)
            and is_self_owned(player, getattr(body, "owner", None))
            and float(getattr(body, "population", 0)) > 0
            and remaining > 0
        ]
        options["colonize"] = {"target_ids": colony_targets}
        options["load_colonists"] = {"targets": sources}
        if cargo > 0 and colony_targets:
            legal.add("colonize")
        elif colony_targets and sources:
            conditional.append(
                {
                    "type": "colonize",
                    "requires_prior_command": "load_colonists",
                    "same_unit": True,
                    "queue": True,
                }
            )
        if sources:
            legal.add("load_colonists")

    mining_targets = [body.id for body in exact_bodies if is_mining_target(body)]
    for command_type in ("mine", "continuous_mine"):
        if command_type in supported:
            options[command_type] = {"target_ids": mining_targets}
            if mining_targets:
                legal.add(command_type)

    stars = [body.id for body in exact_bodies if is_star(body)]
    if "continuous_resupply" in supported:
        options["continuous_resupply"] = {"target_ids": stars}
        if stars:
            legal.add("continuous_resupply")

    constructor = getattr(unit, "constructor_component", None)
    if constructor is not None:
        templates = [
            buildable.unit_template_name
            for buildable in getattr(constructor, "buildable_units", [])
            if float(getattr(player, "credits", 0)) >= buildable.cost_credits
        ]
        options["construct"] = {"template_names": templates}
        if templates:
            legal.add("construct")

    if "deploy_unit" in supported:
        docked = []
        for component_name in ("hangar_component", "strikecraft_bay_component"):
            component = getattr(unit, component_name, None)
            docked.extend(getattr(component, "docked_units", []) or [])
        target_ids = sorted({docked_unit.id for docked_unit in docked})
        options["deploy_unit"] = {"target_ids": target_ids}
        if target_ids:
            legal.add("deploy_unit")
    if "deploy_all_wings" in supported:
        bay = getattr(unit, "strikecraft_bay_component", None)
        if getattr(bay, "docked_units", None):
            legal.add("deploy_all_wings")

    if "use_ability" in supported:
        ready_states = [state for state in ability_states(unit) if state["ready"]]
        abilities = [state["ability"] for state in ready_states]
        options["use_ability"] = {
            "values": abilities,
            "targets_by_ability": {
                state["ability"]: [candidate.id for candidate in visible_units]
                for state in ready_states
                if state["requires_target_unit"]
            },
            "position_required": [
                state["ability"]
                for state in ready_states
                if state["requires_target_position"]
            ],
        }
        if abilities:
            legal.add("use_ability")

    if "lay_minefield" in supported:
        options["lay_minefield"] = {
            "minefield_types": ["anti_ship", "anti_strikecraft"]
        }
        legal.add("lay_minefield")

    inhibitor = getattr(unit, "inhibitor_component", None)
    if "toggle_inhibitor" in supported and inhibitor is not None:
        is_active = bool(getattr(inhibitor, "is_active", False))
        check = inhibitor.check_state_change(not is_active, game.galaxy)
        options["toggle_inhibitor"] = {
            "current_state": "active" if is_active else "inactive",
            "resulting_state": "inactive" if is_active else "active",
            "available": check.allowed,
            "unavailable_reason": None if check.allowed else check.code,
        }
        if check.allowed:
            legal.add("toggle_inhibitor")

    for command_type in ("toggle_cloaking", "continuous_trade"):
        if command_type in supported:
            legal.add(command_type)

    if "transfer_antimatter" in legal:
        storage = getattr(unit, "antimatter_component", None)
        if storage is None or float(getattr(storage, "current_amount", 0)) <= 0:
            legal.discard("transfer_antimatter")

    return sorted(legal), options, conditional


def ability_states(unit: Any) -> list[dict[str, Any]]:
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


def _hull_name(unit: Any) -> str:
    hull = getattr(unit, "hull_size", None)
    name = getattr(hull, "name", None)
    return str(name if name is not None else getattr(hull, "value", hull)).lower()


def _component_by_name(unit: Any, name: str) -> Any | None:
    for component in getattr(unit, "components", {}).values():
        if component.__class__.__name__ == name:
            return component
    return None


def _enum_value(value: Any) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))
