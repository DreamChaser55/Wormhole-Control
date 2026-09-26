"""Dynamic right-click context menu options and submenus construction."""
import typing
import logging
from geometry import Position
from domain.coordinates import HexCoord
from domain.players import are_allies, are_enemies
from domain.identity import GameObject
from domain.units import Unit
from domain.celestials import Star, Planet, Moon, ColonizableAsteroid, MetalAsteroid, Comet, Wormhole, AsteroidField, Nebula
from constants import NebulaType, PlanetType
from unit_components.enums import HyperdriveType
from unit_orders.base import OrderType
from strikecraft_service import required as service_required

logger = logging.getLogger(__name__)


def build_system_context_menu_options(game, target_hex_coord: HexCoord) -> typing.List[typing.Tuple[str, str]]:
    """Builds context menu options for a right-clicked hex coordinate in system view.

    Args:
        game: Target Game instance.
        target_hex_coord (HexCoord): Target axial hex coordinate.

    Returns:
        list of (display_label, action_id) tuples.
    """
    options = []
    current_system = game.galaxy.systems.get(game.current_system_name)
    if not current_system:
        return options


    actors = [a for a in game.selected_objects if not service_required(a)]
    if any(isinstance(actor, Unit) for actor in actors):
        for actor in actors:
            if isinstance(actor, Unit) and actor.hyperdrive_component is not None:
                if target_hex_coord in current_system.hexes and (actor.in_system != current_system.name or actor.in_hex != target_hex_coord):
                    options.append(("Jump Into This Sector", "jump_interhex"))
                    break

    player = game.players[game.current_player_index]
    owned = [u for u in actors if isinstance(u, Unit) and u.owner == player]
    if len(owned) == 1 and owned[0].wormhole_stabilizer_component:
        from wormhole_stabilization import blocker
        for body in getattr(current_system.hexes.get(target_hex_coord), 'celestial_bodies', ()):
            if isinstance(body, Wormhole) and blocker(game, player, owned[0], body) is None:
                options.append((f"Stabilize Wormhole to {body.exit_system_name}", f"stabilize_wormhole_{body.id}"))
    return options


def get_refit_context_options(game, actors: typing.List[Unit], target_unit: Unit) -> typing.List[typing.Tuple[str, typing.Any]]:
    """Builds context menu options for adding/removing components from a friendly target unit.

    Args:
        game: Target Game instance.
        actors (list[Unit]): Selected constructor units.
        target_unit (Unit): Target friendly unit to refit.

    Returns:
        list: Refit option entries.
    """
    if not any(getattr(a, 'constructor_component', None) for a in actors):
        return []
    if not are_allies(target_unit.owner, actors[0].owner):
        return []

    from unit_components.commander import Commander
    from unit_components.hangar import HangarComponent
    from unit_components.strikecraft import StrikecraftBayComponent
    from gui.retrofit_gui.catalog import RETROFIT_COMPONENTS

    refit_options = []
    remove_options = []

    from refit_validation import eligible_component, evaluate_refit
    can_add = any(eligible_component(target_unit, meta['comp_key']) for meta in RETROFIT_COMPONENTS)

    if can_add:
        refit_options.append(("Add Component", "open_retrofit_wizard"))

    for comp_cls, comp_inst in target_unit.components.items():
        if comp_cls == Commander:
            continue
        if isinstance(comp_inst, (HangarComponent, StrikecraftBayComponent)) and comp_inst.docked_units:
            continue
        evaluation = evaluate_refit(target_unit, 'REMOVE', comp_cls.__name__)
        if evaluation.errors:
            continue
        salvage = evaluation.resource_salvage
        remove_options.append((f"{comp_inst.DISPLAY_NAME} (+{salvage.credits:g}c / {salvage.metal:g} metal / {salvage.crystal:g} crystal)", f"refit_remove_{comp_cls.__name__}"))

    if remove_options:
        refit_options.append(("Remove Component", remove_options))

    return refit_options


def get_ability_context_options(game, actors: typing.List[Unit], target_is_unit: bool) -> typing.List[typing.Tuple[str, str]]:
    """Retrieves available unit special abilities applicable to a right-click context target.

    Args:
        game: Target Game instance.
        actors (list[Unit]): Selected units attempting to perform an ability.
        target_is_unit (bool): True if target is another unit, False if target is a position.

    Returns:
        list of (action_id, display_label) tuples for valid abilities.
    """
    current_player = (
        game.players[game.current_player_index]
        if getattr(game, 'players', None) and 0 <= getattr(game, 'current_player_index', 0) < len(game.players)
        else getattr(game, 'current_player', None)
    )
    player_actors = [a for a in actors if a.owner == current_player]
    if not player_actors:
        return []

    ability_map = {}
    for actor in player_actors:
        if not actor.ability_component or actor.ability_component.is_destroyed:
            continue
        for atype, instance in actor.ability_component.abilities.items():
            defn = instance.definition
            is_relevant = defn.requires_target_unit if target_is_unit else defn.requires_target_position

            if is_relevant:
                ability_map.setdefault(atype, []).append((actor, instance))

    if not ability_map:
        return []

    submenu_options = []
    for atype in sorted(ability_map.keys(), key=lambda t: t.value):
        actor_instances = ability_map[atype]
        defn = actor_instances[0][1].definition

        if len(actor_instances) == 1:
            actor, instance = actor_instances[0]
            am_comp = actor.antimatter_component
            has_enough_am = am_comp.current_amount >= defn.antimatter_cost if am_comp else True

            if instance.is_active:
                status = f"Active ({instance.duration_remaining}t)"
            elif instance.cooldown_remaining > 0:
                status = f"Cooldown: {instance.cooldown_remaining}t"
            elif not has_enough_am:
                status = f"Low AM ({int(am_comp.current_amount)}/{defn.antimatter_cost})"
            else:
                status = "Ready"

            label = f"{defn.name} ({status})"
        else:
            ready_count = 0
            total_count = len(actor_instances)
            for actor, instance in actor_instances:
                am_comp = actor.antimatter_component
                has_enough_am = am_comp.current_amount >= defn.antimatter_cost if am_comp else True
                if instance.is_ready and has_enough_am:
                    ready_count += 1
            label = f"{defn.name} ({ready_count}/{total_count} Ready)"

        action_id = f"use_ability_{atype.value}"
        submenu_options.append((label, action_id))

    return submenu_options


def build_sector_context_menu_options(game, clicked_object, clicked_sector_coord: Position) -> typing.Tuple[typing.List[typing.Tuple[str, typing.Any]], typing.Any]:
    """Constructs context menu options for a right-click interaction in sector view.

    Args:
        game: Target Game instance.
        clicked_object: Object clicked under the cursor (or None).
        clicked_sector_coord (Position): Logical coordinates clicked in sector.

    Returns:
        tuple of (options_list, target_object_or_coords).
    """
    target = clicked_object if clicked_object else clicked_sector_coord
    options = []
    target_object = target if isinstance(target, GameObject) else None
    target_coords = target if isinstance(target, Position) else None

    actors = [a for a in game.selected_objects if isinstance(a, Unit) and not service_required(a)]
    current_player = (
        game.players[game.current_player_index]
        if getattr(game, 'players', None) and 0 <= getattr(game, 'current_player_index', 0) < len(game.players)
        else getattr(game, 'current_player', None)
    )

    from domain.deployables import Deployable
    from domain.construction_job import ConstructionJob
    if isinstance(target, ConstructionJob):
        if target.owner == current_player:
            options.append(("Select Builder", "select_constructor_unit"))
            options.append(("Cancel Construction", "cancel_construction_job"))
        if any(actors) and any(a.engines_component and a.engines_component.is_operational for a in actors):
            options.append(("Move Here", "issue_move_order"))
        return options, target
    if isinstance(target_object, Deployable):
        if game.is_unit_visible(target_object):
            if any(a.owner == current_player and a.weapons_component and are_enemies(a.owner, target_object.owner) for a in actors):
                options.append(('Attack deployable', 'tactical_attack'))
            if any(a.owner == current_player and not a.is_disabled and not a.is_hidden_in_gas_giant
                   and are_enemies(a.owner, target_object.owner) and a.weapons_component
                   and a.weapons_component.eligible_turrets_for(target_object, long_range_only=True) for a in actors):
                options.append(('Attack (long-range only)', 'attack_long_range'))
        return options, target
    if any(actors):
        if target_coords is not None:
            if any(a.engines_component and a.engines_component.is_operational for a in actors):
                options.append(("Move Here", "issue_move_order"))
                has_patrol = any(
                    (getattr(a, 'commander_component', None) and (
                        (a.commander_component.current_order and a.commander_component.current_order.order_type == OrderType.PATROL) or
                        any(o.order_type == OrderType.PATROL for o in a.commander_component.orders_queue)
                    ))
                    for a in actors
                )
                if has_patrol:
                    options.append(("Add Patrol Waypoint", "add_patrol_waypoint"))
                options.append(("Patrol Here", "issue_patrol_order"))

            ability_options = get_ability_context_options(game, actors, target_is_unit=False)
            if ability_options:
                options.append(("Use Ability", ability_options))

            for actor in actors:
                if actor.constructor_component:
                    options.append(("Construct...", "open_unit_catalog"))
                    break  # Only need to check one constructor unit

        elif target_object is not None:
            if isinstance(target_object, Unit):
                is_enemy_target = any(target_object.owner and are_enemies(a.owner, target_object.owner) for a in actors)
                is_friendly_target = any(target_object.owner and are_allies(a.owner, target_object.owner) for a in actors)

                if is_enemy_target:
                    if any(a.weapons_component for a in actors):
                        options.append(("Attack Hull", "attack_unit"))
                        from component_visibility import public_components
                        for component in public_components(target_object, enemy=True):
                            component_type = type(component).__name__
                            label = getattr(component, "DISPLAY_NAME", component_type)
                            options.append((f"Attack {label} (50% range)", f"attack_unit_{component_type}"))

                    if game.is_unit_visible(target_object) and any(
                            a.owner == current_player and not a.is_disabled and not a.is_hidden_in_gas_giant
                            and a.weapons_component
                            and a.weapons_component.eligible_turrets_for(target_object, long_range_only=True)
                            for a in actors):
                        from component_visibility import public_components
                        ranged_options = [("Hull", "attack_long_range")]
                        for component in public_components(target_object, enemy=True):
                            component_type = type(component).__name__
                            label = getattr(component, "DISPLAY_NAME", component_type)
                            ranged_options.append((f"{label} (50% range)", f"attack_long_range_{component_type}"))
                        options.append(("Attack (long-range only)", ranged_options))

                    has_intel_actors = any(getattr(a, 'intelligence_component', None) and a.intelligence_component.available_agents > 0 for a in actors)
                    if has_intel_actors:
                        options.append(("Infiltrate Unit", "infiltrate_unit"))

                    if hasattr(target_object, 'has_infiltrating_agent_from') and target_object.has_infiltrating_agent_from(current_player):
                        agent = next((ag for ag in getattr(target_object, 'infiltrating_agents', []) if ag.owner == current_player), None)
                        if agent:
                            sab_options = [
                                ("Sabotage Engines (-50% Speed)", f"sabotage_{agent.id}_ENGINES"),
                                ("Sabotage Weapons (-50% Damage)", f"sabotage_{agent.id}_WEAPONS"),
                                ("Sabotage Defenses (-50% Mitigation)", f"sabotage_{agent.id}_DEFENSES"),
                                ("Sabotage Hyperdrive (+3 Recharge Turns)", f"sabotage_{agent.id}_HYPERDRIVE"),
                                ("Sabotage Sensors (-50% Short, 0 Long)", f"sabotage_{agent.id}_SENSORS"),
                                ("Sabotage Antimatter (-50% Stored AM)", f"sabotage_{agent.id}_ANTIMATTER"),
                            ]
                            options.append(("Sabotage Systems", sab_options))

                            # Relocate options
                            relocate_options = []
                            cur_sys = game.galaxy.systems.get(game.current_system_name)
                            if cur_sys:
                                hex_obj = cur_sys.hexes.get(game.current_sector_coord)
                                if hex_obj:
                                    for dest_u in hex_obj.units:
                                        if dest_u.id != target_object.id and dest_u.owner and are_enemies(current_player, dest_u.owner):
                                            relocate_options.append((f"To {dest_u.name}", f"relocate_{agent.id}_unit_{dest_u.id}"))
                                    for dest_b in hex_obj.celestial_bodies:
                                        if getattr(dest_b, 'owner', None) and are_enemies(current_player, dest_b.owner):
                                            relocate_options.append((f"To {dest_b.name}", f"relocate_{agent.id}_planet_{dest_b.id}"))
                            if relocate_options:
                                options.append(("Relocate Agent", relocate_options))

                            options.append(("Extract Agent", f"extract_agent_{agent.id}"))

                elif is_friendly_target and target_object not in actors:
                    options.append(("Protect", "protect_unit"))
                    target_is_damaged = (
                        target_object.current_hit_points < target_object.max_hit_points or
                        any(c.current_hit_points < c.max_hit_points for c in target_object.components.values())
                    )
                    if target_is_damaged and any(a.repair_component for a in actors):
                        options.append(("Repair", "repair_unit"))

                    from antimatter_logistics import exchange_blocker
                    fuel_actors = [a for a in actors if exchange_blocker(a, target_object, game.galaxy) is None]
                    if fuel_actors:
                        options.append(("Transfer Antimatter", "transfer_antimatter"))
                    if fuel_actors:
                        options.append(("Take Antimatter", "take_antimatter"))
                    if len(actors) == 1 and fuel_actors and fuel_actors[0].engines_component and fuel_actors[0].engines_component.is_operational:
                        options.append(("Continuous Antimatter Transport...", "continuous_antimatter_transport"))

                    is_metal_refinery = bool(getattr(target_object, 'metal_refinery_component', None))

                    is_crystal_refinery = bool(getattr(target_object, 'crystal_refinery_component', None))
                    has_correct_cargo_miners = any(
                        getattr(a, 'mining_component', None) and (
                            (is_metal_refinery and a.mining_component.raw_metal_cargo > 0) or
                            (is_crystal_refinery and a.mining_component.raw_crystal_cargo > 0)
                        ) for a in actors
                    )
                    if (is_metal_refinery or is_crystal_refinery) and has_correct_cargo_miners:
                        options.append(("Unload Resources", "unload_resources"))

                    can_dock_in_hangar = bool(
                        target_object.hangar_component and any(target_object.hangar_component.can_dock(a) for a in actors)
                    )
                    if can_dock_in_hangar:
                        options.append(("Dock in Hangar", "dock_in_hangar"))

                    can_dock_in_bay = bool(
                        target_object.strikecraft_bay_component and any(target_object.strikecraft_bay_component.can_dock(a) for a in actors)
                    )
                    if can_dock_in_bay:
                        options.append(("Dock in Strikecraft Bay", "dock_in_strikecraft_bay"))

                    if len(actors) == 1 and target_object.owner == actors[0].owner:
                        from dismantling import evaluate
                        if evaluate(actors[0], target_object, game.galaxy).blocker is None:
                            options.append(("Dismantle…", "dismantle_unit"))
                    refit_options = get_refit_context_options(game, actors, target_object)
                    if refit_options:
                        options.append(("Refit Unit", refit_options))

                    is_active_habitat = bool(
                        getattr(target_object, 'civilian_habitat_component', None) and
                        not target_object.civilian_habitat_component.is_destroyed and
                        target_object.civilian_habitat_component.is_active(game.galaxy)
                    )
                    has_traders = any(getattr(a, 'trade_component', None) for a in actors)
                    if is_active_habitat and has_traders:
                        options.append(("Trade", "trade"))
                        options.append(("Trade (continuously)", "continuous_trade"))

                    has_ci_actors = any(getattr(a, 'intelligence_component', None) and a.intelligence_component.has_counter_intelligence for a in actors)
                    if has_ci_actors:
                        if hasattr(target_object, 'infiltrating_agents'):
                            for ag in target_object.infiltrating_agents:
                                if ag.is_discovered and ag.owner and current_player.is_enemy_of(ag.owner):
                                    options.append((f"Eliminate Enemy Agent ({ag.owner.name})", f"eliminate_agent_{ag.id}"))

                ability_options = get_ability_context_options(game, actors, target_is_unit=True)
                if ability_options:
                    options.append(("Use Ability", ability_options))

            elif isinstance(target_object, Wormhole):
                from wormhole_stabilization import blocker
                owned = [a for a in actors if a.owner == current_player]
                if len(owned) == 1 and owned[0].wormhole_stabilizer_component and blocker(game, current_player, owned[0], target_object) is None:
                    options.append(("Stabilize Wormhole", "stabilize_wormhole"))
                if any(a.hyperdrive_component and a.hyperdrive_component.drive_type == HyperdriveType.ADVANCED and a.in_system == target_object.in_system for a in actors):
                    options.append(("Jump Wormhole", "jump_wormhole"))

    if target_object is not None:
        if isinstance(target_object, (Planet, Moon, ColonizableAsteroid, MetalAsteroid, AsteroidField, Comet)):
            if isinstance(target_object, Planet):
                if getattr(target_object, 'planet_type', None) == PlanetType.GAS_GIANT:
                    if any(a.owner == current_player and target_object.can_hide_unit(a) for a in actors):
                        options.append(("Hide in Gas Giant", "enter_gas_giant"))
                    friendly_hidden = [u for u in getattr(target_object, 'hidden_units', []) if u.owner == current_player]
                    if friendly_hidden:
                        if len(friendly_hidden) == 1:
                            options.append((f"Order {friendly_hidden[0].name} to Leave", f"leave_gas_giant_{friendly_hidden[0].id}"))
                        else:
                            leave_opts = [(f"Order {u.name} to Leave", f"leave_gas_giant_{u.id}") for u in friendly_hidden]
                            leave_opts.append(("Order All to Leave", "leave_gas_giant_all"))
                            options.append(("Leave Atmosphere", leave_opts))
            if len(game.selected_objects) == 1 and isinstance(game.selected_objects[0], Unit):
                unit = game.selected_objects[0]
                if isinstance(target_object, (Planet, Moon, ColonizableAsteroid)):
                    if getattr(target_object, 'is_colonizable', True):
                        if unit.owner == current_player:
                            from planetary_warfare import command_options
                            for kind, info in command_options(game, current_player, unit, [target_object]).items():
                                if info["targets"]:
                                    options.append(({"recruit_troops": "Recruit Troops...", "invade_planet": "Invade Colony...", "bombard_planet": "Bombard Defenses"}[kind], kind))
                        if unit.colony_component and unit.colony_component.population_cargo > 0 and not target_object.owner:
                            options.append(("Colonize", "colonize"))
                        if unit.colony_component and target_object.owner and are_allies(unit.owner, target_object.owner) and hasattr(target_object, 'population') and target_object.population > 0 and unit.colony_component.population_cargo < unit.colony_component.max_cargo:
                            options.append(("Load Colonists", "load_colonists"))
            if isinstance(target_object, (Planet, Moon, ColonizableAsteroid)):
                if target_object.owner and are_enemies(current_player, target_object.owner):
                    has_intel_actors = any(getattr(a, 'intelligence_component', None) and a.intelligence_component.available_agents > 0 for a in actors)
                    if has_intel_actors:
                        options.append(("Infiltrate Colony", "infiltrate_planet"))

                    if hasattr(target_object, 'has_infiltrating_agent_from') and target_object.has_infiltrating_agent_from(current_player):
                        agent = next((ag for ag in getattr(target_object, 'infiltrating_agents', []) if ag.owner == current_player), None)
                        if agent:
                            col_sab_options = [
                                ("Sabotage Economy (-50% Tax, +25% Siphon)", f"sabotage_{agent.id}_ECONOMY"),
                                ("Sabotage Growth (Halt Pop Growth)", f"sabotage_{agent.id}_GROWTH"),
                            ]
                            options.append(("Sabotage Colony", col_sab_options))

                            # Relocate options
                            relocate_options = []
                            cur_sys = game.galaxy.systems.get(game.current_system_name)
                            if cur_sys:
                                hex_obj = cur_sys.hexes.get(game.current_sector_coord)
                                if hex_obj:
                                    for dest_u in hex_obj.units:
                                        if dest_u.owner and are_enemies(current_player, dest_u.owner):
                                            relocate_options.append((f"To {dest_u.name}", f"relocate_{agent.id}_unit_{dest_u.id}"))
                                    for dest_b in hex_obj.celestial_bodies:
                                        if dest_b.id != target_object.id and getattr(dest_b, 'owner', None) and are_enemies(current_player, dest_b.owner):
                                            relocate_options.append((f"To {dest_b.name}", f"relocate_{agent.id}_planet_{dest_b.id}"))
                            if relocate_options:
                                options.append(("Relocate Agent", relocate_options))

                            options.append(("Extract Agent", f"extract_agent_{agent.id}"))
                elif target_object.owner and are_allies(current_player, target_object.owner):
                    has_ci_actors = any(getattr(a, 'intelligence_component', None) and a.intelligence_component.has_counter_intelligence for a in actors)
                    if has_ci_actors:
                        if hasattr(target_object, 'infiltrating_agents'):
                            for ag in target_object.infiltrating_agents:
                                if ag.is_discovered and ag.owner and are_enemies(current_player, ag.owner):
                                    options.append((f"Eliminate Enemy Agent ({ag.owner.name})", f"eliminate_agent_{ag.id}"))

            if isinstance(target_object, (MetalAsteroid, Comet)) and any(getattr(a, 'mining_component', None) for a in actors):
                options.append(("Mine", "mine"))
                options.append(("Mine (continuously)", "continuous_mine"))
        elif isinstance(target_object, Star):
            if any(getattr(a, 'harvester_component', None) for a in actors):
                options.append(("Resupply (continuously)...", "continuous_resupply"))
        elif isinstance(target_object, Nebula):
            if getattr(target_object, 'nebula_type', None) == NebulaType.HYDROGEN:
                if any(getattr(a, 'harvester_component', None) for a in actors):
                    options.append(("Resupply (continuously)...", "continuous_resupply"))

    return options, target


def build_sector_unit_disambiguation_menu(
    game,
    units: typing.List[Unit],
    clicked_sector_coord: Position
) -> typing.Tuple[typing.List[typing.Any], typing.Any]:
    """Constructs a disambiguation context menu listing multiple units under the cursor.

    Each option in the disambiguation menu represents a unit and navigates into that unit's
    specific context menu when selected.

    Args:
        game: Target Game instance.
        units (list[Unit]): List of units overlapping under the mouse cursor.
        clicked_sector_coord (Position): Logical sector coordinates of the click.

    Returns:
        tuple: (options_list, target).
    """
    options = []
    for unit in units:
        unit_options, _ = build_sector_context_menu_options(game, unit, clicked_sector_coord)
        owner_str = f" ({unit.owner.name})" if getattr(unit, 'owner', None) and getattr(unit.owner, 'name', None) else ""
        label = f"{unit.name}{owner_str}"
        options.append((label, (unit_options, unit)))

    return options, units
