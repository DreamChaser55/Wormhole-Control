import logging
import typing
from events import (
    CancelOrdersEvent, IssueMoveOrderEvent, JumpInterhexEvent, JumpWormholeEvent,
    AttackUnitEvent, ColonizeEvent, LoadColonistsEvent, ConstructEvent, RepairUnitEvent,
    MineEvent, UnloadResourcesEvent, DockEvent, IssuePatrolOrderEvent
)
from entities import (
    MoveOrder, AttackOrder, ColonizeOrder, LoadColonistsOrder, ConstructOrder, RepairOrder,
    MineOrder, UnloadResourcesOrder, DockOrder, PatrolOrder
)
from sector_utils import random_point_in_sector
from constants import HullSize

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
        self.event_bus.subscribe(MineEvent, self.handle_mine)
        self.event_bus.subscribe(UnloadResourcesEvent, self.handle_unload_resources)
        self.event_bus.subscribe(DockEvent, self.handle_dock)

    def handle_cancel_orders(self, event: CancelOrdersEvent):
        for unit in event.units:
            if unit.commander_component:
                unit.commander_component.clear_orders()
                logger.debug(f"  Unit {unit.name} orders cancelled via event.")
        self.game.sidebar_needs_update = True

    def handle_issue_move_order(self, event: IssueMoveOrderEvent):
        for unit in event.units:
            if unit.engines_component:
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
            if unit.engines_component:
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
            if unit.hyperdrive_component:
                if event.target_hex != unit.in_hex:
                    move_params = {
                        "destination_system_name": event.system_name,
                        "destination_hex_coord": event.target_hex,
                        "destination_position": random_point_in_sector()
                    }
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
                    move_order = MoveOrder(unit, move_params)
                    if not event.shift_pressed:
                        unit.commander_component.clear_orders()
                        logger.debug(f"  Unit {unit.name} orders cancelled.")
                    unit.commander_component.add_order(move_order)
                    logger.debug(f"  Unit {unit.name} ordered to move via wormhole {target_wormhole.name} to {exit_system_name}:{exit_wormhole.in_hex}:{exit_wormhole.position} via event.")
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
            if unit.repair_component:
                repair_params = {"target_unit_id": event.target_unit.id}
                repair_order = RepairOrder(unit, repair_params)
                if not event.shift_pressed:
                    unit.commander_component.clear_orders()
                unit.commander_component.add_order(repair_order)
                logger.debug(f"  Unit {unit.name} ordered to repair {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_mine(self, event: MineEvent):
        for unit in event.units:
            if getattr(unit, 'mining_component', None):
                mine_params = {"target_id": event.target_body.id}
                mine_order = MineOrder(unit, mine_params)
                if not event.shift_pressed:
                    unit.commander_component.clear_orders()
                unit.commander_component.add_order(mine_order)
                logger.debug(f"  Unit {unit.name} ordered to mine {event.target_body.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_unload_resources(self, event: UnloadResourcesEvent):
        for unit in event.units:
            if getattr(unit, 'mining_component', None):
                unload_params = {"target_unit_id": event.target_unit.id}
                unload_order = UnloadResourcesOrder(unit, unload_params)
                if not event.shift_pressed:
                    unit.commander_component.clear_orders()
                unit.commander_component.add_order(unload_order)
                logger.debug(f"  Unit {unit.name} ordered to unload resources to {event.target_unit.name} via event.")
        self.game.sidebar_needs_update = True

    def handle_dock(self, event: DockEvent):
        for unit in event.units:
            if unit.hull_size in (HullSize.TINY, HullSize.SMALL):
                dock_params = {"target_carrier_id": event.target_carrier.id}
                dock_order = DockOrder(unit, dock_params)
                if not event.shift_pressed:
                    unit.commander_component.clear_orders()
                unit.commander_component.add_order(dock_order)
                logger.debug(f"  Unit {unit.name} ordered to dock to {event.target_carrier.name} via event.")
        self.game.sidebar_needs_update = True
