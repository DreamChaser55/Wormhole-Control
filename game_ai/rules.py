"""Shared legality helpers; body disclosure may record visibility intel."""

from __future__ import annotations

from typing import Any, Iterable
from .command_spec import COMMAND_SPECS
from component_visibility import public_target_components


def is_colonizable_body(body: Any) -> bool:
    from domain.celestials import ColonizableAsteroid, Moon, Planet
    from constants import PlanetType

    if isinstance(body, Planet):
        if getattr(body, "planet_type", None) == PlanetType.GAS_GIANT:
            return False
        if getattr(body, "is_colonizable", True) is False:
            return False
    return isinstance(body, (Planet, Moon, ColonizableAsteroid))


def is_mining_target(body: Any) -> bool:
    from domain.celestials import Comet, MetalAsteroid

    return isinstance(body, (MetalAsteroid, Comet))


def is_star(body: Any) -> bool:
    from domain.celestials import Star

    return isinstance(body, Star)


def is_antimatter_source(body: Any) -> bool:
    from domain.celestials import Nebula
    from constants import NebulaType

    if is_star(body):
        return True
    if isinstance(body, Nebula) and getattr(body, "nebula_type", None) == NebulaType.HYDROGEN:
        return True
    return False


def has_operational_engines(unit: Any) -> bool:
    """Return whether a unit's installed engines can provide sub-light movement."""
    engines = getattr(unit, "engines_component", None)
    if engines is None:
        return False

    operational = getattr(engines, "is_operational", None)
    if isinstance(operational, bool):
        return operational
    if getattr(engines, "is_destroyed", False) is True:
        return False

    effective_speed = getattr(engines, "effective_speed", None)
    if not isinstance(effective_speed, (int, float)):
        effective_speed = getattr(engines, "speed", None)
    return effective_speed > 0 if isinstance(effective_speed, (int, float)) else True


def compatible_hangar_component(unit: Any, target: Any) -> Any | None:
    component = getattr(target, "hangar_component", None)
    if component is None or not hasattr(component, "can_dock"):
        return None
    return component if component.can_dock(unit) else None


def compatible_strikecraft_bay_component(unit: Any, target: Any) -> Any | None:
    component = getattr(target, "strikecraft_bay_component", None)
    if component is None or not hasattr(component, "can_dock"):
        return None
    return component if component.can_dock(unit) else None


def compatible_docking_component(unit: Any, target: Any) -> Any | None:
    if _hull_name(unit) == "strikecraft_wing":
        return compatible_strikecraft_bay_component(unit, target)
    return compatible_hangar_component(unit, target)


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


def detailed_system_names(galaxy, player, visible_units, presence_hexes):
    """Shared exact-body disclosure boundary for observations and target validation."""
    friendly = {str(unit.in_system) for unit in visible_units
                if relation(player, getattr(unit, "owner", None)) in {"self", "ally"}}
    detailed = set(friendly)
    for name in friendly:
        detailed.update(getattr(galaxy, "system_graph", {}).get(name, {}).keys())
    detailed.update(str(unit.in_system) for unit in visible_units
                    if relation(player, getattr(unit, "owner", None)) == "enemy")
    detailed.update(name for name, _ in presence_hexes)
    return detailed


def body_is_public(game, player, body, selected_units=()):
    if is_star(body) or getattr(body, "owner", None) is not None:
        return True
    units = [u for system in getattr(game.galaxy, "systems", {}).values()
             for sector in system.hexes.values() for u in getattr(sector, "units", [])]
    friendly = [u for u in [*units, *selected_units] if relation(player, u.owner) in {"self", "ally"}]
    if body.in_system in detailed_system_names(game.galaxy, player, friendly, ()):
        return True
    from visibility import VisibilityService
    snapshot = VisibilityService.compute(game.galaxy, player, turn_number=getattr(game, "turn_number", 1))
    visible = [u for u in units if relation(player, u.owner) != "enemy" or u.id in snapshot.visible_enemy_unit_ids]
    return body.in_system in detailed_system_names(game.galaxy, player, visible, snapshot.presence_hexes)


def capability_blocker(unit, command_type):
    from strikecraft_service import command_blocker
    service_blocker = command_blocker(unit, command_type)
    if service_blocker:
        return service_blocker
    from dismantling import offline
    if offline(unit) and command_type not in {'rename_unit', 'cancel_orders', 'clear_explicit_orders', 'cancel_order'}:
        return 'dismantling_conflict'
    if command_type == "set_stance" and not getattr(getattr(unit, "commander_component", None), "supports_stances", False):
        return "capability_unavailable"
    if command_type == "attack_long_range":
        from unit_components.enums import TurretVariant
        if getattr(unit, 'is_disabled', False) is True or not any(t.variant == TurretVariant.LONG_RANGE
                   for t in getattr(getattr(unit, 'weapons_component', None), 'turrets', ())):
            return "capability_unavailable"
    if command_type == "lay_minefield":
        component = _component_by_name(unit, "MinelayerComponent")
        if component is None or getattr(component, "is_destroyed", False) is True:
            return "capability_unavailable"
    if command_type == "enter_gas_giant":
        if _hull_name(unit) == "strikecraft_wing":
            return "capability_unavailable"
    for attribute in COMMAND_SPECS[command_type].capability:
        component = getattr(unit, attribute, None)
        if component is None or getattr(component, "is_destroyed", False) is True:
            return "capability_unavailable"
        if attribute == "engines_component" and not has_operational_engines(unit):
            return "engines_unavailable"
    return None


def supported_commands(unit: Any) -> list[str]:
    commands = ["rename_unit", "cancel_orders", "clear_explicit_orders", "cancel_order", "append_patrol_waypoints"]
    if getattr(getattr(unit, "commander_component", None), "supports_stances", False):
        commands.append("set_stance")
    if getattr(unit, "engines_component", None) is not None:
        commands.extend(["move", "patrol", "protect"])
        if _hull_name(unit) != "strikecraft_wing":
            commands.append("enter_gas_giant")
        if getattr(unit, "weapons_component", None):
            commands.append("defend")
    if getattr(unit, "is_hidden_in_gas_giant", False):
        commands.append("leave_gas_giant")
    if getattr(unit, "weapons_component", None):
        commands.append("attack")
        from unit_components.enums import TurretVariant
        if any(t.variant == TurretVariant.LONG_RANGE for t in unit.weapons_component.turrets):
            commands.append("attack_long_range")
    if getattr(unit, "colony_component", None):
        commands.extend(["colonize", "load_colonists"])
    if getattr(unit, "constructor_component", None):
        commands.extend(["construct", "dismantle_unit"])
    if getattr(unit, "troop_transport_component", None):
        commands.extend(["recruit_troops", "invade_planet"])
    if getattr(unit, "wormhole_stabilizer_component", None):
        commands.append("stabilize_wormhole")
    if getattr(unit, "siege_battery_component", None):
        commands.append("bombard_planet")
    if getattr(unit, "repair_component", None):
        commands.append("repair")
    if getattr(unit, "mining_component", None):
        commands.extend(["mine", "continuous_mine", "unload_resources"])
    if getattr(unit, "antimatter_component", None):
        commands.extend(["transfer_antimatter", "take_antimatter"])
        if has_operational_engines(unit):
            commands.append("continuous_antimatter_transport")
    if getattr(unit, "harvester_component", None) and getattr(
        unit, "antimatter_component", None
    ):
        commands.append("continuous_resupply")
    if _hull_name(unit) == "tiny":
        commands.append("dock_in_hangar")
    elif _hull_name(unit) == "strikecraft_wing":
        commands.append("dock_in_strikecraft_bay")
    if getattr(unit, "hangar_component", None):
        commands.append("deploy_unit")
    if getattr(unit, "strikecraft_bay_component", None):
        commands.extend(["deploy_unit", "deploy_all_wings", "set_wing_production", "set_wing_production_enabled"])
        if 'dismantle_unit' not in commands:
            commands.append('dismantle_unit')
    if getattr(unit, "trade_component", None):
        commands.extend(["trade", "continuous_trade"])
    if getattr(unit, "inhibitor_component", None):
        commands.append("toggle_inhibitor")
    if getattr(unit, "cloaking_component", None):
        commands.append("toggle_cloaking")
    if getattr(unit, "ability_component", None):
        commands.append("use_ability")
        commands.append("cancel_ability")
        from environmental_resistance import instances
        if instances(unit):
            commands.append('toggle_ability')
    intelligence = getattr(unit, "intelligence_component", None)
    if intelligence is not None:
        commands.extend(["infiltrate_unit", "infiltrate_planet", "extract_agent"])
        if getattr(intelligence, "has_counter_intelligence", False):
            commands.extend(["ci_sweep", "eliminate_agent"])
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
    from strikecraft_service import required
    if required(unit):
        return ['rename_unit'], {'service_blocker': 'wing_service_required'}, []
    exact_bodies = list(exact_bodies)
    visible_units = list(visible_units)
    legal: set[str] = {"rename_unit"}
    options: dict[str, Any] = {}
    conditional: list[dict[str, Any]] = []

    commander = getattr(unit, "commander_component", None)
    stances = [
        _enum_value(stance)
        for stance in (
            commander.get_allowed_stances()
            if commander and getattr(commander, "supports_stances", False)
            else []
        )
    ]
    if stances:
        options["set_stance"] = {"values": stances}
        legal.add("set_stance")

    commander_roots = [getattr(commander, "current_order", None), *list(getattr(commander, "orders_queue", []))]
    roots = [root for root in commander_roots if root is not None and getattr(root.status, "name", "") in {"PENDING", "IN_PROGRESS"}]
    options["cancel_order"] = {"order_ids": [root.public_id for root in roots]}
    options["append_patrol_waypoints"] = {"order_ids": [root.public_id for root in roots if root.order_type.name == "PATROL" and len(root.parameters.get("waypoints", [])) < 16]}
    for kind in ("cancel_order", "append_patrol_waypoints"):
        if options[kind]["order_ids"]:
            legal.add(kind)

    if getattr(unit, "is_hidden_in_gas_giant", False):
        legal.update({"leave_gas_giant", "cancel_orders", "clear_explicit_orders"})
        if "move" in supported:
            conditional.append({"type": "move", "requires_prior_command": "leave_gas_giant",
                                "same_unit": True, "queue": True})
        return sorted(legal), options, conditional

    if "cancel_orders" in supported:
        legal.update({"cancel_orders", "clear_explicit_orders"})
    if "move" in supported:
        legal.update({"move", "patrol"})
    if "defend" in supported:
        legal.add("defend")

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

    intelligence = getattr(unit, "intelligence_component", None)
    if intelligence is not None:
        from constants import CI_SWEEP_ANTIMATTER_COST, CI_SWEEP_CREDIT_COST
        from .intelligence import discovered_enemy_agent_hosts, owned_agent_hosts

        available_agents = int(getattr(intelligence, "available_agents", 0))
        operational = not bool(getattr(intelligence, "is_destroyed", False))
        enemy_colonies = [
            body.id
            for body in exact_bodies
            if is_colonizable_body(body)
            and relation(player, getattr(body, "owner", None)) == "enemy"
        ]
        options["infiltrate_unit"] = {"target_ids": [candidate.id for candidate in enemy_units]}
        options["infiltrate_planet"] = {"target_ids": enemy_colonies}
        if operational and available_agents > 0 and options["infiltrate_unit"]["target_ids"]:
            legal.add("infiltrate_unit")
        if operational and available_agents > 0 and enemy_colonies:
            legal.add("infiltrate_planet")

        capacity = int(getattr(intelligence, "agents_capacity", 0))
        extractable = [agent.id for agent, _ in owned_agent_hosts(game.galaxy, player)]
        options["extract_agent"] = {"agent_ids": sorted(extractable)}
        if (
            extractable
            and available_agents < capacity
            and operational
        ):
            legal.add("extract_agent")

        if getattr(intelligence, "has_counter_intelligence", False):
            storage = getattr(unit, "antimatter_component", None)
            ready = (
                not getattr(intelligence, "is_destroyed", False)
                and int(getattr(intelligence, "ci_cooldown_remaining", 0)) <= 0
                and float(getattr(player, "credits", 0)) >= CI_SWEEP_CREDIT_COST
                and storage is not None
                and not getattr(storage, "is_destroyed", False)
                and float(getattr(storage, "current_amount", 0)) >= CI_SWEEP_ANTIMATTER_COST
            )
            options["ci_sweep"] = {
                "available": ready,
                "range": float(getattr(intelligence, "counter_intelligence_range", 500.0)),
                "credit_cost": CI_SWEEP_CREDIT_COST,
                "antimatter_cost": CI_SWEEP_ANTIMATTER_COST,
                "cooldown_remaining": int(getattr(intelligence, "ci_cooldown_remaining", 0)),
            }
            if ready:
                legal.add("ci_sweep")
            discovered = [
                agent.id
                for agent, _ in discovered_enemy_agent_hosts(game.galaxy, player)
            ]
            options["eliminate_agent"] = {"agent_ids": sorted(discovered)}
            if discovered and operational:
                legal.add("eliminate_agent")

    target_options = {
        "attack": [candidate.id for candidate in enemy_units if not callable(getattr(getattr(unit, "weapons_component", None), "eligible_turrets_for", None)) or unit.weapons_component.eligible_turrets_for(candidate)],
        "attack_long_range": [candidate.id for candidate in enemy_units
                              if getattr(unit, "weapons_component", None)
                              and unit.weapons_component.eligible_turrets_for(candidate, long_range_only=True)],
        "protect": [candidate.id for candidate in friendly_units],
        "repair": [candidate.id for candidate in friendly_units],
        "unload_resources": [
            candidate.id
            for candidate in friendly_units
            if getattr(candidate, "metal_refinery_component", None)
            or getattr(candidate, "crystal_refinery_component", None)
        ],
        "dock_in_hangar": [
            candidate.id
            for candidate in friendly_units
            if candidate is not unit
            and compatible_hangar_component(unit, candidate) is not None
        ],
        "dock_in_strikecraft_bay": [
            candidate.id
            for candidate in friendly_units
            if candidate is not unit
            and compatible_strikecraft_bay_component(unit, candidate) is not None
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
    from antimatter_logistics import exchange_blocker, continuous_route_blocker
    fuel_targets = [candidate for candidate in friendly_units if exchange_blocker(unit, candidate, game.galaxy) is None]
    target_options['transfer_antimatter'] = [candidate.id for candidate in fuel_targets if unit.antimatter_component.current_amount > 0 and candidate.antimatter_component.current_amount < candidate.antimatter_component.max_capacity]
    target_options['take_antimatter'] = [candidate.id for candidate in fuel_targets if candidate.antimatter_component.current_amount > 0]
    if getattr(unit, 'antimatter_component', None) and unit.antimatter_component.current_amount >= unit.antimatter_component.max_capacity:
        target_options['take_antimatter'] = []
    if 'continuous_antimatter_transport' in supported:
        sources = [candidate.id for candidate in fuel_targets
                   if continuous_route_blocker(unit, candidate, None, game.galaxy) is None]
        options['continuous_antimatter_transport'] = {'source_ids': sources, 'target_ids': [candidate.id for candidate in fuel_targets], 'distinct_endpoints': True, 'automatic_return_reserve': True, 'destination_modes': ['automatic', 'manual'], 'automatic_when_target_null': True, 'automatic_recipient_scope': 'owned_galaxy_wide'}
        if sources:
            legal.add('continuous_antimatter_transport')
    for command_type, target_ids in target_options.items():
        if command_type in supported:
            options[command_type] = {"target_ids": target_ids}
            if target_ids:
                legal.add(command_type)

    # Empty/full tanks can still plan a pickup followed by delivery, or the
    # reverse. Keep conditional target choices separate from standalone ones.
    for kind, prior in (('transfer_antimatter', 'take_antimatter'),
                        ('take_antimatter', 'transfer_antimatter')):
        if kind in supported and kind not in legal and prior in legal:
            choices = [candidate.id for candidate in fuel_targets if (
                candidate.antimatter_component.current_amount > 0 if kind == 'take_antimatter'
                else candidate.antimatter_component.current_amount < candidate.antimatter_component.max_capacity)]
            if choices:
                options[kind]['queued_target_ids'] = choices
                conditional.append({'type': kind, 'requires_prior_command': prior,
                                    'same_unit': True, 'queue': True})

    for kind in ("attack", "attack_long_range"):
        if kind in options:
            options[kind]["target_components"] = {str(candidate.id): public_target_components(candidate) for candidate in enemy_units if candidate.id in options[kind]["target_ids"]}

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

    if "continuous_resupply" in supported:
        from constants import ANTIMATTER_HARVESTER_RETURN_THRESHOLD
        stars = [body.id for body in exact_bodies if is_antimatter_source(body)
                 and continuous_route_blocker(unit, body, None, game.galaxy, harvesting=True) is None]
        options["continuous_resupply"] = {"source_ids": stars, "target_ids": [candidate.id for candidate in fuel_targets], "destination_modes": ["automatic", "manual"], "automatic_when_target_null": True, "automatic_recipient_scope": "owned_galaxy_wide", "return_reserve": ANTIMATTER_HARVESTER_RETURN_THRESHOLD}
        if stars:
            legal.add("continuous_resupply")

    if "enter_gas_giant" in supported:
        conditional.append({"type": "leave_gas_giant", "requires_prior_command": "enter_gas_giant",
                            "same_unit": True, "queue": True})
        from constants import PlanetType
        gas_giants = [
            body.id
            for body in exact_bodies
            if getattr(body, "planet_type", None) == PlanetType.GAS_GIANT
        ]
        options["enter_gas_giant"] = {"target_ids": gas_giants}
        if gas_giants and has_operational_engines(unit):
            legal.add("enter_gas_giant")

    bay = getattr(unit, "strikecraft_bay_component", None)
    if bay is not None:
        from unit_catalog import wing_template_names
        from construction_customization import TURRET_TYPES, DEFENSE_TYPES
        editable = [i for i in range(bay.max_slots) if bay.production_blocker(i) is None]
        choices = list(wing_template_names()) if editable else []
        options["set_wing_production"] = {
            "slot_indices": editable, "can_clear": bool(editable),
            "template_names": choices,
            "turret_type_override": [None, *TURRET_TYPES],
            "defense_type_override": [None, *DEFENSE_TYPES],
        }
        if choices:
            legal.add("set_wing_production")

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
        from domain.celestials import is_position_in_magnetic_storm, is_position_blocked_by_celestial_field
        from constants import HullSize
        galaxy_ref = getattr(getattr(unit, "game", None), "galaxy", None)
        in_mag_storm = is_position_in_magnetic_storm(galaxy_ref, unit.in_system, unit.in_hex, unit.position)
        docked = []
        for component_name in ("hangar_component", "strikecraft_bay_component"):
            component = getattr(unit, component_name, None)
            for du in (getattr(component, "docked_units", []) or []):
                from strikecraft_abilities import round_now
                wing_comp = getattr(du, 'strikecraft_wing_component', None)
                if wing_comp and wing_comp.recovery_ready_round > round_now(galaxy_ref):
                    continue
                if in_mag_storm and getattr(du, "hull_size", None) == HullSize.STRIKECRAFT_WING:
                    continue
                if is_position_blocked_by_celestial_field(galaxy_ref, unit.in_system, unit.in_hex, unit.position, du):
                    continue
                docked.append(du)
        target_ids = sorted({docked_unit.id for docked_unit in docked})
        options["deploy_unit"] = {"target_ids": target_ids}
        if target_ids:
            legal.add("deploy_unit")
    if "deploy_all_wings" in supported:
        from domain.celestials import is_position_in_magnetic_storm
        galaxy_ref = getattr(getattr(unit, "game", None), "galaxy", None)
        in_mag_storm = is_position_in_magnetic_storm(galaxy_ref, unit.in_system, unit.in_hex, unit.position)
        bay = getattr(unit, "strikecraft_bay_component", None)
        from strikecraft_abilities import round_now
        if getattr(bay, "docked_units", None) and not in_mag_storm and any(
                not w.strikecraft_wing_component or w.strikecraft_wing_component.recovery_ready_round <= round_now(galaxy_ref) for w in bay.docked_units):
            legal.add("deploy_all_wings")

    if "use_ability" in supported:
        ready_states = [state for state in ability_states(unit) if state["ready"] and state.get('activation_mode') != 'toggle']
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

    if 'toggle_ability' in supported:
        from environmental_resistance import instances, availability
        choices = {kind: {'active': inst.is_active, 'resulting_state': not inst.is_active,
                         'unavailable_reason': availability(unit, kind, not inst.is_active)}
                   for kind, inst in instances(unit).items()}
        values = [kind for kind, detail in choices.items() if detail['unavailable_reason'] is None]
        options['toggle_ability'] = {'values': values, 'abilities': choices}
        if values:
            legal.add('toggle_ability')

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

    from .tactical import guidance
    guidance(game, player, unit, legal, options, visible_units, exact_bodies)
    legal = {kind for kind in legal if not capability_blocker(unit, kind)}
    conditional = [entry for entry in conditional if not capability_blocker(unit, entry["type"])]
    cloak = getattr(unit, "cloaking_component", None)
    if cloak is not None:
        active = bool(getattr(cloak, "is_active", False))
        options["toggle_cloaking"] = {"current_state": "active" if active else "inactive", "resulting_state": "inactive" if active else "active", "available": not capability_blocker(unit, "toggle_cloaking")}
    from wormhole_stabilization import command_options as stabilizer_options
    stabilization = stabilizer_options(game, player, unit, exact_bodies)
    if stabilization is not None:
        options["stabilize_wormhole"] = stabilization
        if any(item["blocker"] is None for item in stabilization["targets"]):
            legal.add("stabilize_wormhole")
    from planetary_warfare import command_options
    planetary = command_options(game, player, unit, exact_bodies)
    options.update(planetary)
    legal.update(kind for kind, values in planetary.items() if any(v["blocker"] is None for v in values["targets"]))
    if getattr(unit, "troop_transport_component", None):
        conditional.append({"type": "invade_planet", "requires_prior_command": "recruit_troops", "same_unit": True, "queue": True})
    from dismantling import evaluate, offline
    from campaign_graph import iter_units
    if 'dismantle_unit' in supported:
        targets = []
        for target, _ in iter_units(game.galaxy):
            if target is unit or target.owner != player:
                continue
            preview = evaluate(unit, target, game.galaxy)
            targets.append(dict(target_id=target.id, **preview.public()))
        options['dismantle_unit'] = {'targets': targets}
        if any(item['blocker'] is None for item in targets):
            legal.add('dismantle_unit')
    if 'set_wing_production_enabled' in supported:
        options['set_wing_production_enabled'] = {'enabled': unit.strikecraft_bay_component.production_enabled}
        if not capability_blocker(unit, 'set_wing_production_enabled'):
            legal.add('set_wing_production_enabled')
    if offline(unit):
        legal &= {'rename_unit', 'cancel_orders', 'clear_explicit_orders', 'cancel_order'}
        conditional = []
    return sorted(legal), options, conditional


def ability_states(unit: Any) -> list[dict[str, Any]]:
    from tactical_abilities import SPECS
    component = getattr(unit, "ability_component", None)
    result = []
    for ability_type, instance in getattr(component, "abilities", {}).items():
        definition = getattr(instance, "definition", None)
        ready = bool(getattr(instance, "is_ready", False))
        if ability_type.value not in SPECS and getattr(definition, 'activation_mode', 'cast') != 'toggle':
            ready = component.can_use(ability_type)
        result.append(
            {
                "ability": _enum_value(ability_type),
                "required_location_fields": ["system_name", "hex_coord", "position"] if getattr(definition, "requires_target_position", False) else [],
                "ready": ready,
                "requires_target_unit": bool(
                    getattr(definition, "requires_target_unit", False)
                ),
                "requires_target_position": bool(
                    getattr(definition, "requires_target_position", False)
                ),
            }
        )
    from .tactical import enrich_states
    from environmental_resistance import SPECS as RESISTANCES, availability, details
    for state in result:
        kind = state['ability']
        if kind in RESISTANCES:
            instance = component.abilities[next(key for key in component.abilities if key.value == kind)]
            blocker = availability(unit, kind, not instance.is_active)
            state.update(details(kind), active=instance.is_active, ready=blocker is None,
                         unavailable_reason=blocker, activation_antimatter=0)
    return enrich_states(unit, result)


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
