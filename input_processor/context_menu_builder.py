"""Dynamic right-click context menu options and submenus construction."""
import typing
import logging
from geometry import Position
from utils import HexCoord
from entities import (
    GameObject, Unit, Star, Planet, Moon, ColonizableAsteroid,
    MetalAsteroid, Comet, Wormhole, AsteroidField
)
from unit_components import HyperdriveType

logger = logging.getLogger(__name__)


def _are_allies(p1: typing.Optional[typing.Any], p2: typing.Optional[typing.Any]) -> bool:
    if p1 is None or p2 is None:
        return False
    if p1 is p2:
        return True
    from entities import Player
    if isinstance(p1, Player):
        return p1.is_allied_with(p2)
    if isinstance(p2, Player):
        return p2.is_allied_with(p1)
    p1_id = getattr(p1, 'id', None)
    p2_id = getattr(p2, 'id', None)
    if isinstance(p1_id, (int, str)) and isinstance(p2_id, (int, str)) and p1_id == p2_id:
        return True
    team1 = getattr(p1, 'team_id', None)
    team2 = getattr(p2, 'team_id', None)
    if isinstance(team1, (int, str)) and isinstance(team2, (int, str)):
        return team1 == team2
    return p1 == p2


def _are_enemies(p1: typing.Optional[typing.Any], p2: typing.Optional[typing.Any]) -> bool:
    if p1 is None or p2 is None:
        return False
    from entities import Player
    if isinstance(p1, Player):
        return p1.is_enemy_of(p2)
    if isinstance(p2, Player):
        return p2.is_enemy_of(p1)
    return not _are_allies(p1, p2)


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

    options.append(("View Hex Details", "view_hex"))
    hex_obj = current_system.hexes.get(target_hex_coord)
    if hex_obj:
        if hex_obj.celestial_bodies or hex_obj.units:
            options.append(("Scan Hex Contents", "scan_hex"))
        planet = next((b for b in hex_obj.celestial_bodies if isinstance(b, Planet)), None)
        if planet:
            options.append(("View Planet", "view_planet"))
        wormhole = next((b for b in hex_obj.celestial_bodies if isinstance(b, Wormhole)), None)
        if wormhole:
            options.append(("View Wormhole Info", "view_wormhole"))

    actors = game.selected_objects
    if any(isinstance(actor, Unit) for actor in actors):
        for actor in actors:
            if isinstance(actor, Unit) and actor.hyperdrive_component is not None:
                if target_hex_coord in current_system.hexes and (actor.in_system != current_system.name or actor.in_hex != target_hex_coord):
                    options.append(("Jump Into This Sector", "jump_interhex"))
                    break

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
    if not _are_allies(target_unit.owner, actors[0].owner):
        return []

    from custom_unit_templates import HULL_RESTRICTIONS, COMPONENT_COST_PER_HULL_POINT
    from unit_orders.refit import get_hull_restriction_flag
    from unit_components import Commander, HangarComponent, StrikecraftBayComponent
    from gui.retrofit_gui.catalog import RETROFIT_COMPONENTS

    refit_options = []
    remove_options = []

    forbidden_flags = HULL_RESTRICTIONS.get(target_unit.hull_size, set())
    remaining_cap = target_unit.hull_capacity - target_unit.current_hull_usage

    can_add = False
    if remaining_cap > 0:
        for comp_meta in RETROFIT_COMPONENTS:
            comp_key = comp_meta["comp_key"]
            comp_cls = comp_meta["comp_cls"]
            if comp_cls in target_unit.components:
                continue
            flag_key = get_hull_restriction_flag(comp_key)
            if flag_key in forbidden_flags:
                continue
            if comp_key == "TradeComponent" and not getattr(target_unit, 'engines_component', None):
                continue
            can_add = True
            break

    if can_add:
        refit_options.append(("Add Component", "open_retrofit_wizard"))

    for comp_cls, comp_inst in target_unit.components.items():
        if comp_cls == Commander:
            continue
        if isinstance(comp_inst, (HangarComponent, StrikecraftBayComponent)) and comp_inst.docked_units:
            continue
        salvage_refund = int(round(comp_inst.hull_cost * COMPONENT_COST_PER_HULL_POINT * 0.5))
        remove_options.append((f"{comp_inst.DISPLAY_NAME} (+{salvage_refund}c / -{comp_inst.hull_cost:.0f}h)", f"refit_remove_{comp_cls.__name__}"))

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

    actors = [a for a in game.selected_objects if isinstance(a, Unit)]
    current_player = (
        game.players[game.current_player_index]
        if getattr(game, 'players', None) and 0 <= getattr(game, 'current_player_index', 0) < len(game.players)
        else getattr(game, 'current_player', None)
    )

    if any(actors):
        if target_coords is not None:
            if any(a.engines_component and a.engines_component.is_operational for a in actors):
                options.append(("Move Here", "issue_move_order"))
                options.append(("Patrol Here", "issue_patrol_order"))

            ability_options = get_ability_context_options(game, actors, target_is_unit=False)
            if ability_options:
                options.append(("Use Ability", ability_options))

            for actor in actors:
                if actor.constructor_component:
                    build_options = []
                    for buildable in actor.constructor_component.buildable_units:
                        from unit_templates import UNIT_TEMPLATES
                        template = UNIT_TEMPLATES.get(buildable.unit_template_name, {})
                        display_name = template.get("name", buildable.unit_template_name)
                        cost = buildable.cost_credits
                        build_options.append((f"{display_name} ({cost}c)", f"construct_{buildable.unit_template_name}"))
                    if build_options:
                        options.append(("Construct", build_options))
                    break  # Only need to check one constructor unit

        elif target_object is not None:
            if isinstance(target_object, Unit):
                is_enemy_target = any(target_object.owner and _are_enemies(a.owner, target_object.owner) for a in actors)
                is_friendly_target = any(target_object.owner and _are_allies(a.owner, target_object.owner) for a in actors)

                if is_enemy_target:
                    if any(a.weapons_component for a in actors):
                        options.append(("Attack Hull", "attack_unit"))
                        if target_object.engines_component:
                            options.append(("Attack Engines", "attack_unit_Engines"))
                        if target_object.hyperdrive_component:
                            options.append(("Attack Hyperdrive", "attack_unit_Hyperdrive"))
                        if target_object.weapons_component:
                            options.append(("Attack Weapons", "attack_unit_Weapons"))
                        if target_object.inhibitor_component:
                            options.append(("Attack Inhibitor", "attack_unit_HyperspaceInhibitionFieldEmitter"))
                        # Note: Covert components (e.g. IntelligenceComponent) are hidden from enemy attack menus

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
                                        if dest_u.id != target_object.id and dest_u.owner and _are_enemies(current_player, dest_u.owner):
                                            relocate_options.append((f"To {dest_u.name}", f"relocate_{agent.id}_unit_{dest_u.id}"))
                                    for dest_b in hex_obj.celestial_bodies:
                                        if getattr(dest_b, 'owner', None) and _are_enemies(current_player, dest_b.owner):
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

                    has_antimatter_to_give = any(
                        a.antimatter_component and a.antimatter_component.current_amount > 0
                        for a in actors if a is not target_object
                    )
                    target_am_comp = getattr(target_object, 'antimatter_component', None)
                    target_has_space = target_am_comp is not None and target_am_comp.current_amount < target_am_comp.max_capacity
                    if has_antimatter_to_give and target_has_space:
                        options.append(("Transfer Antimatter", "transfer_antimatter"))

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
                if any(a.hyperdrive_component and a.hyperdrive_component.drive_type == HyperdriveType.ADVANCED and a.in_system == target_object.in_system for a in actors):
                    options.append(("Jump Wormhole", "jump_wormhole"))

    if target_object is not None:
        if isinstance(target_object, (Planet, Moon, ColonizableAsteroid, MetalAsteroid, AsteroidField, Comet)):
            if isinstance(target_object, Planet):
                options.append(("View Planet", "view_planet"))
            if len(game.selected_objects) == 1 and isinstance(game.selected_objects[0], Unit):
                unit = game.selected_objects[0]
                if isinstance(target_object, (Planet, Moon, ColonizableAsteroid)):
                    if unit.colony_component and unit.colony_component.population_cargo > 0 and not target_object.owner:
                        options.append(("Colonize", "colonize"))
                    if unit.colony_component and target_object.owner and _are_allies(unit.owner, target_object.owner) and hasattr(target_object, 'population') and target_object.population > 0 and unit.colony_component.population_cargo < unit.colony_component.max_cargo:
                        options.append(("Load Colonists", "load_colonists"))
            if isinstance(target_object, (Planet, Moon, ColonizableAsteroid)):
                if target_object.owner and _are_enemies(current_player, target_object.owner):
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
                                        if dest_u.owner and _are_enemies(current_player, dest_u.owner):
                                            relocate_options.append((f"To {dest_u.name}", f"relocate_{agent.id}_unit_{dest_u.id}"))
                                    for dest_b in hex_obj.celestial_bodies:
                                        if dest_b.id != target_object.id and getattr(dest_b, 'owner', None) and _are_enemies(current_player, dest_b.owner):
                                            relocate_options.append((f"To {dest_b.name}", f"relocate_{agent.id}_planet_{dest_b.id}"))
                            if relocate_options:
                                options.append(("Relocate Agent", relocate_options))

                            options.append(("Extract Agent", f"extract_agent_{agent.id}"))
                elif target_object.owner and _are_allies(current_player, target_object.owner):
                    has_ci_actors = any(getattr(a, 'intelligence_component', None) and a.intelligence_component.has_counter_intelligence for a in actors)
                    if has_ci_actors:
                        if hasattr(target_object, 'infiltrating_agents'):
                            for ag in target_object.infiltrating_agents:
                                if ag.is_discovered and ag.owner and _are_enemies(current_player, ag.owner):
                                    options.append((f"Eliminate Enemy Agent ({ag.owner.name})", f"eliminate_agent_{ag.id}"))

            if isinstance(target_object, (MetalAsteroid, AsteroidField, Comet)) and any(getattr(a, 'mining_component', None) for a in actors):
                options.append(("Mine", "mine"))
                options.append(("Mine (continuously)", "continuous_mine"))
        elif isinstance(target_object, Wormhole):
            options.append(("View Wormhole Info", "view_wormhole"))
        elif isinstance(target_object, Unit):
            options.append(("View Unit Info", "view_unit"))
        elif isinstance(target_object, Star):
            options.append(("View Star", "view_star"))
            if any(getattr(a, 'harvester_component', None) for a in actors):
                options.append(("Resupply (continuously)", "continuous_resupply"))

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
