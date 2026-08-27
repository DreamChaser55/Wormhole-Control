"""Positional Defend order instructing a unit to guard a target coordinate or entity."""

import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import Position, distance
from constants import HullSize
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder
from .combat import AttackOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)

DEFAULT_DEFEND_GUARD_RADIUS = 1000.0


class DefendOrder(Order):
    """Order instructing a unit to move to and defend a specific position, hex, or celestial body."""

    def __init__(
        self,
        unit: 'Unit',
        parameters: Dict[str, Any] = None,
        parent_order: Optional[Order] = None,
    ):
        super().__init__(unit, OrderType.DEFEND, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        dest_pos = self.parameters.get("destination_position")
        pos_data = None
        if dest_pos is not None:
            if hasattr(dest_pos, "to_tuple"):
                pos_data = list(dest_pos.to_tuple())
            elif isinstance(dest_pos, (list, tuple)):
                pos_data = list(dest_pos)
            elif hasattr(dest_pos, "x") and hasattr(dest_pos, "y"):
                pos_data = [dest_pos.x, dest_pos.y]

        hex_coord = self.parameters.get("destination_hex_coord")
        hex_data = list(hex_coord) if hex_coord is not None else None

        state_data.update(
            {
                "destination_system_name": self.parameters.get("destination_system_name"),
                "destination_hex_coord": hex_data,
                "destination_position": pos_data,
                "target_id": self.parameters.get("target_id"),
                "guard_radius": self.parameters.get("guard_radius", DEFAULT_DEFEND_GUARD_RADIUS),
            }
        )
        return state_data

    def _resolve_destination(self, galaxy_ref: 'Galaxy') -> tuple[Optional[str], Optional[tuple[int, int]], Optional[Position]]:
        dest_system = self.parameters.get("destination_system_name")
        dest_hex = self.parameters.get("destination_hex_coord")
        dest_pos_raw = self.parameters.get("destination_position")

        dest_pos = None
        if dest_pos_raw is not None:
            if isinstance(dest_pos_raw, Position):
                dest_pos = dest_pos_raw
            elif isinstance(dest_pos_raw, (list, tuple)) and len(dest_pos_raw) == 2:
                dest_pos = Position(float(dest_pos_raw[0]), float(dest_pos_raw[1]))
            elif hasattr(dest_pos_raw, "x") and hasattr(dest_pos_raw, "y"):
                dest_pos = Position(float(dest_pos_raw.x), float(dest_pos_raw.y))

        target_id = self.parameters.get("target_id")
        if target_id is not None and galaxy_ref:
            body = None
            if hasattr(galaxy_ref, "get_celestial_body_by_id"):
                body = galaxy_ref.get_celestial_body_by_id(target_id)
            if body is not None:
                dest_system = getattr(body, "in_system", dest_system)
                dest_hex = getattr(body, "in_hex", dest_hex)
                dest_pos = getattr(body, "position", dest_pos)

        if dest_system is None and self.unit:
            dest_system = self.unit.in_system
        if dest_hex is None and self.unit:
            dest_hex = self.unit.in_hex
        if dest_pos is None and self.unit:
            dest_pos = Position(self.unit.position.x, self.unit.position.y)

        return dest_system, dest_hex, dest_pos

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)
        dest_system, dest_hex, dest_pos = self._resolve_destination(galaxy_ref)

        if dest_system is None or dest_hex is None or dest_pos is None:
            self.status = OrderStatus.FAILED
            logger.debug(f"DEFEND order failed for {self.unit.name}: could not resolve destination.")
            return

        in_same_system = self.unit.in_system == dest_system
        in_same_hex = self.unit.in_hex == dest_hex
        dist = distance(self.unit.position, dest_pos) if in_same_system and in_same_hex else float('inf')

        if not in_same_system or not in_same_hex or dist > 30.0:
            move_params = {
                "destination_system_name": dest_system,
                "destination_hex_coord": dest_hex,
                "destination_position": dest_pos,
            }
            self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))

    def _find_nearby_enemy(self, galaxy_ref: 'Galaxy', dest_system: str, dest_hex: tuple[int, int], dest_pos: Position) -> Optional['Unit']:
        weapons = self.unit.weapons_component
        if not weapons or weapons.is_destroyed or not weapons.turrets:
            return None

        if self.unit.in_system != dest_system or self.unit.in_hex != dest_hex:
            return None

        if not galaxy_ref or not hasattr(galaxy_ref, "systems"):
            return None

        system = galaxy_ref.systems.get(dest_system)
        if not system or not hasattr(system, "hexes"):
            return None

        hex_obj = system.hexes.get(dest_hex)
        if not hex_obj or not hasattr(hex_obj, "units"):
            return None

        visibility_snapshot = None
        if self.unit.owner and galaxy_ref:
            from visibility import VisibilityService
            turn_num = getattr(galaxy_ref, "turn_number", 1)
            if hasattr(galaxy_ref, "game") and hasattr(galaxy_ref.game, "turn_number"):
                turn_num = getattr(galaxy_ref.game, "turn_number", 1)
            visibility_snapshot = VisibilityService.compute(galaxy_ref, self.unit.owner, turn_number=turn_num)

        from entities import are_enemies
        from visibility import is_unit_visible
        from unit_components import TurretVariant, WingType

        guard_radius = float(self.parameters.get("guard_radius", DEFAULT_DEFEND_GUARD_RADIUS))
        closest_enemy = None
        min_dist = float('inf')

        for candidate in hex_obj.units:
            if are_enemies(self.unit.owner, candidate.owner) and candidate.current_hit_points > 0:
                if visibility_snapshot is not None and not is_unit_visible(visibility_snapshot, candidate):
                    continue

                # Fighter / Bomber targeting restrictions
                if self.unit.hull_size == HullSize.STRIKECRAFT_WING:
                    wing_comp = getattr(self.unit, "strikecraft_wing_component", None)
                    if wing_comp:
                        if wing_comp.wing_type == WingType.FIGHTER and candidate.hull_size != HullSize.STRIKECRAFT_WING:
                            continue
                        elif wing_comp.wing_type == WingType.BOMBER and candidate.hull_size == HullSize.STRIKECRAFT_WING:
                            continue

                can_target = False
                for t in weapons.turrets:
                    if candidate.hull_size == HullSize.STRIKECRAFT_WING and t.variant != TurretVariant.ANTI_STRIKECRAFT:
                        continue
                    can_target = True
                    break

                if not can_target:
                    continue

                dist_to_defended = distance(dest_pos, candidate.position)
                dist_to_unit = distance(self.unit.position, candidate.position)

                if dist_to_defended <= guard_radius or dist_to_unit <= guard_radius:
                    if dist_to_unit < min_dist:
                        min_dist = dist_to_unit
                        closest_enemy = candidate

        return closest_enemy

    def update(self, galaxy_ref: 'Galaxy') -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            super().update(galaxy_ref)
            return

        dest_system, dest_hex, dest_pos = self._resolve_destination(galaxy_ref)
        if dest_system is None or dest_hex is None or dest_pos is None:
            self.status = OrderStatus.FAILED
            return

        guard_radius = float(self.parameters.get("guard_radius", DEFAULT_DEFEND_GUARD_RADIUS))

        # Check if we are currently executing an AttackOrder sub-order
        has_attack_order = False
        if self.sub_orders:
            current_sub = self.sub_orders[0]
            if current_sub.order_type == OrderType.ATTACK:
                has_attack_order = True
                enemy_id = current_sub.parameters.get("target_unit_id")
                enemy_unit = None
                if galaxy_ref and hasattr(galaxy_ref, "get_unit_by_id"):
                    enemy_unit = galaxy_ref.get_unit_by_id(enemy_id) if enemy_id else None

                is_in_range = False
                if (
                    enemy_unit
                    and enemy_unit.current_hit_points > 0
                    and enemy_unit.in_system == dest_system
                    and enemy_unit.in_hex == dest_hex
                ):
                    dist_to_defended = distance(dest_pos, enemy_unit.position)
                    if dist_to_defended <= guard_radius * 1.2:
                        is_in_range = True

                if not is_in_range:
                    logger.debug(f"[{self.unit.name}] Defend target lost, destroyed, or left perimeter. Resuming position guard.")
                    current_sub.cancel()
                    self.sub_orders.popleft()
                    if self.unit.weapons_component:
                        self.unit.weapons_component.clear_target()
                    has_attack_order = False

        if not has_attack_order:
            # Look for enemies invading the guarded perimeter
            nearby_enemy = self._find_nearby_enemy(galaxy_ref, dest_system, dest_hex, dest_pos)
            if nearby_enemy:
                logger.debug(f"[{self.unit.name}] Hostile detected in defended sector: {nearby_enemy.name}. Engaging!")
                for sub in list(self.sub_orders):
                    sub.cancel()
                self.sub_orders.clear()
                if self.unit.engines_component:
                    self.unit.engines_component.move_target = None
                if self.unit.hyperdrive_component:
                    self.unit.hyperdrive_component.hex_jump_target = None
                    self.unit.hyperdrive_component.wormhole_jump_target = None

                attack_params = {"target_unit_id": nearby_enemy.id}
                self.add_sub_order(AttackOrder(self.unit, attack_params, parent_order=self))
            else:
                # No enemies: verify station-keeping at the defended coordinate
                has_movement_order = False
                if self.sub_orders:
                    current_sub = self.sub_orders[0]
                    if current_sub.order_type in [OrderType.MOVE, OrderType.REACH_WAYPOINT]:
                        has_movement_order = True

                in_same_system_and_hex = (
                    self.unit.in_system == dest_system and self.unit.in_hex == dest_hex
                )
                dist_to_target = (
                    distance(self.unit.position, dest_pos)
                    if in_same_system_and_hex
                    else float("inf")
                )

                if has_movement_order and in_same_system_and_hex and dist_to_target <= 30.0:
                    logger.debug(f"[{self.unit.name}] Arrived at defended post. Holding position.")
                    if self.sub_orders:
                        self.sub_orders[0].cancel()
                        self.sub_orders.popleft()
                    if self.unit.engines_component:
                        self.unit.engines_component.move_target = None
                    has_movement_order = False

                if not has_movement_order and (not in_same_system_and_hex or dist_to_target > 30.0):
                    move_params = {
                        "destination_system_name": dest_system,
                        "destination_hex_coord": dest_hex,
                        "destination_position": Position(dest_pos.x, dest_pos.y),
                    }
                    self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))

        super().update(galaxy_ref)

    def check_completion_conditions(self) -> None:
        pass
