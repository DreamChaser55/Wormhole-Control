import logging

logger = logging.getLogger(__name__)

import typing
from typing import Dict, Optional, Any, TYPE_CHECKING, Deque, List
from enum import Enum, auto
from collections import deque
import random
import math

from utils import HexCoord
from geometry import Position, distance, hex_distance, Circle, is_circle_contained, do_circles_intersect, is_point_in_circle, get_closest_point_on_circle_edge, move_towards_position
from pathfinding import find_intersystem_path, find_hex_jump_path
from hexgrid_utils import hex_to_pixel

if TYPE_CHECKING:
    from galaxy import Galaxy, Wormhole
    from entities import Unit

class OrderStatus(Enum):
    """Enum representing the possible states of an Order."""
    PENDING = auto()      # Order has been created but not started
    IN_PROGRESS = auto()  # Order is currently being executed
    COMPLETED = auto()    # Order has been successfully completed
    FAILED = auto()       # Order has failed and cannot be completed
    CANCELLED = auto()    # Order was cancelled before completion

class OrderType(Enum):
    """Enum representing the different types of orders."""
    REACH_WAYPOINT = auto() # Move to a waypoint (system, hex, position). No dynamic planning or sub-order spawning. Simple movement to a single location. Spawned as sub-order(s) of MOVE.
    MOVE = auto()           # High-level move to a location (system, hex, position). Will plan a potentially multi-leg route to the destination and spawn one or more sub-orders of REACH_WAYPOINT.
    PATROL = auto()         # Patrol between positions
    ATTACK = auto()         # Attack a target
    DEFEND = auto()         # Defend a position or unit
    TOGGLE_INHIBITOR = auto() # Turn the hyperspace inhibitor on or off
    COLONIZE = auto()       # Unload population to colonize a planet
    LOAD_COLONISTS = auto() # Load population from a planet
    CONSTRUCT = auto()      # Construct a new unit/station
    REPAIR = auto()         # Repair a damaged friendly unit
    MINE = auto()           # Mine raw resources from a celestial body
    UNLOAD_RESOURCES = auto() # Unload raw resources to a refinery

class Order:
    """Represents an order given to a unit by the player.
    
    Orders can contain sub-orders that must be completed before the main order
    is considered complete. This creates a recursive order structure.
    """
    order_counter = 0

    def __init__(self, unit: 'Unit', order_type: OrderType, parameters: Dict[str, Any] = None, parent_order: Optional['Order'] = None):
        self.unit = unit
        self.order_id = Order.order_counter
        Order.order_counter += 1
        self.order_type = order_type
        self.parameters = parameters or {}
        self.status = OrderStatus.PENDING
        self.sub_orders: Deque['Order'] = deque()
        self.parent_order = parent_order

    def get_state_data(self) -> Dict[str, Any]:
        """Returns raw structured state data for this order."""
        return {
            "order_type": self.order_type.name,
            "status": self.status.name,
            "parameters": self.parameters,
        }

    def add_sub_order(self, sub_order: 'Order') -> None:
        """Add a sub-order to this order's queue."""
        sub_order.parent_order = self
        sub_order.unit = self.unit
        self.sub_orders.append(sub_order)
        logger.debug(f"  Added sub-order {sub_order.order_type.name} (id:{sub_order.order_id}) to order {self.order_type.name} (id:{self.order_id}) for unit {self.unit.name} (id:{self.unit.id}).")
        
    def remove_sub_order(self, order_id: typing.Union[str, int]) -> bool:
        """Remove a sub-order from the queue by its ID.
        
        Returns True if the order was found and removed, False otherwise.
        """
        for i, order in enumerate(self.sub_orders):
            if order.order_id == order_id:
                self.sub_orders.remove(order)
                return True
        return False

    def is_completed(self) -> bool:
        """Check if this order and all its sub-orders are completed."""
        if self.status != OrderStatus.COMPLETED:
            return False
            
        for sub_order in self.sub_orders:
            if not sub_order.is_completed():
                return False
                
        return True

    def has_active_sub_orders(self) -> bool:
        """Check if any sub-orders are still in progress or pending."""
        for sub_order in self.sub_orders:
            if sub_order.status in [OrderStatus.IN_PROGRESS, OrderStatus.PENDING] or sub_order.has_active_sub_orders():
                return True
        return False

    def update(self, galaxy_ref: 'Galaxy') -> None:
        """Update the order status based on sub-orders status and own completion."""
        # Process the front sub-order in the queue sequentially. We block and wait
        # until the current sub-order is fully resolved (completed, failed, or cancelled).
        while self.sub_orders:
            current_sub_order = self.sub_orders[0]

            if current_sub_order.status == OrderStatus.PENDING:
                current_sub_order.execute(galaxy_ref=galaxy_ref)

            if current_sub_order.status == OrderStatus.IN_PROGRESS:
                current_sub_order.update(galaxy_ref=galaxy_ref)

            if current_sub_order.status in [OrderStatus.COMPLETED, OrderStatus.FAILED, OrderStatus.CANCELLED]:
                self.sub_orders.popleft()
            else:
                return

        # Once all sub-orders are cleared, verify if the parent order itself is complete.
        if self.status == OrderStatus.IN_PROGRESS:
            self.check_completion_conditions()

    def cancel(self) -> None:
        """Cancel this order and all its sub-orders."""
        self.status = OrderStatus.CANCELLED
        for sub_order in self.sub_orders:
            sub_order.cancel()
    
    def check_completion_conditions(self) -> None:
        """Check order-specific completion conditions and update status."""
        pass
        
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(type={self.order_type.name}, status={self.status.name}, id={str(self.order_id)[:8]})"

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        """Execute this order."""
        if self.status != OrderStatus.PENDING:
            return
        self.status = OrderStatus.IN_PROGRESS
        logger.debug(f"[{self.unit.name} (id:{self.unit.id})] {self.__class__.__name__}.execute: {self.order_type.name} (id:{self.order_id}): Executing order.")

    def find_wormhole_to_system(self, current_system_name: str, target_system_name: str, galaxy_ref: 'Galaxy') -> Optional['Wormhole']:
        if not galaxy_ref: return None
        for wh_id, wormhole_obj in galaxy_ref.wormholes.items():
            if wormhole_obj.in_system == current_system_name and \
               wormhole_obj.exit_system_name == target_system_name:
                return wormhole_obj
        return None

class ReachWaypointOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.REACH_WAYPOINT, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        dest_system = self.parameters["destination_system_name"]
        dest_hex = self.parameters["destination_hex_coord"]
        dest_position: Optional[Position] = self.parameters["destination_position"]
        
        current_system = self.unit.in_system
        current_hex = self.unit.in_hex
        
        if dest_system is None or dest_hex is None or dest_position is None:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (incomplete destination parameters).")
            return
            
        # Hex jumps require a hyperdrive. Sub-light movement engines are disabled.
        if current_system == dest_system and current_hex != dest_hex:
            if not self.unit.hyperdrive_component:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (cannot jump hex, no hyperdrive).")
                return
                
            self.unit.hyperdrive_component.hex_jump_target = (dest_hex, dest_position)
            self.unit.hyperdrive_component.wormhole_jump_target = None
            if self.unit.engines_component:
                self.unit.engines_component.move_target = None
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): Initiating HEX JUMP to {dest_hex}:{dest_position} in {dest_system}.")
            
        # Sub-light engine movement is used within the same hex. Hyperdrive targets are cleared.
        elif current_system == dest_system and current_hex == dest_hex:
            if not self.unit.engines_component:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (cannot move in sector, no engines).")
                return

            if distance(self.unit.position, dest_position) < 0.01:
                self.status = OrderStatus.COMPLETED
                self.unit.engines_component.move_target = None
                if self.unit.hyperdrive_component:
                    self.unit.hyperdrive_component.hex_jump_target = None
                    self.unit.hyperdrive_component.wormhole_jump_target = None
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): COMPLETED (already at sub-light destination {dest_position} in {dest_system}:{dest_hex}).")
                return

            self.unit.engines_component.move_target = dest_position
            if self.unit.hyperdrive_component:
                self.unit.hyperdrive_component.hex_jump_target = None
                self.unit.hyperdrive_component.wormhole_jump_target = None
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): Initiating sub-light move to {dest_position} in {dest_system}:{dest_hex}.")
            
        # Inter-system travel requires navigating via a wormhole connecting the two systems.
        else: # current_system != dest_system
            if not self.unit.hyperdrive_component:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (cannot jump to different system, no hyperdrive).")
                return
                
            wormhole = self.find_wormhole_to_system(current_system, dest_system, galaxy_ref)
            if not wormhole:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (no wormhole from {current_system} to {dest_system}).")
                return
                
            self.unit.hyperdrive_component.wormhole_jump_target = wormhole
            self.unit.hyperdrive_component.hex_jump_target = None
            if self.unit.engines_component:
                self.unit.engines_component.move_target = None
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): Initiating SYSTEM JUMP via wormhole {wormhole.name} to {dest_system}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return

        current_system = self.unit.in_system
        current_hex = self.unit.in_hex
        current_position = self.unit.position
        
        dest_system = self.parameters["destination_system_name"]
        dest_hex = self.parameters["destination_hex_coord"]
        dest_position: Position = self.parameters["destination_position"]
        
        if current_system == dest_system and current_hex == dest_hex and distance(current_position, dest_position) < 0.01:
            if self.unit.engines_component:
                self.unit.engines_component.move_target = None
            if self.unit.hyperdrive_component:
                self.unit.hyperdrive_component.hex_jump_target = None
                self.unit.hyperdrive_component.wormhole_jump_target = None
            self.status = OrderStatus.COMPLETED
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] ReachWaypointOrder.check_completion_conditions: {self.order_type.name} (id:{self.order_id}): COMPLETED (arrived at waypoint: {dest_position}:Hex{dest_hex}:{dest_system})")

class MoveOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.MOVE, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)
        self.plan_route(galaxy_ref=galaxy_ref)

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return

        current_system = self.unit.in_system
        current_hex = self.unit.in_hex
        current_position = self.unit.position
        
        dest_system = self.parameters["destination_system_name"]
        dest_hex = self.parameters["destination_hex_coord"]
        dest_position: Position = self.parameters["destination_position"]
        
        if not self.sub_orders and current_system == dest_system and current_hex == dest_hex and distance(current_position, dest_position) < 0.01:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MoveOrder.check_completion_conditions: {self.order_type.name} (id:{self.order_id}): COMPLETED (all sub-orders finished, unit reached destination).")
        else:
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MoveOrder.check_completion_conditions: {self.order_type.name} (id:{self.order_id}): IN_PROGRESS (sub-orders not finished and/or unit has not reached destination).")

    def handle_inhibited_waypoint(self, target_hex: HexCoord, target_pos: Position, is_final_destination: bool, system_name: str, galaxy_ref: 'Galaxy'):
        destination_hex_obj = galaxy_ref.systems[system_name].hexes.get(target_hex)
        if not destination_hex_obj:
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MoveOrder.handle_inhibited_waypoint: ERROR: Destination hex {target_hex} not found in system {system_name}.")
            return

        for zone in destination_hex_obj.get_all_inhibition_zones():
            if is_point_in_circle(target_pos, zone):
                adjusted_pos = get_closest_point_on_circle_edge(target_pos, zone)
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Waypoint {target_pos} in {target_hex} is inhibited. Adjusting landing position to {adjusted_pos}.")
                
                self.add_sub_order(ReachWaypointOrder(self.unit, {
                    "destination_system_name": system_name,
                    "destination_hex_coord": target_hex,
                    "destination_position": adjusted_pos
                }, parent_order=self))

                if is_final_destination:
                    logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Adding sub-light move from {adjusted_pos} to original target {target_pos}.")
                    self.add_sub_order(ReachWaypointOrder(self.unit, {
                        "destination_system_name": system_name,
                        "destination_hex_coord": target_hex,
                        "destination_position": target_pos
                    }, parent_order=self))
                return
        
        self.add_sub_order(ReachWaypointOrder(self.unit, {
            "destination_system_name": system_name,
            "destination_hex_coord": target_hex,
            "destination_position": target_pos
        }, parent_order=self))

    def plan_hex_jump_sequence(self, start_hex: HexCoord, end_hex: HexCoord, end_pos: Position, system_name: str, galaxy_ref: 'Galaxy') -> None:
        logger.debug(f"  [plan_route->plan_hex_jump_sequence] Planning hex jump sequence from {start_hex} to {end_hex} in system {system_name}.")
        if not self.unit.hyperdrive_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MoveOrder.plan_hex_jump_sequence: FAILED (no hyperdrive).")
            return

        jump_range = self.unit.hyperdrive_component.jump_range
        distance_to_jump = hex_distance(start_hex, end_hex)

        if distance_to_jump <= jump_range:
            logger.debug(f"  [plan_route->plan_hex_jump_sequence] Jump is within range ({distance_to_jump} <= {jump_range}). Planning a single jump.")
            self.handle_inhibited_waypoint(end_hex, end_pos, is_final_destination=True, system_name=system_name, galaxy_ref=galaxy_ref)
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Added sub-order(s) for single jump to hex {end_hex}.")
        else:
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Jump to {end_hex} is out of range ({distance_to_jump} > {jump_range}). Planning multi-stage inter-hex jump.")
            waypoints = find_hex_jump_path(start_hex, end_hex, jump_range)
            logger.debug(f"  [plan_route->plan_hex_jump_sequence] Multi-stage jump waypoints from find_hex_jump_path: {waypoints}")
            
            for i, waypoint_hex in enumerate(waypoints):
                is_final = (i == len(waypoints) - 1)
                waypoint_pos = end_pos if is_final else hex_to_pixel(waypoint_hex[0], waypoint_hex[1])
                self.handle_inhibited_waypoint(waypoint_hex, waypoint_pos, is_final_destination=is_final, system_name=system_name, galaxy_ref=galaxy_ref)
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Added waypoint {i+1}/{len(waypoints)} at hex {waypoint_hex}.")

    def plan_route(self, galaxy_ref: 'Galaxy') -> None:
        logger.debug(f"\n--- Planning route for {self.unit.name} (id:{self.unit.id}) ---")
        if not self.unit or not galaxy_ref:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name if self.unit else 'Unknown Unit'}] MOVE(id:{self.order_id}): plan_route: FAILED (no unit or galaxy_ref).")
            return

        current_system = self.unit.in_system
        current_hex = self.unit.in_hex
        current_position = self.unit.position

        dest_system = self.parameters["destination_system_name"]
        dest_hex = self.parameters["destination_hex_coord"]
        dest_position: Optional[Position] = self.parameters["destination_position"]

        logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: From: {current_system}:{current_hex}:{current_position} | To: {dest_system}:{dest_hex}:{dest_position}")

        if dest_system is None or dest_hex is None or dest_position is None:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (incomplete destination parameters).")
            return

        if current_system == dest_system and current_hex == dest_hex and distance(current_position, dest_position) < 0.01:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: COMPLETED (already at destination {dest_system}:{dest_hex}:{dest_position}).")
            return

        # If the unit starts inside an active inhibitor field, it cannot engage its hyperdrive.
        # We must plan a sub-light escape move to the edge of the field before plotting the jump.
        if current_system != dest_system or current_hex != dest_hex:
            current_hex_obj = galaxy_ref.systems[current_system].hexes.get(current_hex)
            if current_hex_obj:
                for zone in current_hex_obj.get_all_inhibition_zones():
                    if is_point_in_circle(current_position, zone):
                        escape_pos = get_closest_point_on_circle_edge(current_position, zone)
                        logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Start position {current_position} is inhibited. Planning escape move to {escape_pos}.")
                        self.add_sub_order(ReachWaypointOrder(self.unit, {
                            "destination_system_name": current_system,
                            "destination_hex_coord": current_hex,
                            "destination_position": escape_pos
                        }, parent_order=self))
                        break

        # Inter-system travel: Destination is in a different system.
        if current_system != dest_system:
            if not self.unit.hyperdrive_component:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (cannot jump system, no hyperdrive).")
                return

            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Checking for direct wormhole from {current_system} to {dest_system}...")
            direct_wormhole = self.find_wormhole_to_system(current_system, dest_system, galaxy_ref)

            if direct_wormhole:
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Direct wormhole from {current_system} to {dest_system} found: {direct_wormhole.name}. Planning a single inter-system jump.")
                exit_wh = galaxy_ref.wormholes[direct_wormhole.exit_wormhole_id]
                if not exit_wh:
                    self.status = OrderStatus.FAILED
                    logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (could not find exit for direct wormhole {direct_wormhole.id} in {dest_system}).")
                    return

                # First, navigate to the entry wormhole.
                if current_hex != direct_wormhole.in_hex:
                    self.plan_hex_jump_sequence(current_hex, direct_wormhole.in_hex, direct_wormhole.position, current_system, galaxy_ref)
                else:
                    self.add_sub_order(ReachWaypointOrder(self.unit, {
                        "destination_system_name": current_system,
                        "destination_hex_coord": direct_wormhole.in_hex,
                        "destination_position": direct_wormhole.position
                    }, parent_order=self))
                    logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Added sub-order to move to direct wormhole position.")

                # Second, execute the wormhole jump.
                self.add_sub_order(ReachWaypointOrder(self.unit, {
                    "destination_system_name": dest_system,
                    "destination_hex_coord": exit_wh.in_hex,
                    "destination_position": exit_wh.position
                }, parent_order=self))
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Added sub-order to jump through direct wormhole to {dest_system}.")

                # If the destination wormhole exit is inhibited, we immediately schedule a sub-light escape
                # maneuver to a random safe point outside the inhibitor field.
                arrival_pos = exit_wh.position
                arrival_hex_obj = galaxy_ref.systems[dest_system].hexes[exit_wh.in_hex]
                if arrival_hex_obj:
                    for zone in arrival_hex_obj.get_all_inhibition_zones():
                        if is_point_in_circle(arrival_pos, zone):
                            angle = random.uniform(0, 2 * math.pi)
                            safe_distance = zone.radius + 1.0
                            safe_pos_x = arrival_pos.x + safe_distance * math.cos(angle)
                            safe_pos_y = arrival_pos.y + safe_distance * math.sin(angle)
                            safe_pos = Position(safe_pos_x, safe_pos_y)

                            self.add_sub_order(ReachWaypointOrder(self.unit, {
                                "destination_system_name": dest_system,
                                "destination_hex_coord": exit_wh.in_hex,
                                "destination_position": safe_pos
                            }, parent_order=self))
                            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Wormhole exit is inhibited. Adding sub-light move to safe position: {safe_pos}.")
                            arrival_pos = safe_pos
                            break

                # Finally, navigate from the exit wormhole to the final destination.
                if exit_wh.in_hex != dest_hex:
                    self.plan_hex_jump_sequence(exit_wh.in_hex, dest_hex, dest_position, dest_system, galaxy_ref)

            else:
                # If no direct wormhole exists, find a multi-system path using Dijkstra's algorithm.
                path_to_destination = find_intersystem_path(galaxy_ref.system_graph, current_system, dest_system)

                if not path_to_destination or len(path_to_destination) < 2:
                    self.status = OrderStatus.FAILED
                    logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (no path found from {current_system} to {dest_system} via pathfinding with find_intersystem_path).")
                    return

                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Path found via pathfinding with find_intersystem_path: {path_to_destination}")
                logger.debug(f"  [plan_route] Path has {len(path_to_destination) - 1} legs.")

                current_leg_arrival_hex = current_hex

                for i in range(len(path_to_destination) - 1):
                    leg_origin_system = path_to_destination[i]
                    leg_destination_system = path_to_destination[i+1]
                    logger.debug(f"\n  --- Planning Leg {i+1}: {leg_origin_system} -> {leg_destination_system} ---")

                    wormhole_for_leg = self.find_wormhole_to_system(leg_origin_system, leg_destination_system, galaxy_ref)
                    if not wormhole_for_leg:
                        self.status = OrderStatus.FAILED
                        logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (pathfinding error - no wormhole for leg {leg_origin_system} -> {leg_destination_system}).")
                        return

                    exit_wormhole_for_leg = galaxy_ref.wormholes[wormhole_for_leg.exit_wormhole_id]
                    if not exit_wormhole_for_leg:
                        self.status = OrderStatus.FAILED
                        logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (pathfinding error - no exit for wormhole {wormhole_for_leg.id}).")
                        return

                    # Navigate from the last leg's entry point to this leg's entry wormhole position.
                    if current_leg_arrival_hex != wormhole_for_leg.in_hex:
                        self.plan_hex_jump_sequence(current_leg_arrival_hex, wormhole_for_leg.in_hex, wormhole_for_leg.position, leg_origin_system, galaxy_ref)
                    else:
                        self.add_sub_order(ReachWaypointOrder(self.unit, {
                            "destination_system_name": leg_origin_system,
                            "destination_hex_coord": wormhole_for_leg.in_hex,
                            "destination_position": wormhole_for_leg.position
                        }, parent_order=self))
                        logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Leg {i+1} - Added sub-order to move by sub-light engines to entry Wormhole position in {leg_origin_system}.")

                    # Jump to the target system of this leg.
                    self.add_sub_order(ReachWaypointOrder(self.unit, {
                        "destination_system_name": leg_destination_system,
                        "destination_hex_coord": exit_wormhole_for_leg.in_hex,
                        "destination_position": exit_wormhole_for_leg.position
                    }, parent_order=self))
                    logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Leg {i+1} - Added sub-order to jump {leg_origin_system} -> {leg_destination_system}.")

                    # Handle case where the intermediate leg exit is blocked by an inhibitor field.
                    arrival_pos_leg = exit_wormhole_for_leg.position
                    arrival_hex_obj_leg = galaxy_ref.systems[leg_destination_system].hexes[exit_wormhole_for_leg.in_hex]
                    if arrival_hex_obj_leg:
                        for zone in arrival_hex_obj_leg.get_all_inhibition_zones():
                            if is_point_in_circle(arrival_pos_leg, zone):
                                angle = random.uniform(0, 2 * math.pi)
                                safe_distance = zone.radius + 1.0
                                safe_pos_x = arrival_pos_leg.x + safe_distance * math.cos(angle)
                                safe_pos_y = arrival_pos_leg.y + safe_distance * math.sin(angle)
                                safe_pos = Position(safe_pos_x, safe_pos_y)

                                self.add_sub_order(ReachWaypointOrder(self.unit, {
                                    "destination_system_name": leg_destination_system,
                                    "destination_hex_coord": exit_wormhole_for_leg.in_hex,
                                    "destination_position": safe_pos
                                }, parent_order=self))
                                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Leg {i+1} exit is inhibited. Adding sub-light move out of inhibition zone to safe position: {safe_pos}.")
                                break

                    current_leg_arrival_hex = exit_wormhole_for_leg.in_hex

                # Plan the final leg within the destination system.
                self.plan_hex_jump_sequence(current_leg_arrival_hex, dest_hex, dest_position, dest_system, galaxy_ref)

        # Intra-system travel: Jump to a different hex in the same system.
        elif current_hex != dest_hex:
            self.plan_hex_jump_sequence(current_hex, dest_hex, dest_position, current_system, galaxy_ref)
        
        # Intra-hex travel: Move directly using sub-light engines.
        else:
            if not self.unit.engines_component:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (cannot plan final sub-light movement leg, no engines).")
                return
            
            sub_order_params = {
                "destination_system_name": dest_system,
                "destination_hex_coord": dest_hex,
                "destination_position": dest_position
            }
            final_move_sub_order = ReachWaypointOrder(self.unit, sub_order_params, parent_order=self)
            self.add_sub_order(final_move_sub_order)

class ToggleInhibitorOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.TOGGLE_INHIBITOR, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)
        
        turn_on = self.parameters.get("turn_on", False)
        
        if not self.unit.inhibitor_component:
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] TOGGLE_INHIBITOR ({self.order_id}): FAILED (no inhibitor component).")
            self.status = OrderStatus.FAILED
            return

        current_hex = galaxy_ref.systems[self.unit.in_system].hexes[self.unit.in_hex]

        if turn_on:
            inhibitor = self.unit.inhibitor_component
            proposed_field = Circle(center=self.unit.position, radius=inhibitor.radius)

            # The inhibitor field must fit entirely inside the hex boundary
            # and cannot overlap with any other active inhibitor fields.
            if not is_circle_contained(proposed_field, current_hex.boundary_circle):
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] TOGGLE_INHIBITOR ({self.order_id}): FAILED (field would cross sector boundary).")
                self.status = OrderStatus.FAILED
                return

            for existing_zone in current_hex.get_all_inhibition_zones():
                if do_circles_intersect(proposed_field, existing_zone):
                    logger.debug(f"[{self.unit.name} (id:{self.unit.id})] TOGGLE_INHIBITOR ({self.order_id}): FAILED (field would overlap with another).")
                    self.status = OrderStatus.FAILED
                    return
            
            inhibitor.turn_on()
            current_hex.dynamic_inhibition_zones[self.unit.id] = proposed_field
            self.status = OrderStatus.COMPLETED
        else:
            if self.unit.id in current_hex.dynamic_inhibition_zones:
                del current_hex.dynamic_inhibition_zones[self.unit.id]
            
            self.unit.inhibitor_component.turn_off()
            self.status = OrderStatus.COMPLETED

class PatrolOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.PATROL, parameters, parent_order)

class AttackOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.ATTACK, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_unit_id = self.parameters.get("target_unit_id")
        target_name = None
        lookup_attempted = False
        lookup_success = False
        if target_unit_id and self.unit and self.unit.game:
            lookup_attempted = True
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if target_unit:
                target_name = target_unit.name
                lookup_success = True
        state_data["target_unit_id"] = target_unit_id
        state_data["target_name"] = target_name
        state_data["lookup_attempted"] = lookup_attempted
        state_data["lookup_success"] = lookup_success
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_unit_id = self.parameters["target_unit_id"]
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)

        target_component_type_str = self.parameters.get("target_component_type")
        target_component_type = None
        if target_component_type_str:
            import unit_components
            target_component_type = getattr(unit_components, target_component_type_str, None)

        if not target_unit:
            self.status = OrderStatus.FAILED
            return
        
        if self.unit.weapons_component:
            self.unit.weapons_component.set_target(target_unit, target_component_type)

            if self.unit.in_system != target_unit.in_system or self.unit.in_hex != target_unit.in_hex:
                in_the_same_system_and_hex = False
            else:
                in_the_same_system_and_hex = True

            in_range = False
            for turret in self.unit.weapons_component.turrets:
                if distance(self.unit.position, target_unit.position) < turret.range:
                    in_range = True
                    break
            
            min_turret_range = min(turret.range for turret in self.unit.weapons_component.turrets)

            if not in_the_same_system_and_hex or not in_range:
                dest_pos = move_towards_position(self.unit.position, target_unit.position, min_turret_range - 5.0)

                move_params = {
                    "destination_system_name": target_unit.in_system,
                    "destination_hex_coord": target_unit.in_hex,
                    "destination_position": dest_pos
                }
                move_order = MoveOrder(self.unit, move_params, parent_order=self)
                self.add_sub_order(move_order)

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        target_unit_id = self.parameters["target_unit_id"]
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
        target_component_type_str = self.parameters.get("target_component_type")

        if not target_unit or target_unit.current_hit_points <= 0:
            self.status = OrderStatus.COMPLETED
            if self.unit.weapons_component:
                self.unit.weapons_component.clear_target()
            return
            
        if target_component_type_str:
            import unit_components
            target_component_type = getattr(unit_components, target_component_type_str, None)
            if target_component_type:
                target_component = target_unit.get_component(target_component_type)
                if not target_component or target_component.is_destroyed:
                    self.status = OrderStatus.COMPLETED
                    if self.unit.weapons_component:
                        self.unit.weapons_component.clear_target()

class ColonizeOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.COLONIZE, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_id = self.parameters.get("target_id")
        if not target_id:
            self.status = OrderStatus.FAILED
            logger.debug(f"COLONIZE order failed: no target_id.")
            return

        target = galaxy_ref.get_celestial_body_by_id(target_id)

        if not target:
            self.status = OrderStatus.FAILED
            logger.debug(f"COLONIZE order failed: Celestial body with ID {target_id} not found.")
            return

        if not self.unit.colony_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"COLONIZE order failed: Unit {self.unit.name} has no ColonyComponent.")
            return

        at_location = (self.unit.in_system == target.in_system and self.unit.in_hex == target.in_hex)

        if not at_location:
            if not self.has_active_sub_orders():
                move_params = {
                    "destination_system_name": target.in_system,
                    "destination_hex_coord": target.in_hex,
                    "destination_position": target.position
                }
                move_order = MoveOrder(self.unit, move_params, parent_order=self)
                self.add_sub_order(move_order)

                colonize_sub_order = ColonizeOrder(self.unit, self.parameters, parent_order=self)
                self.add_sub_order(colonize_sub_order)
            return

        cargo = self.unit.colony_component.population_cargo
        if cargo <= 0:
            self.status = OrderStatus.FAILED
            logger.debug(f"COLONIZE order failed: No population in cargo to unload.")
            return

        success = self.unit.colony_component.unload_population(target, cargo)

        if success:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"COLONIZE order completed: Unit {self.unit.name} successfully colonized {target.name}.")
        else:
            self.status = OrderStatus.FAILED
            logger.debug(f"COLONIZE order failed: Unload population failed for unit {self.unit.name} on {target.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        target_id = self.parameters["target_id"]
        target = self.unit.game.galaxy.get_celestial_body_by_id(target_id)
        if target and target.owner == self.unit.owner:
            self.status = OrderStatus.COMPLETED

class LoadColonistsOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.LOAD_COLONISTS, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_id = self.parameters.get("target_id")
        amount = self.parameters.get("amount", 50)

        if not target_id:
            self.status = OrderStatus.FAILED
            logger.debug(f"LOAD_COLONISTS order failed: no target_id.")
            return

        target = galaxy_ref.get_celestial_body_by_id(target_id)

        if not target:
            self.status = OrderStatus.FAILED
            logger.debug(f"LOAD_COLONISTS order failed: Celestial body with ID {target_id} not found.")
            return

        if not self.unit.colony_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"LOAD_COLONISTS order failed: Unit {self.unit.name} has no ColonyComponent.")
            return

        at_location = (self.unit.in_system == target.in_system and self.unit.in_hex == target.in_hex)

        if not at_location:
            if not self.has_active_sub_orders():
                move_params = {
                    "destination_system_name": target.in_system,
                    "destination_hex_coord": target.in_hex,
                    "destination_position": target.position
                }
                move_order = MoveOrder(self.unit, move_params, parent_order=self)
                self.add_sub_order(move_order)
                
                load_params = {
                    "target_id": target.id,
                    "amount": amount
                }
                load_order = LoadColonistsOrder(self.unit, load_params, parent_order=self)
                self.add_sub_order(load_order)
            return

        success = self.unit.colony_component.load_population(target, amount)

        if success:
            self.status = OrderStatus.COMPLETED
        else:
            self.status = OrderStatus.FAILED
            logger.debug(f"LOAD_COLONISTS order failed for unit {self.unit.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED

class ConstructOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.CONSTRUCT, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not self.unit.constructor_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"CONSTRUCT order failed: Unit {self.unit.name} has no ConstructorComponent.")
            return

        unit_template_name = self.parameters.get("unit_template_name")
        target_pos = self.parameters.get("target_position")

        if not unit_template_name or not target_pos:
            self.status = OrderStatus.FAILED
            logger.debug(f"CONSTRUCT order failed: Missing parameters.")
            return

        constructor = self.unit.constructor_component
        buildable = constructor.can_build(unit_template_name)

        if not buildable:
            self.status = OrderStatus.FAILED
            logger.debug(f"CONSTRUCT order failed: {self.unit.name} cannot build {unit_template_name}.")
            return

        player = next((p for p in self.unit.game.players if p.id == self.unit.owner.id), None)
        if not player:
            self.status = OrderStatus.FAILED
            logger.debug(f"CONSTRUCT order failed: Could not find player with id {self.unit.owner.id}.")
            return
        if player.credits < buildable.cost_credits:
            self.status = OrderStatus.FAILED
            logger.debug(f"CONSTRUCT order failed: Not enough credits.")
            return

        player.credits -= buildable.cost_credits
        constructor.start_construction(unit_template_name, target_pos, galaxy_ref)
        self.status = OrderStatus.COMPLETED


class RepairOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.REPAIR, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_unit_id = self.parameters.get("target_unit_id")
        target_name = None
        lookup_attempted = False
        lookup_success = False
        if target_unit_id and self.unit and self.unit.game:
            lookup_attempted = True
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if target_unit:
                target_name = target_unit.name
                lookup_success = True
        state_data["target_unit_id"] = target_unit_id
        state_data["target_name"] = target_name
        state_data["lookup_attempted"] = lookup_attempted
        state_data["lookup_success"] = lookup_success
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not self.unit.repair_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"REPAIR order failed: Unit {self.unit.name} has no RepairComponent.")
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)

        if not target_unit:
            self.status = OrderStatus.FAILED
            logger.debug(f"REPAIR order failed: Target unit {target_unit_id} not found.")
            return

        if target_unit.owner != self.unit.owner:
            self.status = OrderStatus.FAILED
            logger.debug(f"REPAIR order failed: Target unit {target_unit.name} is not friendly.")
            return

        self.unit.repair_component.set_target(target_unit)

        in_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        in_range = in_same_system_and_hex and (distance(self.unit.position, target_unit.position) <= self.unit.repair_component.repair_range)

        if not in_range:
            if in_same_system_and_hex:
                dest_pos = move_towards_position(self.unit.position, target_unit.position, self.unit.repair_component.repair_range - 5.0)
            else:
                dest_pos = target_unit.position

            move_params = {
                "destination_system_name": target_unit.in_system,
                "destination_hex_coord": target_unit.in_hex,
                "destination_position": dest_pos
            }
            move_order = MoveOrder(self.unit, move_params, parent_order=self)
            self.add_sub_order(move_order)

            repair_sub_order = RepairOrder(self.unit, self.parameters, parent_order=self)
            self.add_sub_order(repair_sub_order)

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)

        if not target_unit or target_unit.current_hit_points <= 0:
            self.status = OrderStatus.COMPLETED
            if self.unit.repair_component:
                self.unit.repair_component.clear_target()
            return

        needs_hull_repair = target_unit.current_hit_points < target_unit.max_hit_points
        damaged_components = [c for c in target_unit.components.values() if c.current_hit_points < c.max_hit_points]

        if not needs_hull_repair and not damaged_components:
            self.status = OrderStatus.COMPLETED
            if self.unit.repair_component:
                self.unit.repair_component.clear_target()
            return

class MineOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.MINE, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_id = self.parameters.get("target_id")
        if not target_id:
            self.status = OrderStatus.FAILED
            logger.debug(f"MINE order failed: no target_id.")
            return

        target = galaxy_ref.get_celestial_body_by_id(target_id)
        if not target:
            self.status = OrderStatus.FAILED
            logger.debug(f"MINE order failed: Celestial body with ID {target_id} not found.")
            return

        if not getattr(self.unit, 'mining_component', None):
            self.status = OrderStatus.FAILED
            logger.debug(f"MINE order failed: Unit {self.unit.name} has no MiningComponent.")
            return

        at_location = (self.unit.in_system == target.in_system and self.unit.in_hex == target.in_hex)
        in_range = at_location and (distance(self.unit.position, target.position) <= self.unit.mining_component.mining_range)

        if not in_range:
            if not self.has_active_sub_orders():
                if at_location:
                    dest_pos = move_towards_position(self.unit.position, target.position, self.unit.mining_component.mining_range - 5.0)
                else:
                    dest_pos = target.position

                move_params = {
                    "destination_system_name": target.in_system,
                    "destination_hex_coord": target.in_hex,
                    "destination_position": dest_pos
                }
                move_order = MoveOrder(self.unit, move_params, parent_order=self)
                self.add_sub_order(move_order)

                mine_sub_order = MineOrder(self.unit, self.parameters, parent_order=self)
                self.add_sub_order(mine_sub_order)
            return

        self.unit.mining_component.set_target(target)
        logger.debug(f"MINE order: {self.unit.name} started mining {target.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if self.unit.mining_component:
            if self.unit.mining_component.get_cargo_fullness() >= 1.0:
                self.status = OrderStatus.COMPLETED
                self.unit.mining_component.clear_target()
                logger.debug(f"MINE order completed: Cargo full for {self.unit.name}.")

class UnloadResourcesOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.UNLOAD_RESOURCES, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = galaxy_ref.get_unit_by_id(target_unit_id)

        if not target_unit:
            self.status = OrderStatus.FAILED
            logger.debug(f"UNLOAD_RESOURCES order failed: Target unit {target_unit_id} not found.")
            return

        if not getattr(self.unit, 'mining_component', None):
            self.status = OrderStatus.FAILED
            logger.debug(f"UNLOAD_RESOURCES order failed: Unit {self.unit.name} has no MiningComponent.")
            return

        is_metal_refinery = bool(getattr(target_unit, 'metal_refinery_component', None))
        is_crystal_refinery = bool(getattr(target_unit, 'crystal_refinery_component', None))

        if not (is_metal_refinery or is_crystal_refinery):
            self.status = OrderStatus.FAILED
            logger.debug(f"UNLOAD_RESOURCES order failed: Target {target_unit.name} has no refinery components.")
            return

        # Determine unload range from either component
        unload_range = 300.0
        if is_metal_refinery:
            unload_range = target_unit.metal_refinery_component.unload_range
        elif is_crystal_refinery:
            unload_range = target_unit.crystal_refinery_component.unload_range

        at_location = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        in_range = at_location and (distance(self.unit.position, target_unit.position) <= unload_range)

        if not in_range:
            if not self.has_active_sub_orders():
                if at_location:
                    dest_pos = move_towards_position(self.unit.position, target_unit.position, unload_range - 5.0)
                else:
                    dest_pos = target_unit.position

                move_params = {
                    "destination_system_name": target_unit.in_system,
                    "destination_hex_coord": target_unit.in_hex,
                    "destination_position": dest_pos
                }
                move_order = MoveOrder(self.unit, move_params, parent_order=self)
                self.add_sub_order(move_order)

                unload_sub_order = UnloadResourcesOrder(self.unit, self.parameters, parent_order=self)
                self.add_sub_order(unload_sub_order)
            return

        # We are in range, execute unload
        metal_amount, crystal_amount = self.unit.mining_component.unload_to_refinery()

        if is_metal_refinery and metal_amount > 0:
            target_unit.metal_refinery_component.accept_resources(metal_amount)
        elif not is_metal_refinery and metal_amount > 0:
            # Drop it if not matching
            logger.debug(f"{self.unit.name} dumped {metal_amount} metal as {target_unit.name} cannot refine it.")

        if is_crystal_refinery and crystal_amount > 0:
            target_unit.crystal_refinery_component.accept_resources(crystal_amount)
        elif not is_crystal_refinery and crystal_amount > 0:
            # Drop it if not matching
            logger.debug(f"{self.unit.name} dumped {crystal_amount} crystal as {target_unit.name} cannot refine it.")

        self.status = OrderStatus.COMPLETED
        logger.debug(f"UNLOAD_RESOURCES order completed: {self.unit.name} unloaded resources to {target_unit.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        # Execution is immediate once in range, so handled above.
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED
