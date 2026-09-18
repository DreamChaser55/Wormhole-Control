import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import Position, distance, position_at_distance_from_target
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from domain.units import Unit

logger = logging.getLogger(__name__)


class ConstructOrder(Order):
    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.CONSTRUCT, parameters, parent_order)
        from construction_customization import OVERRIDE_FIELDS
        for field in OVERRIDE_FIELDS:
            self.parameters.setdefault(field, None)

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        from location_validation import validate_order
        if not validate_order(self, galaxy_ref):
            return
        super().execute(galaxy_ref)

        if not self.unit.constructor_component:
            self.fail("capability_unavailable")
            logger.debug(f"CONSTRUCT order failed: Unit {self.unit.name} has no ConstructorComponent.")
            return

        unit_template_name = self.parameters.get("unit_template_name")
        target_pos = self.parameters.get("target_position")

        if not unit_template_name or target_pos is None:
            self.fail("invalid_parameters")
            logger.debug(f"CONSTRUCT order failed: Missing parameters.")
            return

        if not isinstance(target_pos, Position):
            target_pos = Position(*target_pos)
            self.parameters["target_position"] = target_pos

        constructor = self.unit.constructor_component
        from construction_customization import validate_template_overrides
        from unit_templates import get_template
        try:
            validate_template_overrides(get_template(unit_template_name, self.unit.owner),
                                        self.parameters["turret_type_override"], self.parameters["defense_type_override"])
        except ValueError:
            self.fail("invalid_parameters")
            return
        buildable = constructor.can_build(unit_template_name)

        if not buildable:
            self.fail("execution_failed")
            logger.debug(f"CONSTRUCT order failed: {self.unit.name} cannot build {unit_template_name}.")
            return

        target_sys = self.parameters["target_system_name"]
        target_hex = self.parameters["target_hex_coord"]

        in_same_hex = (self.unit.in_system == target_sys and self.unit.in_hex == target_hex)
        in_range = in_same_hex and (distance(self.unit.position, target_pos) <= constructor.build_range)

        if not in_range:
            engines = getattr(self.unit, "engines_component", None)
            if not engines or not engines.is_operational:
                self.fail("target_out_of_range")
                logger.debug(f"CONSTRUCT order failed: {self.unit.name} cannot reach construction site because it lacks operational engines.")
                gui = getattr(getattr(self.unit, 'game', None), 'gui', None)
                if gui:
                    gui.show_warning_dialog(
                        f"Unit <b>{self.unit.name}</b> cannot reach the construction site at ({target_pos.x:.0f}, {target_pos.y:.0f}) because it lacks operational engines.",
                        title="Target Out of Range"
                    )
                return

            if in_same_hex:
                dest_pos = position_at_distance_from_target(self.unit.position, target_pos, constructor.build_range - 5.0)
            else:
                dest_pos = target_pos

            move_params = {
                "destination_system_name": target_sys,
                "destination_hex_coord": target_hex,
                "destination_position": dest_pos,
            }
            self.add_sub_order(MoveOrder(self.unit, move_params, parent_order=self))
            self.add_sub_order(ConstructOrder(self.unit, self.parameters.copy(), parent_order=self))
            return

        player = next((p for p in getattr(getattr(self.unit, 'game', None), 'players', []) if p.id == self.unit.owner.id), None)
        if not player and getattr(self.unit, 'owner', None):
            player = self.unit.owner
        if not player:
            self.fail("execution_failed")
            logger.debug(f"CONSTRUCT order failed: Could not find player with id {self.unit.owner.id}.")
            return
        if player.credits < buildable.cost_credits:
            self.fail("insufficient_resources")
            logger.debug(f"CONSTRUCT order failed: Not enough credits.")
            if self.unit and getattr(self.unit, 'game', None) and self.unit.game.gui:
                self.unit.game.gui.show_warning_dialog(
                    f"Insufficient credits to construct <b>{unit_template_name}</b>.<br>Required: {buildable.cost_credits:.0f} credits (Available: {player.credits:.0f}).",
                    title="Insufficient Resources"
                )
            return

        success = constructor.start_construction(unit_template_name, target_pos, galaxy_ref, system_name=target_sys, hex_coord=target_hex, order=self,
                                                 turret_type_override=self.parameters["turret_type_override"],
                                                 defense_type_override=self.parameters["defense_type_override"])
        if success:
            constructor.construction_order_id = self.public_id
            self._charged_credits = buildable.cost_credits
            self._charged_player_id = self.unit.owner.id
        else:
            self.fail("construction_unavailable")

    def check_completion_conditions(self) -> None:
        if self.sub_orders:
            return
        if self._charged_player_id is None:
            self.status = OrderStatus.COMPLETED
            return
        constructor = self.unit.constructor_component
        if not constructor or constructor.current_construction_target is None:
            self.status = OrderStatus.COMPLETED

    def cancel(self) -> None:
        if self.status in {OrderStatus.COMPLETED, OrderStatus.FAILED, OrderStatus.CANCELLED}:
            return
        constructor = self.unit.constructor_component
        if constructor and constructor.current_construction_target and getattr(constructor, "construction_order_id", None) == self.public_id:
            self.refund_charge()
            constructor.cancel_construction()
        super().cancel()
