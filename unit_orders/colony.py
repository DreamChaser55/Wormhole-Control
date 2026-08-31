import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance
from constants import DEFAULT_STANDOFF_DISTANCE
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


def within_colony_range(unit, target):
    """Shared, side-effect-free proximity used by execution and batch projection."""
    radius = getattr(target, "collision_radius", getattr(target, "radius", 0.0))
    return (unit.in_system == target.in_system and unit.in_hex == target.in_hex
            and distance(unit.position, target.position) <= radius + DEFAULT_STANDOFF_DISTANCE + 0.01)


class ColonizeOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.COLONIZE, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_id = self.parameters.get("target_id")
        if not target_id:
            self.fail("invalid_parameters")
            logger.debug(f"COLONIZE order failed: no target_id.")
            return

        target = galaxy_ref.get_celestial_body_by_id(target_id)

        if not target:
            self.fail("target_unavailable")
            logger.debug(f"COLONIZE order failed: Celestial body with ID {target_id} not found.")
            return

        if not self.unit.colony_component:
            self.fail("capability_unavailable")
            logger.debug(f"COLONIZE order failed: Unit {self.unit.name} has no ColonyComponent.")
            return

        in_range = within_colony_range(self.unit, target)

        if not in_range:
            if not self.has_active_sub_orders():
                move_order = MoveOrder.for_celestial_approach(
                    self.unit,
                    target,
                    DEFAULT_STANDOFF_DISTANCE,
                    parent_order=self,
                )
                self.add_sub_order(move_order)

                colonize_sub_order = ColonizeOrder(self.unit, self.parameters, parent_order=self)
                self.add_sub_order(colonize_sub_order)
            return

        cargo = self.unit.colony_component.population_cargo
        if cargo <= 0:
            self.fail("insufficient_population")
            logger.debug(f"COLONIZE order failed: No population in cargo to unload.")
            return

        success = self.unit.colony_component.unload_population(target, cargo)

        if success:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"COLONIZE order completed: Unit {self.unit.name} successfully colonized {target.name}.")
        else:
            self.fail("target_unavailable")
            logger.debug(f"COLONIZE order failed: Unload population failed for unit {self.unit.name} on {target.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            target_id = self.parameters.get("target_id")
            if target_id is not None and getattr(self.unit, 'game', None) and getattr(self.unit.game, 'galaxy', None):
                target = self.unit.game.galaxy.get_celestial_body_by_id(target_id)
                if target and target.owner == self.unit.owner:
                    self.status = OrderStatus.COMPLETED


class LoadColonistsOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.LOAD_COLONISTS, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        target_id = self.parameters.get("target_id")
        amount = self.parameters.get("amount", 50)

        if not target_id:
            self.fail("invalid_parameters")
            logger.debug(f"LOAD_COLONISTS order failed: no target_id.")
            return

        target = galaxy_ref.get_celestial_body_by_id(target_id)

        if not target:
            self.fail("target_unavailable")
            logger.debug(f"LOAD_COLONISTS order failed: Celestial body with ID {target_id} not found.")
            return

        if not self.unit.colony_component:
            self.fail("capability_unavailable")
            logger.debug(f"LOAD_COLONISTS order failed: Unit {self.unit.name} has no ColonyComponent.")
            return

        in_range = within_colony_range(self.unit, target)

        if not in_range:
            if not self.has_active_sub_orders():
                move_order = MoveOrder.for_celestial_approach(
                    self.unit,
                    target,
                    DEFAULT_STANDOFF_DISTANCE,
                    parent_order=self,
                )
                self.add_sub_order(move_order)
                
                load_params = {
                    "target_id": target.id,
                    "target_name": getattr(target, 'name', None),
                    "amount": amount
                }
                load_order = LoadColonistsOrder(self.unit, load_params, parent_order=self)
                self.add_sub_order(load_order)
            return

        success = self.unit.colony_component.load_population(target, amount)

        if success:
            self.status = OrderStatus.COMPLETED
        else:
            self.fail("execution_failed")
            logger.debug(f"LOAD_COLONISTS order failed for unit {self.unit.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED
