from unit_orders.base import OrderTargetField
import logging
from game_logging import format_unit_for_log
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from domain.units import Unit

logger = logging.getLogger(__name__)


class RepairOrder(Order):
    target_fields = (OrderTargetField('target_unit_id', 'unit', public=True),)

    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.REPAIR, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_unit_id = self.parameters.get("target_unit_id")
        target_name = None
        lookup_attempted = False
        lookup_success = False
        if target_unit_id is not None and self.unit and self.unit.game:
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
            self.fail("execution_failed")
            logger.debug(f"REPAIR order failed: Unit {format_unit_for_log(self.unit)} has no RepairComponent.")
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)

        if not target_unit:
            self.fail("target_unavailable")
            logger.debug(f"REPAIR order failed: Target unit {target_unit_id} not found.")
            return

        from domain.players import are_allies
        if not are_allies(self.unit.owner, target_unit.owner):
            self.fail("target_unavailable")
            logger.debug(f"REPAIR order failed: Target unit {format_unit_for_log(target_unit)} is not friendly/allied.")
            return

        self.unit.repair_component.set_target(target_unit)

        in_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        in_range = in_same_system_and_hex and (distance(self.unit.position, target_unit.position) <= self.unit.repair_component.repair_range)

        if not in_range:
            move_order = MoveOrder.for_unit_approach(
                self.unit,
                target_unit,
                self.unit.repair_component.repair_range - 5.0,
                parent_order=self,
            )
            self.add_sub_order(move_order)

            repair_sub_order = RepairOrder(self.unit, self.parameters, parent_order=self)
            self.add_sub_order(repair_sub_order)

    def refresh_approach(self, galaxy_ref: 'Galaxy') -> None:
        """Rebind stale approach waypoints when the repaired unit moved."""
        if self.status != OrderStatus.IN_PROGRESS or not self.unit.repair_component:
            return
        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = galaxy_ref.get_unit_by_id(target_unit_id) if galaxy_ref and target_unit_id is not None else None
        if not target_unit or target_unit.current_hit_points <= 0:
            return
        if not self.sub_orders or self.sub_orders[0].order_type != OrderType.MOVE:
            return
        repair_range = self.unit.repair_component.repair_range
        local = self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex
        if local and distance(self.unit.position, target_unit.position) <= repair_range:
            self.sub_orders[0].cancel()
            self.sub_orders.popleft()
            return
        child = self.sub_orders[0]
        dest_system = child.parameters.get("destination_system_name")
        dest_hex = child.parameters.get("destination_hex_coord")
        dest_pos = child.parameters.get("destination_position")
        changed_sector = dest_system != target_unit.in_system or dest_hex != target_unit.in_hex
        moved_out_of_bubble = local and dest_pos is not None and distance(dest_pos, target_unit.position) > repair_range - 1.0
        if changed_sector or moved_out_of_bubble:
            child.cancel()
            self.sub_orders.popleft()
            fresh = MoveOrder.for_unit_approach(
                self.unit,
                target_unit,
                repair_range - 5.0,
                parent_order=self,
            )
            fresh.unit = self.unit
            self.sub_orders.appendleft(fresh)
            fresh.execute(galaxy_ref)
            if fresh.status == OrderStatus.IN_PROGRESS:
                fresh.update(galaxy_ref)

    def update(self, galaxy_ref: 'Galaxy') -> None:
        self.refresh_approach(galaxy_ref)
        super().update(galaxy_ref)

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
