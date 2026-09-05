"""Context menu action execution and game event bus dispatch."""
import typing
import logging
import pygame
from geometry import Position
from entities import Unit, Planet, Moon, ColonizableAsteroid, MetalAsteroid, Comet, Wormhole, AsteroidField
from events import (
    CancelOrdersEvent, IssueMoveOrderEvent, IssuePatrolOrderEvent, JumpInterhexEvent, JumpWormholeEvent,
    AttackUnitEvent, ColonizeEvent, LoadColonistsEvent, ConstructEvent, RepairUnitEvent,
    MineEvent, UnloadResourcesEvent, DockEvent, UseAbilityEvent, IssueProtectOrderEvent,
    ContinuousMineEvent, TransferAntimatterEvent, ContinuousResupplyEvent, LayMinefieldEvent,
    RefitUnitEvent, TradeEvent, ContinuousTradeEvent,
    InfiltrateUnitEvent, InfiltratePlanetEvent, RelocateAgentEvent,
    SabotageEvent, CISweepEvent, EliminateAgentEvent, ExtractAgentEvent,
    EnterGasGiantEvent, LeaveGasGiantEvent
)

logger = logging.getLogger(__name__)


def _get_shift_pressed() -> bool:
    try:
        return bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)
    except Exception:
        return False


def handle_context_menu_action(game, action_id: str, target: typing.Any) -> None:
    """Executes the action selected by the user from a right-click context menu.

    Args:
        game: Target Game instance.
        action_id (str): Identifier of the chosen menu command (e.g., 'move', 'attack', 'patrol').
        target (typing.Any): Target object or coordinate associated with the context menu.
    """
    current_player = game.players[game.current_player_index]
    shift_pressed = _get_shift_pressed()

    selected_units = [obj for obj in game.selected_objects if isinstance(obj, Unit) and obj.owner == current_player]

    logger.debug(f"Context Action: '{action_id}', Target: {target}, Actors: {[u.name for u in selected_units]}, SHIFT: {shift_pressed}")

    # Robustly extract action_id if it is nested (from context menu with sub-options)
    extracted_action_id = action_id
    while isinstance(extracted_action_id, list) and len(extracted_action_id) > 0:
        extracted_action_id = extracted_action_id[0]
    if isinstance(extracted_action_id, tuple) and len(extracted_action_id) > 1:
        extracted_action_id = extracted_action_id[1]
    elif isinstance(extracted_action_id, tuple):
        extracted_action_id = extracted_action_id[0]
    if not isinstance(extracted_action_id, str):
        extracted_action_id = str(extracted_action_id)

    if extracted_action_id == "view_hex":
        logger.debug("  Action: View Hex Details (Not Implemented)")
    elif extracted_action_id == "view_planet":
        logger.debug(f"  Action: View Planet {getattr(target, 'name', target)} Info (Not Implemented)")
    elif extracted_action_id == "view_star":
        logger.debug(f"  Action: View Star {getattr(target, 'name', target)} Info (Not Implemented)")
    elif extracted_action_id == "view_wormhole":
        logger.debug(f"  Action: View Wormhole {getattr(target, 'name', target)} Info (Not Implemented)")
    elif extracted_action_id == "view_unit":
        logger.debug(f"  Action: View Unit {getattr(target, 'name', target)} Info (Not Implemented)")
    elif extracted_action_id == "scan_hex":
        logger.debug("  Action: Scan Hex Contents (Not Implemented)")
    elif extracted_action_id == "leave_gas_giant_all":
        if isinstance(target, Planet):
            units = [u for u in getattr(target, 'hidden_units', []) if u.owner == current_player]
            if units:
                game.event_bus.publish(LeaveGasGiantEvent(
                    units=units,
                    shift_pressed=shift_pressed
                ))
                game.sidebar_needs_update = True
    elif extracted_action_id.startswith("leave_gas_giant_"):
        unit_id_str = extracted_action_id[len("leave_gas_giant_"):]
        try:
            unit_id = int(unit_id_str)
            unit = game.galaxy.get_unit_by_id(unit_id) if getattr(game, 'galaxy', None) else None
            if unit and unit.owner == current_player:
                game.event_bus.publish(LeaveGasGiantEvent(
                    units=[unit],
                    shift_pressed=shift_pressed
                ))
                game.sidebar_needs_update = True
        except ValueError:
            pass

    elif selected_units:
        disabled_units = [u for u in selected_units if u.is_disabled]
        if disabled_units and extracted_action_id not in ("cancel_orders", "view_unit", "view_hex", "view_planet", "view_star", "view_wormhole"):
            if game.gui:
                unit_names = ", ".join(u.name for u in disabled_units)
                game.gui.show_warning_dialog(
                    f"Unit(s) <b>{unit_names}</b> are disabled by Ion/EMP attack and cannot execute orders.",
                    title="Units Disabled"
                )

        if extracted_action_id == "cancel_orders":
            game.event_bus.publish(CancelOrdersEvent(selected_units))

        elif extracted_action_id == "issue_move_order":
            if isinstance(target, Position):
                game.event_bus.publish(IssueMoveOrderEvent(
                    selected_units,
                    game.current_system_name,
                    game.current_sector_coord,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id == "issue_patrol_order":
            if isinstance(target, Position):
                game.event_bus.publish(IssuePatrolOrderEvent(
                    selected_units,
                    game.current_system_name,
                    game.current_sector_coord,
                    target,
                    shift_pressed=shift_pressed,
                    add_waypoint=False
                ))

        elif extracted_action_id == "add_patrol_waypoint":
            if isinstance(target, Position):
                game.event_bus.publish(IssuePatrolOrderEvent(
                    selected_units,
                    game.current_system_name,
                    game.current_sector_coord,
                    target,
                    shift_pressed=False,
                    add_waypoint=True
                ))

        elif extracted_action_id == "jump_interhex":
            if isinstance(target, tuple) and len(target) == 2:
                game.event_bus.publish(JumpInterhexEvent(
                    selected_units,
                    game.current_system_name,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id == "jump_wormhole":
            if isinstance(target, Wormhole):
                game.event_bus.publish(JumpWormholeEvent(
                    selected_units,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id.startswith("attack_unit"):
            if isinstance(target, Unit):
                parts = extracted_action_id.split("_", 2)
                target_component_type_str = parts[2] if len(parts) == 3 else None
                if target_component_type_str:
                    from component_visibility import public_target_components
                    if target_component_type_str not in public_target_components(target):
                        return
                game.event_bus.publish(AttackUnitEvent(
                    selected_units,
                    target,
                    shift_pressed,
                    target_component_type_str
                ))

        elif extracted_action_id == "colonize":
            if isinstance(target, (Planet, Moon, ColonizableAsteroid)):
                game.event_bus.publish(ColonizeEvent(
                    selected_units,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id == "load_colonists":
            if isinstance(target, (Planet, Moon, ColonizableAsteroid)):
                amount_to_load = 25
                game.event_bus.publish(LoadColonistsEvent(
                    selected_units,
                    target,
                    amount_to_load,
                    shift_pressed
                ))

        elif extracted_action_id == "repair_unit":
            if isinstance(target, Unit):
                game.event_bus.publish(RepairUnitEvent(
                    selected_units,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id == "transfer_antimatter":
            if isinstance(target, Unit):
                game.event_bus.publish(TransferAntimatterEvent(
                    selected_units,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id == "protect_unit":
            if isinstance(target, Unit):
                game.event_bus.publish(IssueProtectOrderEvent(
                    selected_units,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id in ("dock_at_carrier", "dock_in_hangar", "dock_in_strikecraft_bay"):
            if isinstance(target, Unit):
                if extracted_action_id == "dock_in_hangar":
                    dockable_units = [u for u in selected_units if getattr(target, 'hangar_component', None) and target.hangar_component.can_dock(u)]
                    units_to_dock = dockable_units if dockable_units else selected_units
                elif extracted_action_id == "dock_in_strikecraft_bay":
                    dockable_units = [u for u in selected_units if getattr(target, 'strikecraft_bay_component', None) and target.strikecraft_bay_component.can_dock(u)]
                    units_to_dock = dockable_units if dockable_units else selected_units
                else:
                    units_to_dock = selected_units

                game.event_bus.publish(DockEvent(
                    units_to_dock,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id == "mine":
            if isinstance(target, (MetalAsteroid, AsteroidField, Comet)):
                game.event_bus.publish(MineEvent(
                    selected_units,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id == "continuous_mine":
            if isinstance(target, (MetalAsteroid, AsteroidField, Comet)):
                game.event_bus.publish(ContinuousMineEvent(
                    selected_units,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id == "continuous_resupply":
            from entities import Star as StarEntity
            if isinstance(target, StarEntity):
                game.event_bus.publish(ContinuousResupplyEvent(
                    selected_units,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id == "unload_resources":
            if isinstance(target, Unit):
                game.event_bus.publish(UnloadResourcesEvent(
                    selected_units,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id in ("lay_minefield", "lay_minefield_anti_ship", "lay_minefield_anti_strikecraft"):
            mtype = "anti_strikecraft" if extracted_action_id == "lay_minefield_anti_strikecraft" else "anti_ship"
            game.event_bus.publish(LayMinefieldEvent(
                selected_units,
                minefield_type=mtype,
                shift_pressed=shift_pressed
            ))

        elif extracted_action_id == "trade":
            if isinstance(target, Unit):
                game.event_bus.publish(TradeEvent(
                    selected_units,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id == "continuous_trade":
            if isinstance(target, Unit):
                game.event_bus.publish(ContinuousTradeEvent(
                    selected_units,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id.startswith("construct_"):
            unit_template_name = extracted_action_id.split("construct_")[1]
            if isinstance(target, Position):
                game.event_bus.publish(ConstructEvent(
                    selected_units,
                    unit_template_name,
                    target,
                    shift_pressed
                ))

        elif extracted_action_id == "open_retrofit_wizard":
            if isinstance(target, Unit):
                if getattr(game, 'gui', None) and hasattr(game.gui, 'show_retrofit_wizard'):
                    game.gui.show_retrofit_wizard(
                        target_unit=target,
                        constructor_units=selected_units,
                        shift_pressed=shift_pressed
                    )

        elif extracted_action_id.startswith("refit_add_"):
            comp_name = extracted_action_id[len("refit_add_"):]
            if isinstance(target, Unit):
                if getattr(game, 'gui', None) and hasattr(game.gui, 'show_retrofit_wizard'):
                    game.gui.show_retrofit_wizard(
                        target_unit=target,
                        component_type=comp_name,
                        constructor_units=selected_units,
                        shift_pressed=shift_pressed
                    )
                else:
                    game.event_bus.publish(RefitUnitEvent(
                        selected_units,
                        target_unit=target,
                        action="ADD",
                        component_type=comp_name,
                        shift_pressed=shift_pressed
                    ))

        elif extracted_action_id.startswith("refit_remove_"):
            comp_name = extracted_action_id[len("refit_remove_"):]
            if isinstance(target, Unit):
                game.event_bus.publish(RefitUnitEvent(
                    selected_units,
                    target_unit=target,
                    action="REMOVE",
                    component_type=comp_name,
                    shift_pressed=shift_pressed
                ))

        elif extracted_action_id.startswith("use_ability_"):
            ability_type_str = extracted_action_id[len("use_ability_"):]
            target_unit = target if isinstance(target, Unit) else None
            target_position = target if isinstance(target, Position) else None
            game.event_bus.publish(UseAbilityEvent(
                units=selected_units,
                ability_type_str=ability_type_str,
                target_unit=target_unit,
                target_position=target_position,
                target_system_name=game.current_system_name,
                target_hex_coord=game.current_sector_coord,
                shift_pressed=shift_pressed,
            ))

        elif extracted_action_id == "infiltrate_unit":
            if isinstance(target, Unit):
                game.event_bus.publish(InfiltrateUnitEvent(
                    units=selected_units,
                    target_unit=target,
                    shift_pressed=shift_pressed,
                ))

        elif extracted_action_id == "infiltrate_planet":
            if isinstance(target, (Planet, Moon, ColonizableAsteroid)):
                game.event_bus.publish(InfiltratePlanetEvent(
                    units=selected_units,
                    target_body=target,
                    target_system=game.current_system_name,
                    target_hex=game.current_sector_coord,
                    shift_pressed=shift_pressed,
                ))

        elif extracted_action_id == "ci_sweep":
            game.event_bus.publish(CISweepEvent(
                units=selected_units,
                shift_pressed=shift_pressed,
            ))

        elif extracted_action_id.startswith("sabotage_"):
            parts = extracted_action_id.split("_")
            if len(parts) >= 3:
                agent_id = int(parts[1])
                sab_type = "_".join(parts[2:])
                game.event_bus.publish(SabotageEvent(
                    units=selected_units,
                    agent_id=agent_id,
                    sabotage_type=sab_type,
                    shift_pressed=shift_pressed,
                ))

        elif extracted_action_id.startswith("relocate_"):
            parts = extracted_action_id.split("_")
            if len(parts) >= 4:
                agent_id = int(parts[1])
                target_type = parts[2]  # "unit" or "planet"
                dest_id = int(parts[3])
                game.event_bus.publish(RelocateAgentEvent(
                    units=selected_units,
                    agent_id=agent_id,
                    target_type=target_type,
                    destination_id=dest_id,
                    shift_pressed=shift_pressed,
                ))

        elif extracted_action_id.startswith("eliminate_agent_"):
            agent_id = int(extracted_action_id[len("eliminate_agent_"):])
            game.event_bus.publish(EliminateAgentEvent(
                units=selected_units,
                agent_id=agent_id,
                shift_pressed=shift_pressed,
            ))

        elif extracted_action_id.startswith("extract_agent_"):
            agent_id = int(extracted_action_id[len("extract_agent_"):])
            game.event_bus.publish(ExtractAgentEvent(
                units=selected_units,
                agent_id=agent_id,
                shift_pressed=shift_pressed,
            ))

        elif extracted_action_id == "enter_gas_giant":
            if isinstance(target, Planet):
                game.event_bus.publish(EnterGasGiantEvent(
                    units=selected_units,
                    gas_giant=target,
                    shift_pressed=shift_pressed,
                ))

        else:
            logger.debug(f"  Unknown context action ID or no valid unit selected: {extracted_action_id}")

        game.sidebar_needs_update = True
    else:
        logger.debug(f"  Unknown context action ID or no valid unit selected: {extracted_action_id}")
