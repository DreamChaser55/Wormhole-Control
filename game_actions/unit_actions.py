"""GUI action handlers for unit commands, stances, abilities, and carrier wing deployment."""
import logging
import pygame
import typing

from entities import Unit
from events import CancelOrdersEvent, LayMinefieldEvent, UseAbilityEvent
from geometry import distance, hex_distance
from pathfinding import find_intersystem_path
from unit_components import UnitStance, WingType
from unit_orders import DeployAllWingsOrder, DeployUnitOrder, DockOrder, UnloadResourcesOrder, ToggleInhibitorOrder

logger = logging.getLogger(__name__)



def handle_deploy_ship(game, action: dict) -> None:
    carrier_id = action.get('carrier_id')
    docked_unit_id = action.get('docked_unit_id')
    carrier = game.galaxy.get_unit_by_id(carrier_id) if game.galaxy else None
    if carrier and (carrier.hangar_component or carrier.strikecraft_bay_component):
        current_player = game.players[game.current_player_index] if game.players else None
        if carrier.owner == current_player:
            deploy_order = DeployUnitOrder(carrier, {"docked_unit_id": docked_unit_id})
            if carrier.commander_component:
                carrier.commander_component.add_order(deploy_order)
                logger.debug(f"Issued DEPLOY_UNIT order for carrier {carrier.name} (docked unit ID: {docked_unit_id}).")
    game.sidebar_needs_update = True


def handle_launch_all_wings(game, action: dict) -> None:
    carrier_id = action.get('carrier_id')
    carrier = game.galaxy.get_unit_by_id(carrier_id) if game.galaxy else None
    if carrier and carrier.strikecraft_bay_component:
        current_player = game.players[game.current_player_index] if game.players else None
        if carrier.owner == current_player:
            deploy_order = DeployAllWingsOrder(carrier)
            if carrier.commander_component:
                carrier.commander_component.add_order(deploy_order)
                logger.debug(f"Issued DEPLOY_ALL_WINGS order for carrier {carrier.name}.")
    game.sidebar_needs_update = True


def handle_recall_ship(game, action: dict) -> None:
    carrier_id = action.get('carrier_id')
    launched_unit_id = action.get('launched_unit_id')
    carrier = game.galaxy.get_unit_by_id(carrier_id) if game.galaxy else None
    launched_unit = game.galaxy.get_unit_by_id(launched_unit_id) if game.galaxy else None
    if carrier and launched_unit and carrier.strikecraft_bay_component:
        current_player = game.players[game.current_player_index] if game.players else None
        if carrier.owner == current_player:
            dock_order = DockOrder(launched_unit, {"target_carrier_id": carrier.id})
            if launched_unit.commander_component:
                launched_unit.commander_component.add_order(dock_order)
                logger.debug(f"Issued DOCK order for launched wing {launched_unit.name} to dock to carrier {carrier.name}.")
    game.sidebar_needs_update = True


def handle_toggle_build_wing_type(game, action: dict) -> None:
    carrier_id = action.get('carrier_id')
    carrier = game.galaxy.get_unit_by_id(carrier_id) if game.galaxy else None
    if carrier and carrier.strikecraft_bay_component:
        current_player = game.players[game.current_player_index] if game.players else None
        if carrier.owner == current_player:
            bay = carrier.strikecraft_bay_component
            if bay.build_wing_type == WingType.FIGHTER:
                bay.build_wing_type = WingType.BOMBER
            else:
                bay.build_wing_type = WingType.FIGHTER
            logger.debug(f"Carrier {carrier.name} build wing type toggled to {bay.build_wing_type.name}.")
    game.sidebar_needs_update = True


def _iter_friendly_refineries(galaxy, unit: Unit) -> list:
    """Helper to collect all friendly refineries across galaxy star systems."""
    friendly_refineries = []
    for system in galaxy.systems.values():
        for hex_obj in system.hexes.values():
            for u in hex_obj.units:
                if u.owner == unit.owner:
                    if getattr(u, 'metal_refinery_component', None) is not None or \
                       getattr(u, 'crystal_refinery_component', None) is not None:
                        friendly_refineries.append(u)
    return friendly_refineries


def _refinery_distance(galaxy, unit: Unit, refinery: Unit) -> float:
    """Helper to calculate sector/inter-system path distance from a unit to a refinery."""
    if unit.in_system == refinery.in_system:
        if unit.in_hex == refinery.in_hex:
            return distance(unit.position, refinery.position)
        else:
            return hex_distance(unit.in_hex, refinery.in_hex) * 10000.0
    else:
        path = find_intersystem_path(galaxy.system_graph, unit.in_system, refinery.in_system, unit.hull_size)
        if path is None:
            return float('inf')
        return (len(path) - 1) * 1000000.0 + hex_distance(unit.in_hex, refinery.in_hex) * 10000.0


def handle_unload_resources_nearest(game, action: dict) -> None:
    unit_id = action.get('unit_id')
    shift_pressed = action.get('shift_pressed', False)
    unit = game.galaxy.get_unit_by_id(unit_id) if game.galaxy else None
    if unit and getattr(unit, 'mining_component', None) is not None:
        mining_comp = unit.mining_component
        if mining_comp.raw_metal_cargo <= 0 and mining_comp.raw_crystal_cargo <= 0:
            if getattr(game, 'gui', None):
                game.gui.show_warning_dialog(
                    f"Unit <b>{unit.name}</b> has no raw metal or crystal cargo to unload.",
                    title="Cargo Empty"
                )
            game.sidebar_needs_update = True
            return

        friendly_refineries = _iter_friendly_refineries(game.galaxy, unit)

        nearest_metal = None
        min_metal_dist = float('inf')
        nearest_crystal = None
        min_crystal_dist = float('inf')

        for r in friendly_refineries:
            dist = _refinery_distance(game.galaxy, unit, r)
            if dist == float('inf'):
                continue
            if getattr(r, 'metal_refinery_component', None) is not None:
                if dist < min_metal_dist:
                    min_metal_dist = dist
                    nearest_metal = r
            if getattr(r, 'crystal_refinery_component', None) is not None:
                if dist < min_crystal_dist:
                    min_crystal_dist = dist
                    nearest_crystal = r

        orders_to_add = []
        if mining_comp.raw_metal_cargo > 0 and nearest_metal is not None:
            orders_to_add.append(UnloadResourcesOrder(unit, {"target_unit_id": nearest_metal.id}))
        if mining_comp.raw_crystal_cargo > 0 and nearest_crystal is not None:
            orders_to_add.append(UnloadResourcesOrder(unit, {"target_unit_id": nearest_crystal.id}))

        if orders_to_add:
            if not shift_pressed and unit.commander_component:
                unit.commander_component.clear_orders()
            for order in orders_to_add:
                if unit.commander_component:
                    unit.commander_component.add_order(order)
                    logger.debug(f"Added UnloadResourcesOrder to unit {unit.name} queue targeting refinery ID {order.parameters['target_unit_id']}.")
        else:
            if getattr(game, 'gui', None):
                game.gui.show_warning_dialog(
                    f"No friendly operational refineries found in range to receive cargo from <b>{unit.name}</b>.",
                    title="No Refinery Found"
                )
    game.sidebar_needs_update = True


def handle_lay_minefield(game, action: dict) -> None:
    action_type = action['action']
    unit_id = action.get('unit_id')
    shift_pressed = action.get('shift_pressed', False)
    mtype = action.get('minefield_type', 'anti_strikecraft' if action_type == 'lay_minefield_anti_strikecraft' else 'anti_ship')
    unit = game.galaxy.get_unit_by_id(unit_id) if game.galaxy else None
    if unit:
        game.event_bus.publish(LayMinefieldEvent(
            units=[unit],
            minefield_type=mtype,
            shift_pressed=shift_pressed
        ))
        logger.debug(f"GUI: Lay Minefield ({mtype}) button pressed for unit {unit.name} (id:{unit.id}).")
    game.sidebar_needs_update = True


def handle_set_stance(game, action: dict) -> None:
    unit_id = action.get('unit_id')
    stance_display_name = action.get('stance_display_name')
    unit = game.galaxy.get_unit_by_id(unit_id) if game.galaxy else None
    current_player = game.players[game.current_player_index] if game.players else None
    if unit and unit.commander_component and stance_display_name:
        if unit.owner == current_player:
            matching_stance = None
            for stance in UnitStance:
                if stance.display_name == stance_display_name:
                    matching_stance = stance
                    break
            if matching_stance is not None:
                allowed_stances = unit.commander_component.get_allowed_stances()
                if matching_stance in allowed_stances:
                    unit.commander_component.stance = matching_stance
                    logger.debug(f"Unit {unit.name} (id:{unit.id}) stance set to {matching_stance.name}.")
                else:
                    logger.warning(f"Unit {unit.name} (id:{unit.id}) stance {matching_stance.name} is not allowed.")
                    if game.gui:
                        game.gui.show_warning_dialog(
                            f"Stance '{matching_stance.display_name}' is not allowed for unit '{unit.name}'.",
                            title="Invalid Stance"
                        )
            else:
                logger.debug(f"Stance not found for display name: {stance_display_name}")
    game.sidebar_needs_update = True


def handle_cycle_stance(game, action: dict) -> None:
    unit_id = action.get('unit_id')
    unit = game.galaxy.get_unit_by_id(unit_id) if game.galaxy else None
    current_player = game.players[game.current_player_index] if game.players else None
    if unit and unit.commander_component:
        if unit.owner == current_player:
            allowed_stances = unit.commander_component.get_allowed_stances()
            if allowed_stances:
                current_stance = unit.commander_component.stance
                if current_stance not in allowed_stances:
                    current_stance = allowed_stances[0]
                current_idx = allowed_stances.index(current_stance)
                next_idx = (current_idx + 1) % len(allowed_stances)
                unit.commander_component.stance = allowed_stances[next_idx]
                logger.debug(f"Unit {unit.name} (id:{unit.id}) stance cycled to {unit.commander_component.stance.name}.")
    game.sidebar_needs_update = True


def handle_rename_unit(game, action: dict) -> None:
    new_name = action.get('new_name', '').strip()
    selected_units = [obj for obj in game.selected_objects if isinstance(obj, Unit)]
    current_player = game.players[game.current_player_index] if game.players else None
    if selected_units and isinstance(selected_units[0], Unit) and selected_units[0].owner == current_player:
        unit_to_rename = selected_units[0]
        if new_name and len(new_name) <= 30:
            logger.debug(f"Renaming unit '{unit_to_rename.name}' -> '{new_name}'")
            unit_to_rename.name = new_name
        else:
            logger.debug(f"Rename rejected (empty or too long: '{new_name}'). Keeping '{unit_to_rename.name}'.")
    game.sidebar_needs_update = True


def handle_use_ability(game, action: dict) -> None:
    ability_type_str = action.get('ability_type_str')
    requires_unit = action.get('requires_target_unit', False)
    requires_pos = action.get('requires_target_position', False)
    selected_units = [u for u in game.selected_objects if isinstance(u, Unit)]
    if selected_units and ability_type_str:
        keys = pygame.key.get_pressed()
        shift_pressed = bool(keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])

        if requires_unit or requires_pos:
            game.pending_ability = (ability_type_str, requires_unit, requires_pos)
            logger.debug(f"Ability {ability_type_str} awaiting target (unit={requires_unit}, pos={requires_pos}).")
        else:
            game.event_bus.publish(UseAbilityEvent(
                units=selected_units,
                ability_type_str=ability_type_str,
                shift_pressed=shift_pressed,
            ))
            logger.debug(f"Fired self-targeted ability {ability_type_str} for {len(selected_units)} unit(s) (shift={shift_pressed}).")
    game.sidebar_needs_update = True


def handle_stop_unit(game, action: dict) -> None:
    unit_id = action.get('unit_id')
    unit = game.galaxy.get_unit_by_id(unit_id) if (game.galaxy and unit_id is not None) else None
    current_player = game.players[game.current_player_index] if game.players else None
    if unit and unit.owner == current_player:
        game.event_bus.publish(CancelOrdersEvent([unit]))
    game.sidebar_needs_update = True


def handle_stop_selected_units(game, action: dict) -> None:
    current_player = game.players[game.current_player_index] if game.players else None
    units_to_stop = [
        u for u in game.selected_objects
        if isinstance(u, Unit) and u.owner == current_player and u.commander_component and u.commander_component.get_active_orders_count() > 0
    ]
    if units_to_stop:
        game.event_bus.publish(CancelOrdersEvent(units_to_stop))
    game.sidebar_needs_update = True


def handle_toggle_inhibitor(game, action: dict) -> None:
    """Toggles hyperspace inhibitor fields on all selected owned units.

    Args:
        game: Target game instance.
        action (dict): Action payload containing the 'shift_pressed' queueing flag.
    """
    shift_pressed = action.get('shift_pressed', False)
    for unit in game.selected_objects:
        if isinstance(unit, Unit) and unit.inhibitor_component:
            if shift_pressed:
                turn_on = not unit.inhibitor_component.is_active
                unit.commander_component.add_order(
                    ToggleInhibitorOrder(unit, {'turn_on': turn_on}))
                logger.debug(f"Queued TOGGLE_INHIBITOR order for {unit.name}.")
            else:
                success = unit.inhibitor_component.toggle(galaxy_ref=game.galaxy)
                if success:
                    logger.debug(f"Directly toggled inhibitor for {unit.name}.")
                else:
                    logger.debug(f"Direct inhibitor toggle failed for {unit.name}.")
                    if getattr(game, 'gui', None):
                        game.gui.show_warning_dialog(
                            f"Failed to toggle Hyperspace Inhibitor Field on unit <b>{unit.name}</b>.",
                            title="Toggle Failed"
                        )
    game.sidebar_needs_update = True


def handle_toggle_cloaking(game, action: dict) -> None:
    """Toggles cloaking device on all selected owned units.

    Args:
        game: Target game instance.
        action (dict): Action payload containing the 'shift_pressed' queueing flag.
    """
    for unit in game.selected_objects:
        if isinstance(unit, Unit) and unit.cloaking_component:
            success = unit.cloaking_component.toggle()
            if success:
                logger.debug(f"Directly toggled cloaking for {unit.name}.")
            else:
                logger.debug(f"Direct cloaking toggle failed for {unit.name}.")
                if getattr(game, 'gui', None):
                    game.gui.show_warning_dialog(
                        f"Failed to toggle Cloaking Device on unit <b>{unit.name}</b>.",
                        title="Toggle Failed"
                    )
    game.sidebar_needs_update = True


def handle_confirm_retrofit(game, action: dict) -> None:
    from events import RefitUnitEvent
    target_unit = action.get("target_unit")
    constructor_units = action.get("constructor_units") or []
    component_type = action.get("component_type")
    component_config = action.get("component_config") or {}
    cost_credits = action.get("cost_credits")
    time_to_build = action.get("time_to_build")
    shift_pressed = action.get("shift_pressed", False)

    if target_unit and constructor_units:
        game.event_bus.publish(RefitUnitEvent(
            units=constructor_units,
            target_unit=target_unit,
            action="ADD",
            component_type=component_type,
            component_config=component_config,
            cost_credits=cost_credits,
            time_to_build=time_to_build,
            shift_pressed=shift_pressed,
        ))
    game.sidebar_needs_update = True


def handle_ci_sweep(game, action: dict) -> None:
    """Dispatches a Counter-Intelligence sweep event for the target unit or selected units.

    Args:
        game: Target game instance.
        action (dict): Action payload containing 'unit_id' and optional 'shift_pressed'.
    """
    from events import CISweepEvent
    unit_id = action.get('unit_id')
    units = []
    if unit_id is not None:
        unit = game.galaxy.get_unit_by_id(unit_id) if game.galaxy else None
        if unit:
            units = [unit]
    else:
        units = [u for u in game.selected_objects if isinstance(u, Unit)]

    if units:
        game.event_bus.publish(CISweepEvent(
            units=units,
            shift_pressed=action.get('shift_pressed', False)
        ))
    game.sidebar_needs_update = True


HANDLERS: typing.Dict[str, typing.Callable[[typing.Any, dict], None]] = {
    'deploy_ship': handle_deploy_ship,
    'launch_all_wings': handle_launch_all_wings,
    'recall_ship': handle_recall_ship,
    'toggle_build_wing_type': handle_toggle_build_wing_type,
    'unload_resources_nearest': handle_unload_resources_nearest,
    'lay_minefield': handle_lay_minefield,
    'lay_minefield_anti_ship': handle_lay_minefield,
    'lay_minefield_anti_strikecraft': handle_lay_minefield,
    'set_stance': handle_set_stance,
    'cycle_stance': handle_cycle_stance,
    'rename_unit': handle_rename_unit,
    'use_ability': handle_use_ability,
    'stop_unit': handle_stop_unit,
    'stop_selected_units': handle_stop_selected_units,
    'toggle_inhibitor': handle_toggle_inhibitor,
    'toggle_cloaking': handle_toggle_cloaking,
    'confirm_retrofit': handle_confirm_retrofit,
    'ci_sweep': handle_ci_sweep,
}
