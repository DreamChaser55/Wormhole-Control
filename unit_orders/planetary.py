"""Approach-only orders; the planetary turn phase owns all economic/combat effects."""
from .base import Order, OrderStatus, OrderType, OrderTargetField
from .movement import MoveOrder
from planetary_balance import INVASION_RANGE, SIEGE_RANGE


class PlanetaryOrder(Order):
    update_on_start = False
    target_fields = (OrderTargetField('target_id', 'celestial'),)
    KIND = ''

    def __init__(self, unit, parameters=None, parent_order=None):
        super().__init__(unit, OrderType[self.KIND], parameters, parent_order)

    def fail(self, reason="execution_failed"):
        for child in self.sub_orders:
            child.cancel()
        self.sub_orders.clear()
        super().fail(reason)

    def _prepare(self, galaxy):
        from planetary_warfare import exact_body, blocker, in_range
        game = self.unit.game
        target = exact_body(game, self.unit.owner, self.parameters.get('target_id'))
        # Future queued recruitment may satisfy cargo/resources; execution rechecks.
        cargo = self.unit.troop_transport_component
        error = blocker(game, self.unit.owner, self.KIND.lower(), target, self.unit,
                        self.parameters.get('amount'), resources=False,
                        troops=max(cargo.troops, self.parameters.get('amount', 0)) if cargo and self.KIND == 'INVADE_PLANET' else None)
        if error:
            self.fail(error)
            return
        if not in_range(self.unit, target, self.KIND.lower()) and not self.has_active_sub_orders():
            self.add_sub_order(MoveOrder.for_celestial_approach(
                self.unit, target, SIEGE_RANGE if self.KIND == 'BOMBARD_PLANET' else INVASION_RANGE,
                parent_order=self))

    def execute(self, galaxy_ref):
        super().execute(galaxy_ref)
        self._prepare(galaxy_ref)

    def update(self, galaxy_ref):
        if self.status != OrderStatus.IN_PROGRESS:
            return
        self._prepare(galaxy_ref)
        if self.status == OrderStatus.IN_PROGRESS:
            super().update(galaxy_ref)

    def check_completion_conditions(self):
        # Arriving is not completing the planetary action.
        pass


class RecruitTroopsOrder(PlanetaryOrder):
    KIND = 'RECRUIT_TROOPS'


class BombardPlanetOrder(PlanetaryOrder):
    KIND = 'BOMBARD_PLANET'


class InvadePlanetOrder(PlanetaryOrder):
    KIND = 'INVADE_PLANET'
