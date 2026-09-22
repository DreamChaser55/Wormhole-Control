import logging
import typing
from events import (
    CancelOrdersEvent, IssueMoveOrderEvent, JumpInterhexEvent, JumpWormholeEvent,
    AttackUnitEvent, ColonizeEvent, LoadColonistsEvent, ConstructEvent, RepairUnitEvent,
    MineEvent, UnloadResourcesEvent, DockEvent, IssuePatrolOrderEvent, UseAbilityEvent,
    IssueProtectOrderEvent, ContinuousMineEvent, TransferAntimatterEvent, ContinuousResupplyEvent,
    LayMinefieldEvent, RefitUnitEvent, TradeEvent, ContinuousTradeEvent,
    InfiltrateUnitEvent, InfiltratePlanetEvent, RelocateAgentEvent,
    SabotageEvent, CISweepEvent, EliminateAgentEvent, ExtractAgentEvent,
    EnterGasGiantEvent, LeaveGasGiantEvent
)
from unit_orders.movement import MoveOrder, calculate_required_antimatter
from unit_orders.combat import AttackOrder, AttackLongRangeOrder, ProtectOrder
from unit_orders.colony import ColonizeOrder, LoadColonistsOrder
from unit_orders.construction import ConstructOrder
from unit_orders.repair import RepairOrder
from unit_orders.mining import MineOrder, UnloadResourcesOrder, ContinuousMineOrder
from unit_orders.hangar import DockOrder
from unit_orders.patrol import PatrolOrder
from unit_orders.abilities import UseAbilityOrder
from unit_orders.antimatter import TransferAntimatterOrder
from unit_orders.minelayer import LayMinefieldOrder
from unit_orders.refit import RefitOrder
from unit_orders.trade import TradeOrder, ContinuousTradeOrder
from unit_orders.intelligence import InfiltrateUnitOrder, InfiltratePlanetOrder, RelocateAgentOrder, SabotageOrder, CISweepOrder, EliminateAgentOrder, ExtractAgentOrder
from unit_orders.gas_giant import EnterGasGiantOrder, LeaveGasGiantOrder

from sector_utils import random_point_in_sector
from constants import HullSize
from unit_orders.base import OrderType

logger = logging.getLogger(__name__)

class OrderSystem:
    """System that listens for order requests and creates/assigns orders to units."""
    def __init__(self, game_instance, event_bus):
        self.game = game_instance
        self.event_bus = event_bus
        self._subscribe_all()

    def _controllable_units(self, units):
        from strikecraft_service import required
        return [unit for unit in units if not required(unit)]

    def _subscribe_all(self):
        def subscribe(event_type, callback):
            def committed(event):
                try:
                    callback(event)
                finally:
                    from turn_briefing import refresh_discoveries
                    refresh_discoveries(self.game)
            self.event_bus.subscribe(event_type, committed)

        subscribe(CancelOrdersEvent, self.handle_cancel_orders)
        subscribe(IssueMoveOrderEvent, self.handle_issue_move_order)
        subscribe(IssuePatrolOrderEvent, self.handle_issue_patrol_order)
        subscribe(JumpInterhexEvent, self.handle_jump_interhex)
        subscribe(JumpWormholeEvent, self.handle_jump_wormhole)
        subscribe(AttackUnitEvent, self.handle_attack_unit)
        subscribe(ColonizeEvent, self.handle_colonize)
        subscribe(LoadColonistsEvent, self.handle_load_colonists)
        subscribe(ConstructEvent, self.handle_construct)
        subscribe(RepairUnitEvent, self.handle_repair_unit)
        subscribe(RefitUnitEvent, self.handle_refit_unit)
        subscribe(MineEvent, self.handle_mine)
        subscribe(ContinuousMineEvent, self.handle_continuous_mine)
        subscribe(UnloadResourcesEvent, self.handle_unload_resources)
        subscribe(DockEvent, self.handle_dock)
        subscribe(UseAbilityEvent, self.handle_use_ability)
        subscribe(IssueProtectOrderEvent, self.handle_issue_protect_order)
        subscribe(TransferAntimatterEvent, self.handle_transfer_antimatter)
        subscribe(ContinuousResupplyEvent, self.handle_continuous_resupply)
        subscribe(LayMinefieldEvent, self.handle_lay_minefield)
        subscribe(TradeEvent, self.handle_trade)
        subscribe(ContinuousTradeEvent, self.handle_continuous_trade)
        subscribe(InfiltrateUnitEvent, self.handle_infiltrate_unit)
        subscribe(InfiltratePlanetEvent, self.handle_infiltrate_planet)
        subscribe(RelocateAgentEvent, self.handle_relocate_agent)
        subscribe(SabotageEvent, self.handle_sabotage)
        subscribe(CISweepEvent, self.handle_ci_sweep)
        subscribe(EliminateAgentEvent, self.handle_eliminate_agent)
        subscribe(ExtractAgentEvent, self.handle_extract_agent)
        subscribe(EnterGasGiantEvent, self.handle_enter_gas_giant)
        subscribe(LeaveGasGiantEvent, self.handle_leave_gas_giant)

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

    def validate_engines_for_unit(self, unit, order_label: str) -> bool:
        """Validate that a unit can accept an order requiring sub-light engines."""
        engines = unit.engines_component
        if not engines:
            if getattr(self.game, 'gui', None):
                self.game.gui.show_warning_dialog(
                    f"Unit <b>{unit.name}</b> has no sub-light engines and cannot execute {order_label} orders.",
                    title="No Engines"
                )
            return False

        if engines.is_destroyed:
            if getattr(self.game, 'gui', None):
                self.game.gui.show_warning_dialog(
                    f"Unit <b>{unit.name}</b> has destroyed Engines and cannot execute {order_label} orders until they are repaired.",
                    title="Engines Destroyed"
                )
            return False

        if not engines.is_operational:
            if getattr(self.game, 'gui', None):
                self.game.gui.show_warning_dialog(
                    f"Unit <b>{unit.name}</b> has no operational sub-light engines and cannot execute {order_label} orders.",
                    title="Engines Offline"
                )
            return False

        return True

    def handle_cancel_orders(self, event: CancelOrdersEvent):
        for unit in self._controllable_units(event.units):
            if unit.commander_component:
                unit.commander_component.stop_and_idle()
                logger.debug(f"  Unit {unit.name} stopped and stance reset via event.")
        self.game.sidebar_needs_update = True

    def _event_location(self, system_name, hex_coord, position):
        from location_validation import location
        try:
            return location(system_name, hex_coord, position, self.game.galaxy)
        except ValueError as exc:
            if getattr(self.game, 'gui', None):
                self.game.gui.show_warning_dialog(str(exc), title="Invalid destination")
            return None

    def handle_issue_move_order(self, event: IssueMoveOrderEvent):
        site = self._event_location(event.system_name, event.sector_coord, event.destination)
        if site is None:
            return
        event.system_name, event.sector_coord, event.destination = site
        for unit in self._controllable_units(event.units):
            if not self.validate_engines_for_unit(unit, "move"):
                continue
            from constants import HullSize
            from domain.celestials import is_position_in_magnetic_storm, is_position_blocked_by_celestial_field
            if unit.hull_size == HullSize.STRIKECRAFT_WING and is_position_in_magnetic_storm(self.game.galaxy, event.system_name, event.sector_coord, event.destination):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> is a strikecraft wing and cannot enter magnetic storms.",
                        title="Magnetic Storm Hazard"
                    )
                continue
            if is_position_blocked_by_celestial_field(self.game.galaxy, event.system_name, event.sector_coord, event.destination, unit):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> ({unit.hull_size.name}) is too large to enter this dense celestial field.",
                        title="Field Density Restriction"
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
                unit.commander_component.clear_explicit_orders()
                logger.debug(f"  Unit {unit.name} orders cancelled.")
            unit.commander_component.add_order(move_order)
            logger.debug(f"  Unit {unit.name} ordered to move to {event.system_name}:{event.sector_coord}:{event.destination} via event.")
        self.game.sidebar_needs_update = True

    def handle_issue_patrol_order(self, event: IssuePatrolOrderEvent):
        site = self._event_location(event.system_name, event.sector_coord, event.destination)
        if site is None:
            return
        event.system_name, event.sector_coord, event.destination = site
        add_waypoint = getattr(event, 'add_waypoint', getattr(event, 'ctrl_pressed', False))
        for unit in self._controllable_units(event.units):
            if not self.validate_engines_for_unit(unit, "patrol"):
                continue
            from constants import HullSize
            from domain.celestials import is_position_in_magnetic_storm, is_position_blocked_by_celestial_field
            if unit.hull_size == HullSize.STRIKECRAFT_WING and is_position_in_magnetic_storm(self.game.galaxy, event.system_name, event.sector_coord, event.destination):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> is a strikecraft wing and cannot enter magnetic storms.",
                        title="Magnetic Storm Hazard"
                    )
                continue
            if is_position_blocked_by_celestial_field(self.game.galaxy, event.system_name, event.sector_coord, event.destination, unit):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> ({unit.hull_size.name}) is too large to enter this dense celestial field.",
                        title="Field Density Restriction"
                    )
                continue
            if not self.validate_antimatter_for_unit(unit, event.system_name, event.sector_coord, event.destination):
                continue
            existing_patrol = None
            if add_waypoint:
                if unit.commander_component.orders_queue:
                    last_order = unit.commander_component.orders_queue[-1]
                    if last_order.order_type == OrderType.PATROL:
                        existing_patrol = last_order
                if not existing_patrol and unit.commander_component.current_order and unit.commander_component.current_order.order_type == OrderType.PATROL:
                    existing_patrol = unit.commander_component.current_order

            if add_waypoint and existing_patrol:
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
                    unit.commander_component.clear_explicit_orders()
                    logger.debug(f"  Unit {unit.name} orders cancelled.")
                unit.commander_component.add_order(patrol_order)
                logger.debug(f"  Unit {unit.name} ordered to patrol to {event.system_name}:{event.sector_coord}:{event.destination} via event.")
        self.game.sidebar_needs_update = True

    def handle_jump_interhex(self, event: JumpInterhexEvent):
        for unit in self._controllable_units(event.units):
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
                    unit.commander_component.clear_explicit_orders()
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

        for unit in self._controllable_units(event.units):
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
                        unit.commander_component.clear_explicit_orders()
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
        for unit in self._controllable_units(event.units):
            if event.long_range_only:
                from domain.players import are_enemies
                if (unit.owner != self.game.players[self.game.current_player_index]
                        or unit.is_disabled or unit.is_hidden_in_gas_giant
                        or not are_enemies(unit.owner, event.target_unit.owner)
                        or not self.game.is_unit_visible(event.target_unit)
                        or not unit.weapons_component
                        or not unit.weapons_component.eligible_turrets_for(event.target_unit, long_range_only=True)):
                    continue
            attack_params = {"target_unit_id": event.target_unit.id}
            if event.target_component_type_str:
                attack_params["target_component_type"] = event.target_component_type_str
            order_class = AttackLongRangeOrder if event.long_range_only else AttackOrder
            attack_order = order_class(unit, attack_params)
            if not event.shift_pressed:
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(attack_order)
            logger.debug(f"  Unit {unit.name} ordered to attack {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_colonize(self, event: ColonizeEvent):
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(colonize_order)
            logger.debug(f"  Unit {unit.name} ordered to colonize {event.target_body.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_load_colonists(self, event: LoadColonistsEvent):
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(load_order)
            logger.debug(f"  Unit {unit.name} ordered to load {event.amount} colonists from planet {event.target_body.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_construct(self, event: ConstructEvent):
        site = self._event_location(event.target_system_name, event.target_hex_coord, event.target_position)
        if site is None:
            return
        system_name, hex_coord, position = site
        from geometry import Position, distance
        from location_validation import format_location
        for unit in self._controllable_units(event.units):
            constructor = unit.constructor_component
            if not constructor:
                continue
            engines = unit.engines_component
            if (not engines or not engines.is_operational) and (unit.in_system != system_name or unit.in_hex != hex_coord or distance(unit.position, position) > constructor.build_range):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog("The construction site is outside this builder's reach.", title="Target Out of Range")
                continue
            construct_params = {
                "unit_template_name": event.unit_template_name,
                "target_position": Position(position.x, position.y),
                "target_system_name": system_name,
                "target_hex_coord": hex_coord
            }
            construct_order = ConstructOrder(unit, construct_params)
            if not event.shift_pressed:
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(construct_order)
            logger.debug(f"  Unit {unit.name} ordered to construct {event.unit_template_name} at {format_location(system_name, hex_coord, position)} via event.")
        self.game.sidebar_needs_update = True

    def handle_repair_unit(self, event: RepairUnitEvent):
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(repair_order)
            logger.debug(f"  Unit {unit.name} ordered to repair {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_refit_unit(self, event: RefitUnitEvent):
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(refit_order)
            logger.debug(f"  Unit {unit.name} ordered to refit {event.target_unit.name} ({event.action} {event.component_type}) via event.")
        self.game.sidebar_needs_update = True

    def handle_issue_protect_order(self, event: IssueProtectOrderEvent):
        for unit in self._controllable_units(event.units):
            protect_params = {"target_unit_id": event.target_unit.id}
            protect_order = ProtectOrder(unit, protect_params)
            if not event.shift_pressed:
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(protect_order)
            logger.debug(f"  Unit {unit.name} ordered to protect {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_mine(self, event: MineEvent):
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(mine_order)
            logger.debug(f"  Unit {unit.name} ordered to mine {event.target_body.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_continuous_mine(self, event: ContinuousMineEvent):
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(continuous_mine_order)
            logger.debug(f"  Unit {unit.name} ordered to continuous mine {event.target_body.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_unload_resources(self, event: UnloadResourcesEvent):
        is_metal_refinery = bool(getattr(event.target_unit, 'metal_refinery_component', None))
        is_crystal_refinery = bool(getattr(event.target_unit, 'crystal_refinery_component', None))
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(unload_order)
            logger.debug(f"  Unit {unit.name} ordered to unload resources to {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_dock(self, event: DockEvent):
        for unit in self._controllable_units(event.units):
            if unit.hull_size not in (HullSize.TINY, HullSize.SMALL, HullSize.STRIKECRAFT_WING):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> (Hull Size: {unit.hull_size.name}) cannot dock. Only Tiny, Small, and Strikecraft Wing hull sizes are supported.",
                        title="Invalid Dock Target"
                    )
                continue
            dock_params = {"target_carrier_id": event.target_carrier.id}
            dock_order = DockOrder(unit, dock_params)
            if not event.shift_pressed:
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(dock_order)
            logger.debug(f"  Unit {unit.name} ordered to dock to {event.target_carrier.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_use_ability(self, event: UseAbilityEvent):
        from location_validation import ability_target_kind
        try:
            positional = ability_target_kind(event.ability_type_str) in {"position", "celestial_position"}
        except ValueError:
            return
        if positional:
            site = self._event_location(event.target_system_name, event.target_hex_coord, event.target_position)
            if site is None:
                return
            event.target_system_name, event.target_hex_coord, event.target_position = site
        from tactical_abilities import SPECS
        if event.ability_type_str in SPECS:
            from tactical_ui import issue
            spec = SPECS[event.ability_type_str]
            for unit in self._controllable_units(event.units):
                command = {'type': 'use_ability', 'unit_ids': [unit.id], 'ability': event.ability_type_str, 'queue': event.shift_pressed}
                if event.target_unit is not None:
                    command['target_id'] = event.target_unit.id
                if spec.target_kind == 'celestial_position':
                    command['target_id'] = getattr(self.game, 'pending_catalyst_body_id', None)
                if event.target_position is not None:
                    command.update(position=[event.target_position.x, event.target_position.y], system_name=event.target_system_name, hex_coord=list(event.target_hex_coord))
                issue(self.game, command)
            return
        for unit in self._controllable_units(event.units):
            if not unit.ability_component:
                continue
            if event.ability_type_str == "microjump" and (unit.in_system != event.target_system_name or unit.in_hex != event.target_hex_coord):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog("Microjump requires a destination in the unit's current sector.", title="Target Out of Range")
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(ability_order)
            logger.debug(f"  Unit {unit.name} ordered to use ability {event.ability_type_str} via event.")
        self.game.sidebar_needs_update = True

    def handle_transfer_antimatter(self, event: TransferAntimatterEvent):
        """Creates TransferAntimatterOrders for selected units that have antimatter
        to give, sending it to the friendly target unit's storage."""
        from tactical_ui import issue
        from antimatter_logistics import exchange_blocker
        units = [u.id for u in event.units if exchange_blocker(u, event.target_unit, self.game.galaxy) is None and (event.shift_pressed or u.antimatter_component.current_amount > 0)]
        if units:
            issue(self.game, {'type': 'transfer_antimatter', 'unit_ids': units, 'target_id': event.target_unit.id, 'queue': event.shift_pressed})

    def handle_continuous_resupply(self, event: ContinuousResupplyEvent):
        """Issue continuous harvesting through the shared command gateway."""
        from tactical_ui import issue
        units = [u.id for u in event.units if getattr(u, 'harvester_component', None)
                 and getattr(u, 'antimatter_component', None)]
        if units:
            issue(self.game, {'type': 'continuous_resupply', 'unit_ids': units,
                             'source_id': event.target_body.id,
                             'target_id': event.target_unit.id if event.target_unit else None,
                             'queue': event.shift_pressed})

    def handle_lay_minefield(self, event: LayMinefieldEvent):
        """Creates LayMinefieldOrders for selected units with MinelayerComponent."""
        mtype = getattr(event, 'minefield_type', 'anti_ship')
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(lay_order)
            logger.debug(f"  Unit {unit.name} ordered to lay {mtype} minefield via event.")
        self.game.sidebar_needs_update = True

    def handle_trade(self, event: TradeEvent):
        """Creates TradeOrders for selected units with TradeComponent, targeting an active Civilian Habitat."""
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(trade_order)
            logger.debug(f"  Unit {unit.name} ordered to trade with {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_continuous_trade(self, event: ContinuousTradeEvent):
        """Creates ContinuousTradeOrders for selected units with TradeComponent."""
        for unit in self._controllable_units(event.units):
            if not getattr(unit, 'trade_component', None):
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        f"Unit <b>{unit.name}</b> lacks a Trade Component and cannot engage in commerce.",
                        title="No Trade Module"
                    )
                continue
            continuous_trade_order = ContinuousTradeOrder(unit)
            if not event.shift_pressed:
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(continuous_trade_order)
            logger.debug(f"  Unit {unit.name} ordered to continuous trade via event.")
        self.game.sidebar_needs_update = True

    def handle_infiltrate_unit(self, event: InfiltrateUnitEvent):
        """Creates InfiltrateUnitOrders for selected units with IntelligenceComponent."""
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
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
        for unit in self._controllable_units(event.units):
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
                "system": event.target_system,
                "hex": event.target_hex,
            }
            order = InfiltratePlanetOrder(unit, params)
            if not event.shift_pressed:
                unit.commander_component.clear_explicit_orders()
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
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(order)
            logger.debug(f"  Unit {unit.name} ordered CI Sweep via event.")
            if getattr(self.game, 'galaxy', None):
                order.execute(self.game.galaxy)
                self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True

    def handle_eliminate_agent(self, event: EliminateAgentEvent):
        """Dispatches EliminateAgentOrder to selected Counter-Intelligence units."""
        for unit in self._controllable_units(event.units):
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
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(order)
            logger.debug(f"  Unit {unit.name} ordered to eliminate Agent {event.agent_id} via event.")
            if getattr(self.game, 'galaxy', None):
                order.execute(self.game.galaxy)
                self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True

    def handle_extract_agent(self, event: ExtractAgentEvent):
        """Dispatches ExtractAgentOrder to extract an agent back into an intelligence vessel."""
        for unit in self._controllable_units(event.units):
            intel_comp = getattr(unit, 'intelligence_component', None)
            if not intel_comp:
                continue
            order = ExtractAgentOrder(unit, {"agent_id": event.agent_id})
            if not event.shift_pressed:
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(order)
            logger.debug(f"  Unit {unit.name} ordered to extract Agent {event.agent_id} via event.")
            if getattr(self.game, 'galaxy', None):
                order.execute(self.game.galaxy)
                self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True

    def handle_enter_gas_giant(self, event: EnterGasGiantEvent):
        """Dispatches EnterGasGiantOrder to selected ships."""
        for unit in self._controllable_units(event.units):
            if getattr(unit, 'hull_size', None) == HullSize.STRIKECRAFT_WING:
                if getattr(self.game, 'gui', None):
                    self.game.gui.show_warning_dialog(
                        "Strikecraft wings cannot enter gas giant atmospheres.",
                        title="Entry Prohibited"
                    )
                continue
            if not self.validate_engines_for_unit(unit, "Enter Gas Giant"):
                continue
            order = EnterGasGiantOrder(unit, {"target_id": event.gas_giant.id})
            if not event.shift_pressed:
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(order)
            logger.debug(f"  Unit {unit.name} ordered to enter gas giant {event.gas_giant.name} via event.")
            if getattr(self.game, 'galaxy', None):
                order.execute(self.game.galaxy)
                self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True

    def handle_leave_gas_giant(self, event: LeaveGasGiantEvent):
        """Dispatches LeaveGasGiantOrder to selected hidden ships."""
        for unit in self._controllable_units(event.units):
            order = LeaveGasGiantOrder(unit, {})
            if not event.shift_pressed:
                unit.commander_component.clear_explicit_orders()
            unit.commander_component.add_order(order)
            logger.debug(f"  Unit {unit.name} ordered to leave gas giant via event.")
            if getattr(self.game, 'galaxy', None):
                order.execute(self.game.galaxy)
                self.game.visibility_dirty = True
        self.game.sidebar_needs_update = True
