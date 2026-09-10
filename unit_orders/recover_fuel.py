"""Explicit, visibility-checked recovery of a persistent fuel cache."""
from .base import Order, OrderStatus, OrderType, OrderTargetField
from .movement import MoveOrder
from geometry import distance
from tactical_abilities import find_deployable, sector_for, deployed, RECOVERY_RANGE


def recovery_blocker(unit, cache, galaxy, *, fuel_amount=None):
    from visibility import VisibilityService, is_unit_visible
    if cache is None or cache.kind != 'fuel_cache' or cache.fuel <= 0:
        return 'target_unavailable'
    snapshot = VisibilityService.compute(galaxy, unit.owner, record_intel=False)
    if not is_unit_visible(snapshot, cache):
        return 'target_unavailable'
    am = unit.antimatter_component
    if not deployed(unit, galaxy) or not am or am.is_destroyed or (am.current_amount if fuel_amount is None else fuel_amount) >= am.max_capacity:
        return 'capability_unavailable'
    return None


class RecoverFuelCacheOrder(Order):
    target_fields = (OrderTargetField('target_unit_id', 'deployable'),)

    def __init__(self, unit, parameters=None, parent_order=None):
        super().__init__(unit, OrderType.RECOVER_FUEL_CACHE, parameters, parent_order)

    def execute(self, galaxy_ref):
        super().execute(galaxy_ref)
        self._recover(galaxy_ref)

    def _recover(self, galaxy):
        cache = find_deployable(galaxy, self.parameters.get('target_unit_id'))
        error = recovery_blocker(self.unit, cache, galaxy)
        if error:
            self.fail(error)
            return
        if sector_for(cache, galaxy) is not sector_for(self.unit, galaxy) or distance(self.unit.position, cache.position) > RECOVERY_RANGE:
            if not self.sub_orders:
                self.add_sub_order(MoveOrder.for_unit_approach(self.unit, cache, RECOVERY_RANGE-5, parent_order=self))
            return
        added = self.unit.antimatter_component.add(cache.fuel)
        cache.fuel -= added
        if cache.fuel <= 0:
            cache.destroy()
        self.status = OrderStatus.COMPLETED

    def update(self, galaxy_ref):
        super().update(galaxy_ref)
        if self.status == OrderStatus.IN_PROGRESS and not self.sub_orders:
            self._recover(galaxy_ref)

    def check_completion_conditions(self):
        pass  # Recovery, not merely finishing an approach, completes this order.
