import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import Circle, is_circle_contained, do_circles_intersect
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
