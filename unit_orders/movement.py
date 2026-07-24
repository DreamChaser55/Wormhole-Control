import logging
import math
import random
from typing import Dict, Optional, Any, TYPE_CHECKING

from utils import HexCoord
from geometry import Position, distance, hex_distance, is_point_in_circle, get_closest_point_on_circle_edge
from pathfinding import find_intersystem_path, find_hex_jump_path
from constants import XP_JUMP_RANGE_BONUS
from .base import Order, OrderStatus, OrderType

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


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
