import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance
from constants import DEFAULT_STANDOFF_DISTANCE, HullSize, PlanetType
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit, Planet

logger = logging.getLogger(__name__)


def within_gas_giant_range(unit: 'Unit', target: Any) -> bool:
    """Proximity check for gas giant entry."""
    radius = getattr(target, "collision_radius", getattr(target, "radius", 0.0))
    return (unit.in_system == target.in_system and unit.in_hex == target.in_hex
            and distance(unit.position, target.position) <= radius + DEFAULT_STANDOFF_DISTANCE + 0.01)


class EnterGasGiantOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.ENTER_GAS_GIANT, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_id = self.parameters.get("target_id")
        target_name = None
        if target_id and getattr(self.unit, 'game', None) and getattr(self.unit.game, 'galaxy', None):
            target = self.unit.game.galaxy.get_celestial_body_by_id(target_id)
            if target:
                target_name = target.name
        state_data["target_id"] = target_id
        state_data["target_name"] = target_name
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if getattr(self.unit, 'hull_size', None) == HullSize.STRIKECRAFT_WING:
            self.fail("hazard_blocked")
            logger.debug(f"ENTER_GAS_GIANT failed: Strikecraft wings cannot enter gas giants.")
            return

        eng = getattr(self.unit, 'engines_component', None)
        if not eng or not getattr(eng, 'is_operational', False):
            self.fail("capability_unavailable")
            logger.debug(f"ENTER_GAS_GIANT failed: Unit {self.unit.name} has no operational engines.")
            return

        target_id = self.parameters.get("target_id")
        if not target_id:
            self.fail("invalid_parameters")
            logger.debug(f"ENTER_GAS_GIANT failed: No target_id specified.")
            return

        target = galaxy_ref.get_celestial_body_by_id(target_id)
        if not target:
            self.fail("target_unavailable")
            logger.debug(f"ENTER_GAS_GIANT failed: Target {target_id} not found.")
            return

        if getattr(target, 'planet_type', None) != PlanetType.GAS_GIANT:
            self.fail("target_unavailable")
            logger.debug(f"ENTER_GAS_GIANT failed: Target {target.name} is not a gas giant.")
            return

        in_range = within_gas_giant_range(self.unit, target)
        if not in_range:
            if not self.has_active_sub_orders():
                move_order = MoveOrder.for_celestial_approach(
                    self.unit,
                    target,
                    DEFAULT_STANDOFF_DISTANCE,
                    parent_order=self,
                )
                self.add_sub_order(move_order)
                enter_sub_order = EnterGasGiantOrder(self.unit, self.parameters, parent_order=self)
                self.add_sub_order(enter_sub_order)
                if self.sub_orders:
                    self.sub_orders[0].execute(galaxy_ref=galaxy_ref)
            return

        success = target.hide_unit(self.unit, galaxy_ref)
        if success:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"ENTER_GAS_GIANT completed: {self.unit.name} is now hidden in {target.name}.")
        else:
            self.fail("execution_failed")
            logger.debug(f"ENTER_GAS_GIANT failed: Could not hide {self.unit.name} in {target.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            if getattr(self.unit, 'is_hidden_in_gas_giant', False):
                self.status = OrderStatus.COMPLETED


class LeaveGasGiantOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.LEAVE_GAS_GIANT, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        if not getattr(self.unit, 'is_hidden_in_gas_giant', False) and getattr(self.unit, 'hidden_in_gas_giant_id', None) is None:
            self.fail("invalid_state")
            logger.debug(f"LEAVE_GAS_GIANT failed: Unit {self.unit.name} is not hidden in a gas giant.")
            return

        gas_giant_id = getattr(self.unit, 'hidden_in_gas_giant_id', None)
        target = None
        if gas_giant_id is not None:
            target = galaxy_ref.get_celestial_body_by_id(gas_giant_id)

        if not target and self.unit.in_system and self.unit.in_hex is not None:
            sys_obj = galaxy_ref.systems.get(self.unit.in_system)
            if sys_obj:
                hex_obj = sys_obj.hexes.get(self.unit.in_hex)
                if hex_obj:
                    for b in hex_obj.celestial_bodies:
                        if getattr(b, 'planet_type', None) == PlanetType.GAS_GIANT and self.unit in getattr(b, 'hidden_units', []):
                            target = b
                            break

        if not target:
            self.fail("target_unavailable")
            logger.debug(f"LEAVE_GAS_GIANT failed: Gas giant not found for unit {self.unit.name}.")
            return

        emerge_pos = target.release_unit(self.unit, galaxy_ref)
        if emerge_pos:
            self.status = OrderStatus.COMPLETED
            logger.debug(f"LEAVE_GAS_GIANT completed: {self.unit.name} emerged at {emerge_pos}.")
        else:
            self.fail("execution_failed")
            logger.debug(f"LEAVE_GAS_GIANT failed: Could not release {self.unit.name} from {target.name}.")

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            if not getattr(self.unit, 'is_hidden_in_gas_giant', False):
                self.status = OrderStatus.COMPLETED
