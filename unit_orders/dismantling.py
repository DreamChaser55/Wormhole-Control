"""Dismantling owns one cancellable job and settles only at owner End Turn."""
from unit_orders.base import Order, OrderStatus, OrderType, OrderTargetField
from campaign_graph import find_unit
import dismantling as rules


class DismantleOrder(Order):
    target_fields = (OrderTargetField('target_unit_id', 'unit'),)

    def __init__(self, unit, parameters=None, parent_order=None):
        super().__init__(unit, OrderType.DISMANTLE_UNIT, parameters, parent_order)
        self.phase = 'pending'
        self.members = []
        self.owner_id = unit.owner.id
        self.progress = 0
        self.duration = 0
        self.last_round = -1
        self.settled = False

    def execute(self, galaxy_ref):
        super().execute(galaxy_ref)
        self.prepare(galaxy_ref)

    def prepare(self, galaxy):
        if self.status != OrderStatus.IN_PROGRESS:
            return
        target = find_unit(galaxy, self.parameters.get('target_unit_id'))
        evaluation = rules.evaluate(self.unit, target, galaxy, ignore_orders=(self.public_id,))
        if evaluation.blocker or self.unit.owner.id != self.owner_id:
            self.fail(evaluation.blocker or 'ownership_lost')
            return
        constructor = self.unit.constructor_component
        if (target.hull_size != rules.HullSize.STRIKECRAFT_WING and constructor
                and (constructor.current_construction_target or constructor.current_refit_target)):
            self.fail('capability_unavailable')
            return
        if self.phase == 'working':
            ids = [m['unit_id'] for m in self.members]
            if ids != [u.id for u in rules.tree(target)] or not rules.in_range(self.unit, target):
                self.fail('target_unavailable')
            return
        self.unit._dismantle_executor = self
        for member in rules.tree(target):
            member._dismantle_job = self
        for bay in rules.bays_for(self.unit, target):
            if getattr(bay, '_dismantle_job', None) is not self:
                bay.production_enabled = False
            bay._dismantle_job = self
        if not rules.in_range(self.unit, target):
            self.phase = 'approach'
            if not self.sub_orders:
                from unit_orders.movement import MoveOrder
                self.add_sub_order(MoveOrder.for_unit_approach(self.unit, target,
                                   self.unit.constructor_component.build_range - 5, parent_order=self))
            return
        if evaluation.waiting:
            self.phase = 'waiting_for_paid_bay_work'
            return
        if self.unit.is_disabled or any(b.unit.is_disabled for b in rules.bays_for(self.unit, target)):
            self.phase = 'waiting_for_worker'
            return
        self.members = evaluation.members
        self.duration = evaluation.duration
        for child in self.sub_orders:
            child.cancel()
        self.sub_orders.clear()
        self.phase = 'working'
        for member in list(rules.tree(target)):
            member._dismantle_job = self
            commander = member.commander_component
            if commander:
                commander.clear_explicit_orders()
                commander.suspend_stance_activity('dismantling')
            if member.engines_component:
                member.engines_component.clear_move_target()
            if member.hyperdrive_component:
                member.hyperdrive_component.clear_jump_target()
            from environmental_resistance import deactivate
            from wormhole_stabilization import interrupt
            deactivate(member)
            interrupt(member)
            if member.inhibitor_component:
                member.inhibitor_component.turn_off()
            if member.cloaking_component:
                member.cloaking_component.deactivate()
            if member.ability_component:
                for kind, instance in member.ability_component.abilities.items():
                    if instance.is_active:
                        member.ability_component._expire_ability(kind, galaxy)
        rules.dirty(self.unit.game)

    def check_completion_conditions(self):
        if not self.sub_orders:
            self.prepare(self.unit.in_galaxy or self.unit.game.galaxy)

    def update(self, galaxy_ref):
        super().update(galaxy_ref)
        if self.status not in {OrderStatus.PENDING, OrderStatus.IN_PROGRESS}:
            rules.release(self)

    def advance(self, galaxy, round_number):
        self.prepare(galaxy)
        if (self.status != OrderStatus.IN_PROGRESS or self.phase != 'working'
                or self.unit.is_disabled or self.last_round == round_number):
            return
        target = find_unit(galaxy, self.parameters['target_unit_id'])
        if any(b.unit.is_disabled for b in rules.bays_for(self.unit, target)):
            return
        self.last_round = round_number
        self.progress += 1
        rules.dirty(self.unit.game)
        if self.progress < self.duration:
            return
        members = [find_unit(galaxy, item['unit_id']) for item in self.members]
        refund = sum(0.5 * item['build_cost'] * unit.current_hit_points / unit.max_hit_points
                     for item, unit in zip(self.members, members))
        self.settled = True
        self.status = OrderStatus.COMPLETED
        rules.release(self)
        from turn_briefing import record
        record(self.unit.game, self.unit.owner, 'development', 'Dismantling completed (credits recovered)',
               subject=members[0], amount=refund)
        # Children first, so removal never treats carried craft as combat losses.
        for unit in reversed(members):
            unit.remove_for_dismantling()
        self.unit.owner.credits += refund

    def fail(self, reason='execution_failed'):
        for child in self.sub_orders:
            child.cancel()
        self.sub_orders.clear()
        rules.release(self)
        super().fail(reason)

    def cancel(self):
        rules.release(self)
        super().cancel()

    def get_persistence_state(self):
        return {**super().get_persistence_state(), **{key: getattr(self, key) for key in
                ('phase', 'members', 'owner_id', 'progress', 'duration', 'last_round', 'settled')}}

    def get_state_data(self):
        return dict(super().get_state_data(), phase=self.phase, progress=self.progress, duration=self.duration)

    def restore_persistence_state(self, state):
        super().restore_persistence_state(state)
        from state_codec import number
        number(self.parameters['target_unit_id'], 'target_unit_id', 0, integer=True)
        if state['phase'] not in {'pending', 'approach', 'waiting_for_paid_bay_work', 'waiting_for_worker', 'working'}:
            raise ValueError('Invalid dismantling phase')
        for key in ('owner_id', 'progress', 'duration'):
            number(state[key], key, 0, integer=True)
        number(state['last_round'], 'last_round', -1, integer=True)
        if type(state['settled']) is not bool or not isinstance(state['members'], list):
            raise ValueError('Invalid dismantling state')
        for member in state['members']:
            from state_codec import fields
            fields(member, ('unit_id', 'name', 'build_cost', 'turns', 'estimated_refund', 'cargo_lost'), 'dismantling member')
            for key in ('unit_id', 'build_cost', 'turns'):
                number(member[key], key, 1 if key == 'turns' else 0, integer=True)
            number(member['estimated_refund'], 'estimated_refund', 0)
            if not isinstance(member['name'], str) or not isinstance(member['cargo_lost'], dict):
                raise ValueError('Invalid dismantling member details')
            for value in member['cargo_lost'].values():
                number(value, 'cargo quantity', 0)
        if state['progress'] > state['duration']:
            raise ValueError('Invalid dismantling progress')
        for key in ('phase', 'members', 'owner_id', 'progress', 'duration', 'last_round', 'settled'):
            setattr(self, key, state[key])

    def resume(self, galaxy_ref):
        super().resume(galaxy_ref)  # Bind locks after every commander has restored.

    def restore_bindings(self, galaxy):
        target = find_unit(galaxy, self.parameters.get('target_unit_id'))
        evaluation = rules.evaluate(self.unit, target, galaxy, ignore_orders=(self.public_id,))
        if evaluation.blocker or self.owner_id != self.unit.owner.id or self.settled:
            raise ValueError('Invalid saved dismantling claim')
        if self.last_round > self.unit.game.turn_number or (self.progress > 0 and self.last_round < 0):
            raise ValueError('Invalid saved dismantling turn')
        current = self.unit.commander_component.current_order is self
        if (not current and (self.phase != 'pending' or self.status != OrderStatus.PENDING)
                or self.phase != 'pending' and self.status != OrderStatus.IN_PROGRESS):
            raise ValueError('Invalid saved dismantling lifecycle')
        if self.phase == 'working':
            if (evaluation.waiting or not rules.in_range(self.unit, target) or self.members != evaluation.members
                    and [(m['unit_id'], m['build_cost'], m['turns']) for m in self.members]
                    != [(m['unit_id'], m['build_cost'], m['turns']) for m in evaluation.members]
                    or self.duration != evaluation.duration or self.progress >= self.duration):
                raise ValueError('Invalid saved dismantling membership or valuation')
            for member in rules.tree(target):
                commander = member.commander_component
                if commander and (commander.current_order or commander.orders_queue):
                    raise ValueError('Offline dismantling target has explicit orders')
                member._dismantle_job = self
        elif self.members or self.duration or self.progress:
            raise ValueError('Unstarted dismantling contains work')
        if self.phase != 'pending':
            self.unit._dismantle_executor = self
            for member in rules.tree(target):
                member._dismantle_job = self
            for bay in rules.bays_for(self.unit, target):
                bay._dismantle_job = self
