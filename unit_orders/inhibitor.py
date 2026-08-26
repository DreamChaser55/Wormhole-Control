import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from .base import Order, OrderStatus, OrderType

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


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

        result = self.unit.inhibitor_component.set_active(turn_on, galaxy_ref)
        if not result.allowed:
            logger.debug(
                "[%s (id:%s)] TOGGLE_INHIBITOR (%s): FAILED (%s).",
                self.unit.name,
                self.unit.id,
                self.order_id,
                result.message,
            )
            self.status = OrderStatus.FAILED
            return

        self.status = OrderStatus.COMPLETED
