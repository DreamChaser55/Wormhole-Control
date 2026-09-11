"""Explicit wing orders issued by a carrier's abilities."""
from geometry import distance
from .base import Order, OrderStatus, OrderType, OrderTargetField
from .combat import AttackOrder
from .movement import MoveOrder
from .hangar import DOCKING_RANGE


class CarrierWingOrder(Order):
    phase = 'approach'

    def blocker(self, galaxy):
        from strikecraft_abilities import source_valid, owned_wing
        if galaxy is None:
            return 'target_unavailable'
        source = galaxy.get_unit_by_id(self.parameters.get('source_carrier_id'))
        kind = self.order_type.name.lower()
        if not source_valid(source, kind, galaxy, self.parameters.get('source_owner_id')):
            return 'capability_unavailable'
        if not owned_wing(source, self.unit, galaxy):
            return 'target_unavailable'
        engines = self.unit.engines_component
        if self.unit.is_disabled or not engines or engines.is_destroyed or engines.speed <= 0:
            return 'capability_unavailable'
        from tactical_abilities import get_instance
        if get_instance(source, kind).duration_remaining <= 0:
            return 'ability_expired'
        return None

    def execute(self, galaxy_ref):
        super().execute(galaxy_ref)
        self.update(galaxy_ref)

    def clear_children(self):
        for child in self.sub_orders:
            child.cancel()
        self.sub_orders.clear()
        if self.unit.weapons_component:
            self.unit.weapons_component.clear_target()

    def fail(self, reason='execution_failed'):
        self.clear_children()
        super().fail(reason)

    def get_persistence_state(self):
        return {**super().get_persistence_state(), 'phase': self.phase}

    def restore_persistence_state(self, state):
        super().restore_persistence_state(state)
        phase = state.get('phase')
        if phase not in ('approach', 'release', 'complete'):
            raise ValueError('Invalid carrier wing order phase')
        from state_codec import number
        for field in ('source_carrier_id', 'source_owner_id', 'release_round', 'expires_round'):
            number(self.parameters.get(field), 'wing_order.' + field, 0, integer=True)
        self.phase = phase


class AttackRunOrder(CarrierWingOrder):
    target_fields = (OrderTargetField('target_unit_id', 'unit'), OrderTargetField('source_carrier_id', 'unit', public=False))

    def __init__(self, unit, parameters=None, parent_order=None):
        super().__init__(unit, OrderType.ATTACK_RUN, parameters, parent_order)
        self.phase = 'approach'

    def blocker(self, galaxy):
        blocker = super().blocker(galaxy)
        if blocker:
            return blocker
        from tactical_abilities import deployed, sector_for
        from domain.players import are_enemies
        from visibility import VisibilityService, is_unit_visible
        target = galaxy.get_unit_by_id(self.parameters.get('target_unit_id'))
        if not target or not deployed(target, galaxy) or not are_enemies(self.unit.owner, target.owner):
            return 'target_unavailable'
        if sector_for(target, galaxy) is not sector_for(self.unit, galaxy):
            return 'target_unavailable'
        snapshot = VisibilityService.compute(galaxy, self.unit.owner, record_intel=False)
        if not is_unit_visible(snapshot, target):
            return 'target_unavailable'
        weapons = self.unit.weapons_component
        if not weapons or weapons.is_destroyed or not weapons.eligible_turrets_for(target):
            return 'capability_unavailable'
        return None

    def update(self, galaxy_ref):
        if self.status != OrderStatus.IN_PROGRESS:
            return
        blocker = self.blocker(galaxy_ref)
        if blocker:
            self.fail(blocker)
            return
        if not self.sub_orders:
            self.add_sub_order(AttackOrder(self.unit, {'target_unit_id': self.parameters['target_unit_id']}, self))
        child = self.sub_orders[0]
        if child.status == OrderStatus.PENDING:
            child.execute(galaxy_ref)
        child.update(galaxy_ref)
        if child.status in (OrderStatus.FAILED, OrderStatus.CANCELLED):
            self.fail(child.failure_reason or 'path_unavailable')
            return
        from strikecraft_abilities import round_now
        target = galaxy_ref.get_unit_by_id(self.parameters['target_unit_id'])
        in_range = any(distance(self.unit.position, target.position) < t.range
                       for t in self.unit.weapons_component.eligible_turrets_for(target))
        self.phase = 'release' if in_range and round_now(galaxy_ref) >= self.parameters['release_round'] else 'approach'
        # Weapon updates clear unauthorized approach locks; restore only this active child.
        if self.phase == 'release':
            self.unit.weapons_component.set_target(target)

    def finish_salvo(self):
        self.clear_children()
        self.phase = 'complete'
        self.status = OrderStatus.COMPLETED


class EmergencyRecoveryOrder(CarrierWingOrder):
    target_fields = (OrderTargetField('target_carrier_id', 'unit'),)

    def __init__(self, unit, parameters=None, parent_order=None):
        super().__init__(unit, OrderType.EMERGENCY_RECOVERY, parameters, parent_order)
        self.phase = 'approach'

    def update(self, galaxy_ref):
        if self.status != OrderStatus.IN_PROGRESS:
            return
        blocker = self.blocker(galaxy_ref)
        if blocker:
            self.fail(blocker)
            return
        carrier = galaxy_ref.get_unit_by_id(self.parameters['target_carrier_id'])
        bay = carrier.strikecraft_bay_component
        if not bay.can_dock(self.unit):
            self.fail('insufficient_capacity')
            return
        if distance(self.unit.position, carrier.position) <= DOCKING_RANGE:
            self.clear_children()
            # Dock clears explicit work. Record completion before that cleanup.
            self.phase = 'complete'
            self.status = OrderStatus.COMPLETED
            if bay.dock(self.unit, galaxy_ref):
                from strikecraft_abilities import round_now
                self.unit.strikecraft_wing_component.recovery_ready_round = round_now(galaxy_ref) + 1
            return
        if self.sub_orders:
            move = self.sub_orders[0]
            if move.status == OrderStatus.FAILED:
                self.fail(move.failure_reason or 'path_unavailable')
                return
            # Refresh the approach when the carrier moves, preserving ordinary routing.
            destination = self.parameters.get('last_carrier_position')
            if move.status == OrderStatus.COMPLETED or destination != [carrier.position.x, carrier.position.y]:
                self.clear_children()
        if not self.sub_orders:
            self.parameters['last_carrier_position'] = [carrier.position.x, carrier.position.y]
            move = MoveOrder.for_unit_approach(self.unit, carrier, DOCKING_RANGE - 5, parent_order=self)
            self.add_sub_order(move)
        move = self.sub_orders[0]
        if move.status == OrderStatus.PENDING:
            move.execute(galaxy_ref)
        move.update(galaxy_ref)
