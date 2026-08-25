import logging
import typing
from events import (
    CancelOrdersEvent, IssueMoveOrderEvent, JumpInterhexEvent, JumpWormholeEvent,
    AttackUnitEvent, ColonizeEvent, LoadColonistsEvent, ConstructEvent, RepairUnitEvent,
    MineEvent, UnloadResourcesEvent, DockEvent, IssuePatrolOrderEvent, UseAbilityEvent,
    IssueProtectOrderEvent, ContinuousMineEvent, TransferAntimatterEvent, ContinuousResupplyEvent,
    LayMinefieldEvent, RefitUnitEvent, TradeEvent, ContinuousTradeEvent,
    InfiltrateUnitEvent, InfiltratePlanetEvent, RelocateAgentEvent,
    SabotageEvent, CISweepEvent, EliminateAgentEvent, ExtractAgentEvent
)
from unit_orders import (
    MoveOrder, AttackOrder, ColonizeOrder, LoadColonistsOrder, ConstructOrder, RepairOrder,
    MineOrder, UnloadResourcesOrder, DockOrder, PatrolOrder, UseAbilityOrder, ProtectOrder,
    ContinuousMineOrder, TransferAntimatterOrder, ContinuousResupplyOrder, LayMinefieldOrder,
    RefitOrder, TradeOrder, ContinuousTradeOrder, calculate_required_antimatter,
    InfiltrateUnitOrder, InfiltratePlanetOrder, RelocateAgentOrder, SabotageOrder,
    CISweepOrder, EliminateAgentOrder, ExtractAgentOrder
)

from sector_utils import random_point_in_sector
from constants import HullSize
from unit_orders import OrderType

logger = logging.getLogger(__name__)

class OrderSystem:
    """System that listens for order requests and creates/assigns orders to units."""
    def __init__(self, game_instance, event_bus):
        self.game = game_instance
        self.event_bus = event_bus
        self._subscribe_all()

    def _subscribe_all(self):
        self.event_bus.subscribe(CancelOrdersEvent, self.handle_cancel_orders)
        self.event_bus.subscribe(IssueMoveOrderEvent, self.handle_issue_move_order)
        self.event_bus.subscribe(IssuePatrolOrderEvent, self.handle_issue_patrol_order)
        self.event_bus.subscribe(JumpInterhexEvent, self.handle_jump_interhex)
        self.event_bus.subscribe(JumpWormholeEvent, self.handle_jump_wormhole)
        self.event_bus.subscribe(AttackUnitEvent, self.handle_attack_unit)
        self.event_bus.subscribe(ColonizeEvent, self.handle_colonize)
        self.event_bus.subscribe(LoadColonistsEvent, self.handle_load_colonists)
        self.event_bus.subscribe(ConstructEvent, self.handle_construct)
        self.event_bus.subscribe(RepairUnitEvent, self.handle_repair_unit)
        self.event_bus.subscribe(RefitUnitEvent, self.handle_refit_unit)
        self.event_bus.subscribe(MineEvent, self.handle_mine)
        self.event_bus.subscribe(ContinuousMineEvent, self.handle_continuous_mine)
        self.event_bus.subscribe(UnloadResourcesEvent, self.handle_unload_resources)
        self.event_bus.subscribe(DockEvent, self.handle_dock)
        self.event_bus.subscribe(UseAbilityEvent, self.handle_use_ability)
        self.event_bus.subscribe(IssueProtectOrderEvent, self.handle_issue_protect_order)
        self.event_bus.subscribe(TransferAntimatterEvent, self.handle_transfer_antimatter)
        self.event_bus.subscribe(ContinuousResupplyEvent, self.handle_continuous_resupply)
        self.event_bus.subscribe(LayMinefieldEvent, self.handle_lay_minefield)
        self.event_bus.subscribe(TradeEvent, self.handle_trade)
        self.event_bus.subscribe(ContinuousTradeEvent, self.handle_continuous_trade)
        self.event_bus.subscribe(InfiltrateUnitEvent, self.handle_infiltrate_unit)
        self.event_bus.subscribe(InfiltratePlanetEvent, self.handle_infiltrate_planet)
        self.event_bus.subscribe(RelocateAgentEvent, self.handle_relocate_agent)
        self.event_bus.subscribe(SabotageEvent, self.handle_sabotage)
        self.event_bus.subscribe(CISweepEvent, self.handle_ci_sweep)
        self.event_bus.subscribe(EliminateAgentEvent, self.handle_eliminate_agent)
        self.event_bus.subscribe(ExtractAgentEvent, self.handle_extract_agent)

    def validate_antimatter_for_unit(self, unit, dest_system, dest_hex, dest_pos=None) -> bool:
        galaxy_ref = getattr(self.game, 'galaxy', None)
        if not galaxy_ref:
            return True
        am_comp = getattr(unit, 'antimatter_component', None)
        if not am_comp:
            return True

        required_am = calculate_required_antimatter(unit, galaxy_ref, dest_system, dest_hex, dest_pos)
        if required_am > 0 and am_comp.current_amount < required_am:
            logger.warning(f"Insufficient antimatter for unit {unit.name}: required {required_am:.1f}, available {am_comp.current_amount:.1f}")
            if getattr(self.game, 'gui', None):
                self.game.gui.show_error_dialog(
                    f"Unit <b>{unit.name}</b> has insufficient antimatter reserves to complete the destination journey.<br><br>"
                    f"<b>Required:</b> {required_am:.1f} AM<br>"
                    f"<b>Current Reserves:</b> {am_comp.current_amount:.1f}/{am_comp.max_capacity:.1f} AM",
                    title="Insufficient Antimatter"
                )
            return False
        return True

    def handle_cancel_orders(self, event: CancelOrdersEvent):
        for unit in event.units:
            if unit.commander_component:
                unit.commander_component.clear_orders()
                logger.debug(f"  Unit {unit.name} orders cancelled via event.")
        self.game.sidebar_needs_update = True

    def handle_issue_move_order(self, event: IssueMoveOrderEvent):
        for unit in event.units:
            if not unit.engines_component:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> has no sub-light engines and cannot execute move orders.",
                        title="No Engines"
                    )
                continue
            # Jumping to a different sector or system requires a hyperdrive.
            needs_hyperdrive = (event.system_name != unit.in_system or event.sector_coord != unit.in_hex)
            if needs_hyperdrive and not unit.hyperdrive_component:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> has no hyperdrive module and cannot jump to a different sector.",
                        title="No Hyperdrive"
                    )
                continue
            if not self.validate_antimatter_for_unit(unit, event.system_name, event.sector_coord, event.destination):
                continue
            move_params = {
                "destination_system_name": event.system_name,
                "destination_hex_coord": event.sector_coord,
                "destination_position": event.destination
            }
            move_order = MoveOrder(unit, move_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
                logger.debug(f"  Unit {unit.name} orders cancelled.")
            unit.commander_component.add_order(move_order)
            logger.debug(f"  Unit {unit.name} ordered to move to {event.system_name}:{event.sector_coord}:{event.destination} via event.")
        self.game.sidebar_needs_update = True

    def handle_issue_patrol_order(self, event: IssuePatrolOrderEvent):
        for unit in event.units:
            if not unit.engines_component:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> has no sub-light engines and cannot execute patrol orders.",
                        title="No Engines"
                    )
                continue
            if not self.validate_antimatter_for_unit(unit, event.system_name, event.sector_coord, event.destination):
                continue
            existing_patrol = None
            if event.shift_pressed:
                if unit.commander_component.orders_queue:
                    last_order = unit.commander_component.orders_queue[-1]
                    if last_order.order_type == OrderType.PATROL:
                        existing_patrol = last_order
                elif unit.commander_component.current_order and unit.commander_component.current_order.order_type == OrderType.PATROL:
                    existing_patrol = unit.commander_component.current_order

            if existing_patrol:
                existing_patrol.add_waypoint(event.system_name, event.sector_coord, event.destination)
                logger.debug(f"  Added waypoint to existing patrol order for unit {unit.name}: {event.system_name}:{event.sector_coord}:{event.destination}")
            else:
                patrol_params = {
                    "destination_system_name": event.system_name,
                    "destination_hex_coord": event.sector_coord,
                    "destination_position": event.destination
                }
                patrol_order = PatrolOrder(unit, patrol_params)
                if not event.shift_pressed:
                    unit.commander_component.clear_orders()
                    logger.debug(f"  Unit {unit.name} orders cancelled.")
                unit.commander_component.add_order(patrol_order)
                logger.debug(f"  Unit {unit.name} ordered to patrol to {event.system_name}:{event.sector_coord}:{event.destination} via event.")
        self.game.sidebar_needs_update = True

    def handle_jump_interhex(self, event: JumpInterhexEvent):
        for unit in event.units:
            if not unit.hyperdrive_component:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> has no hyperdrive module and cannot perform hyperspace jumps.",
                        title="No Hyperdrive"
                    )
                continue
            if event.system_name != unit.in_system or event.target_hex != unit.in_hex:
                move_params = {
                    "destination_system_name": event.system_name,
                    "destination_hex_coord": event.target_hex,
                    "destination_position": random_point_in_sector()
                }
                if not self.validate_antimatter_for_unit(unit, event.system_name, event.target_hex, move_params["destination_position"]):
                    continue
                move_order = MoveOrder(unit, move_params)
                if not event.shift_pressed:
                    unit.commander_component.clear_orders()
                    logger.debug(f"  Unit {unit.name} orders cancelled.")
                unit.commander_component.add_order(move_order)
                logger.debug(f"  Unit {unit.name} ordered to move to {event.system_name}:{event.target_hex}:{move_params['destination_position']} via event.")
        self.game.sidebar_needs_update = True

    def handle_jump_wormhole(self, event: JumpWormholeEvent):
        target_wormhole = event.wormhole
        exit_wh_id = target_wormhole.exit_wormhole_id
        exit_system_name = target_wormhole.exit_system_name
        
        if not self.game.galaxy:
            return
            
        exit_wormhole = self.game.galaxy.wormholes.get(exit_wh_id, None)
        if not exit_wormhole:
            return

        for unit in event.units:
            if unit.hyperdrive_component:
                if (unit.in_system == target_wormhole.in_system and
                        target_wormhole.stability > 0 and
                        exit_system_name and
                        exit_wormhole.in_system == exit_system_name):
                    move_params = {
                        "destination_system_name": exit_system_name,
                        "destination_hex_coord": exit_wormhole.in_hex,
                        "destination_position": exit_wormhole.position 
                    }
                    if not self.validate_antimatter_for_unit(unit, exit_system_name, exit_wormhole.in_hex, exit_wormhole.position):
                        continue
                    move_order = MoveOrder(unit, move_params)
                    if not event.shift_pressed:
                        unit.commander_component.clear_orders()
                        logger.debug(f"  Unit {unit.name} orders cancelled.")
                    unit.commander_component.add_order(move_order)
                    logger.debug(f"  Unit {unit.name} ordered to move via wormhole {target_wormhole.name} to {exit_system_name}:{exit_wormhole.in_hex}:{exit_wormhole.position} via event.")
            else:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> has no hyperdrive module and cannot perform wormhole jumps.",
                        title="No Hyperdrive"
                    )
        self.game.sidebar_needs_update = True

    def handle_attack_unit(self, event: AttackUnitEvent):
        for unit in event.units:
            attack_params = {"target_unit_id": event.target_unit.id}
            if event.target_component_type_str:
                attack_params["target_component_type"] = event.target_component_type_str
            attack_order = AttackOrder(unit, attack_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(attack_order)
            logger.debug(f"  Unit {unit.name} ordered to attack {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_colonize(self, event: ColonizeEvent):
        for unit in event.units:
            col_comp = getattr(unit, 'colony_component', None)
            if not col_comp:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Colony Component and cannot colonize.",
                        title="Cannot Colonize"
                    )
                continue
            if col_comp.population_cargo <= 0:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> has no colonists in cargo to establish a colony on <b>{event.target_body.name}</b>.",
                        title="Cannot Colonize"
                    )
                continue
            colonize_params = {
                "target_id": event.target_body.id,
                "target_name": event.target_body.name
            }
            colonize_order = ColonizeOrder(unit, colonize_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(colonize_order)
            logger.debug(f"  Unit {unit.name} ordered to colonize {event.target_body.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_load_colonists(self, event: LoadColonistsEvent):
        for unit in event.units:
            if not getattr(unit, 'colony_component', None):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Colony Component and cannot load colonists.",
                        title="Cannot Load Colonists"
                    )
                continue
            load_params = {
                "target_id": event.target_body.id,
                "target_name": event.target_body.name,
                "amount": event.amount
            }
            load_order = LoadColonistsOrder(unit, load_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(load_order)
            logger.debug(f"  Unit {unit.name} ordered to load {event.amount} colonists from planet {event.target_body.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_construct(self, event: ConstructEvent):
        for unit in event.units:
            construct_params = {
                "unit_template_name": event.unit_template_name,
                "target_position": event.target_position
            }
            construct_order = ConstructOrder(unit, construct_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(construct_order)
            logger.debug(f"  Unit {unit.name} ordered to construct {event.unit_template_name} at {event.target_position} via event.")
        self.game.sidebar_needs_update = True

    def handle_repair_unit(self, event: RepairUnitEvent):
        for unit in event.units:
            if not getattr(unit, 'repair_component', None):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Repair Component and cannot repair units.",
                        title="No Repair Module"
                    )
                continue
            repair_params = {"target_unit_id": event.target_unit.id}
            repair_order = RepairOrder(unit, repair_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(repair_order)
            logger.debug(f"  Unit {unit.name} ordered to repair {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_refit_unit(self, event: RefitUnitEvent):
        for unit in event.units:
            if not getattr(unit, 'constructor_component', None):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Constructor Component and cannot refit units.",
                        title="No Constructor"
                    )
                continue
            refit_params = {
                "target_unit_id": event.target_unit.id,
                "action": event.action,
                "component_type": event.component_type,
                "component_config": event.component_config,
                "cost_credits": event.cost_credits,
                "time_to_build": event.time_to_build,
            }
            refit_order = RefitOrder(unit, refit_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(refit_order)
            logger.debug(f"  Unit {unit.name} ordered to refit {event.target_unit.name} ({event.action} {event.component_type}) via event.")
        self.game.sidebar_needs_update = True

    def handle_issue_protect_order(self, event: IssueProtectOrderEvent):
        for unit in event.units:
            protect_params = {"target_unit_id": event.target_unit.id}
            protect_order = ProtectOrder(unit, protect_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(protect_order)
            logger.debug(f"  Unit {unit.name} ordered to protect {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_mine(self, event: MineEvent):
        for unit in event.units:
            if not getattr(unit, 'mining_component', None):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Mining Component and cannot extract resources.",
                        title="No Mining Module"
                    )
                continue
            mine_params = {"target_id": event.target_body.id}
            mine_order = MineOrder(unit, mine_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(mine_order)
            logger.debug(f"  Unit {unit.name} ordered to mine {event.target_body.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_continuous_mine(self, event: ContinuousMineEvent):
        for unit in event.units:
            if not getattr(unit, 'mining_component', None):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Mining Component and cannot extract resources.",
                        title="No Mining Module"
                    )
                continue
            mine_params = {"target_id": event.target_body.id}
            continuous_mine_order = ContinuousMineOrder(unit, mine_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(continuous_mine_order)
            logger.debug(f"  Unit {unit.name} ordered to continuous mine {event.target_body.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_unload_resources(self, event: UnloadResourcesEvent):
        is_metal_refinery = bool(getattr(event.target_unit, 'metal_refinery_component', None))
        is_crystal_refinery = bool(getattr(event.target_unit, 'crystal_refinery_component', None))
        for unit in event.units:
            mining_comp = getattr(unit, 'mining_component', None)
            if not mining_comp:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Mining Component and cannot unload resources.",
                        title="No Mining Module"
                    )
                continue
            has_correct_cargo = (
                (is_metal_refinery and mining_comp.raw_metal_cargo > 0) or
                (is_crystal_refinery and mining_comp.raw_crystal_cargo > 0)
            )
            if not has_correct_cargo:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> does not have matching raw cargo to unload into <b>{event.target_unit.name}</b>.",
                        title="Incompatible Cargo"
                    )
                continue
            unload_params = {"target_unit_id": event.target_unit.id}
            unload_order = UnloadResourcesOrder(unit, unload_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(unload_order)
            logger.debug(f"  Unit {unit.name} ordered to unload resources to {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_dock(self, event: DockEvent):
        for unit in event.units:
            if unit.hull_size not in (HullSize.TINY, HullSize.SMALL):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> (Hull Size: {unit.hull_size.name}) cannot dock. Only Tiny and Small hull sizes are supported.",
                        title="Invalid Dock Target"
                    )
                continue
            dock_params = {"target_carrier_id": event.target_carrier.id}
            dock_order = DockOrder(unit, dock_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(dock_order)
            logger.debug(f"  Unit {unit.name} ordered to dock to {event.target_carrier.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_use_ability(self, event: UseAbilityEvent):
        for unit in event.units:
            if not unit.ability_component:
                continue
            ability_params = {
                "ability_type": event.ability_type_str,
            }
            if event.target_unit:
                ability_params["target_unit_id"] = event.target_unit.id
            if event.target_position:
                ability_params["target_position"] = event.target_position
                ability_params["target_system_name"] = getattr(event, "target_system_name", None)
                ability_params["target_hex_coord"] = getattr(event, "target_hex_coord", None)
            ability_order = UseAbilityOrder(unit, ability_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(ability_order)
            logger.debug(f"  Unit {unit.name} ordered to use ability {event.ability_type_str} via event.")
        self.game.sidebar_needs_update = True

    def handle_transfer_antimatter(self, event: TransferAntimatterEvent):
        """Creates TransferAntimatterOrders for selected units that have antimatter
        to give, sending it to the friendly target unit's storage."""
        for unit in event.units:
            am_comp = getattr(unit, 'antimatter_component', None)
            if am_comp and am_comp.current_amount > 0 and unit is not event.target_unit:
                transfer_params = {"target_unit_id": event.target_unit.id}
                transfer_order = TransferAntimatterOrder(unit, transfer_params)
                if not event.shift_pressed:
                    unit.commander_component.clear_orders()
                unit.commander_component.add_order(transfer_order)
                logger.debug(f"  Unit {unit.name} ordered to transfer antimatter to {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_continuous_resupply(self, event: ContinuousResupplyEvent):
        """Creates ContinuousResupplyOrders for selected units that have an
        AntimatterHarvester component, targeting the given star body."""
        for unit in event.units:
            if not getattr(unit, 'harvester_component', None):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks an Antimatter Harvester and cannot harvest antimatter from stars.",
                        title="No Harvester Module"
                    )
                continue
            resupply_params = {
                "target_id": event.target_body.id,
                "target_name": getattr(event.target_body, 'name', f"Star {event.target_body.id}"),
            }
            resupply_order = ContinuousResupplyOrder(unit, resupply_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(resupply_order)
            logger.debug(f"  Unit {unit.name} ordered to continuously resupply from star {event.target_body.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_lay_minefield(self, event: LayMinefieldEvent):
        """Creates LayMinefieldOrders for selected units with MinelayerComponent."""
        mtype = getattr(event, 'minefield_type', 'anti_ship')
        for unit in event.units:
            has_minelayer = getattr(unit, 'minelayer_component', None) is not None or (hasattr(unit, 'components') and any(c.__class__.__name__ == 'MinelayerComponent' for c in unit.components.values()))
            if not has_minelayer:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Minelayer Component and cannot deploy minefields.",
                        title="No Minelayer Module"
                    )
                continue
            lay_order = LayMinefieldOrder(unit, minefield_type=mtype)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(lay_order)
            logger.debug(f"  Unit {unit.name} ordered to lay {mtype} minefield via event.")
        self.game.sidebar_needs_update = True

    def handle_trade(self, event: TradeEvent):
        """Creates TradeOrders for selected units with TradeComponent, targeting an active Civilian Habitat."""
        for unit in event.units:
            if not getattr(unit, 'trade_component', None):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Trade Component and cannot engage in commerce.",
                        title="No Trade Module"
                    )
                continue
            trade_params = {"target_unit_id": event.target_unit.id}
            trade_order = TradeOrder(unit, trade_params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(trade_order)
            logger.debug(f"  Unit {unit.name} ordered to trade with {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_continuous_trade(self, event: ContinuousTradeEvent):
        """Creates ContinuousTradeOrders for selected units with TradeComponent."""
        for unit in event.units:
            if not getattr(unit, 'trade_component', None):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Trade Component and cannot engage in commerce.",
                        title="No Trade Module"
                    )
                continue
            continuous_trade_order = ContinuousTradeOrder(unit)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(continuous_trade_order)
            logger.debug(f"  Unit {unit.name} ordered to continuous trade via event.")
        self.game.sidebar_needs_update = True

    def handle_infiltrate_unit(self, event: InfiltrateUnitEvent):
        """Creates InfiltrateUnitOrders for selected units with IntelligenceComponent."""
        for unit in event.units:
            intel_comp = getattr(unit, 'intelligence_component', None)
            if not intel_comp:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks an Intelligence Suite and cannot deploy agents.",
                        title="No Intelligence Suite"
                    )
                continue
            if intel_comp.available_agents <= 0:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> has no remaining agents available to deploy.",
                        title="No Agents Available"
                    )
                continue
            order = InfiltrateUnitOrder(unit, {"target_unit_id": event.target_unit.id})
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(order)
            logger.debug(f"  Unit {unit.name} ordered to infiltrate {event.target_unit.name} via event.")

            # If already in range in the same sector, execute immediately to deploy agent in real time
            if getattr(self.game, 'galaxy', None) and unit.in_system == event.target_unit.in_system and unit.in_hex == event.target_unit.in_hex:
                from geometry import distance
                from unit_orders.intelligence import INTELLIGENCE_OPERATIONAL_RANGE
                if distance(unit.position, event.target_unit.position) <= INTELLIGENCE_OPERATIONAL_RANGE:
                    order.execute(self.game.galaxy)
                    self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True

    def handle_infiltrate_planet(self, event: InfiltratePlanetEvent):
        """Creates InfiltratePlanetOrders for selected units with IntelligenceComponent."""
        for unit in event.units:
            intel_comp = getattr(unit, 'intelligence_component', None)
            if not intel_comp:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks an Intelligence Suite and cannot deploy agents.",
                        title="No Intelligence Suite"
                    )
                continue
            if intel_comp.available_agents <= 0:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> has no remaining agents available to deploy.",
                        title="No Agents Available"
                    )
                continue
            params = {
                "target_body_id": getattr(event.target_body, 'id', None),
                "target_body_name": getattr(event.target_body, 'name', None),
                "system": event.target_system,
                "hex": event.target_hex,
            }
            order = InfiltratePlanetOrder(unit, params)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(order)
            logger.debug(f"  Unit {unit.name} ordered to infiltrate {getattr(event.target_body, 'name', 'colony')} via event.")

            # If already in range in the same sector, execute immediately to deploy agent in real time
            if getattr(self.game, 'galaxy', None) and unit.in_system == event.target_system and unit.in_hex == event.target_hex:
                from geometry import distance
                from unit_orders.intelligence import INTELLIGENCE_OPERATIONAL_RANGE
                if distance(unit.position, event.target_body.position) <= INTELLIGENCE_OPERATIONAL_RANGE:
                    order.execute(self.game.galaxy)
                    self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True

    def handle_relocate_agent(self, event: RelocateAgentEvent):
        """Dispatches RelocateAgentOrder directly or to the agent's controlling unit."""
        unit = event.units[0] if event.units else None
        if not unit and getattr(self.game, 'current_player', None):
            for u in self.game.current_player.units:
                if getattr(u, 'intelligence_component', None):
                    unit = u
                    break
        if unit and getattr(self.game, 'galaxy', None):
            order = RelocateAgentOrder(unit, {
                "agent_id": event.agent_id,
                "target_type": event.target_type,
                "destination_id": event.destination_id,
            })
            order.execute(self.game.galaxy)
            self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True

    def handle_sabotage(self, event: SabotageEvent):
        """Dispatches SabotageOrder for the specified agent."""
        unit = event.units[0] if event.units else None
        if not unit and getattr(self.game, 'current_player', None):
            for u in self.game.current_player.units:
                if getattr(u, 'intelligence_component', None):
                    unit = u
                    break
        if unit and getattr(self.game, 'galaxy', None):
            order = SabotageOrder(unit, {
                "agent_id": event.agent_id,
                "sabotage_type": event.sabotage_type,
            })
            order.execute(self.game.galaxy)
            self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True

    def handle_ci_sweep(self, event: CISweepEvent):
        """Dispatches CISweepOrder to selected Counter-Intelligence units."""
        from constants import CI_SWEEP_CREDIT_COST, CI_SWEEP_ANTIMATTER_COST
        for unit in event.units:
            intel_comp = getattr(unit, 'intelligence_component', None)
            if not intel_comp or not intel_comp.has_counter_intelligence:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Counter-Intelligence Suite.",
                        title="No Counter-Intelligence"
                    )
                continue

            if intel_comp.ci_cooldown_remaining > 0:
                if getattr(self.game, 'gui', None):
                    turns_label = f"{intel_comp.ci_cooldown_remaining} turn" if intel_comp.ci_cooldown_remaining == 1 else f"{intel_comp.ci_cooldown_remaining} turns"
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> Counter-Intelligence Suite is recharging ({turns_label} remaining).",
                        title="CI Sweep On Cooldown"
                    )
                continue

            if not unit.owner or getattr(unit.owner, 'credits', 0.0) < CI_SWEEP_CREDIT_COST:
                if getattr(self.game, 'gui', None):
                    avail = getattr(unit.owner, 'credits', 0.0) if unit.owner else 0.0
                    self.game.gui.show_warning_dialog(
                        f"Insufficient empire credits for Counter-Intelligence Sweep.<br>"
                        f"Requires <b>{int(CI_SWEEP_CREDIT_COST)}</b> credits (Treasury: <b>{int(avail)}</b>).",
                        title="Insufficient Credits"
                    )
                continue

            am_comp = getattr(unit, 'antimatter_component', None)
            if not am_comp or am_comp.is_destroyed or am_comp.current_amount < CI_SWEEP_ANTIMATTER_COST:
                if getattr(self.game, 'gui', None):
                    avail_am = am_comp.current_amount if am_comp else 0.0
                    self.game.gui.show_warning_dialog(
                        f"Insufficient antimatter on <b>{unit.name}</b> for Counter-Intelligence Sweep.<br>"
                        f"Requires <b>{int(CI_SWEEP_ANTIMATTER_COST)}</b> AM (Available: <b>{int(avail_am)}</b>).",
                        title="Insufficient Antimatter"
                    )
                continue

            order = CISweepOrder(unit)
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(order)
            logger.debug(f"  Unit {unit.name} ordered CI Sweep via event.")
            if getattr(self.game, 'galaxy', None):
                order.execute(self.game.galaxy)
                self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True

    def handle_eliminate_agent(self, event: EliminateAgentEvent):
        """Dispatches EliminateAgentOrder to selected Counter-Intelligence units."""
        for unit in event.units:
            intel_comp = getattr(unit, 'intelligence_component', None)
            if not intel_comp or not intel_comp.has_counter_intelligence:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Counter-Intelligence Suite.",
                        title="No Counter-Intelligence"
                    )
                continue
            order = EliminateAgentOrder(unit, {"agent_id": event.agent_id})
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(order)
            logger.debug(f"  Unit {unit.name} ordered to eliminate Agent {event.agent_id} via event.")
            if getattr(self.game, 'galaxy', None):
                order.execute(self.game.galaxy)
                self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True

    def handle_extract_agent(self, event: ExtractAgentEvent):
        """Dispatches ExtractAgentOrder to extract an agent back into an intelligence vessel."""
        for unit in event.units:
            intel_comp = getattr(unit, 'intelligence_component', None)
            if not intel_comp:
                continue
            order = ExtractAgentOrder(unit, {"agent_id": event.agent_id})
            if not event.shift_pressed:
                unit.commander_component.clear_orders()
            unit.commander_component.add_order(order)
            logger.debug(f"  Unit {unit.name} ordered to extract Agent {event.agent_id} via event.")
            if getattr(self.game, 'galaxy', None):
                order.execute(self.game.galaxy)
                self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True



