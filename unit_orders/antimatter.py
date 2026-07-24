import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance, move_towards_position
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


class TransferAntimatterOrder(Order):
    """Transfers antimatter from this unit's own AntimatterStorage into a
    friendly target unit's AntimatterStorage. This is how units without an
    AntimatterHarvester component are replenished: another unit (typically
    a harvester, but any unit with stored antimatter) must fly over and
    transfer some of its reserves.

    Modeled on RepairOrder: approaches the target if out of range, then
    transfers ANTIMATTER_TRANSFER_RATE per turn until the target is full
    or the source is depleted.
    """
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.TRANSFER_ANTIMATTER, parameters, parent_order)

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

    def _get_transfer_range(self) -> float:
        from constants import ANTIMATTER_TRANSFER_RANGE
        return ANTIMATTER_TRANSFER_RANGE

    def _do_transfer_tick(self, target_unit: 'Unit') -> None:
        """Performs a single turn's worth of antimatter transfer from this unit to the target."""
        from constants import ANTIMATTER_TRANSFER_RATE
        source_am = self.unit.antimatter_component
        target_am = target_unit.antimatter_component
        if not source_am or not target_am:
            return
        amount_to_send = min(ANTIMATTER_TRANSFER_RATE, source_am.current_amount)
        if amount_to_send <= 0:
            return
        added = target_am.add(amount_to_send)
        if added > 0:
            source_am.consume(added)
            logger.debug(f"TRANSFER_ANTIMATTER: {self.unit.name} transferred {added:.1f} antimatter to {target_unit.name}. "
                         f"Source: {source_am.current_amount:.1f}/{source_am.max_capacity:.1f}, "
                         f"Target: {target_am.current_amount:.1f}/{target_am.max_capacity:.1f}")

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not self.unit.antimatter_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"TRANSFER_ANTIMATTER order failed: Unit {self.unit.name} has no AntimatterStorage.")
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)

        if not target_unit:
            self.status = OrderStatus.FAILED
            logger.debug(f"TRANSFER_ANTIMATTER order failed: Target unit {target_unit_id} not found.")
            return

        if target_unit.owner != self.unit.owner:
            self.status = OrderStatus.FAILED
            logger.debug(f"TRANSFER_ANTIMATTER order failed: Target unit {target_unit.name} is not friendly.")
            return

        if not target_unit.antimatter_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"TRANSFER_ANTIMATTER order failed: Target unit {target_unit.name} has no AntimatterStorage.")
            return

        transfer_range = self._get_transfer_range()
        in_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        in_range = in_same_system_and_hex and (distance(self.unit.position, target_unit.position) <= transfer_range)

        if not in_range:
            if in_same_system_and_hex:
                dest_pos = move_towards_position(self.unit.position, target_unit.position, transfer_range - 5.0)
            else:
                dest_pos = target_unit.position

            move_params = {
                "destination_system_name": target_unit.in_system,
                "destination_hex_coord": target_unit.in_hex,
                "destination_position": dest_pos
            }
            self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))

    def update(self, galaxy_ref: 'Galaxy') -> None:
        super().update(galaxy_ref)

        if self.status != OrderStatus.IN_PROGRESS:
            return
        if self.sub_orders:
            # Still approaching the target unit.
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id) if target_unit_id else None

        if (not target_unit or target_unit.owner != self.unit.owner or
                not target_unit.antimatter_component or not self.unit.antimatter_component):
            self.status = OrderStatus.FAILED
            return

        transfer_range = self._get_transfer_range()
        in_same_system_and_hex = (self.unit.in_system == target_unit.in_system and self.unit.in_hex == target_unit.in_hex)
        in_range = in_same_system_and_hex and (distance(self.unit.position, target_unit.position) <= transfer_range)

        if not in_range:
            # Target moved away since we last checked; re-approach.
            if in_same_system_and_hex:
                dest_pos = move_towards_position(self.unit.position, target_unit.position, transfer_range - 5.0)
            else:
                dest_pos = target_unit.position

            move_params = {
                "destination_system_name": target_unit.in_system,
                "destination_hex_coord": target_unit.in_hex,
                "destination_position": dest_pos
            }
            self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))
            return

        self._do_transfer_tick(target_unit)
        self.check_completion_conditions()

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id) if target_unit_id else None

        source_am = self.unit.antimatter_component
        target_am = target_unit.antimatter_component if target_unit else None

        if not target_unit or not source_am or not target_am:
            self.status = OrderStatus.COMPLETED
            return

        # Complete once the source is fully depleted or the target is fully topped up.
        if source_am.current_amount <= 0.0 or target_am.current_amount >= target_am.max_capacity:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"TRANSFER_ANTIMATTER order completed: {self.unit.name} -> {target_unit.name}.")
