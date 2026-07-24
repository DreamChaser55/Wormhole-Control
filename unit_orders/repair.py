import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance, move_towards_position
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


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
