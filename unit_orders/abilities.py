import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance, move_towards_position
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from entities import Unit

logger = logging.getLogger(__name__)


class UseAbilityOrder(Order):
    """
    Order to activate a unit's special ability.

    For abilities that require a target unit the order validates range and moves
    the unit closer if necessary before firing. For abilities that require a
    target position, no auto-movement is performed — the position is used directly.
    For self-targeted abilities neither target is required.
    """
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.USE_ABILITY, parameters, parent_order)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)

        from unit_components import AbilityType

        if not self.unit.ability_component:
            logger.debug(f"[{self.unit.name}] USE_ABILITY order failed: unit has no AbilityComponent.")
            self.status = OrderStatus.FAILED
            return

        ability_type_str = self.parameters.get("ability_type")
        if not ability_type_str:
            logger.debug(f"[{self.unit.name}] USE_ABILITY order failed: no ability_type parameter.")
            self.status = OrderStatus.FAILED
            return

        try:
            ability_type = AbilityType(ability_type_str)
        except ValueError:
            logger.debug(f"[{self.unit.name}] USE_ABILITY order failed: unknown ability_type '{ability_type_str}'.")
            self.status = OrderStatus.FAILED
            return

        if not self.unit.ability_component.can_use(ability_type):
            logger.debug(f"[{self.unit.name}] USE_ABILITY order failed: ability {ability_type.name} not ready (on cooldown or already active).")
            self.status = OrderStatus.FAILED
            return

        from unit_components import ABILITY_DEFINITIONS
        defn = ABILITY_DEFINITIONS.get(ability_type)
        if not defn:
            self.status = OrderStatus.FAILED
            return

        target_unit_id = self.parameters.get("target_unit_id")
        target_position = self.parameters.get("target_position")

        # --- Pre-validation for CAPTURE_UNIT ability ---
        if ability_type == AbilityType.CAPTURE_UNIT and target_unit_id is not None:
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if target_unit:
                if target_unit.owner == self.unit.owner:
                    logger.debug(f"[{self.unit.name}] USE_ABILITY: target unit {target_unit.name} is already friendly.")
                    self.status = OrderStatus.FAILED
                    return
                if target_unit.engines_component is not None:
                    engines_disabled = target_unit.engines_component.is_destroyed or target_unit.is_disabled
                    if not engines_disabled:
                        logger.debug(f"[{self.unit.name}] USE_ABILITY: target {target_unit.name} engines are not disabled.")
                        self.status = OrderStatus.FAILED
                        return
                from unit_components import Defenses
                if target_unit.weapons_component and not target_unit.weapons_component.is_destroyed:
                    logger.debug(f"[{self.unit.name}] USE_ABILITY: target {target_unit.name} weapons are active.")
                    self.status = OrderStatus.FAILED
                    return
                defenses = target_unit.get_component(Defenses)
                if defenses and not defenses.is_destroyed:
                    logger.debug(f"[{self.unit.name}] USE_ABILITY: target {target_unit.name} defenses are active.")
                    self.status = OrderStatus.FAILED
                    return

        # --- Range check for unit-targeted abilities ---
        if defn.requires_target_unit and target_unit_id is not None:
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if not target_unit or target_unit.current_hit_points <= 0:
                logger.debug(f"[{self.unit.name}] USE_ABILITY: target unit {target_unit_id} not found or dead.")
                self.status = OrderStatus.FAILED
                return

            in_same_hex = (self.unit.in_system == target_unit.in_system and
                           self.unit.in_hex == target_unit.in_hex)
            in_range = in_same_hex and (distance(self.unit.position, target_unit.position) <= defn.range)

            if not in_range:
                if not self.has_active_sub_orders():
                    dest_pos = move_towards_position(self.unit.position, target_unit.position, defn.range - 5.0)
                    move_params = {
                        "destination_system_name": target_unit.in_system,
                        "destination_hex_coord": target_unit.in_hex,
                        "destination_position": dest_pos,
                    }
                    self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))
                    # Re-queue this ability order to fire once in range
                    self.add_sub_order(UseAbilityOrder(self.unit, self.parameters, parent_order=self))
                return

        # --- Range check for position-targeted abilities ---
        elif defn.requires_target_position and target_position is not None:
            target_sys = self.parameters.get("target_system_name") or self.unit.in_system
            target_hex = self.parameters.get("target_hex_coord") or self.unit.in_hex

            in_same_hex = (self.unit.in_system == target_sys and
                           self.unit.in_hex == target_hex)
            in_range = in_same_hex and (distance(self.unit.position, target_position) <= defn.range)

            if not in_range:
                if not self.has_active_sub_orders():
                    if in_same_hex:
                        dest_pos = move_towards_position(self.unit.position, target_position, defn.range - 5.0)
                    else:
                        dest_pos = target_position
                    
                    move_params = {
                        "destination_system_name": target_sys,
                        "destination_hex_coord": target_hex,
                        "destination_position": dest_pos,
                    }
                    self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))
                    # Re-queue this ability order to fire once in range
                    self.add_sub_order(UseAbilityOrder(self.unit, self.parameters, parent_order=self))
                return

        # --- Activate the ability ---
        success = self.unit.ability_component.activate(
            ability_type=ability_type,
            galaxy=galaxy_ref,
            target_unit_id=target_unit_id,
            target_position=target_position,
            target_system_name=self.parameters.get("target_system_name"),
            target_hex_coord=self.parameters.get("target_hex_coord"),
        )
        if success:
            logger.debug(f"[{self.unit.name}] USE_ABILITY: {ability_type.name} activated successfully.")
            self.status = OrderStatus.COMPLETED
        else:
            logger.debug(f"[{self.unit.name}] USE_ABILITY: {ability_type.name} activation failed.")
            self.status = OrderStatus.FAILED

    def check_completion_conditions(self) -> None:
        if self.status != OrderStatus.IN_PROGRESS:
            return
        if not self.sub_orders:
            self.status = OrderStatus.COMPLETED
