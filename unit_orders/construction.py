import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from .base import Order, OrderStatus, OrderType

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


class ConstructOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.CONSTRUCT, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not self.unit.constructor_component:
            self.status = OrderStatus.FAILED
            logger.debug(f"CONSTRUCT order failed: Unit {self.unit.name} has no ConstructorComponent.")
            return

        unit_template_name = self.parameters.get("unit_template_name")
        target_pos = self.parameters.get("target_position")

        if not unit_template_name or not target_pos:
            self.status = OrderStatus.FAILED
            logger.debug(f"CONSTRUCT order failed: Missing parameters.")
            return

        constructor = self.unit.constructor_component
        buildable = constructor.can_build(unit_template_name)

        if not buildable:
            self.status = OrderStatus.FAILED
            logger.debug(f"CONSTRUCT order failed: {self.unit.name} cannot build {unit_template_name}.")
            return

        player = next((p for p in self.unit.game.players if p.id == self.unit.owner.id), None)
        if not player:
            self.status = OrderStatus.FAILED
            logger.debug(f"CONSTRUCT order failed: Could not find player with id {self.unit.owner.id}.")
            return
        if player.credits < buildable.cost_credits:
            self.status = OrderStatus.FAILED
            logger.debug(f"CONSTRUCT order failed: Not enough credits.")
            return

        success = constructor.start_construction(unit_template_name, target_pos, galaxy_ref)
        if not success:
            self.status = OrderStatus.FAILED

    def check_completion_conditions(self) -> None:
        constructor = self.unit.constructor_component
        if not constructor or constructor.current_construction_target is None:
            self.status = OrderStatus.COMPLETED

    def cancel(self) -> None:
        constructor = self.unit.constructor_component
        if constructor and constructor.current_construction_target:
            unit_template_name = constructor.current_construction_target[0]
            buildable = constructor.can_build(unit_template_name)
            if buildable:
                player = next((p for p in self.unit.game.players if p.id == self.unit.owner.id), None)
                if player:
                    player.credits += buildable.cost_credits
                    logger.debug(f"Refunded {buildable.cost_credits} credits to player {player.name} for cancelled construction of {unit_template_name}.")
            constructor.cancel_construction()
        super().cancel()
