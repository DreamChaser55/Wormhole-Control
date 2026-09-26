import logging
from game_logging import format_unit_for_log
from typing import Dict, Optional, Any, TYPE_CHECKING

from .base import Order, OrderStatus, OrderType

if TYPE_CHECKING:
    from galaxy import Galaxy
    from domain.units import Unit

logger = logging.getLogger(__name__)


class ToggleInhibitorOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.TOGGLE_INHIBITOR, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)
        
        turn_on = self.parameters.get("turn_on", False)
        
        if not self.unit.inhibitor_component:
            logger.debug(f"[{format_unit_for_log(self.unit)}] TOGGLE_INHIBITOR ({self.local_order_id}): FAILED (no inhibitor component).")
            self.status = OrderStatus.FAILED
            return

        result = self.unit.inhibitor_component.set_active(turn_on, galaxy_ref)
        if not result.allowed:
            logger.debug(
                "[%s] TOGGLE_INHIBITOR (%s): FAILED (%s).",
                format_unit_for_log(self.unit),
                self.local_order_id,
                result.message,
            )
            self.status = OrderStatus.FAILED
            return

        self.status = OrderStatus.COMPLETED
