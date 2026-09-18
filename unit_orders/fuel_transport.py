"""Storage-based pickups, deliveries and repeating depot transport."""

from .base import Order, OrderStatus, OrderType, OrderTargetField
from .movement import MoveOrder
from constants import ANTIMATTER_TRANSFER_RANGE
from antimatter_logistics import (
    exchange_blocker,
    exchange,
    in_transfer_range,
    estimate_approach,
    buffered_fuel,
    equipment_upkeep,
)


class TransferAntimatterOrder(Order):
    update_on_start = False
    target_fields = (OrderTargetField("target_unit_id", "unit", public=True),)
    TYPE = "TRANSFER_ANTIMATTER"
    TAKE = False

    def __init__(self, unit, parameters=None, parent_order=None):
        super().__init__(unit, OrderType[self.TYPE], parameters, parent_order)

    def get_state_data(self):
        data = super().get_state_data()
        target = self.unit.game.galaxy.get_unit_by_id(
            self.parameters.get("target_unit_id")
        )
        data.update(
            target_unit_id=self.parameters.get("target_unit_id"),
            target_name=target.name if target else None,
            lookup_attempted=True,
            lookup_success=target is not None,
        )
        return data

    def _target(self, galaxy):
        return galaxy.get_unit_by_id(self.parameters.get("target_unit_id"))

    def _reserve(self):
        return float(self.parameters.get("reserve", 0.0))

    def _pair(self, target):
        return (target, self.unit) if self.TAKE else (self.unit, target)

    def _prepare(self, galaxy):
        target = self._target(galaxy)
        blocker = exchange_blocker(self.unit, target, galaxy)
        if blocker:
            self.fail(blocker)
            return None
        donor, receiver = self._pair(target)
        if (
            donor.antimatter_component.current_amount <= self._reserve()
            or receiver.antimatter_component.current_amount
            >= receiver.antimatter_component.max_capacity
        ):
            self.status = OrderStatus.COMPLETED
            return None
        if not in_transfer_range(self.unit, target):
            if not self.sub_orders:
                self.add_sub_order(
                    MoveOrder.for_unit_approach(
                        self.unit,
                        target,
                        ANTIMATTER_TRANSFER_RANGE - 5,
                        parent_order=self,
                    )
                )
            return None
        return target

    def execute(self, galaxy_ref):
        super().execute(galaxy_ref)
        self._prepare(galaxy_ref)

    def update(self, galaxy_ref):
        if self.status != OrderStatus.IN_PROGRESS:
            return
        # Recheck endpoints even during an approach.
        blocker = exchange_blocker(self.unit, self._target(galaxy_ref), galaxy_ref)
        if blocker:
            for child in self.sub_orders:
                child.cancel()
            self.sub_orders.clear()
            self.fail(blocker)
            return
        super().update(galaxy_ref)
        if self.status != OrderStatus.IN_PROGRESS or self.sub_orders:
            return
        target = self._prepare(galaxy_ref)
        if target is not None:
            exchange(*self._pair(target), self._reserve())
            self._prepare(galaxy_ref)


class TakeAntimatterOrder(TransferAntimatterOrder):
    TYPE = "TAKE_ANTIMATTER"
    TAKE = True


class ContinuousFuelDeliveryOrder(Order):
    """Continuous loading/delivery with a configured or automatically chosen recipient.

    Harvesters specialize the source and reserve rules, sharing the delivery lifecycle.
    """
    update_on_start = False
    HARVESTING = False
    TYPE = OrderType.CONTINUOUS_ANTIMATTER_TRANSPORT
    SOURCE_FIELD = "source_unit_id"
    target_fields = (
        OrderTargetField("target_unit_id", "unit", public=True),
        OrderTargetField("source_unit_id", "unit", public=True),
    )

    def __init__(self, unit, parameters=None, parent_order=None):
        super().__init__(unit, self.TYPE, parameters, parent_order)
        self.phase = self.loading_phase
        self.waiting_reason = None
        from constants import ANTIMATTER_HARVESTER_RETURN_THRESHOLD
        self.return_reserve = float(ANTIMATTER_HARVESTER_RETURN_THRESHOLD) if self.HARVESTING else 0.0
        self.active_destination_unit_id = None

    @property
    def loading_phase(self):
        return "harvesting" if self.HARVESTING else "loading"

    @property
    def automatic(self):
        return self.parameters.get("target_unit_id") is None

    def source(self, galaxy):
        lookup = (galaxy.get_celestial_body_by_id if self.HARVESTING
                  else galaxy.get_unit_by_id)
        return lookup(self.parameters.get(self.SOURCE_FIELD))

    def get_persistence_state(self):
        return dict(super().get_persistence_state(), phase=self.phase,
                    waiting_reason=self.waiting_reason, return_reserve=self.return_reserve,
                    active_destination_unit_id=self.active_destination_unit_id)

    def restore_persistence_state(self, state):
        super().restore_persistence_state(state)
        from state_codec import number

        if (state["phase"] not in (self.loading_phase, "delivering") or
                state["waiting_reason"] not in (None, "source_empty", "destination_full",
                                               "insufficient_load", "no_destination")):
            raise ValueError("Invalid continuous fuel phase")
        number(state["return_reserve"], "return_reserve", 0)
        number(self.parameters.get(self.SOURCE_FIELD), self.SOURCE_FIELD, 0, integer=True)
        for value in (self.parameters.get("target_unit_id"), state["active_destination_unit_id"]):
            if value is not None:
                number(value, "destination_unit_id", 0, integer=True)
        if (not self.automatic and state["active_destination_unit_id"] not in
                (None, self.parameters["target_unit_id"])):
            raise ValueError("Manual route has a different active destination")
        self.phase = state["phase"]
        self.waiting_reason = state["waiting_reason"]
        self.return_reserve = state["return_reserve"]
        self.active_destination_unit_id = state["active_destination_unit_id"]

    def get_state_data(self):
        data = super().get_state_data()
        galaxy = self.unit.game.galaxy
        source = self.source(galaxy)
        destination = galaxy.get_unit_by_id(self.parameters.get("target_unit_id"))
        active = galaxy.get_unit_by_id(self.active_destination_unit_id)
        data.update(phase=self.phase, waiting_reason=self.waiting_reason,
                    return_reserve=self.return_reserve,
                    destination_mode="automatic" if self.automatic else "manual",
                    source_id=self.parameters.get(self.SOURCE_FIELD),
                    source_name=source.name if source else None,
                    target_unit_id=self.parameters.get("target_unit_id"),
                    target_name=destination.name if destination else None,
                    active_destination_unit_id=self.active_destination_unit_id,
                    active_destination_name=active.name if active else None)
        return data

    def _clear_approach(self):
        for child in self.sub_orders:
            child.cancel()
        self.sub_orders.clear()

    def _clear_destination(self):
        self._clear_approach()
        self.active_destination_unit_id = None

    def _endpoints(self, galaxy):
        from antimatter_logistics import continuous_source_blocker
        source = self.source(galaxy)
        destination = galaxy.get_unit_by_id(self.parameters.get("target_unit_id"))
        blocker = ("invalid_parameters" if self.parameters.get(self.SOURCE_FIELD) is None
                   else continuous_source_blocker(self.unit, source, galaxy, harvesting=self.HARVESTING))
        if not blocker and not self.automatic:
            blocker = exchange_blocker(self.unit, destination, galaxy)
            if source is destination:
                blocker = "invalid_parameters"
        if blocker:
            self._clear_approach()
            self.fail(blocker)
            return None
        return source, destination

    def _budget(self, source, destination, galaxy, *, from_source=False):
        from antimatter_logistics import delivery_budget
        return delivery_budget(self.unit, source, destination, galaxy,
                               harvesting=self.HARVESTING, from_source=from_source)

    def _approach(self, target, galaxy, *, source=False):
        from antimatter_logistics import at_source, source_range
        harvesting = source and self.HARVESTING
        arrived = (at_source(self.unit, target, True) if harvesting
                   else in_transfer_range(self.unit, target))
        if arrived:
            self._clear_approach()
            return True
        radius = source_range(self.unit, harvesting)
        estimate = estimate_approach(self.unit, galaxy, target, approach_range=radius)
        if estimate is None:
            self.fail("path_unavailable")
        elif self.unit.antimatter_component.current_amount < buffered_fuel(estimate.fuel):
            self.fail("insufficient_resources")
        elif not self.sub_orders:
            factory = MoveOrder.for_celestial_approach if harvesting else MoveOrder.for_unit_approach
            # Celestial approaches express standoff from the surface; harvesting
            # range, like the estimator, is measured from the body's center.
            standoff = radius - 5 - (target.collision_radius if harvesting else 0)
            move = factory(self.unit, target, standoff, parent_order=self)
            move.parameters["logistics_anchor"] = self._anchor(target)
            self.add_sub_order(move)
        return False

    @staticmethod
    def _anchor(target):
        return [target.in_system, list(target.in_hex), [target.position.x, target.position.y]]

    def _advance_approach(self, target, galaxy):
        if not self.sub_orders:
            return True
        child = self.sub_orders[0]
        # Moving depots are followed by identity, including while already travelling.
        if child.parameters.get("logistics_anchor") != self._anchor(target):
            self._clear_approach()
            return True
        if child.status == OrderStatus.PENDING:
            child.execute(galaxy)
        if child.status == OrderStatus.IN_PROGRESS:
            child.update(galaxy)
        if child.status == OrderStatus.COMPLETED:
            self.sub_orders.popleft()
            return True
        if child.status == OrderStatus.FAILED:
            if self.automatic and self.phase == "delivering":
                failed_id = self.active_destination_unit_id
                self._clear_destination()
                source = self.source(galaxy)
                replacement = self._choose_destination(source, galaxy, excluded=(failed_id,))
                if replacement is None:
                    self._return_to_source(source, galaxy, "no_destination")
                else:
                    self._approach(replacement, galaxy)
            else:
                reason = child.failure_reason or "suborder_failed"
                self._clear_approach()
                self.fail(reason)
        elif child.status == OrderStatus.CANCELLED:
            self.cancel()
        return False

    def execute(self, galaxy_ref):
        super().execute(galaxy_ref)
        pair = self._endpoints(galaxy_ref)
        if not pair:
            return
        source, destination = pair
        if destination is not None:
            budget = self._budget(source, destination, galaxy_ref, from_source=True)
            if budget is None:
                self.fail("path_unavailable")
                return
            if budget >= self.unit.antimatter_component.max_capacity:
                self.fail("insufficient_capacity")
                return
        self._approach(source, galaxy_ref, source=True)

    def _return_to_source(self, source, galaxy, reason=None):
        self._clear_destination()
        self.phase = self.loading_phase
        self.waiting_reason = reason
        self._approach(source, galaxy, source=True)

    def _choose_destination(self, source, galaxy, *, excluded=()):
        from antimatter_logistics import automatic_recipient
        destination = automatic_recipient(self.unit, source, galaxy,
                                          harvesting=self.HARVESTING, excluded=excluded)
        self.active_destination_unit_id = destination.id if destination else None
        return destination

    def update(self, galaxy_ref):
        if self.status != OrderStatus.IN_PROGRESS:
            return
        pair = self._endpoints(galaxy_ref)
        if not pair:
            return
        source, configured = pair
        tank = self.unit.antimatter_component
        destination = galaxy_ref.get_unit_by_id(self.active_destination_unit_id)
        if self.phase == "delivering":
            if self.automatic:
                valid = (destination is not None and destination.owner is self.unit.owner
                         and destination is not source
                         and exchange_blocker(self.unit, destination, galaxy_ref) is None
                         and destination.antimatter_component.current_amount
                         < destination.antimatter_component.max_capacity)
                budget = self._budget(source, destination, galaxy_ref) if valid else None
                if budget is None or tank.current_amount <= budget:
                    self._clear_destination()
                    destination = self._choose_destination(source, galaxy_ref)
                if destination is None:
                    self._return_to_source(source, galaxy_ref, "no_destination")
                    return
            else:
                destination = configured
                self.active_destination_unit_id = destination.id
                if self.HARVESTING and destination.antimatter_component.current_amount >= destination.antimatter_component.max_capacity:
                    self._return_to_source(source, galaxy_ref, "destination_full")
                    return
        target = source if self.phase == self.loading_phase else destination
        if not self._advance_approach(target, galaxy_ref):
            return
        self.waiting_reason = None
        if self.phase == self.loading_phase:
            if not self._approach(source, galaxy_ref, source=True):
                return
            if not self.HARVESTING:
                exchange(source, self.unit)
            ready = (tank.current_amount >= tank.max_capacity or
                     not self.HARVESTING and source.antimatter_component.current_amount <= 0)
            destination = configured if not self.automatic else self._choose_destination(source, galaxy_ref)
            if destination is None:
                self.waiting_reason = "no_destination"
                return
            budget = self._budget(source, destination, galaxy_ref)
            if budget is None:
                self.fail("path_unavailable")
            elif budget >= tank.max_capacity:
                self.fail("insufficient_capacity")
            elif destination.antimatter_component.current_amount >= destination.antimatter_component.max_capacity:
                self.waiting_reason = "destination_full"
            elif tank.current_amount <= budget:
                self.waiting_reason = "insufficient_load"
            elif ready:
                self.phase = "delivering"
                self.active_destination_unit_id = destination.id
                self._approach(destination, galaxy_ref)
        else:
            if not self._approach(destination, galaxy_ref):
                return
            if self.HARVESTING:
                from constants import ANTIMATTER_HARVESTER_RETURN_THRESHOLD
                self.return_reserve = ANTIMATTER_HARVESTER_RETURN_THRESHOLD
            else:
                estimate = estimate_approach(self.unit, galaxy_ref, source)
                if estimate is None:
                    self.fail("path_unavailable")
                    return
                self.return_reserve = buffered_fuel(estimate.fuel) + equipment_upkeep(self.unit)
            exchange(self.unit, destination, self.return_reserve)
            if tank.current_amount <= self.return_reserve:
                self._return_to_source(source, galaxy_ref)
            elif destination.antimatter_component.current_amount >= destination.antimatter_component.max_capacity:
                if self.HARVESTING and not self.automatic:
                    self._return_to_source(source, galaxy_ref, "destination_full")
                elif self.automatic:
                    self._clear_destination()
                else:
                    self.waiting_reason = "destination_full"


class ContinuousAntimatterTransportOrder(ContinuousFuelDeliveryOrder):
    """Load at a unit depot and deliver with a calculated return reserve."""
