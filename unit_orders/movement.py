import logging
import math
import random
import typing
from typing import Dict, Optional, Any, TYPE_CHECKING

from utils import HexCoord
from geometry import (
    Position, Vector, distance, hex_distance, is_point_in_circle,
    get_closest_point_on_circle_edge, clamp_point_to_circle, Circle,
    segment_intersects_circle, compute_avoidance_waypoints,
    position_at_distance_from_target
)
from pathfinding import find_intersystem_path, find_hex_jump_path
from constants import XP_JUMP_RANGE_BONUS, SECTOR_CIRCLE_RADIUS_LOGICAL, DEFAULT_STANDOFF_DISTANCE
from .base import Order, OrderStatus, OrderType

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit, CelestialBody

logger = logging.getLogger(__name__)


def get_hex_collision_obstacles(
    galaxy_ref: Optional['Galaxy'],
    system_name: Optional[str],
    hex_coord: Optional[HexCoord]
) -> typing.List[Circle]:
    """Returns a list of Circle collision obstacles for solid celestial bodies in the given hex."""
    if not galaxy_ref or not system_name or hex_coord is None:
        return []
    systems = getattr(galaxy_ref, 'systems', None)
    if not isinstance(systems, dict):
        return []
    system = systems.get(system_name)
    if not system:
        return []
    hexes = getattr(system, 'hexes', None)
    if not isinstance(hexes, dict):
        return []
    hex_obj = hexes.get(hex_coord)
    if not hex_obj:
        return []
    obstacles = []
    for body in getattr(hex_obj, 'celestial_bodies', []):
        r = getattr(body, 'collision_radius', 0.0)
        if isinstance(r, (int, float)) and r > 0.0:
            obstacles.append(Circle(body.position, float(r)))
    return obstacles


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
            if not self.unit.hyperdrive_component or not self.unit.hyperdrive_component.is_functional:
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (cannot jump hex, no functional hyperdrive).")
                return
                
            self.unit.hyperdrive_component.set_hex_jump_target((dest_hex, dest_position), self.order_id)
            if self.unit.engines_component:
                self.unit.engines_component.clear_move_target(self.order_id)
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): Initiating HEX JUMP to {dest_hex}:{dest_position} in {dest_system}.")
            
        # Sub-light engine movement is used within the same hex. Hyperdrive targets are cleared.
        elif current_system == dest_system and current_hex == dest_hex:
            engines = self.unit.engines_component
            if not engines or not engines.is_operational:
                self.status = OrderStatus.FAILED
                if engines:
                    engines.clear_move_target(self.order_id)
                reason = "no engines" if not engines else "engines are destroyed or offline"
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (cannot move in sector, {reason}).")
                return

            if distance(self.unit.position, dest_position) < 0.01:
                self.status = OrderStatus.COMPLETED
                self.unit.engines_component.clear_move_target(self.order_id)
                if self.unit.hyperdrive_component:
                    self.unit.hyperdrive_component.clear_jump_target(self.order_id)
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): COMPLETED (already at sub-light destination {dest_position} in {dest_system}:{dest_hex}).")
                return

            obstacles = get_hex_collision_obstacles(galaxy_ref, dest_system, dest_hex)
            avoidance_wps = compute_avoidance_waypoints(self.unit.position, dest_position, obstacles, margin=50.0)
            if avoidance_wps:
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): Path intersects celestial body. Spawning {len(avoidance_wps)} avoidance sub-order(s).")
                for wp in avoidance_wps:
                    self.add_sub_order(ReachWaypointOrder(self.unit, {
                        "destination_system_name": dest_system,
                        "destination_hex_coord": dest_hex,
                        "destination_position": wp
                    }, parent_order=self))
                self.add_sub_order(ReachWaypointOrder(self.unit, {
                    "destination_system_name": dest_system,
                    "destination_hex_coord": dest_hex,
                    "destination_position": dest_position
                }, parent_order=self))
                if self.sub_orders:
                    self.sub_orders[0].execute(galaxy_ref=galaxy_ref)
                return

            self.unit.engines_component.set_move_target(dest_position, self.order_id)
            if self.unit.hyperdrive_component:
                self.unit.hyperdrive_component.clear_jump_target(self.order_id)
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): Initiating sub-light move to {dest_position} in {dest_system}:{dest_hex}.")
            
        # Inter-system travel requires navigating via a wormhole connecting the two systems.
        else: # current_system != dest_system
            from unit_components import HyperdriveType
            if (
                not self.unit.hyperdrive_component
                or not self.unit.hyperdrive_component.is_functional
                or self.unit.hyperdrive_component.drive_type != HyperdriveType.ADVANCED
            ):
                self.status = OrderStatus.FAILED
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (cannot jump to different system, no advanced hyperdrive).")
                return
                
            wormhole = self.find_wormhole_to_system(current_system, dest_system, galaxy_ref, self.unit.hull_size)
            if not wormhole:
                self.status = OrderStatus.FAILED
                any_wh = self.find_wormhole_to_system(current_system, dest_system, galaxy_ref, ship_size=None)
                if any_wh:
                    logger.warning(f"[{self.unit.name} (id:{self.order_id})] REACH_WAYPOINT(id:{self.order_id}): FAILED: Unit '{self.unit.name}' (size {self.unit.hull_size.name}) is too large for wormhole {any_wh.name} (max capacity: {any_wh.diameter.name}).")
                    if self.unit and getattr(self.unit, 'game', None) and self.unit.game.gui:
                        self.unit.game.gui.show_warning_dialog(
                            f"Unit '{self.unit.name}' (size {self.unit.hull_size.name}) is too large for wormhole {any_wh.name} (max capacity: {any_wh.diameter.name}).",
                            title="Wormhole Capacity Exceeded"
                        )
                else:
                    logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): FAILED (no wormhole from {current_system} to {dest_system}).")
                return
                
            self.unit.hyperdrive_component.set_wormhole_jump_target(wormhole, self.order_id)
            if self.unit.engines_component:
                self.unit.engines_component.clear_move_target(self.order_id)
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): Initiating SYSTEM JUMP via wormhole {wormhole.name} to {dest_system}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return

        destination_requires_jump = (
            self.unit.in_system != self.parameters.get("destination_system_name")
            or self.unit.in_hex != self.parameters.get("destination_hex_coord")
        )
        if destination_requires_jump:
            drive = self.unit.hyperdrive_component
            if not drive or not drive.is_functional:
                if drive:
                    drive.clear_jump_target(self.order_id)
                self.status = OrderStatus.FAILED
                logger.debug(
                    f"[{self.unit.name} (id:{self.unit.id})] REACH_WAYPOINT(id:{self.order_id}): "
                    "FAILED (functional hyperdrive unavailable)."
                )
                return

        from unit_components.movement import JumpStatus
        if self.unit.hyperdrive_component and self.unit.hyperdrive_component.jump_status == JumpStatus.ERROR:
            if self.unit.engines_component:
                self.unit.engines_component.clear_move_target(self.order_id)
            self.unit.hyperdrive_component.clear_jump_target(self.order_id)
            self.unit.hyperdrive_component.jump_status = JumpStatus.READY
            self.status = OrderStatus.FAILED
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] ReachWaypointOrder.check_completion_conditions: {self.order_type.name} (id:{self.order_id}): FAILED (hyperdrive reported ERROR state).")
            return

        current_system = self.unit.in_system
        current_hex = self.unit.in_hex
        current_position = self.unit.position
        
        dest_system = self.parameters["destination_system_name"]
        dest_hex = self.parameters["destination_hex_coord"]
        dest_position: Position = self.parameters["destination_position"]

        is_active_sublight_leg = (
            current_system == dest_system
            and current_hex == dest_hex
            and distance(current_position, dest_position) >= 0.01
        )
        if is_active_sublight_leg:
            engines = self.unit.engines_component
            if not engines or not engines.is_operational:
                if engines:
                    engines.clear_move_target(self.order_id)
                self.status = OrderStatus.FAILED
                reason = "no engines" if not engines else "engines are destroyed or offline"
                logger.debug(
                    f"[{self.unit.name} (id:{self.unit.id})] "
                    f"ReachWaypointOrder.check_completion_conditions: {self.order_type.name} "
                    f"(id:{self.order_id}): FAILED (cannot continue sub-light movement, {reason})."
                )
                return
        
        if current_system == dest_system and current_hex == dest_hex and distance(current_position, dest_position) < 0.01:
            if self.unit.engines_component:
                self.unit.engines_component.clear_move_target(self.order_id)
            if self.unit.hyperdrive_component:
                self.unit.hyperdrive_component.clear_jump_target(self.order_id)
            self.status = OrderStatus.COMPLETED
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] ReachWaypointOrder.check_completion_conditions: {self.order_type.name} (id:{self.order_id}): COMPLETED (arrived at waypoint: {dest_position}:Hex{dest_hex}:{dest_system})")

    def cancel(self) -> None:
        super().cancel()
        if self.unit.engines_component:
            self.unit.engines_component.clear_move_target(self.order_id)
        if self.unit.hyperdrive_component:
            self.unit.hyperdrive_component.clear_jump_target(self.order_id)

    def resume(self, galaxy_ref: 'Galaxy') -> None:
        """Restore the active actuator binding without replanning the route."""
        super().resume(galaxy_ref)
        if self.status != OrderStatus.IN_PROGRESS or self.sub_orders:
            return
        dest_system = self.parameters.get("destination_system_name")
        dest_hex = self.parameters.get("destination_hex_coord")
        dest_position = self.parameters.get("destination_position")
        if dest_system is None or dest_hex is None or dest_position is None:
            return
        if self.unit.in_system == dest_system and self.unit.in_hex == dest_hex:
            engines = self.unit.engines_component
            if engines and engines.is_operational and distance(self.unit.position, dest_position) >= 0.01:
                engines.set_move_target(dest_position, self.order_id)
            return
        drive = self.unit.hyperdrive_component
        if not drive or not drive.is_functional:
            return
        if self.unit.in_system == dest_system:
            drive.set_hex_jump_target((dest_hex, dest_position), self.order_id)
            return
        from unit_components import HyperdriveType
        if drive.drive_type == HyperdriveType.ADVANCED:
            wormhole = self.find_wormhole_to_system(self.unit.in_system, dest_system, galaxy_ref, self.unit.hull_size)
            if wormhole:
                drive.set_wormhole_jump_target(wormhole, self.order_id)


class MoveOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.MOVE, parameters, parent_order)

    @classmethod
    def for_unit_approach(
        cls,
        unit: 'Unit',
        target_unit: 'Unit',
        standoff_distance: float,
        parent_order: Optional[Order] = None,
    ) -> 'MoveOrder':
        """Create a move whose final position is resolved around a target unit.

        The target location is captured for display and serialization, but the
        route planner refreshes it when the order first executes.  This keeps
        callers from independently reproducing the same arrival geometry.
        """
        return cls(unit, {
            "destination_system_name": target_unit.in_system,
            "destination_hex_coord": target_unit.in_hex,
            "destination_position": Position(target_unit.position.x, target_unit.position.y),
            "target_unit_id": target_unit.id,
            "standoff_distance": standoff_distance,
            "approach_position_resolved": False,
        }, parent_order=parent_order)

    @classmethod
    def for_celestial_approach(
        cls,
        unit: 'Unit',
        target_body: 'CelestialBody',
        standoff_distance: float = DEFAULT_STANDOFF_DISTANCE,
        parent_order: Optional[Order] = None,
    ) -> 'MoveOrder':
        """Create a move whose final position is resolved around a target celestial body.

        The target location is captured for display and serialization, but the
        route planner refreshes it when the order first executes.  This keeps
        callers from independently reproducing the same arrival geometry.
        """
        return cls(unit, {
            "destination_system_name": target_body.in_system,
            "destination_hex_coord": target_body.in_hex,
            "destination_position": Position(target_body.position.x, target_body.position.y),
            "target_celestial_id": target_body.id,
            "standoff_distance": standoff_distance,
            "approach_position_resolved": False,
        }, parent_order=parent_order)

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

    def _resolve_unit_approach_destination(self, galaxy_ref: 'Galaxy') -> bool:
        """Resolve an optional target-unit move to a point on its standoff circle."""
        target_unit_id = self.parameters.get("target_unit_id")
        if target_unit_id is None:
            return True
        if self.parameters.get("approach_position_resolved"):
            return True

        target_unit = galaxy_ref.get_unit_by_id(target_unit_id)
        if not target_unit:
            self.status = OrderStatus.FAILED
            logger.debug(
                f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): "
                f"FAILED (target unit {target_unit_id} no longer exists)."
            )
            return False

        try:
            standoff_distance = float(self.parameters.get("standoff_distance"))
        except (TypeError, ValueError):
            standoff_distance = 0.0
        if not math.isfinite(standoff_distance) or standoff_distance <= 0.0:
            self.status = OrderStatus.FAILED
            logger.debug(
                f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): "
                f"FAILED (invalid standoff distance {self.parameters.get('standoff_distance')})."
            )
            return False

        system = galaxy_ref.systems.get(target_unit.in_system)
        destination_hex_obj = system.hexes.get(target_unit.in_hex) if system else None
        if not destination_hex_obj:
            self.status = OrderStatus.FAILED
            logger.debug(
                f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): "
                f"FAILED (target sector {target_unit.in_system}:{target_unit.in_hex} not found)."
            )
            return False

        target_position = target_unit.position
        boundary_circle = getattr(destination_hex_obj, "boundary_circle", None)
        if not isinstance(boundary_circle, Circle):
            boundary_circle = Circle(Position(0.0, 0.0), SECTOR_CIRCLE_RADIUS_LOGICAL)
        same_sector = (
            self.unit.in_system == target_unit.in_system
            and self.unit.in_hex == target_unit.in_hex
        )

        if same_sector:
            resolved_position = position_at_distance_from_target(
                self.unit.position,
                target_position,
                standoff_distance,
            )
            if not is_point_in_circle(resolved_position, boundary_circle):
                self.status = OrderStatus.FAILED
                logger.debug(
                    f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): "
                    "FAILED (same-sector standoff point lies outside the sector)."
                )
                return False
        else:
            inhibition_zones = destination_hex_obj.get_all_inhibition_zones()
            containing_zone = next(
                (zone for zone in inhibition_zones if is_point_in_circle(target_position, zone)),
                None,
            )

            if containing_zone:
                outward = target_position - containing_zone.center
                if outward.magnitude_sq() < 1e-9:
                    outward = Vector(1.0, 0.0)
                else:
                    outward = outward.normalize()

                resolved_position = target_position + (outward * standoff_distance)
                if not is_point_in_circle(resolved_position, boundary_circle):
                    self.status = OrderStatus.FAILED
                    logger.debug(
                        f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): "
                        "FAILED (outward inhibited standoff point lies outside the sector)."
                    )
                    return False
            else:
                resolved_position = None
                max_attempts = 128
                for _ in range(max_attempts):
                    angle = random.uniform(0.0, 2.0 * math.pi)
                    candidate = target_position + Vector(
                        math.cos(angle) * standoff_distance,
                        math.sin(angle) * standoff_distance,
                    )
                    if not is_point_in_circle(candidate, boundary_circle):
                        continue
                    if any(is_point_in_circle(candidate, zone) for zone in inhibition_zones):
                        continue
                    resolved_position = candidate
                    break

                if resolved_position is None:
                    self.status = OrderStatus.FAILED
                    logger.debug(
                        f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): "
                        "FAILED (could not find an uninhibited standoff point after 128 attempts)."
                    )
                    return False

        self.parameters["destination_system_name"] = target_unit.in_system
        self.parameters["destination_hex_coord"] = target_unit.in_hex
        self.parameters["destination_position"] = resolved_position
        self.parameters["approach_position_resolved"] = True
        logger.debug(
            f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): "
            f"Resolved target-unit standoff destination for {target_unit.name} "
            f"at distance {standoff_distance:.2f}: {resolved_position}."
        )
        return True

    def _resolve_celestial_approach_destination(self, galaxy_ref: 'Galaxy') -> bool:
        """Resolve an optional target-celestial move to a point on its standoff circle."""
        target_celestial_id = self.parameters.get("target_celestial_id")
        if target_celestial_id is None:
            return True
        if self.parameters.get("approach_position_resolved"):
            return True

        target_body = galaxy_ref.get_celestial_body_by_id(target_celestial_id)
        if not target_body:
            self.status = OrderStatus.FAILED
            logger.debug(
                f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): "
                f"FAILED (target celestial body {target_celestial_id} no longer exists)."
            )
            return False

        try:
            standoff_distance = float(self.parameters.get("standoff_distance", DEFAULT_STANDOFF_DISTANCE))
        except (TypeError, ValueError):
            standoff_distance = DEFAULT_STANDOFF_DISTANCE
        if not math.isfinite(standoff_distance) or standoff_distance < 0.0:
            self.status = OrderStatus.FAILED
            logger.debug(
                f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): "
                f"FAILED (invalid standoff distance {self.parameters.get('standoff_distance')})."
            )
            return False

        target_radius = getattr(target_body, 'collision_radius', getattr(target_body, 'radius', 0.0))
        total_standoff = target_radius + standoff_distance

        system = galaxy_ref.systems.get(target_body.in_system)
        destination_hex_obj = system.hexes.get(target_body.in_hex) if system else None
        if not destination_hex_obj:
            self.status = OrderStatus.FAILED
            logger.debug(
                f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): "
                f"FAILED (target sector {target_body.in_system}:{target_body.in_hex} not found)."
            )
            return False

        target_position = target_body.position
        boundary_circle = getattr(destination_hex_obj, "boundary_circle", None)
        if not isinstance(boundary_circle, Circle):
            boundary_circle = Circle(Position(0.0, 0.0), SECTOR_CIRCLE_RADIUS_LOGICAL)

        same_sector = (
            self.unit.in_system == target_body.in_system
            and self.unit.in_hex == target_body.in_hex
        )

        if same_sector:
            resolved_position = position_at_distance_from_target(
                self.unit.position,
                target_position,
                total_standoff,
            )
        else:
            # Arriving from another sector or system:
            # Determine incoming approach direction based on hex layout
            if self.unit.in_system == target_body.in_system:
                from hexgrid_utils import hex_to_pixel
                p_orig = hex_to_pixel(self.unit.in_hex[0], self.unit.in_hex[1])
                p_dest = hex_to_pixel(target_body.in_hex[0], target_body.in_hex[1])
                diff = p_orig - p_dest
                direction = diff.normalize() if diff.magnitude_sq() > 1e-9 else Vector(1.0, 0.0)
            else:
                # Inter-system travel: Find entry wormhole in destination system if available
                direct_wh = self.find_wormhole_to_system(self.unit.in_system, target_body.in_system, galaxy_ref, self.unit.hull_size)
                if direct_wh and direct_wh.exit_wormhole_id:
                    exit_wh = galaxy_ref.wormholes.get(direct_wh.exit_wormhole_id)
                    if exit_wh:
                        from hexgrid_utils import hex_to_pixel
                        p_orig = hex_to_pixel(exit_wh.in_hex[0], exit_wh.in_hex[1])
                        p_dest = hex_to_pixel(target_body.in_hex[0], target_body.in_hex[1])
                        diff = p_orig - p_dest
                        direction = diff.normalize() if diff.magnitude_sq() > 1e-9 else Vector(1.0, 0.0)
                    else:
                        direction = Vector(1.0, 0.0)
                else:
                    direction = Vector(1.0, 0.0)

            resolved_position = target_position + (direction * total_standoff)

        if not is_point_in_circle(resolved_position, boundary_circle):
            resolved_position = clamp_point_to_circle(resolved_position, boundary_circle)

        self.parameters["destination_system_name"] = target_body.in_system
        self.parameters["destination_hex_coord"] = target_body.in_hex
        self.parameters["destination_position"] = resolved_position
        self.parameters["approach_position_resolved"] = True
        logger.debug(
            f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): "
            f"Resolved target-celestial standoff destination for {target_body.name} "
            f"at distance {total_standoff:.2f}: {resolved_position}."
        )
        return True

    def handle_inhibited_waypoint(self, target_hex: HexCoord, target_pos: Position, is_final_destination: bool, system_name: str, galaxy_ref: 'Galaxy'):
        destination_hex_obj = galaxy_ref.systems[system_name].hexes.get(target_hex)
        if not destination_hex_obj:
            logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MoveOrder.handle_inhibited_waypoint: ERROR: Destination hex {target_hex} not found in system {system_name}.")
            return

        zones = destination_hex_obj.get_all_inhibition_zones()

        if is_final_destination:
            # Final destination: snap to the edge of its containing zone, then add a
            # sub-light follow-up move so the unit ultimately reaches its exact target.
            for zone in zones:
                if is_point_in_circle(target_pos, zone):
                    adjusted_pos = get_closest_point_on_circle_edge(target_pos, zone)
                    logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Final waypoint {target_pos} in {target_hex} is inhibited. Adjusting landing position to {adjusted_pos}.")
                    self.add_sub_order(ReachWaypointOrder(self.unit, {
                        "destination_system_name": system_name,
                        "destination_hex_coord": target_hex,
                        "destination_position": adjusted_pos
                    }, parent_order=self))
                    logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Adding sub-light move from {adjusted_pos} to original target {target_pos}.")
                    obstacles = get_hex_collision_obstacles(galaxy_ref, system_name, target_hex)
                    avoidance_wps = compute_avoidance_waypoints(adjusted_pos, target_pos, obstacles, margin=50.0)
                    for wp in avoidance_wps:
                        self.add_sub_order(ReachWaypointOrder(self.unit, {
                            "destination_system_name": system_name,
                            "destination_hex_coord": target_hex,
                            "destination_position": wp
                        }, parent_order=self))
                    self.add_sub_order(ReachWaypointOrder(self.unit, {
                        "destination_system_name": system_name,
                        "destination_hex_coord": target_hex,
                        "destination_position": target_pos
                    }, parent_order=self))
                    return

            # No inhibition — land at the exact target.
            self.add_sub_order(ReachWaypointOrder(self.unit, {
                "destination_system_name": system_name,
                "destination_hex_coord": target_hex,
                "destination_position": target_pos
            }, parent_order=self))

        else:
            # Intermediate waypoint: the unit must land outside every inhibition field so
            # it can immediately re-engage its hyperdrive.  Simple iterative pushes can
            # oscillate when zones overlap, so instead we compute the net escape direction
            # from all currently-blocking zones in one pass and advance to clear all of
            # them, then repeat until no blocking zone remains.
            SAFE_MARGIN = 1.0
            MAX_PASSES = 20  # Safety cap against degenerate zone configurations.
            adjusted_pos = target_pos
            was_adjusted = False

            for _ in range(MAX_PASSES):
                # Collect all zones that still block the current candidate position.
                blocking = [z for z in zones if is_point_in_circle(adjusted_pos, z)]
                if not blocking:
                    break  # All zones are clear.

                # Compute the net outward direction as the sum of unit vectors pointing
                # from each blocking zone's centre toward the current candidate.
                net_dir = Vector(0.0, 0.0)
                max_required_dist = 0.0
                for zone in blocking:
                    diff = adjusted_pos - zone.center
                    if diff.magnitude_sq() < 1e-9:
                        diff = Vector(1.0, 0.0)  # At centre: pick arbitrary direction.
                    else:
                        diff = diff.normalize()
                    net_dir = net_dir + diff
                    max_required_dist = max(max_required_dist, zone.radius + SAFE_MARGIN)

                # If all blocking zones happen to be perfectly opposed the net vector
                # collapses to zero — break the tie with an arbitrary unit vector.
                if net_dir.magnitude_sq() < 1e-9:
                    net_dir = Vector(1.0, 0.0)
                else:
                    net_dir = net_dir.normalize()

                # Advance from the origin of the most constraining blocking zone so we
                # are guaranteed to clear it while moving in the net escape direction.
                dominant_zone = max(blocking, key=lambda z: z.radius)
                adjusted_pos = dominant_zone.center + (net_dir * (dominant_zone.radius + SAFE_MARGIN))
                was_adjusted = True
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route->plan_hex_jump_sequence: Intermediate waypoint in {target_hex} is inhibited. Adjusting landing position to {adjusted_pos}.")

            if was_adjusted:
                # Clamp to the sector boundary so the position stays inside the hex.
                adjusted_pos = clamp_point_to_circle(adjusted_pos, destination_hex_obj.boundary_circle)

            self.add_sub_order(ReachWaypointOrder(self.unit, {
                "destination_system_name": system_name,
                "destination_hex_coord": target_hex,
                "destination_position": adjusted_pos
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

        if not self._resolve_unit_approach_destination(galaxy_ref):
            return

        if not self._resolve_celestial_approach_destination(galaxy_ref):
            return

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
                gui = getattr(getattr(self.unit, 'game', None), 'gui', None)
                if gui:
                    gui.show_warning_dialog(
                        f"Unit <b>{self.unit.name}</b> requires an Advanced Hyperdrive or direct wormhole to jump to system <b>{dest_system}</b>.",
                        title="Route Planning Failed"
                    )
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
                elif distance(arrival_pos, dest_position) >= 0.01:
                    self.handle_inhibited_waypoint(dest_hex, dest_position, is_final_destination=True, system_name=dest_system, galaxy_ref=galaxy_ref)



            else:
                # If no direct wormhole exists, find a multi-system path using Dijkstra's algorithm.
                path_to_destination = find_intersystem_path(galaxy_ref.system_graph, current_system, dest_system, self.unit.hull_size)

                if not path_to_destination or len(path_to_destination) < 2:
                    self.sub_orders.clear()
                    self.status = OrderStatus.FAILED
                    unrestricted_path = find_intersystem_path(galaxy_ref.system_graph, current_system, dest_system, ship_size=None)
                    gui = getattr(getattr(self.unit, 'game', None), 'gui', None)
                    if unrestricted_path and len(unrestricted_path) >= 2:
                        logger.warning(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED: Unit '{self.unit.name}' (size {self.unit.hull_size.name}) is too large for wormhole(s) along route {unrestricted_path}.")
                        if gui:
                            gui.show_warning_dialog(
                                f"Unit '{self.unit.name}' (size {self.unit.hull_size.name}) cannot navigate to destination: Wormhole(s) along route cannot accommodate its hull size.",
                                title="Route Planning Failed"
                            )
                    else:
                        logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (no path found from {current_system} to {dest_system} via pathfinding with find_intersystem_path).")
                        if gui:
                            gui.show_warning_dialog(
                                f"No valid navigation route found for <b>{self.unit.name}</b> from {current_system} to destination system <b>{dest_system}</b>.",
                                title="No Route Available"
                            )
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
                        self.sub_orders.clear()
                        self.status = OrderStatus.FAILED
                        logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (pathfinding error - no wormhole for leg {leg_origin_system} -> {leg_destination_system}).")
                        return

                    exit_wormhole_for_leg = galaxy_ref.wormholes[wormhole_for_leg.exit_wormhole_id]
                    if not exit_wormhole_for_leg:
                        self.sub_orders.clear()
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
            engines = self.unit.engines_component
            if not engines or not engines.is_operational:
                self.status = OrderStatus.FAILED
                if engines:
                    engines.clear_move_target(self.order_id)
                reason = "no engines" if not engines else "engines are destroyed or offline"
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: FAILED (cannot plan final sub-light movement leg, {reason}).")
                return
            
            obstacles = get_hex_collision_obstacles(galaxy_ref, dest_system, dest_hex)
            avoidance_wps = compute_avoidance_waypoints(current_position, dest_position, obstacles, margin=50.0)
            if avoidance_wps:
                logger.debug(f"[{self.unit.name} (id:{self.unit.id})] MOVE(id:{self.order_id}): plan_route: Direct sub-light path intersects celestial body. Adding {len(avoidance_wps)} avoidance waypoint(s).")
                for wp in avoidance_wps:
                    self.add_sub_order(ReachWaypointOrder(self.unit, {
                        "destination_system_name": dest_system,
                        "destination_hex_coord": dest_hex,
                        "destination_position": wp
                    }, parent_order=self))

            sub_order_params = {
                "destination_system_name": dest_system,
                "destination_hex_coord": dest_hex,
                "destination_position": dest_position
            }
            final_move_sub_order = ReachWaypointOrder(self.unit, sub_order_params, parent_order=self)
            self.add_sub_order(final_move_sub_order)


def calculate_required_antimatter(
    unit: 'Unit',
    galaxy_ref: Optional['Galaxy'],
    destination_system_name: str,
    destination_hex_coord: HexCoord,
    destination_position: Optional[Position] = None
) -> float:
    """Calculates the total antimatter required for a unit to complete a movement journey.

    Includes antimatter costs for:
    - Sub-light engine movement (ENGINE_ANTIMATTER_COST_PER_TURN per turn)
    - Intra-system hyperdrive hex jumps (get_hyperdrive_hex_jump_cost)
    - Inter-system hyperdrive wormhole jumps (get_hyperdrive_system_jump_cost)
    """
    if not unit or not getattr(unit, 'antimatter_component', None) or not galaxy_ref:
        return 0.0

    from custom_unit_templates import (
        get_hyperdrive_system_jump_cost,
        get_hyperdrive_hex_jump_cost,
        get_sublight_antimatter_cost_per_turn
    )
    from constants import XP_SPEED_BONUS, XP_JUMP_RANGE_BONUS

    curr_system = unit.in_system
    curr_hex = unit.in_hex
    curr_pos = unit.position

    if curr_system is None or curr_hex is None or curr_pos is None:
        return 0.0

    hd_comp = unit.hyperdrive_component
    engine_comp = unit.engines_component

    sys_jump_cost = get_hyperdrive_system_jump_cost(unit.hull_size)
    hex_jump_cost = get_hyperdrive_hex_jump_cost(unit.hull_size)

    effective_speed = (engine_comp.speed * unit.xp_multiplier(XP_SPEED_BONUS)) if engine_comp else 0.0
    effective_jump_range = int(hd_comp.jump_range * unit.xp_multiplier(XP_JUMP_RANGE_BONUS)) if hd_comp else 0
    sublight_cost_per_turn = get_sublight_antimatter_cost_per_turn(unit.hull_size, effective_speed)

    def _sublight_cost(p1: Optional[Position], p2: Optional[Position]) -> float:
        if not engine_comp or effective_speed <= 0.0 or p1 is None or p2 is None:
            return 0.0
        dist = distance(p1, p2)
        if dist < 0.01:
            return 0.0
        turns = math.ceil(dist / effective_speed)
        return turns * sublight_cost_per_turn

    def _hex_jump_cost_seq(start_h: HexCoord, end_h: HexCoord) -> float:
        if start_h == end_h:
            return 0.0
        if not hd_comp or effective_jump_range <= 0:
            return 0.0
        dist = hex_distance(start_h, end_h)
        if dist <= effective_jump_range:
            return hex_jump_cost
        waypoints = find_hex_jump_path(start_h, end_h, effective_jump_range)
        return len(waypoints) * hex_jump_cost

    def _get_landing_sublight_cost(sys_name: str, target_h: HexCoord, target_p: Optional[Position]) -> float:
        if target_p is None:
            return 0.0
        sys_obj = galaxy_ref.systems.get(sys_name) if hasattr(galaxy_ref, 'systems') and galaxy_ref.systems else None
        if not sys_obj:
            return 0.0
        hex_obj = sys_obj.hexes.get(target_h) if hasattr(sys_obj, 'hexes') and sys_obj.hexes else None
        if not hex_obj:
            return 0.0
        zones = hex_obj.get_all_inhibition_zones() if hasattr(hex_obj, 'get_all_inhibition_zones') else []
        for zone in zones:
            if is_point_in_circle(target_p, zone):
                adjusted_pos = get_closest_point_on_circle_edge(target_p, zone)
                return _sublight_cost(adjusted_pos, target_p)
        return 0.0

    total_antimatter = 0.0

    # Account for departure escape cost if origin is currently inhibited and we are jumping out
    if curr_system != destination_system_name or curr_hex != destination_hex_coord:
        origin_sys_obj = galaxy_ref.systems.get(curr_system) if hasattr(galaxy_ref, 'systems') and galaxy_ref.systems else None
        if origin_sys_obj:
            origin_hex_obj = origin_sys_obj.hexes.get(curr_hex) if hasattr(origin_sys_obj, 'hexes') and origin_sys_obj.hexes else None
            if origin_hex_obj:
                zones = origin_hex_obj.get_all_inhibition_zones() if hasattr(origin_hex_obj, 'get_all_inhibition_zones') else []
                for zone in zones:
                    if is_point_in_circle(curr_pos, zone):
                        escape_pos = get_closest_point_on_circle_edge(curr_pos, zone)
                        total_antimatter += _sublight_cost(curr_pos, escape_pos)
                        curr_pos = escape_pos
                        break

    # Inter-system movement
    if curr_system != destination_system_name:
        direct_wh = Order.find_wormhole_to_system(None, curr_system, destination_system_name, galaxy_ref, unit.hull_size)
        if direct_wh:
            path_to_dest = [curr_system, destination_system_name]
        else:
            path_to_dest = find_intersystem_path(galaxy_ref.system_graph, curr_system, destination_system_name, unit.hull_size)

        if not path_to_dest or len(path_to_dest) < 2:
            return 0.0

        curr_leg_arrival_hex = curr_hex
        curr_leg_pos = curr_pos

        for i in range(len(path_to_dest) - 1):
            leg_origin = path_to_dest[i]
            leg_dest = path_to_dest[i + 1]
            wh_for_leg = Order.find_wormhole_to_system(None, leg_origin, leg_dest, galaxy_ref, unit.hull_size)
            if not wh_for_leg:
                break
            exit_wh = galaxy_ref.wormholes.get(wh_for_leg.exit_wormhole_id)
            if not exit_wh:
                break

            # Navigate to entry wormhole position/hex
            if curr_leg_arrival_hex != wh_for_leg.in_hex:
                total_antimatter += _hex_jump_cost_seq(curr_leg_arrival_hex, wh_for_leg.in_hex)
                total_antimatter += _get_landing_sublight_cost(leg_origin, wh_for_leg.in_hex, wh_for_leg.position)
            else:
                total_antimatter += _sublight_cost(curr_leg_pos, wh_for_leg.position)

            # System jump cost
            total_antimatter += sys_jump_cost

            curr_leg_arrival_hex = exit_wh.in_hex
            curr_leg_pos = exit_wh.position

            # Handle inhibited wormhole exit
            dest_sys_obj = galaxy_ref.systems.get(leg_dest) if hasattr(galaxy_ref, 'systems') and galaxy_ref.systems else None
            if dest_sys_obj:
                exit_hex_obj = dest_sys_obj.hexes.get(exit_wh.in_hex) if hasattr(dest_sys_obj, 'hexes') and dest_sys_obj.hexes else None
                if exit_hex_obj:
                    zones = exit_hex_obj.get_all_inhibition_zones() if hasattr(exit_hex_obj, 'get_all_inhibition_zones') else []
                    for zone in zones:
                        if is_point_in_circle(curr_leg_pos, zone):
                            safe_distance = zone.radius + 1.0
                            turns = math.ceil(safe_distance / effective_speed) if effective_speed > 0 else 0
                            total_antimatter += turns * sublight_cost_per_turn
                            curr_leg_pos = Position(curr_leg_pos.x + safe_distance, curr_leg_pos.y)
                            break

        # Final leg in destination system
        if curr_leg_arrival_hex != destination_hex_coord:
            total_antimatter += _hex_jump_cost_seq(curr_leg_arrival_hex, destination_hex_coord)
            if destination_position:
                total_antimatter += _get_landing_sublight_cost(destination_system_name, destination_hex_coord, destination_position)
        else:
            if destination_position:
                total_antimatter += _sublight_cost(curr_leg_pos, destination_position)

    # Intra-system movement
    elif curr_hex != destination_hex_coord:
        total_antimatter += _hex_jump_cost_seq(curr_hex, destination_hex_coord)
        if destination_position:
            total_antimatter += _get_landing_sublight_cost(curr_system, destination_hex_coord, destination_position)

    # Intra-hex sub-light movement
    else:
        if destination_position:
            total_antimatter += _sublight_cost(curr_pos, destination_position)

    return total_antimatter
