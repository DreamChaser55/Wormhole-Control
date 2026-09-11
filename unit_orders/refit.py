from unit_orders.base import OrderTargetField
import logging
from typing import Dict, Optional, Any, TYPE_CHECKING

from geometry import distance
from .base import Order, OrderStatus, OrderType
from .movement import MoveOrder

if TYPE_CHECKING:
    from galaxy import Galaxy
    from domain.units import Unit

logger = logging.getLogger(__name__)


def get_hull_restriction_flag(component_name: str) -> str:
    from refit_validation import COMPONENT_SPECS, canonical_component_name
    spec = COMPONENT_SPECS.get(canonical_component_name(component_name))
    return spec.flag if spec else f"has_{component_name.lower()}"



class RefitOrder(Order):
    """Order instructing a unit with a Constructor to add or remove components on a friendly unit."""
    target_fields = (OrderTargetField('target_unit_id', 'unit', public=True),)

    def __init__(self, unit: 'Unit', parameters: Dict[str, Any] = None, parent_order: Optional[Order] = None):
        super().__init__(unit, OrderType.REFIT_UNIT, parameters, parent_order)

    def get_state_data(self) -> Dict[str, Any]:
        state_data = super().get_state_data()
        target_unit_id = self.parameters.get("target_unit_id")
        action = self.parameters.get("action", "ADD")
        component_type = self.parameters.get("component_type", "")
        cost_credits = self.parameters.get("cost_credits", 0)
        time_to_build = self.parameters.get("time_to_build", 1)

        target_name = None
        lookup_attempted = False
        lookup_success = False
        if target_unit_id is not None and self.unit and self.unit.game and self.unit.game.galaxy:
            lookup_attempted = True
            target_unit = self.unit.game.galaxy.get_unit_by_id(target_unit_id)
            if target_unit:
                target_name = target_unit.name
                lookup_success = True

        state_data.update({
            "target_unit_id": target_unit_id,
            "target_name": target_name,
            "action": action,
            "component_type": component_type,
            "cost_credits": cost_credits,
            "time_to_build": time_to_build,
            "lookup_attempted": lookup_attempted,
            "lookup_success": lookup_success,
        })
        return state_data

    def execute(self, galaxy_ref: 'Galaxy') -> None:
        super().execute(galaxy_ref)
        from refit_validation import evaluate_refit
        from domain.players import are_allies
        constructor = self.unit.constructor_component
        target = galaxy_ref.get_unit_by_id(self.parameters.get("target_unit_id"))
        if not constructor or constructor.is_destroyed:
            self.fail("refit_unavailable")
            return
        if not target or target.current_hit_points <= 0 or not are_allies(self.unit.owner, target.owner):
            self.fail("target_unavailable")
            return
        action = self.parameters.get("action", "ADD")
        evaluation = evaluate_refit(target, action, self.parameters.get("component_type"),
                                    self.parameters.get("component_config"))
        if evaluation.errors:
            self.fail("invalid_refit")
            gui = getattr(self.unit.game, 'gui', None)
            if gui:
                from html import escape
                gui.show_warning_dialog('<br>'.join(escape(e) for e in evaluation.errors), title="Invalid Retrofit")
            return
        in_range = (self.unit.in_system == target.in_system and self.unit.in_hex == target.in_hex
                    and distance(self.unit.position, target.position) <= constructor.build_range)
        if not in_range:
            self.add_sub_order(MoveOrder.for_unit_approach(self.unit, target,
                                constructor.build_range - 5.0, parent_order=self))
            self.add_sub_order(RefitOrder(self.unit, self.parameters.copy(), parent_order=self))
            return
        # Hints supplied by UI/events never determine charges or installed hull usage.
        self.parameters.update(component_type=evaluation.component_name,
                               component_config=evaluation.configuration,
                               cost_credits=evaluation.cost_credits,
                               time_to_build=evaluation.duration)
        if not constructor.start_refit(target, action, evaluation.component_name,
                                       evaluation.configuration, order=self):
            self.fail("refit_unavailable")

    def check_completion_conditions(self) -> None:
        # A parent approach order owns no charge and completes after its children.
        # The actual refit child is settled explicitly by its Constructor.
        if (self.status == OrderStatus.IN_PROGRESS and not self.sub_orders
                and self._charged_player_id is None):
            self.status = OrderStatus.COMPLETED

    def cancel(self) -> None:
        if self.status in {OrderStatus.COMPLETED, OrderStatus.FAILED, OrderStatus.CANCELLED}:
            return
        constructor = self.unit.constructor_component
        if constructor and constructor.current_refit_target and constructor.refit_order_id == self.public_id:
            constructor.cancel_refit()
        super().cancel()
