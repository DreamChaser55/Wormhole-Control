import typing
from typing import Dict, Optional, Any, TYPE_CHECKING, Deque, List
from enum import Enum, auto
import uuid
from collections import deque
import random
import math

from utils import HexCoord, timeit
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
        self.parameters = parameters or {} # e.g., {"destination_system_name": "Sol", "destination_hex_coord": (0,1), "destination_position": (100.5, -50.2)}
        self.status = OrderStatus.PENDING
        self.sub_orders: Deque['Order'] = deque()
        self.parent_order = parent_order

    def get_info_text(self) -> List[str]:
        """Returns a list of formatted HTML text lines for this order for display in UI."""
        order_type_name = self.order_type.name

        # Define colors for styling
        MOVE_TYPE_COLOR = "#87CEEB"    # Cyan for Move order type
        WAYPOINT_TYPE_COLOR = "#98FB98" # Green for Waypoint order type
        ATTACK_TYPE_COLOR = "#FF0000"   # Red for Attack order type
        TOGGLE_INHIBITOR_TYPE_COLOR = "#A020F0" # Purple for Toggle Inhibitor type
        TOGGLE_INHIBITOR_ON_COLOR = "#90EE90" # Light Green for Inhibitor Activate
        TOGGLE_INHIBITOR_OFF_COLOR = "#F08080" # Light Red for Inhibitor Deactivate
        PATROL_TYPE_COLOR = "#DAA520" # Goldenrod for Patrol (example)
        COLONIZE_COLOR = "#FFD700" # Gold for Colonize
        LOAD_COLONISTS_COLOR = "#ADD8E6" # Light Blue for Load Colonists
        INFO_COLOR = "#D3D3D3"       # Light Gray for general info (destinations, targets, hex/pos)

        if order_type_name == "MOVE":
            dsys = self.parameters.get("destination_system_name", "N/A")
            dhex = self.parameters.get("destination_hex_coord", "N/A")
            dpos_param = self.parameters.get("destination_position", None)
            dpos_str = f"({dpos_param.x:.1f}, {dpos_param.y:.1f})" if isinstance(dpos_param, Position) else "N/A"

            move_type_styled = f"<font color='{MOVE_TYPE_COLOR}'><b>Move:</b></font>"
            dsys_styled = f"<font color='{INFO_COLOR}'><i>{dsys}</i></font>" if dsys != "N/A" else f"<font color='{INFO_COLOR}'>N/A</font>"
            dhex_styled = f"<font color='{INFO_COLOR}'>{dhex}</font>"
            dpos_styled = f"<font color='{INFO_COLOR}'>{dpos_str}</font>"
            return [
                move_type_styled,
                f"  Sys: {dsys_styled}",
                f"  Hex: {dhex_styled}",
                f"  Pos: {dpos_styled}"
            ]

        elif order_type_name == "REACH_WAYPOINT":
            dsys = self.parameters.get("destination_system_name", "N/A")
            dhex = self.parameters.get("destination_hex_coord", "N/A")
            dpos_param = self.parameters.get("destination_position", None)
            dpos_str = f"({dpos_param.x:.1f}, {dpos_param.y:.1f})" if isinstance(dpos_param, Position) else "N/A"

            waypoint_type_styled = f"<font color='{WAYPOINT_TYPE_COLOR}'><b>Waypoint:</b></font>"
            dsys_styled = f"<font color='{INFO_COLOR}'><i>{dsys}</i></font>" if dsys != "N/A" else f"<font color='{INFO_COLOR}'>N/A</font>"
            dhex_styled = f"<font color='{INFO_COLOR}'>{dhex}</font>"
            dpos_styled = f"<font color='{INFO_COLOR}'>{dpos_str}</font>"
            return [
                waypoint_type_styled,
                f"  Sys: {dsys_styled}",
                f"  Hex: {dhex_styled}",
                f"  Pos: {dpos_styled}"
            ]

        elif order_type_name == "TOGGLE_INHIBITOR":
            turn_on = self.parameters.get("turn_on", False)
            action = "Activate" if turn_on else "Deactivate"
            status_color = TOGGLE_INHIBITOR_ON_COLOR if turn_on else TOGGLE_INHIBITOR_OFF_COLOR
            action_styled = f"<font color='{status_color}'>{action}</font>"
            toggle_inhibitor_type_styled = f"<font color='{TOGGLE_INHIBITOR_TYPE_COLOR}'><b>Toggle Inhibitor:</b></font>"
            return [f"{toggle_inhibitor_type_styled} {action_styled}"]

        elif order_type_name == "PATROL":
            patrol_type_styled = f"<font color='{PATROL_TYPE_COLOR}'><b>🔄 Patrol:</b></font>"
            return [f"{patrol_type_styled} <font color='{INFO_COLOR}'><i>(Details TBD)</i></font>"]

        elif order_type_name == "ATTACK":
            target_unit_id = self.parameters.get("target_unit_id")
            target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>Unknown Target</i></font>"
            if target_unit_id and self.unit and self.unit.game:
                target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
                if target_unit:
                    target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>{target_unit.name}</i></font>"
                else:
                    target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_unit_id} (Not found)</i></font>"
            elif target_unit_id:
                 target_unit_name_styled = f"<font color='{INFO_COLOR}'><i>Target ID: {target_unit_id}</i></font>"

            attack_type_styled = f"<font color='{ATTACK_TYPE_COLOR}'><b>Attack:</b></font>"
            return [f"{attack_type_styled} {target_unit_name_styled}"]

        elif order_type_name == "COLONIZE":
            target_name = self.parameters.get("target_name", "Unknown Target")
            colonize_type_styled = f"<font color='{COLONIZE_COLOR}'><b>Colonize:</b></font>"
            target_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
            return [f"{colonize_type_styled} {target_styled}"]

        elif order_type_name == "LOAD_COLONISTS":
            target_name = self.parameters.get("target_name", "Unknown Target")
            load_type_styled = f"<font color='{LOAD_COLONISTS_COLOR}'><b>Load Colonists:</b></font>"
            target_styled = f"<font color='{INFO_COLOR}'><i>{target_name}</i></font>"
            return [f"{load_type_styled} {target_styled}"]

        else:
            # Default styling for other order types
            return [f"<font color='{INFO_COLOR}'>{order_type_name} ({self.status.name})</font>"]

    def add_sub_order(self, sub_order: 'Order') -> None:
        """Add a sub-order to this order's queue."""
        sub_order.parent_order = self
        sub_order.unit = self.unit
        self.sub_orders.append(sub_order)
        print(f"  Added sub-order {sub_order.order_type.name} (id:{sub_order.order_id}) to order {self.order_type.name} (id:{self.order_id}) for unit {self.unit.name} (id:{self.unit.id}).")
        
    def remove_sub_order(self, order_id: str) -> bool:
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
            
        # Check if all sub-orders are completed
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
        # 1. Process active sub-orders
        while self.sub_orders:
            current_sub_order = self.sub_orders[0]  # Front of the deque

            if current_sub_order.status == OrderStatus.PENDING:
                current_sub_order.execute(galaxy_ref=galaxy_ref)
                # execute() will change its status to IN_PROGRESS, COMPLETED, or FAILED.

            # If IN_PROGRESS after execute()...
            if current_sub_order.status == OrderStatus.IN_PROGRESS:
                current_sub_order.update(galaxy_ref=galaxy_ref)  # ...run recursive update()

            # If the sub-order is now finished, remove it and continue the loop
            # to process the next sub-order in the same parent update cycle.
            if current_sub_order.status in [OrderStatus.COMPLETED, OrderStatus.FAILED, OrderStatus.CANCELLED]:
                self.sub_orders.popleft()
                # Loop continues to process the new front of the deque, if any
            else:
                # If the current sub-order is still IN_PROGRESS (and its own update didn't complete it),
                # then the parent order must wait for this sub-order.
                # No further sub-orders or the parent order's own logic can proceed this turn.
                return

        # 2. If all sub-orders are completed (deque is empty), proceed with this order's own logic to check completion conditions.
        if self.status == OrderStatus.IN_PROGRESS:
            self.check_completion_conditions() # this method might change self.status

    def cancel(self) -> None:
        """Cancel this order and all its sub-orders."""
        self.status = OrderStatus.CANCELLED
        
        for sub_order in self.sub_orders:
            sub_order.cancel()
    
    def check_completion_conditions(self) -> None:
        """
        Check order-specific completion conditions and update status.
        """
        if self.status != OrderStatus.IN_PROGRESS:
            return

        if self.order_type == OrderType.MOVE:
            # A MOVE order is complete if it was IN_PROGRESS and all its sub-orders are now finished (no REACH_WAYPOINTs remain in the deque). We also check if the unit actually reached the destination.

            csys = self.unit.in_system
            chex = self.unit.in_hex
            cpos = self.unit.position
            
            dsys = self.parameters["destination_system_name"]
            dhex = self.parameters["destination_hex_coord"]
            dpos: Position = self.parameters["destination_position"]
            
            if not self.sub_orders and csys == dsys and chex == dhex and distance(cpos, dpos) < 0.01:
                # Check if the sub-order deque is empty and if the unit is at the destination position
                self.status = OrderStatus.COMPLETED
                print(f"[{self.unit.name} (id:{self.unit.id})] Order.check_completion_conditions: {self.order_type.name} (id:{self.order_id}): COMPLETED (all sub-orders finished, unit reached destination).")
            else:
                print(f"[{self.unit.name} (id:{self.unit.id})] Order.check_completion_conditions: {self.order_type.name} (id:{self.order_id}): IN_PROGRESS (sub-orders not finished and/or unit has not reached destination).")

            return  # Return, as MOVE's own check is done.
        
        elif self.order_type == OrderType.TOGGLE_INHIBITOR:
            # This order is atomic and its status is set to COMPLETED or FAILED within _execute.
            # No further checks are needed here.
            return

        elif self.order_type == OrderType.REACH_WAYPOINT:
            # REACH_WAYPOINT sub-order is complete when the unit reaches the destination position.
            csys = self.unit.in_system
            chex = self.unit.in_hex
            cpos = self.unit.position
            
            dsys = self.parameters["destination_system_name"]
            dhex = self.parameters["destination_hex_coord"]
            dpos: Position = self.parameters["destination_position"]
            
            if csys == dsys and chex == dhex and distance(cpos, dpos) < 0.01:
                # If the unit is at destination position, change REACH_WAYPOINT order status to COMPLETED and clear active engines and hyperdrive movement targets.
                if self.unit.engines_component:
                    self.unit.engines_component.move_target = None
                if self.unit.hyperdrive_component:
                    self.unit.hyperdrive_component.hex_jump_target = None
                    self.unit.hyperdrive_component.wormhole_jump_target = None
                self.status = OrderStatus.COMPLETED
                print(f"[{self.unit.name} (id:{self.unit.id})] Order.check_completion_conditions: {self.order_type.name} (id:{self.order_id}): COMPLETED (arrived at waypoint: {dpos}:Hex{dhex}:{dsys})")
                return

        elif self.order_type == OrderType.PATROL:
            # Implement patrol completion logic
            pass

        elif self.order_type == OrderType.ATTACK:
            target_unit_id = self.parameters["target_unit_id"]
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if not target_unit or target_unit.current_hit_points <= 0:
                self.status = OrderStatus.COMPLETED

        elif self.order_type == OrderType.COLONIZE:
            target_id = self.parameters["target_id"]
            target = self.unit.game.galaxy.get_celestial_body_by_id(target_id)
            if target and target.owner == self.unit.owner:
                self.status = OrderStatus.COMPLETED

        elif self.order_type == OrderType.LOAD_COLONISTS:
            # LOAD_COLONISTS order should perform the load immidiately in its execute method (if unit is in the target planet's hex), or enqueue an order to move to the target planet and then enqueue another order to LOAD_COLONISTS there. Thus, if it has no sub-orders, it should be completed
            if not self.sub_orders:
                self.status = OrderStatus.COMPLETED

        # Other order types need their own logic here
        
    def __repr__(self) -> str:
        return f"Order(type={self.order_type.name}, status={self.status.name}, id={self.order_id[:8]})"

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        """Execute this order based on its type."""
        if self.status != OrderStatus.PENDING:
            return
        
        self.status = OrderStatus.IN_PROGRESS

        print(f"[{self.unit.name} (id:{self.unit.id})] Order.execute: {self.order_type.name} (id:{self.order_id}): Executing order.")

        if self.order_type == OrderType.MOVE:
            self.plan_route(galaxy_ref=galaxy_ref)
        elif self.order_type == OrderType.REACH_WAYPOINT:
            self._execute_reach_waypoint(galaxy_ref=galaxy_ref)
        elif self.order_type == OrderType.TOGGLE_INHIBITOR:
            self._execute_toggle_inhibitor(galaxy_ref=galaxy_ref)
        elif self.order_type == OrderType.PATROL:
            self._execute_patrol()
        elif self.order_type == OrderType.ATTACK:
            self._execute_attack(galaxy_ref=galaxy_ref)
        elif self.order_type == OrderType.COLONIZE:
            self._execute_colonize(galaxy_ref=galaxy_ref)
        elif self.order_type == OrderType.LOAD_COLONISTS:
            self._execute_load_colonists(galaxy_ref=galaxy_ref)
        elif self.order_type == OrderType.CONSTRUCT:
            self._execute_construct(galaxy_ref=galaxy_ref)
        # Add execution methods for other order types as needed

    # --- MOVE order methods ---

    def find_wormhole_to_system(self, current_system_name: str, target_system_name: str, galaxy_ref: 'Galaxy') -> Optional['Wormhole']:
        if not galaxy_ref: return None
        for wh_id, wormhole_obj in galaxy_ref.wormholes.items():
            if wormhole_obj.in_system == current_system_name and \
               wormhole_obj.exit_system_name == target_system_name:
                return wormhole_obj
        return None
    
        # --- Helper function to handle inhibited waypoints ---
    def handle_inhibited_waypoint(self, target_hex: HexCoord, target_pos: Position, is_final_destination: bool, system_name: str, galaxy_ref: 'Galaxy'):
        destination_hex_obj = galaxy_ref.systems[system_name].hexes.get(target_hex)
        if not destination_hex_obj:
            # If hex doesn't exist, print an error
            print(f"[{self.unit.name} (id:{self.unit.id})] _plan_hex_jump_sequence->handle_inhibited_waypoint: ERROR: Destination hex {target_hex} not found in system {system_name}.")
            return

        for zone in destination_hex_obj.get_all_inhibition_zones():
            if is_point_in_circle(target_pos, zone):
                # Waypoint is inhibited.
                adjusted_pos = get_closest_point_on_circle_edge(target_pos, zone)
                print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Waypoint {target_pos} in {target_hex} is inhibited. Adjusting landing position to {adjusted_pos}.")
                
                # Add REACH_WAYPOINT for the jump to the adjusted (safe) position.
                self.add_sub_order(Order(self.unit, OrderType.REACH_WAYPOINT, {
                    "destination_system_name": system_name,
                    "destination_hex_coord": target_hex,
                    "destination_position": adjusted_pos
                }, parent_order=self))

                # If this was the final destination, add a second sub-order for sub-light travel
                # from the adjusted position to the original (inhibited) target position.
                if is_final_destination:
                    print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Adding sub-light move from {adjusted_pos} to original target {target_pos}.")
                    self.add_sub_order(Order(self.unit, OrderType.REACH_WAYPOINT, {
                        "destination_system_name": system_name,
                        "destination_hex_coord": target_hex,
                        "destination_position": target_pos # The original, inhibited position
                    }, parent_order=self))
                return # Exit after handling the first inhibition zone found.
        
        # If no inhibition zone was found, add the waypoint normally.
        self.add_sub_order(Order(self.unit, OrderType.REACH_WAYPOINT, {
            "destination_system_name": system_name,
            "destination_hex_coord": target_hex,
            "destination_position": target_pos
        }, parent_order=self))

    def plan_hex_jump_sequence(self, start_hex: HexCoord, end_hex: HexCoord, end_pos: Position, system_name: str, galaxy_ref: 'Galaxy') -> None:
        """
        Helper method to create one or more REACH_WAYPOINT sub-orders for a hex jump,
        respecting the unit's jump range.
        If the final destination is inhibited, it will create a jump to the edge of the
        inhibition zone, followed by a sub-light move to the final destination.
        """
        print(f"  [plan_route->plan_hex_jump_sequence] Planning hex jump sequence from {start_hex} to {end_hex} in system {system_name}.")
        if not self.unit.hyperdrive_component:
            self.status = OrderStatus.FAILED
            print(f"[{self.unit.name} (id:{self.unit.id})] _plan_hex_jump_sequence: FAILED (no hyperdrive).")
            return

        jump_range = self.unit.hyperdrive_component.jump_range
        distance_to_jump = hex_distance(start_hex, end_hex)

        # --- Main logic for planning jumps ---
        if distance_to_jump <= jump_range:
            # Single jump
            print(f"  [plan_route->plan_hex_jump_sequence] Jump is within range ({distance_to_jump} <= {jump_range}). Planning a single jump.")
            self.handle_inhibited_waypoint(end_hex, end_pos, is_final_destination=True, system_name=system_name, galaxy_ref=galaxy_ref)
            print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Added sub-order(s) for single jump to hex {end_hex}.")
        else:
            # Multi-stage jump
            print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Jump to {end_hex} is out of range ({distance_to_jump} > {jump_range}). Planning multi-stage inter-hex jump.")
            waypoints = find_hex_jump_path(start_hex, end_hex, jump_range)
            print(f"  [plan_route->plan_hex_jump_sequence] Multi-stage jump waypoints from find_hex_jump_path: {waypoints}")
            
            for i, waypoint_hex in enumerate(waypoints):
                is_final = (i == len(waypoints) - 1)
                # For intermediate waypoints, target the center of the hex. For the final one, use the specified end_pos.
                waypoint_pos = end_pos if is_final else hex_to_pixel(waypoint_hex[0], waypoint_hex[1])
                
                self.handle_inhibited_waypoint(waypoint_hex, waypoint_pos, is_final_destination=is_final, system_name=system_name, galaxy_ref=galaxy_ref)
                print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Added waypoint {i+1}/{len(waypoints)} at hex {waypoint_hex}.")

    def plan_route(self, galaxy_ref: 'Galaxy') -> None: # This is pretty much the execute_move() method
        """
        Executes a MOVE order. Contains core logic to determine the REACH_WAYPOINT sub-orders for this MOVE order.
        It will create one or more REACH_WAYPOINT sub-orders (as needed for the movement steps),
        or mark the order as completed/failed if a route cannot be planned or is already complete.
        """
        print(f"\n--- Planning route for {self.unit.name} (id:{self.unit.id}) ---")
        if not self.unit or not galaxy_ref:
            self.status = OrderStatus.FAILED
            print(f"[{self.unit.name if self.unit else 'Unknown Unit'}] MOVE(id:{self.order_id}): plan_route: FAILED (no unit or galaxy_ref).")
            return

        # Get current location status
        csys = self.unit.in_system
        chex = self.unit.in_hex
        cpos = self.unit.position

        # Get destination parameters
        dsys = self.parameters["destination_system_name"]
        dhex = self.parameters["destination_hex_coord"]
        dpos: Optional[Position] = self.parameters["destination_position"]

        print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: From: {csys}:{chex}:{cpos} | To: {dsys}:{dhex}:{dpos}")

        if dsys is None or dhex is None or dpos is None:
            self.status = OrderStatus.FAILED
            print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (incomplete destination parameters).")
            return

        # Check if already at the final destination
        if csys == dsys and chex == dhex and distance(cpos, dpos) < 0.01:  # Small threshold for floating point precision
            self.status = OrderStatus.COMPLETED
            print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: COMPLETED (already at destination {dsys}:{dhex}:{dpos}).")
            return

        # --- Pre-planning checks for hyperspace jumps ---
        # If a jump is required (different system or hex), check if the starting position is inhibited.
        if csys != dsys or chex != dhex:
            current_hex_obj = galaxy_ref.systems[csys].hexes.get(chex)
            if current_hex_obj:
                for zone in current_hex_obj.get_all_inhibition_zones():
                    if is_point_in_circle(cpos, zone):
                        # Current position is inhibited. Plan a sub-light move to the edge of the inhibition zone first.
                        escape_pos = get_closest_point_on_circle_edge(cpos, zone)
                        print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Start position {cpos} is inhibited. Planning escape move to {escape_pos}.")
                        self.add_sub_order(Order(self.unit, OrderType.REACH_WAYPOINT, {
                            "destination_system_name": csys,
                            "destination_hex_coord": chex,
                            "destination_position": escape_pos
                        }, parent_order=self))
                        # After planning the escape, the rest of the route planning can proceed.
                        # The unit will first execute the escape maneuver, and on subsequent turns,
                        # the jump orders will execute from the new, uninhibited position.
                        break # Found an inhibition zone, no need to check others.

        # 1. Inter-system travel: Destination is in a different system
        if csys != dsys:
            if not self.unit.hyperdrive_component:
                self.status = OrderStatus.FAILED
                print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (cannot jump system, no hyperdrive).")
                return

            # First, check for a direct wormhole
            print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Checking for direct wormhole from {csys} to {dsys}...")
            direct_wormhole = self.find_wormhole_to_system(csys, dsys, galaxy_ref)

            if direct_wormhole:
                # Direct jump possible
                print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Direct wormhole from {csys} to {dsys} found: {direct_wormhole.name}. Planning a single inter-system jump.")
                exit_wh = galaxy_ref.wormholes[direct_wormhole.exit_wormhole_id]
                if not exit_wh:
                    self.status = OrderStatus.FAILED
                    print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (could not find exit for direct wormhole {direct_wormhole.id} in {dsys}).")
                    return

                # 1.1. Sub-order(s) to reach wormhole
                if chex != direct_wormhole.in_hex:
                    # If not in the right hex, plan the sequence of jumps to get there.
                    # This sequence will include the final move to the wormhole's exact position.
                    self.plan_hex_jump_sequence(chex, direct_wormhole.in_hex, direct_wormhole.position, csys, galaxy_ref)
                else:
                    # If already in the correct hex, just plan a sub-light move to the wormhole's position.
                    self.add_sub_order(Order(self.unit, OrderType.REACH_WAYPOINT, {
                        "destination_system_name": csys,
                        "destination_hex_coord": direct_wormhole.in_hex,
                        "destination_position": direct_wormhole.position
                    }, parent_order=self))
                    print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Added sub-order to move to direct wormhole position.")

                # 1.2. Sub-order to jump through wormhole
                self.add_sub_order(Order(self.unit, OrderType.REACH_WAYPOINT, {
                    "destination_system_name": dsys, # Target system for jump
                    "destination_hex_coord": exit_wh.in_hex,    # Arrival hex in target system
                    "destination_position": exit_wh.position  # Arrival position in target system
                }, parent_order=self))
                print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Added sub-order to jump through direct wormhole to {dsys}.")

                # 1.3. Check if wormhole exit is inhibited and add sub-light move if needed
                arrival_pos = exit_wh.position
                arrival_hex_obj = galaxy_ref.systems[dsys].hexes[exit_wh.in_hex]
                if arrival_hex_obj:
                    for zone in arrival_hex_obj.get_all_inhibition_zones():
                        if is_point_in_circle(arrival_pos, zone):
                            # Move out of the inhibition zone to a random point just outside its radius
                            angle = random.uniform(0, 2 * math.pi)
                            # Move slightly more than the radius to be safely outside
                            safe_distance = zone.radius + 1.0
                            safe_pos_x = arrival_pos.x + safe_distance * math.cos(angle)
                            safe_pos_y = arrival_pos.y + safe_distance * math.sin(angle)
                            safe_pos = Position(safe_pos_x, safe_pos_y)

                            self.add_sub_order(Order(self.unit, OrderType.REACH_WAYPOINT, {
                                "destination_system_name": dsys,
                                "destination_hex_coord": exit_wh.in_hex,
                                "destination_position": safe_pos
                            }, parent_order=self))
                            print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Wormhole exit is inhibited. Adding sub-light move to safe position: {safe_pos}.")
                            arrival_pos = safe_pos # Update arrival_pos for subsequent planning
                            break

                # 1.4. Sub-order(s) to move to final destination position
                if exit_wh.in_hex != dhex:
                    self.plan_hex_jump_sequence(exit_wh.in_hex, dhex, dpos, dsys, galaxy_ref)

            else:
                # No direct wormhole, try pathfinding
                print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: No direct wormhole from {csys} to {dsys}. Attempting pathfinding using Dijkstra's algorithm (find_intersystem_path).")
                path_to_destination = find_intersystem_path(galaxy_ref.system_graph, csys, dsys)

                if not path_to_destination or len(path_to_destination) < 2:
                    self.status = OrderStatus.FAILED
                    print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (no path found from {csys} to {dsys} via pathfinding with find_intersystem_path).")
                    return

                print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Path found via pathfinding with find_intersystem_path: {path_to_destination}")
                print(f"  [plan_route] Path has {len(path_to_destination) - 1} legs.")

                current_leg_arrival_hex = chex # Unit's current hex at the start of planning

                for i in range(len(path_to_destination) - 1):
                    leg_origin_system = path_to_destination[i]
                    leg_destination_system = path_to_destination[i+1]
                    print(f"\n  --- Planning Leg {i+1}: {leg_origin_system} -> {leg_destination_system} ---")

                    wormhole_for_leg = self.find_wormhole_to_system(leg_origin_system, leg_destination_system, galaxy_ref)
                    if not wormhole_for_leg:
                        self.status = OrderStatus.FAILED
                        print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (pathfinding error - no wormhole for leg {leg_origin_system} -> {leg_destination_system}).")
                        return

                    exit_wormhole_for_leg = galaxy_ref.wormholes[wormhole_for_leg.exit_wormhole_id]
                    if not exit_wormhole_for_leg:
                        self.status = OrderStatus.FAILED
                        print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (pathfinding error - no exit for wormhole {wormhole_for_leg.id}).")
                        return

                    # Sub-order(s) to reach entry wormhole hex and move to entry wormhole position
                    if current_leg_arrival_hex != wormhole_for_leg.in_hex:
                        self.plan_hex_jump_sequence(current_leg_arrival_hex, wormhole_for_leg.in_hex, wormhole_for_leg.position, leg_origin_system, galaxy_ref)
                    else:
                        # If we are already in the correct hex, just add a sub-light move to the wormhole position.
                        self.add_sub_order(Order(self.unit, OrderType.REACH_WAYPOINT, {
                            "destination_system_name": leg_origin_system,
                            "destination_hex_coord": wormhole_for_leg.in_hex,
                            "destination_position": wormhole_for_leg.position
                        }, parent_order=self))
                        print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Leg {i+1} - Added sub-order to move by sub-light engines to entry Wormhole position in {leg_origin_system}.")

                    # Sub-order to jump through wormhole
                    self.add_sub_order(Order(self.unit, OrderType.REACH_WAYPOINT, {
                        "destination_system_name": leg_destination_system, # Target system for jump
                        "destination_hex_coord": exit_wormhole_for_leg.in_hex,    # Arrival hex
                        "destination_position": exit_wormhole_for_leg.position  # Arrival position
                    }, parent_order=self))
                    print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Leg {i+1} - Added sub-order to jump {leg_origin_system} -> {leg_destination_system}.")

                    # Check if the arrival point of this leg is inhibited
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

                                self.add_sub_order(Order(self.unit, OrderType.REACH_WAYPOINT, {
                                    "destination_system_name": leg_destination_system,
                                    "destination_hex_coord": exit_wormhole_for_leg.in_hex,
                                    "destination_position": safe_pos
                                }, parent_order=self))
                                print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Leg {i+1} exit is inhibited. Adding sub-light move out of inhibition zone to safe position: {safe_pos}.")
                                break # Found an inhibition zone, no need to check others

                    current_leg_arrival_hex = exit_wormhole_for_leg.in_hex # Update for next leg

                # After all inter-system jumps, unit is in 'dsys' at 'current_leg_arrival_hex'.
                # Plan final movement within the destination system.
                print(f"\n  [plan_route] Planning final movement from hex {current_leg_arrival_hex} to {dhex} in system {dsys}.")
                self.plan_hex_jump_sequence(current_leg_arrival_hex, dhex, dpos, dsys, galaxy_ref)

        # 2. Intra-system, inter-hex travel: Destination is in the same system but a different hex
        elif chex != dhex:  # csys == dsys
            self.plan_hex_jump_sequence(chex, dhex, dpos, csys, galaxy_ref)
        
        # 3. Intra-system, intra-hex travel (sub-light): Destination is in the same system and hex, but at a different position
        else:  # csys == dsys and chex == dhex
            if not self.unit.engines_component:
                self.status = OrderStatus.FAILED
                print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (cannot plan final sub-light movement leg, no engines).")
                return
            
            print(f"  [plan_route] Destination is in the same hex. Planning final sub-light movement.")
            print(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Adding REACH_WAYPOINT sub-order for final sub-light movement leg to {dpos} in {dsys}:{dhex}.")
            sub_order_params = {
                "destination_system_name": dsys,
                "destination_hex_coord": dhex,
                "destination_position": dpos
            }
            final_move_sub_order = Order(self.unit, OrderType.REACH_WAYPOINT, sub_order_params, parent_order=self)
            self.add_sub_order(final_move_sub_order)
    
    # --- REACH_WAYPOINT order methods ---

    def _execute_reach_waypoint(self, galaxy_ref: 'Galaxy') -> None:
        """Execute a REACH_WAYPOINT order."""
        dsys = self.parameters["destination_system_name"]
        dhex = self.parameters["destination_hex_coord"]
        dpos: Optional[Position] = self.parameters["destination_position"]
        
        # Get current location
        csys = self.unit.in_system
        chex = self.unit.in_hex
        
        # Check if destination is valid
        if dsys is None or dhex is None or dpos is None:
            self.status = OrderStatus.FAILED
            print(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (incomplete destination parameters).")
            return
            
        # Case 1: Different hex in same system - use hyperdrive to jump
        if csys == dsys and chex != dhex:
            if not self.unit.hyperdrive_component:
                self.status = OrderStatus.FAILED
                print(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (cannot jump hex, no hyperdrive).")
                return
                
            # Configure hyperdrive for hex jump
            self.unit.hyperdrive_component.hex_jump_target = (dhex, dpos)
            self.unit.hyperdrive_component.wormhole_jump_target = None
            # Clear engines move target when jumping
            if self.unit.engines_component:
                self.unit.engines_component.move_target = None
            print(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): Initiating HEX JUMP to {dhex}:{dpos} in {dsys}.")
            
        # Case 2: Same hex, different position - use engines for sublight movement
        elif csys == dsys and chex == dhex:
            if not self.unit.engines_component:
                self.status = OrderStatus.FAILED
                print(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (cannot move in sector, no engines).")
                return

            # Check if already at the destination position
            if distance(self.unit.position, dpos) < 0.01:
                self.status = OrderStatus.COMPLETED
                self.unit.engines_component.move_target = None # Ensure move_target is cleared
                if self.unit.hyperdrive_component:
                    self.unit.hyperdrive_component.hex_jump_target = None
                    self.unit.hyperdrive_component.wormhole_jump_target = None
                print(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): COMPLETED (already at sub-light destination {dpos} in {dsys}:{dhex}).")
                return

            # Configure engines for movement
            self.unit.engines_component.move_target = dpos
            # Clear hyperdrive targets
            if self.unit.hyperdrive_component:
                self.unit.hyperdrive_component.hex_jump_target = None
                self.unit.hyperdrive_component.wormhole_jump_target = None
            print(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): Initiating sub-light move to {dpos} in {dsys}:{dhex}.")
            
        # Case 3: Different system - need to use a wormhole to jump
        else: # csys != dsys
            if not self.unit.hyperdrive_component:
                self.status = OrderStatus.FAILED
                print(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (cannot jump to different system, no hyperdrive).")
                return
                
            # Find a wormhole to the destination system
            wormhole = self.find_wormhole_to_system(csys, dsys, galaxy_ref)
            if not wormhole:
                self.status = OrderStatus.FAILED
                print(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (no wormhole from {csys} to {dsys}).")
                return
                
            # Configure hyperdrive for wormhole jump
            self.unit.hyperdrive_component.wormhole_jump_target = wormhole
            self.unit.hyperdrive_component.hex_jump_target = None
            # Clear engines move target when jumping
            if self.unit.engines_component:
                self.unit.engines_component.move_target = None
            print(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): Initiating SYSTEM JUMP via wormhole {wormhole.name} to {dsys}.")


    # --- PATROL order methods ---

    def _execute_patrol(self) -> None:
        """Execute a PATROL order (placeholder for future implementation)."""
        # This is a placeholder for future patrol order implementation
        pass

    def _execute_attack(self, galaxy_ref: 'Galaxy') -> None:
        """Executes an ATTACK order."""
        target_unit_id = self.parameters["target_unit_id"]
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)

        if not target_unit:
            self.status = OrderStatus.FAILED
            return
        
        if self.unit.weapons_component:
            # Set the target of the Weapons component
            self.unit.weapons_component.set_target(target_unit)

            # Check if target is in the same system, hex and in range of at least 1 turret
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
                # Move towards target, but not right on top of it
                dest_pos = move_towards_position(self.unit.position, target_unit.position, min_turret_range - 5.0)

                move_params = {
                    "destination_system_name": target_unit.in_system,
                    "destination_hex_coord": target_unit.in_hex,
                    "destination_position": dest_pos
                }
                move_order = Order(self.unit, OrderType.MOVE, move_params, parent_order=self)
                self.add_sub_order(move_order)

    # --- TOGGLE_INHIBITOR order methods ---

    def _execute_toggle_inhibitor(self, galaxy_ref: 'Galaxy') -> None:
        """Executes the order to turn the inhibitor field on or off."""
        turn_on = self.parameters.get("turn_on", False)
        
        if not self.unit.inhibitor_component:
            print(f"[{self.unit.name} (id:{self.unit.id})] TOGGLE_INHIBITOR ({self.order_id}): FAILED (no inhibitor component).")
            self.status = OrderStatus.FAILED
            return

        current_hex = galaxy_ref.systems[self.unit.in_system].hexes[self.unit.in_hex]

        if turn_on:
            # --- Logic for turning the field ON ---
            inhibitor = self.unit.inhibitor_component
            proposed_field = Circle(center=self.unit.position, radius=inhibitor.radius)

            # 1. Validate containment
            if not is_circle_contained(proposed_field, current_hex.boundary_circle):
                print(f"[{self.unit.name} (id:{self.unit.id})] TOGGLE_INHIBITOR ({self.order_id}): FAILED (field would cross sector boundary).")
                self.status = OrderStatus.FAILED
                return

            # 2. Validate intersection
            for existing_zone in current_hex.get_all_inhibition_zones():
                if do_circles_intersect(proposed_field, existing_zone):
                    print(f"[{self.unit.name} (id:{self.unit.id})] TOGGLE_INHIBITOR ({self.order_id}): FAILED (field would overlap with another).")
                    self.status = OrderStatus.FAILED
                    return
            
            # All checks passed, turn it on
            inhibitor.turn_on()
            current_hex.dynamic_inhibition_zones[self.unit.id] = proposed_field
            self.status = OrderStatus.COMPLETED

        else:
            # --- Logic for turning the field OFF ---
            if self.unit.id in current_hex.dynamic_inhibition_zones:
                del current_hex.dynamic_inhibition_zones[self.unit.id]
            
            self.unit.inhibitor_component.turn_off()
            self.status = OrderStatus.COMPLETED

    # --- COLONIZE order methods ---

    def _execute_colonize(self, galaxy_ref: 'Galaxy') -> None:
        """Executes a COLONIZE order."""
        target_id = self.parameters.get("target_id")
        if not target_id:
            self.status = OrderStatus.FAILED
            print(f"COLONIZE order failed: no target_id.")
            return

        target = galaxy_ref.get_celestial_body_by_id(target_id)

        if not target:
            self.status = OrderStatus.FAILED
            print(f"COLONIZE order failed: Celestial body with ID {target_id} not found.")
            return

        if not self.unit.colony_component:
            self.status = OrderStatus.FAILED
            print(f"COLONIZE order failed: Unit {self.unit.name} has no ColonyComponent.")
            return

        # Check if we are at the target's location
        at_location = (self.unit.in_system == target.in_system and self.unit.in_hex == target.in_hex)

        if not at_location:
            # If not at location, create a MOVE sub-order to get there, then a COLONIZE sub-order
            if not self.has_active_sub_orders():
                move_params = {
                    "destination_system_name": target.in_system,
                    "destination_hex_coord": target.in_hex,
                    "destination_position": target.position
                }
                move_order = Order(self.unit, OrderType.MOVE, move_params, parent_order=self)
                self.add_sub_order(move_order)

                # Add a COLONIZE sub-order to be executed upon arrival
                colonize_sub_order = Order(self.unit, OrderType.COLONIZE, self.parameters, parent_order=self)
                self.add_sub_order(colonize_sub_order)
            return

        # We are at the location. Time to colonize.
        cargo = self.unit.colony_component.population_cargo
        if cargo <= 0:
            self.status = OrderStatus.FAILED
            print(f"COLONIZE order failed: No population in cargo to unload.")
            return

        success = self.unit.colony_component.unload_population(target, cargo)

        if success:
            self.status = OrderStatus.COMPLETED
            print(f"COLONIZE order completed: Unit {self.unit.name} successfully colonized {target.name}.")
        else:
            self.status = OrderStatus.FAILED
            print(f"COLONIZE order failed: Unload population failed for unit {self.unit.name} on {target.name}.")

    # --- LOAD_COLONISTS order methods ---

    def _execute_load_colonists(self, galaxy_ref: 'Galaxy') -> None:
        """Executes a LOAD_COLONISTS order."""
        target_id = self.parameters.get("target_id")
        amount = self.parameters.get("amount", 50)

        if not target_id:
            self.status = OrderStatus.FAILED
            print(f"LOAD_COLONISTS order failed: no target_id.")
            return

        target = galaxy_ref.get_celestial_body_by_id(target_id)

        if not target:
            self.status = OrderStatus.FAILED
            print(f"LOAD_COLONISTS order failed: Celestial body with ID {target_id} not found.")
            return

        if not self.unit.colony_component:
            self.status = OrderStatus.FAILED
            print(f"LOAD_COLONISTS order failed: Unit {self.unit.name} has no ColonyComponent.")
            return

        # Check if we are at the target's location
        at_location = (self.unit.in_system == target.in_system and self.unit.in_hex == target.in_hex)

        if not at_location:
            if not self.has_active_sub_orders():
                # add a sub-order to move to the target
                move_params = {
                    "destination_system_name": target.in_system,
                    "destination_hex_coord": target.in_hex,
                    "destination_position": target.position
                }
                move_order = Order(self.unit, OrderType.MOVE, move_params, parent_order=self)
                self.add_sub_order(move_order)
                
                # add a sub-order to load colonists (will be executed after the move)
                load_params = {
                    "target_id": target.id,
                    "amount": amount
                }
                load_order = Order(self.unit, OrderType.LOAD_COLONISTS, load_params, parent_order=self)
                self.add_sub_order(load_order)

            return

        # We are at the location. Time to load.
        success = self.unit.colony_component.load_population(target, amount)

        if success:
            self.status = OrderStatus.COMPLETED
        else:
            self.status = OrderStatus.FAILED
            print(f"LOAD_COLONISTS order failed for unit {self.unit.name}.")

    def _execute_construct(self, galaxy_ref: 'Galaxy') -> None:
        """Executes a CONSTRUCT order."""
        if not self.unit.constructor_component:
            self.status = OrderStatus.FAILED
            print(f"CONSTRUCT order failed: Unit {self.unit.name} has no ConstructorComponent.")
            return

        unit_template_name = self.parameters.get("unit_template_name")
        target_pos = self.parameters.get("target_position")

        if not unit_template_name or not target_pos:
            self.status = OrderStatus.FAILED
            print(f"CONSTRUCT order failed: Missing parameters.")
            return

        constructor = self.unit.constructor_component
        buildable = constructor.can_build(unit_template_name)

        if not buildable:
            self.status = OrderStatus.FAILED
            print(f"CONSTRUCT order failed: {self.unit.name} cannot build {unit_template_name}.")
            return

        # Check resources
        # Use self.unit.game.players to find the player by id
        player = next((p for p in self.unit.game.players if p.id == self.unit.owner.id), None)
        if not player:
            self.status = OrderStatus.FAILED
            print(f"CONSTRUCT order failed: Could not find player with id {self.unit.owner.id}.")
            return
        if player.credits < buildable.cost_credits:
            self.status = OrderStatus.FAILED
            print(f"CONSTRUCT order failed: Not enough credits.")
            return

        # Deduct resources and start construction
        player.credits -= buildable.cost_credits
        constructor.start_construction(unit_template_name, target_pos, galaxy_ref)
        self.status = OrderStatus.COMPLETED # The order is to *start* construction
