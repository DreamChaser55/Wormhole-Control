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
from constants import HullSize, XP_JUMP_RANGE_BONUS

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
    PROTECT = auto()        # Protect a friendly unit, follow it and attack nearby enemies
    TOGGLE_INHIBITOR = auto() # Turn the hyperspace inhibitor on or off
    COLONIZE = auto()       # Unload population to colonize a planet
    LOAD_COLONISTS = auto() # Load population from a planet
    CONSTRUCT = auto()      # Construct a new unit/station
    REPAIR = auto()         # Repair a damaged friendly unit
    MINE = auto()           # Mine raw resources from a celestial body
    UNLOAD_RESOURCES = auto() # Unload raw resources to a refinery
    DOCK = auto()
    DEPLOY_UNIT = auto()
    DEPLOY_ALL_WINGS = auto()
    USE_ABILITY = auto()  # Use a special ability (with optional target unit or position)
    CONTINUOUS_MINE = auto() # Cycles between mining and unloading at closest refinery


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

            if current_sub_order.status == OrderStatus.FAILED:
                self.status = OrderStatus.FAILED
                for sub in list(self.sub_orders):
                    sub.cancel()
                self.sub_orders.clear()
                return

            elif current_sub_order.status == OrderStatus.CANCELLED:
                self.status = OrderStatus.CANCELLED
                for sub in list(self.sub_orders):
                    sub.cancel()
                self.sub_orders.clear()
                return

            elif current_sub_order.status == OrderStatus.COMPLETED:
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

    def find_wormhole_to_system(self, current_system_name: str, target_system_name: str, galaxy_ref: 'Galaxy', ship_size: Optional[HullSize] = None) -> Optional['Wormhole']:
        if not galaxy_ref: return None
        for wh_id, wormhole_obj in galaxy_ref.wormholes.items():
            if wormhole_obj.in_system == current_system_name and \
               wormhole_obj.exit_system_name == target_system_name:
                if ship_size and ship_size.value > wormhole_obj.diameter.value:
                    continue
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
            from unit_components import HyperdriveType
            if not self.unit.hyperdrive_component or self.unit.hyperdrive_component.drive_type != HyperdriveType.ADVANCED:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (cannot jump to different system, no advanced hyperdrive).")
                return
                
            wormhole = self.find_wormhole_to_system(current_system, dest_system, galaxy_ref, self.unit.hull_size)
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

        jump_range = int(self.unit.hyperdrive_component.jump_range * self.unit.xp_multiplier(XP_JUMP_RANGE_BONUS))
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
                waypoint_pos = end_pos if is_final else Position(0.0, 0.0)
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
            from unit_components import HyperdriveType
            if not self.unit.hyperdrive_component or self.unit.hyperdrive_component.drive_type != HyperdriveType.ADVANCED:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (cannot jump system, no advanced hyperdrive).")
                return

            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Checking for direct wormhole from {current_system} to {dest_system}...")
            direct_wormhole = self.find_wormhole_to_system(current_system, dest_system, galaxy_ref, self.unit.hull_size)

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
                path_to_destination = find_intersystem_path(galaxy_ref.system_graph, current_system, dest_system, self.unit.hull_size)

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

                    wormhole_for_leg = self.find_wormhole_to_system(leg_origin_system, leg_destination_system, galaxy_ref, self.unit.hull_size)
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
        self.start_system_name = None
        self.start_hex_coord = None
        self.start_position = None
        self.patrol_phase = "TO_TARGET" # "TO_TARGET" or "TO_START"
        self.current_waypoint_index = 0

        if "waypoints" not in self.parameters and "destination_position" in self.parameters:
            self.parameters["waypoints"] = [{
                "system_name": self.parameters["destination_system_name"],
                "hex_coord": self.parameters["destination_hex_coord"],
                "position": self.parameters["destination_position"]
            }]

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)
        self.start_system_name = self.unit.in_system
        self.start_hex_coord = self.unit.in_hex
        self.start_position = Position(self.unit.position.x, self.unit.position.y)
        self.current_waypoint_index = 0
        self._spawn_move_to_current_waypoint()

    def _spawn_move_to_current_waypoint(self) -> None:
        wps = self.parameters.get("waypoints", [])
        if not wps:
            self.status = OrderStatus.FAILED
            return

        num_wps = len(wps)
        idx = self.current_waypoint_index
        if idx < num_wps:
            self.patrol_phase = "TO_TARGET"
            wp = wps[idx]
            move_params = {
                "destination_system_name": wp["system_name"],
                "destination_hex_coord": wp["hex_coord"],
                "destination_position": wp["position"]
            }
        else:
            self.patrol_phase = "TO_START"
            move_params = {
                "destination_system_name": self.start_system_name,
                "destination_hex_coord": self.start_hex_coord,
                "destination_position": self.start_position
            }
        self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))

    def add_waypoint(self, system_name: str, hex_coord: HexCoord, position: Position) -> None:
        if "waypoints" not in self.parameters:
            self.parameters["waypoints"] = []
            if "destination_position" in self.parameters:
                self.parameters["waypoints"].append({
                    "system_name": self.parameters["destination_system_name"],
                    "hex_coord": self.parameters["destination_hex_coord"],
                    "position": self.parameters["destination_position"]
                })

        old_len = len(self.parameters["waypoints"])
        self.parameters["waypoints"].append({
            "system_name": system_name,
            "hex_coord": hex_coord,
            "position": position
        })

        if self.status == OrderStatus.IN_PROGRESS:
            if getattr(self, "current_waypoint_index", 0) == old_len:
                self.current_waypoint_index = old_len + 1

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        state_data["current_waypoint_index"] = getattr(self, "current_waypoint_index", 0)
        if "waypoints" in self.parameters:
            state_data["parameters"]["waypoints"] = self.parameters["waypoints"]
        return state_data

    def _find_nearby_enemy(self, galaxy_ref: 'Galaxy') -> Optional['Unit']:
        weapons = self.unit.weapons_component
        if not weapons or weapons.is_destroyed or not weapons.turrets:
            return None

        from unit_components import TurretVariant

        system = galaxy_ref.systems.get(self.unit.in_system)
        if not system:
            return None

        hex_obj = system.hexes.get(self.unit.in_hex)
        if not hex_obj:
            return None

        closest_enemy = None
        min_dist = float('inf')

        for unit in hex_obj.units:
            if unit.owner != self.unit.owner and unit.current_hit_points > 0:
                # Fighter/Bomber targeting rules
                if self.unit.hull_size == HullSize.STRIKECRAFT_WING:
                    wing_comp = self.unit.strikecraft_wing_component
                    if wing_comp:
                        from unit_components import WingType
                        if wing_comp.wing_type == WingType.FIGHTER:
                            if unit.hull_size != HullSize.STRIKECRAFT_WING:
                                continue
                        elif wing_comp.wing_type == WingType.BOMBER:
                            if unit.hull_size == HullSize.STRIKECRAFT_WING:
                                continue

                # Find maximum range of turrets that can target this unit
                can_target = False
                max_range_for_unit = 0.0
                for t in weapons.turrets:
                    if unit.hull_size == HullSize.STRIKECRAFT_WING and t.variant != TurretVariant.ANTI_STRIKECRAFT:
                        continue
                    can_target = True
                    if t.range > max_range_for_unit:
                        max_range_for_unit = t.range

                if not can_target:
                    continue

                dist = distance(self.unit.position, unit.position)
                if dist <= max_range_for_unit and dist < min_dist:
                    min_dist = dist
                    closest_enemy = unit

        return closest_enemy

    def update(self, galaxy_ref: 'Galaxy') -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            super().update(galaxy_ref)
            return

        # Check if we are currently executing an AttackOrder
        has_attack_order = False
        if self.sub_orders:
            current_sub = self.sub_orders[0]
            if current_sub.order_type == OrderType.ATTACK:
                has_attack_order = True
                target_id = current_sub.parameters.get("target_unit_id")
                target_unit = self.unit.game.galaxy.get_unit_by_id(target_id) if target_id else None
                if (not target_unit or 
                    target_unit.current_hit_points <= 0 or 
                    target_unit.in_system != self.unit.in_system or 
                    target_unit.in_hex != self.unit.in_hex):
                    # Target is dead, missing, or fled the sector. Cancel the attack order.
                    logger.debug(f"[{self.unit.name}] Patrol target lost, dead, or fled. Resuming patrol.")
                    current_sub.cancel()
                    self.sub_orders.popleft()
                    if self.unit.weapons_component:
                        self.unit.weapons_component.clear_target()
                    # Re-route to current waypoint destination
                    self._spawn_move_to_current_waypoint()
                    has_attack_order = False

        if not has_attack_order:
            # Look for nearby enemies to engage
            nearby_enemy = self._find_nearby_enemy(galaxy_ref)
            if nearby_enemy:
                logger.debug(f"[{self.unit.name}] Enemy detected: {nearby_enemy.name}. Engaging!")
                # Cancel current movement sub-orders
                for sub in list(self.sub_orders):
                    sub.cancel()
                self.sub_orders.clear()
                if self.unit.engines_component:
                    self.unit.engines_component.move_target = None
                if self.unit.hyperdrive_component:
                    self.unit.hyperdrive_component.hex_jump_target = None
                    self.unit.hyperdrive_component.wormhole_jump_target = None

                # Spawn attack order
                attack_params = {"target_unit_id": nearby_enemy.id}
                self.add_sub_order(AttackOrder(self.unit, attack_params, parent_order=self))

        super().update(galaxy_ref)

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return

        # If we reach here and sub-orders are empty, it means the current movement leg has finished.
        # Transition to the next phase of the patrol loop.
        wps = self.parameters.get("waypoints", [])
        num_wps = len(wps)
        self.current_waypoint_index = (self.current_waypoint_index + 1) % (num_wps + 1)
        self._spawn_move_to_current_waypoint()

        idx = self.current_waypoint_index
        if idx < num_wps:
            logger.debug(f"[{self.unit.name}] Patrol leg completed. Heading to waypoint {idx}: {wps[idx]['position']}")
        else:
            logger.debug(f"[{self.unit.name}] Patrol leg completed. Returning to start: {self.start_position}")

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

    def update(self, galaxy_ref: 'Galaxy') -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            super().update(galaxy_ref)
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id) if target_unit_id else None

        if not target_unit or target_unit.current_hit_points <= 0:
            super().update(galaxy_ref)
            return

        weapons = self.unit.weapons_component
        if not weapons or not weapons.turrets:
            super().update(galaxy_ref)
            return

        min_turret_range = min(turret.range for turret in weapons.turrets)

        in_the_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        
        in_range = False
        if in_the_same_system_and_hex:
            for turret in weapons.turrets:
                if distance(self.unit.position, target_unit.position) < turret.range:
                    in_range = True
                    break

        # Check if we have an active movement sub-order
        has_movement_order = False
        if self.sub_orders:
            current_sub = self.sub_orders[0]
            if current_sub.order_type == OrderType.MOVE:
                has_movement_order = True
                dest_system = current_sub.parameters.get("destination_system_name")
                dest_hex = current_sub.parameters.get("destination_hex_coord")
                dest_pos = current_sub.parameters.get("destination_position")

                # If we are now in the same system and hex, and already within range, we should cancel the movement sub-order.
                if in_the_same_system_and_hex and in_range:
                    logger.debug(f"[{self.unit.name}] Target {target_unit.name} is in weapon range. Cancelling movement.")
                    current_sub.cancel()
                    self.sub_orders.popleft()
                    if self.unit.engines_component:
                        self.unit.engines_component.move_target = None
                    if self.unit.hyperdrive_component:
                        self.unit.hyperdrive_component.hex_jump_target = None
                        self.unit.hyperdrive_component.wormhole_jump_target = None
                    has_movement_order = False
                else:
                    # Otherwise, check if target has moved away from our movement destination parameters
                    target_moved = False
                    if dest_system != target_unit.in_system or dest_hex != target_unit.in_hex:
                        target_moved = True
                    elif dest_pos:
                        current_offset = distance(dest_pos, target_unit.position)
                        if abs(current_offset - (min_turret_range - 5.0)) > 15.0:
                            target_moved = True

                    if target_moved:
                        logger.debug(f"[{self.unit.name}] Target {target_unit.name} moved. Recalculating path.")
                        current_sub.cancel()
                        self.sub_orders.popleft()
                        if self.unit.engines_component:
                            self.unit.engines_component.move_target = None
                        if self.unit.hyperdrive_component:
                            self.unit.hyperdrive_component.hex_jump_target = None
                            self.unit.hyperdrive_component.wormhole_jump_target = None
                        has_movement_order = False

        # If we don't have a movement order, check if we need to move
        if not has_movement_order:
            if not in_the_same_system_and_hex or not in_range:
                dest_pos = move_towards_position(self.unit.position, target_unit.position, min_turret_range - 5.0)
                move_params = {
                    "destination_system_name": target_unit.in_system,
                    "destination_hex_coord": target_unit.in_hex,
                    "destination_position": dest_pos
                }
                move_order = MoveOrder(self.unit, move_params, parent_order=self)
                self.add_sub_order(move_order)

        super().update(galaxy_ref)



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

class ProtectOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.PROTECT, parameters, parent_order)

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
        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id) if target_unit_id else None

        if not target_unit:
            self.status = OrderStatus.FAILED
            logger.debug(f"PROTECT order failed: Target unit {target_unit_id} not found.")
            return

        if target_unit.owner != self.unit.owner:
            self.status = OrderStatus.FAILED
            logger.debug(f"PROTECT order failed: Target unit {target_unit.name} is not friendly.")
            return

    def _find_nearby_enemy(self, galaxy_ref: 'Galaxy', target_unit: 'Unit') -> Optional['Unit']:
        weapons = self.unit.weapons_component
        if not weapons or weapons.is_destroyed or not weapons.turrets:
            return None

        from unit_components import TurretVariant, WingType

        # The protector must be in the same system and hex as the protected unit to search for enemies
        if self.unit.in_system != target_unit.in_system or self.unit.in_hex != target_unit.in_hex:
            return None

        system = galaxy_ref.systems.get(self.unit.in_system)
        if not system:
            return None

        hex_obj = system.hexes.get(self.unit.in_hex)
        if not hex_obj:
            return None

        closest_enemy = None
        min_dist = float('inf')

        # Any enemy that gets closer than 1000.0 to the protected ship is a valid target.
        detection_range = 1000.0

        for candidate in hex_obj.units:
            if candidate.owner != self.unit.owner and candidate.current_hit_points > 0:
                # Fighter/Bomber targeting rules
                if self.unit.hull_size == HullSize.STRIKECRAFT_WING:
                    wing_comp = self.unit.strikecraft_wing_component
                    if wing_comp:
                        if wing_comp.wing_type == WingType.FIGHTER:
                            if candidate.hull_size != HullSize.STRIKECRAFT_WING:
                                continue
                        elif wing_comp.wing_type == WingType.BOMBER:
                            if candidate.hull_size == HullSize.STRIKECRAFT_WING:
                                continue

                can_target = False
                for t in weapons.turrets:
                    if candidate.hull_size == HullSize.STRIKECRAFT_WING and t.variant != TurretVariant.ANTI_STRIKECRAFT:
                        continue
                    can_target = True
                    break

                if not can_target:
                    continue

                dist_to_protector = distance(self.unit.position, candidate.position)
                dist_to_protected = distance(target_unit.position, candidate.position)

                if dist_to_protected < detection_range:
                    if dist_to_protector < min_dist:
                        min_dist = dist_to_protector
                        closest_enemy = candidate

        return closest_enemy

    def update(self, galaxy_ref: 'Galaxy') -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            super().update(galaxy_ref)
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id) if target_unit_id else None

        if not target_unit or target_unit.current_hit_points <= 0:
            self.status = OrderStatus.COMPLETED
            if self.unit.weapons_component:
                self.unit.weapons_component.clear_target()
            return

        # Check if we are currently executing an AttackOrder
        has_attack_order = False
        if self.sub_orders:
            current_sub = self.sub_orders[0]
            if current_sub.order_type == OrderType.ATTACK:
                has_attack_order = True
                enemy_id = current_sub.parameters.get("target_unit_id")
                enemy_unit = self.unit.game.galaxy.get_unit_by_id(enemy_id) if enemy_id else None

                is_in_range = False
                if (enemy_unit and 
                        enemy_unit.current_hit_points > 0 and 
                        enemy_unit.in_system == self.unit.in_system and 
                        enemy_unit.in_hex == self.unit.in_hex and
                        target_unit.in_system == self.unit.in_system and
                        target_unit.in_hex == self.unit.in_hex):
                    dist_to_protected = distance(target_unit.position, enemy_unit.position)
                    if dist_to_protected < 1000.0:
                        is_in_range = True

                if not is_in_range:
                    logger.debug(f"[{self.unit.name}] Protect attack target lost, dead, or out of threat range. Resuming protection.")
                    current_sub.cancel()
                    self.sub_orders.popleft()
                    if self.unit.weapons_component:
                        self.unit.weapons_component.clear_target()
                    has_attack_order = False

        if not has_attack_order:
            # Look for nearby enemies to engage
            nearby_enemy = self._find_nearby_enemy(galaxy_ref, target_unit)
            if nearby_enemy:
                logger.debug(f"[{self.unit.name}] Enemy detected near protected target: {nearby_enemy.name}. Engaging!")
                # Cancel current movement/follow sub-orders
                for sub in list(self.sub_orders):
                    sub.cancel()
                self.sub_orders.clear()
                if self.unit.engines_component:
                    self.unit.engines_component.move_target = None
                if self.unit.hyperdrive_component:
                    self.unit.hyperdrive_component.hex_jump_target = None
                    self.unit.hyperdrive_component.wormhole_jump_target = None

                # Spawn attack order
                attack_params = {"target_unit_id": nearby_enemy.id}
                self.add_sub_order(AttackOrder(self.unit, attack_params, parent_order=self))
            else:
                # If no enemies, handle follow movement
                has_movement_order = False
                if self.sub_orders:
                    current_sub = self.sub_orders[0]
                    if current_sub.order_type in [OrderType.MOVE, OrderType.REACH_WAYPOINT]:
                        has_movement_order = True
                        dest_system = current_sub.parameters.get("destination_system_name")
                        dest_hex = current_sub.parameters.get("destination_hex_coord")
                        dest_pos = current_sub.parameters.get("destination_position")

                        # If protected unit changed system/hex, or moved significantly from movement destination:
                        if (dest_system != target_unit.in_system or
                                dest_hex != target_unit.in_hex or
                                (dest_pos and distance(dest_pos, target_unit.position) > 15.0)):
                            logger.debug(f"[{self.unit.name}] Protected unit {target_unit.name} moved. Recalculating path.")
                            current_sub.cancel()
                            self.sub_orders.popleft()
                            has_movement_order = False

                if has_movement_order:
                    # Cancel movement order if we are already close enough
                    if self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex:
                        dist_to_target = distance(self.unit.position, target_unit.position)
                        if dist_to_target <= 30.0:
                            logger.debug(f"[{self.unit.name}] Close enough to protected unit {target_unit.name}. Stopping movement.")
                            if self.sub_orders:
                                self.sub_orders[0].cancel()
                                self.sub_orders.popleft()
                            if self.unit.engines_component:
                                self.unit.engines_component.move_target = None
                            has_movement_order = False

                if not has_movement_order:
                    in_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
                    dist_to_target = distance(self.unit.position, target_unit.position) if in_same_system_and_hex else float('inf')

                    if not in_same_system_and_hex or dist_to_target > 30.0:
                        move_params = {
                            "destination_system_name": target_unit.in_system,
                            "destination_hex_coord": target_unit.in_hex,
                            "destination_position": Position(target_unit.position.x, target_unit.position.y)
                        }
                        self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))

        super().update(galaxy_ref)

    def check_completion_conditions(self) -> None:
        pass

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

        success = constructor.start_construction(unit_template_name, target_pos, galaxy_ref)
        if not success:
            self.status = OrderStatus.FAILED

    def check_completion_conditions(self) -> None:
        constructor = self.unit.constructor_component
        if not constructor or constructor.current_construction_target is None:
            self.status = OrderStatus.COMPLETED

    def cancel(self) -> None:
        constructor = self.unit.constructor_component
        if constructor and constructor.current_construction_target:
            unit_template_name = constructor.current_construction_target[0]
            buildable = constructor.can_build(unit_template_name)
            if buildable:
                player = next((p for p in self.unit.game.players if p.id == self.unit.owner.id), None)
                if player:
                    player.credits += buildable.cost_credits
                    logger.debug(f"Refunded {buildable.cost_credits} credits to player {player.name} for cancelled construction of {unit_template_name}.")
            constructor.cancel_construction()
        super().cancel()



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
        metal_amount, crystal_amount = self.unit.mining_component.unload_to_refinery(
            unload_metal=is_metal_refinery,
            unload_crystal=is_crystal_refinery
        )

        if is_metal_refinery and metal_amount > 0:
            target_unit.metal_refinery_component.accept_resources(metal_amount)

        if is_crystal_refinery and crystal_amount > 0:
            target_unit.crystal_refinery_component.accept_resources(crystal_amount)

        self.status = OrderStatus.COMPLETED
        logger.debug(f"UNLOAD_RESOURCES order completed: {self.unit.name} unloaded resources to {target_unit.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        # Execution is immediate once in range, so handled above.
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED


class DockOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.DOCK, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_carrier_id = self.parameters.get("target_carrier_id")
        target_name = None
        if target_carrier_id and self.unit and self.unit.game:
            target_carrier = self.unit.game.galaxy.get_unit_by_id(target_carrier_id)
            if target_carrier:
                target_name = target_carrier.name
        state_data["target_carrier_id"] = target_carrier_id
        state_data["target_name"] = target_name
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_carrier_id = self.parameters.get("target_carrier_id")
        target_carrier = self.unit.game.galaxy.get_unit_by_id(target_carrier_id)

        if not target_carrier:
            self.status = OrderStatus.FAILED
            logger.debug(f"DOCK order failed: Target carrier {target_carrier_id} not found.")
            return

        docking_component = None
        if self.unit.hull_size == HullSize.STRIKECRAFT_WING and target_carrier.strikecraft_bay_component:
            docking_component = target_carrier.strikecraft_bay_component
        elif target_carrier.hangar_component:
            docking_component = target_carrier.hangar_component

        if not docking_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"DOCK order failed: Target carrier {target_carrier.name} has no compatible hangar/strikecraftbay for {self.unit.name}.")
            return

        if not docking_component.can_dock(self.unit):
            self.status = OrderStatus.FAILED
            logger.debug(f"DOCK order failed: Target carrier {target_carrier.name} has no space/slots for {self.unit.name}.")
            return

        docking_range = 100.0
        in_same_system_and_hex = (self.unit.in_system == target_carrier.in_system and self.unit.in_hex == target_carrier.in_hex)
        in_range = in_same_system_and_hex and (distance(self.unit.position, target_carrier.position) <= docking_range)

        if not in_range:
            if in_same_system_and_hex:
                dest_pos = move_towards_position(self.unit.position, target_carrier.position, docking_range - 5.0)
            else:
                dest_pos = target_carrier.position

            move_params = {
                "destination_system_name": target_carrier.in_system,
                "destination_hex_coord": target_carrier.in_hex,
                "destination_position": dest_pos
            }
            move_order = MoveOrder(self.unit, move_params, parent_order=self)
            self.add_sub_order(move_order)

            dock_sub_order = DockOrder(self.unit, self.parameters, parent_order=self)
            self.add_sub_order(dock_sub_order)
            return

        success = docking_component.dock(self.unit, galaxy_ref)
        if success:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"Unit {self.unit.name} successfully docked to {target_carrier.name}.")
        else:
            self.status = OrderStatus.FAILED
            logger.debug(f"Docking of {self.unit.name} to {target_carrier.name} failed.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED


class DeployUnitOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.DEPLOY_UNIT, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        docked_unit_id = self.parameters.get("docked_unit_id")
        docked_name = None
        if docked_unit_id and self.unit and self.unit.game:
            docked_units = []
            if self.unit.hangar_component:
                docked_units.extend(self.unit.hangar_component.docked_units)
            if self.unit.strikecraft_bay_component:
                docked_units.extend(self.unit.strikecraft_bay_component.docked_units)
            for du in docked_units:
                if du.id == docked_unit_id:
                    docked_name = du.name
                    break
        state_data["docked_unit_id"] = docked_unit_id
        state_data["docked_name"] = docked_name
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not self.unit.hangar_component and not self.unit.strikecraft_bay_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"DEPLOY_UNIT order failed: Unit {self.unit.name} has no HangarComponent or StrikecraftBayComponent.")
            return

        docked_unit_id = self.parameters.get("docked_unit_id")
        docked_unit = None
        source_component = None
        
        if self.unit.hangar_component:
            for du in self.unit.hangar_component.docked_units:
                if du.id == docked_unit_id:
                    docked_unit = du
                    source_component = self.unit.hangar_component
                    break
        if not docked_unit and self.unit.strikecraft_bay_component:
            for du in self.unit.strikecraft_bay_component.docked_units:
                if du.id == docked_unit_id:
                    docked_unit = du
                    source_component = self.unit.strikecraft_bay_component
                    break

        if not docked_unit:
            self.status = OrderStatus.FAILED
            logger.debug(f"DEPLOY_UNIT order failed: Docked unit {docked_unit_id} not found in hangar or strikecraft bay.")
            return

        success = source_component.deploy(docked_unit, galaxy_ref)
        if success:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"Unit {docked_unit.name} successfully deployed from {self.unit.name}.")
        else:
            self.status = OrderStatus.FAILED
            logger.debug(f"Deployment of {docked_unit.name} from {self.unit.name} failed.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED


class DeployAllWingsOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.DEPLOY_ALL_WINGS, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not self.unit.strikecraft_bay_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"DEPLOY_ALL_WINGS order failed: Unit {self.unit.name} has no StrikecraftBayComponent.")
            return

        comp = self.unit.strikecraft_bay_component
        if not comp.docked_units:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"DEPLOY_ALL_WINGS: No docked strikecraft wings to deploy on {self.unit.name}.")
            return

        docked_copy = list(comp.docked_units)
        success_count = 0
        for docked_unit in docked_copy:
            success = comp.deploy(docked_unit, galaxy_ref)
            if success:
                success_count += 1

        if success_count > 0:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"Successfully deployed {success_count} fighter wings from {self.unit.name}.")
        else:
            self.status = OrderStatus.FAILED
            logger.debug(f"Failed to deploy any fighter wings from {self.unit.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED


class UseAbilityOrder(Order):
    """
    Order to activate a unit's special ability.

    For abilities that require a target unit the order validates range and moves
    the unit closer if necessary before firing. For abilities that require a
    target position, no auto-movement is performed — the position is used directly.
    For self-targeted abilities neither target is required.
    """
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.USE_ABILITY, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        from unit_components import AbilityType, AbilityComponent

        if not self.unit.ability_component:
            logger.debug(f"[{self.unit.name}] USE_ABILITY order failed: unit has no AbilityComponent.")
            self.status = OrderStatus.FAILED
            return

        ability_type_str = self.parameters.get("ability_type")
        if not ability_type_str:
            logger.debug(f"[{self.unit.name}] USE_ABILITY order failed: no ability_type parameter.")
            self.status = OrderStatus.FAILED
            return

        try:
            ability_type = AbilityType(ability_type_str)
        except ValueError:
            logger.debug(f"[{self.unit.name}] USE_ABILITY order failed: unknown ability_type '{ability_type_str}'.")
            self.status = OrderStatus.FAILED
            return

        if not self.unit.ability_component.can_use(ability_type):
            logger.debug(f"[{self.unit.name}] USE_ABILITY order failed: ability {ability_type.name} not ready (on cooldown or already active).")
            self.status = OrderStatus.FAILED
            return

        from unit_components import ABILITY_DEFINITIONS
        defn = ABILITY_DEFINITIONS.get(ability_type)
        if not defn:
            self.status = OrderStatus.FAILED
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_position = self.parameters.get("target_position")

        # --- Pre-validation for CAPTURE_UNIT ability ---
        if ability_type == AbilityType.CAPTURE_UNIT and target_unit_id is not None:
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if target_unit:
                if target_unit.owner == self.unit.owner:
                    logger.debug(f"[{self.unit.name}] USE_ABILITY: target unit {target_unit.name} is already friendly.")
                    self.status = OrderStatus.FAILED
                    return
                if target_unit.engines_component is not None:
                    engines_disabled = target_unit.engines_component.is_destroyed or target_unit.is_disabled
                    if not engines_disabled:
                        logger.debug(f"[{self.unit.name}] USE_ABILITY: target {target_unit.name} engines are not disabled.")
                        self.status = OrderStatus.FAILED
                        return
                from unit_components import Defenses
                if target_unit.weapons_component and not target_unit.weapons_component.is_destroyed:
                    logger.debug(f"[{self.unit.name}] USE_ABILITY: target {target_unit.name} weapons are active.")
                    self.status = OrderStatus.FAILED
                    return
                defenses = target_unit.get_component(Defenses)
                if defenses and not defenses.is_destroyed:
                    logger.debug(f"[{self.unit.name}] USE_ABILITY: target {target_unit.name} defenses are active.")
                    self.status = OrderStatus.FAILED
                    return

        # --- Range check for unit-targeted abilities ---
        if defn.requires_target_unit and target_unit_id is not None:
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if not target_unit or target_unit.current_hit_points <= 0:
                logger.debug(f"[{self.unit.name}] USE_ABILITY: target unit {target_unit_id} not found or dead.")
                self.status = OrderStatus.FAILED
                return

            in_same_hex = (self.unit.in_system == target_unit.in_system and
                           self.unit.in_hex == target_unit.in_hex)
            in_range = in_same_hex and (distance(self.unit.position, target_unit.position) <= defn.range)

            if not in_range:
                if not self.has_active_sub_orders():
                    dest_pos = move_towards_position(self.unit.position, target_unit.position, defn.range - 5.0)
                    move_params = {
                        "destination_system_name": target_unit.in_system,
                        "destination_hex_coord": target_unit.in_hex,
                        "destination_position": dest_pos,
                    }
                    self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))
                    # Re-queue this ability order to fire once in range
                    self.add_sub_order(UseAbilityOrder(self.unit, self.parameters, parent_order=self))
                return

        # --- Range check for position-targeted abilities ---
        elif defn.requires_target_position and target_position is not None:
            target_sys = self.parameters.get("target_system_name") or self.unit.in_system
            target_hex = self.parameters.get("target_hex_coord") or self.unit.in_hex

            in_same_hex = (self.unit.in_system == target_sys and
                           self.unit.in_hex == target_hex)
            in_range = in_same_hex and (distance(self.unit.position, target_position) <= defn.range)

            if not in_range:
                if not self.has_active_sub_orders():
                    if in_same_hex:
                        dest_pos = move_towards_position(self.unit.position, target_position, defn.range - 5.0)
                    else:
                        dest_pos = target_position
                    
                    move_params = {
                        "destination_system_name": target_sys,
                        "destination_hex_coord": target_hex,
                        "destination_position": dest_pos,
                    }
                    self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))
                    # Re-queue this ability order to fire once in range
                    self.add_sub_order(UseAbilityOrder(self.unit, self.parameters, parent_order=self))
                return

        # --- Activate the ability ---
        success = self.unit.ability_component.activate(
            ability_type=ability_type,
            galaxy=galaxy_ref,
            target_unit_id=target_unit_id,
            target_position=target_position,
            target_system_name=self.parameters.get("target_system_name"),
            target_hex_coord=self.parameters.get("target_hex_coord"),
        )
        if success:
            logger.debug(f"[{self.unit.name}] USE_ABILITY: {ability_type.name} activated successfully.")
            self.status = OrderStatus.COMPLETED
        else:
            logger.debug(f"[{self.unit.name}] USE_ABILITY: {ability_type.name} activation failed.")
            self.status = OrderStatus.FAILED

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED


class ContinuousMineOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.CONTINUOUS_MINE, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_id = self.parameters.get("target_id")
        if not target_id:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CONTINUOUS_MINE order failed: no target_id.")
            return

        target = galaxy_ref.get_celestial_body_by_id(target_id)
        if not target:
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CONTINUOUS_MINE order failed: Celestial body with ID {target_id} not found.")
            return

        if not getattr(self.unit, 'mining_component', None):
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name}] CONTINUOUS_MINE order failed: Unit has no MiningComponent.")
            return

        mining_comp = self.unit.mining_component
        if mining_comp.get_cargo_fullness() >= 1.0:
            refinery = self._find_closest_refinery(galaxy_ref)
            if not refinery:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name}] CONTINUOUS_MINE order failed: Cargo full but no refinery found.")
                return
            self._spawn_unload_order(refinery.id)
        else:
            self._spawn_mine_order(target_id)

    def _spawn_mine_order(self, target_id: str) -> None:
        mine_params = {"target_id": target_id}
        self.add_sub_order(MineOrder(self.unit, mine_params, parent_order=self))

    def _spawn_unload_order(self, refinery_id: typing.Union[str, int]) -> None:
        unload_params = {"target_unit_id": refinery_id}
        self.add_sub_order(UnloadResourcesOrder(self.unit, unload_params, parent_order=self))

    def _find_closest_refinery(self, galaxy_ref: 'Galaxy') -> Optional['Unit']:
        mining_comp = self.unit.mining_component
        if not mining_comp:
            return None

        has_metal = mining_comp.raw_metal_cargo > 0
        has_crystal = mining_comp.raw_crystal_cargo > 0

        target = galaxy_ref.get_celestial_body_by_id(self.parameters.get("target_id"))
        from entities import Asteroid, AsteroidField, Moon
        if not has_metal and not has_crystal and target:
            if isinstance(target, (Asteroid, AsteroidField)):
                has_metal = True
            elif isinstance(target, Moon):
                has_crystal = True

        friendly_refineries = []
        for system in galaxy_ref.systems.values():
            for hex_obj in system.hexes.values():
                for u in hex_obj.units:
                    if u.owner == self.unit.owner:
                        is_metal_ref = getattr(u, 'metal_refinery_component', None) is not None
                        is_crystal_ref = getattr(u, 'crystal_refinery_component', None) is not None
                        if (has_metal and is_metal_ref) or (has_crystal and is_crystal_ref):
                            friendly_refineries.append(u)

        if not friendly_refineries:
            return None

        def get_dist_to_refinery(refinery):
            if self.unit.in_system == refinery.in_system:
                if self.unit.in_hex == refinery.in_hex:
                    return distance(self.unit.position, refinery.position)
                else:
                    return hex_distance(self.unit.in_hex, refinery.in_hex) * 10000.0
            else:
                path = find_intersystem_path(galaxy_ref.system_graph, self.unit.in_system, refinery.in_system, self.unit.hull_size)
                if path is None:
                    return float('inf')
                return (len(path) - 1) * 1000000.0 + hex_distance(self.unit.in_hex, refinery.in_hex) * 10000.0

        nearest_refinery = None
        min_dist = float('inf')
        for r in friendly_refineries:
            dist = get_dist_to_refinery(r)
            if dist < min_dist:
                min_dist = dist
                nearest_refinery = r

        return nearest_refinery

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return

        if not self.sub_orders:
            galaxy_ref = self.unit.game.galaxy
            target_id = self.parameters.get("target_id")
            
            mining_comp = self.unit.mining_component
            if not mining_comp:
                self.status = OrderStatus.FAILED
                return

            if mining_comp.get_cargo_fullness() >= 1.0:
                refinery = self._find_closest_refinery(galaxy_ref)
                if not refinery:
                    self.status = OrderStatus.FAILED
                    logger.debug(f"[{self.unit.name}] ContinuousMineOrder failed: cargo full, no refinery found.")
                    return
                self._spawn_unload_order(refinery.id)
                logger.debug(f"[{self.unit.name}] ContinuousMineOrder: cargo full. Heading to refinery {refinery.name} (id:{refinery.id}).")
            else:
                self._spawn_mine_order(target_id)
                logger.debug(f"[{self.unit.name}] ContinuousMineOrder: cargo has space. Heading back to mine target {target_id}.")
