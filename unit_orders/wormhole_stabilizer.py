"""Continuous approach-and-maintain order; turn phases own fuel and activation."""
from .base import Order, OrderStatus, OrderType, OrderTargetField
from .movement import MoveOrder
from wormhole_stabilization import STABILIZER_RANGE, blocker, in_range


class StabilizeWormholeOrder(Order):
    update_on_start = False
    target_fields = (OrderTargetField('target_id', 'celestial'),)

    def __init__(self, unit, parameters=None, parent_order=None):
        super().__init__(unit, OrderType.STABILIZE_WORMHOLE, parameters, parent_order)
        self.powered = False
        self.phase = 'approach'

    def _prepare(self, galaxy):
        target = galaxy.wormholes.get(self.parameters.get('target_id'))
        error = blocker(self.unit.game, self.unit.owner, self.unit, target, check_path=False)
        if error:
            self.fail(error)
        elif not self.unit.is_disabled and not in_range(self.unit, target) and not self.sub_orders:
            self.powered = False
            self.phase = 'approach'
            self.add_sub_order(MoveOrder.for_celestial_approach(
                self.unit, target, STABILIZER_RANGE - 5, parent_order=self))

    def execute(self, galaxy_ref):
        if self.status != OrderStatus.PENDING:
            return
        self.powered = False
        self.phase = 'approach'
        super().execute(galaxy_ref)
        self._prepare(galaxy_ref)
        # Approach movement can be prepared on issuance; only support/payment wait.
        if self.status == OrderStatus.IN_PROGRESS and self.sub_orders:
            super().update(galaxy_ref)

    def update(self, galaxy_ref):
        if self.status != OrderStatus.IN_PROGRESS:
            return
        self._prepare(galaxy_ref)
        if self.status == OrderStatus.IN_PROGRESS and not self.unit.is_disabled:
            super().update(galaxy_ref)

    def check_completion_conditions(self):
        pass  # Continuous work never completes merely by arriving.

    def fail(self, reason='execution_failed'):
        self.powered = False
        self.phase = 'approach'
        for child in self.sub_orders:
            child.cancel()
        self.sub_orders.clear()
        super().fail(reason)

    def cancel(self):
        self.powered = False
        self.phase = 'approach'
        super().cancel()

    def get_persistence_state(self):
        return dict(super().get_persistence_state(), powered=self.powered, phase=self.phase)

    def restore_persistence_state(self, state):
        super().restore_persistence_state(state)
        from state_codec import number
        number(self.parameters.get('target_id'), 'stabilizer.target_id', 0, integer=True)
        if type(state['powered']) is not bool or state['phase'] not in (
                'approach', 'maintaining', 'waiting_for_antimatter', 'disabled'):
            raise ValueError('Invalid wormhole stabilization state')
        if state['powered'] != (state['phase'] == 'maintaining'):
            raise ValueError('Inconsistent wormhole stabilization state')
        if state['powered'] and self.status != OrderStatus.IN_PROGRESS:
            raise ValueError('Only an active stabilizer order can be powered')
        self.powered, self.phase = state['powered'], state['phase']

    def get_state_data(self):
        return dict(super().get_state_data(), phase=self.phase, powered=self.powered)
