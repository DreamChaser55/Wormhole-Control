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
    route_budget,
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


class ContinuousAntimatterTransportOrder(Order):
    update_on_start = False
    target_fields = (
        OrderTargetField("target_unit_id", "unit", public=True),
        OrderTargetField("source_unit_id", "unit", public=True),
    )

    def __init__(self, unit, parameters=None, parent_order=None):
        super().__init__(
            unit, OrderType.CONTINUOUS_ANTIMATTER_TRANSPORT, parameters, parent_order
        )
        self.phase = "loading"
        self.waiting_reason = None
        self.return_reserve = 0.0

    def get_persistence_state(self):
        return dict(
            super().get_persistence_state(),
            phase=self.phase,
            waiting_reason=self.waiting_reason,
            return_reserve=self.return_reserve,
        )

    def restore_persistence_state(self, state):
        super().restore_persistence_state(state)
        from state_codec import number

        if state["phase"] not in ("loading", "delivering") or state[
            "waiting_reason"
        ] not in (None, "source_empty", "destination_full", "insufficient_load"):
            raise ValueError("Invalid antimatter transport phase")
        number(state["return_reserve"], "return_reserve", 0)
        self.phase, self.waiting_reason, self.return_reserve = (
            state["phase"],
            state["waiting_reason"],
            state["return_reserve"],
        )

    def get_state_data(self):
        data = super().get_state_data()
        data.update(
            phase=self.phase,
            waiting_reason=self.waiting_reason,
            return_reserve=self.return_reserve,
        )
        for field in ("source_unit_id", "target_unit_id"):
            target = self.unit.game.galaxy.get_unit_by_id(self.parameters.get(field))
            data[field] = target.id if target else None
            data[field.replace("_unit_id", "_name")] = target.name if target else None
        return data

    def _endpoints(self, galaxy):
        source = galaxy.get_unit_by_id(self.parameters.get("source_unit_id"))
        destination = galaxy.get_unit_by_id(self.parameters.get("target_unit_id"))
        blocker = exchange_blocker(self.unit, source, galaxy) or exchange_blocker(
            self.unit, destination, galaxy
        )
        if (
            not self.unit.engines_component
            or not self.unit.engines_component.is_operational
        ):
            blocker = "capability_unavailable"
        if blocker or source is destination:
            for child in self.sub_orders:
                child.cancel()
            self.sub_orders.clear()
            self.fail(blocker or "invalid_parameters")
            return None
        return source, destination

    def _approach(self, target, galaxy):
        if in_transfer_range(self.unit, target):
            return True
        estimate = estimate_approach(self.unit, galaxy, target)
        if estimate is None:
            self.fail("path_unavailable")
        elif self.unit.antimatter_component.current_amount < buffered_fuel(
            estimate.fuel
        ):
            self.fail("insufficient_resources")
        else:
            self.add_sub_order(
                MoveOrder.for_unit_approach(
                    self.unit, target, ANTIMATTER_TRANSFER_RANGE - 5, parent_order=self
                )
            )
        return False

    def execute(self, galaxy_ref):
        super().execute(galaxy_ref)
        pair = self._endpoints(galaxy_ref)
        if pair:
            budget = route_budget(self.unit, *pair, galaxy_ref)
            if budget is None:
                self.fail("path_unavailable")
            elif budget >= self.unit.antimatter_component.max_capacity:
                self.fail("insufficient_capacity")
            else:
                self._approach(pair[0], galaxy_ref)

    def update(self, galaxy_ref):
        if self.status != OrderStatus.IN_PROGRESS:
            return
        pair = self._endpoints(galaxy_ref)
        if not pair:
            return
        super().update(galaxy_ref)
        if self.status != OrderStatus.IN_PROGRESS or self.sub_orders:
            return
        source, destination = pair
        self.waiting_reason = None
        tank = self.unit.antimatter_component
        if self.phase == "loading":
            if not self._approach(source, galaxy_ref):
                return
            exchange(source, self.unit)
            budget = route_budget(self.unit, source, destination, galaxy_ref)
            if budget is None:
                self.fail("path_unavailable")
                return
            if budget >= tank.max_capacity:
                self.fail("insufficient_capacity")
                return
            if (
                destination.antimatter_component.current_amount
                >= destination.antimatter_component.max_capacity
            ):
                self.waiting_reason = "destination_full"
            elif tank.current_amount <= budget:
                self.waiting_reason = "insufficient_load"
            elif (
                tank.current_amount >= tank.max_capacity
                or source.antimatter_component.current_amount <= 0
            ):
                self.phase = "delivering"
                self._approach(destination, galaxy_ref)
            else:
                self.waiting_reason = (
                    "source_empty"
                    if source.antimatter_component.current_amount <= 0
                    else None
                )
        else:
            if not self._approach(destination, galaxy_ref):
                return
            estimate = estimate_approach(self.unit, galaxy_ref, source)
            if estimate is None:
                self.fail("path_unavailable")
                return
            # Include the equipment debit later in this delivery turn.
            self.return_reserve = buffered_fuel(estimate.fuel) + equipment_upkeep(
                self.unit
            )
            exchange(self.unit, destination, self.return_reserve)
            if tank.current_amount <= self.return_reserve:
                self.phase = "loading"
                self._approach(source, galaxy_ref)
            elif (
                destination.antimatter_component.current_amount
                >= destination.antimatter_component.max_capacity
            ):
                self.waiting_reason = "destination_full"
