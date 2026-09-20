"""Shared dismantling policy and owner-turn settlement; no presentation imports."""
from dataclasses import dataclass, field
from math import ceil
from contextlib import contextmanager
from contextvars import ContextVar

from campaign_graph import find_unit, is_deployed, iter_units
from constants import HullSize
from geometry import distance

_projected_offline = ContextVar('dismantling_projected_offline', default=None)


@contextmanager
def projected_offline(unit_ids):
    """Let pure preflight validators read projected locks without changing units."""
    token = _projected_offline.set(frozenset(unit_ids))
    try:
        yield
    finally:
        _projected_offline.reset(token)


def offline(unit):
    projected = _projected_offline.get()
    if projected is not None:
        return getattr(unit, 'id', None) in projected
    job = getattr(unit, '_dismantle_job', None)
    return job is not None and job.phase == 'working' and not job.settled


def tree(unit):
    yield unit
    for bay in (unit.hangar_component, unit.strikecraft_bay_component):
        if bay:
            for child in bay.docked_units:
                yield from tree(child)


def jobs(galaxy):
    for unit, _ in iter_units(galaxy):
        commander = unit.commander_component
        if commander:
            for root in [commander.current_order, *commander.orders_queue]:
                if root and root.order_type.name == 'DISMANTLE_UNIT' and root.status.name in {'PENDING', 'IN_PROGRESS'}:
                    yield root


def job_members(job, galaxy):
    target = find_unit(galaxy, job.parameters.get('target_unit_id'))
    return list(tree(target)) if target else []


def bays_for(actor, target):
    bays = [u.strikecraft_bay_component for u in tree(target)
            if u.strikecraft_bay_component and not u.strikecraft_bay_component.is_destroyed]
    if target.hull_size == HullSize.STRIKECRAFT_WING:
        bays.insert(0, actor.strikecraft_bay_component)
    return bays


def in_range(actor, target):
    if target.hull_size == HullSize.STRIKECRAFT_WING:
        return True  # Containment is checked separately.
    constructor = actor.constructor_component
    return bool(constructor and actor.in_system == target.in_system and actor.in_hex == target.in_hex
                and distance(actor.position, target.position) <= constructor.build_range)


@dataclass
class Evaluation:
    blocker: str | None = None
    members: list = field(default_factory=list)
    duration: int = 0
    refund: float = 0.0
    waiting: bool = False

    def public(self):
        return dict(blocker=self.blocker, members=self.members, turns_required=self.duration,
                    estimated_refund=self.refund, waiting_for_paid_bay_work=self.waiting)


def evaluate(actor, target, galaxy, *, ignore_orders=(), check_claims=True):
    result = Evaluation()
    def reject(reason):
        result.blocker = reason
        return result
    if (target is None or actor is target or target.owner != actor.owner
            or getattr(target, '_destroyed', False) or target.current_hit_points <= 0):
        return reject('target_unavailable')
    if (not is_deployed(actor, galaxy) or actor.is_hidden_in_gas_giant
            or getattr(actor, '_destroyed', False) or actor.current_hit_points <= 0):
        return reject('capability_unavailable')
    wing = target.hull_size == HullSize.STRIKECRAFT_WING
    component = actor.strikecraft_bay_component if wing else actor.constructor_component
    if component is None or component.is_destroyed:
        return reject('capability_unavailable')
    if wing:
        if (target not in component.docked_units or not target.strikecraft_wing_component
                or target.strikecraft_wing_component.mother_carrier is not actor):
            return reject('target_unavailable')
    elif not is_deployed(target, galaxy) or target.is_hidden_in_gas_giant:
        return reject('target_unavailable')
    members = list(tree(target))
    ids = {u.id for u in members}
    if actor.id in ids:
        return reject('dismantling_conflict')
    for unit in members:
        if (unit.owner != actor.owner or unit.is_temporary or unit.lifetime is not None
                or unit.current_hit_points <= 0 or getattr(unit, '_destroyed', False)):
            return reject('target_unavailable')
        if unit.hull_size == HullSize.STRIKECRAFT_WING:
            mother = unit.strikecraft_wing_component.mother_carrier if unit.strikecraft_wing_component else None
            bay = mother.strikecraft_bay_component if mother else None
            if not bay or bay.is_destroyed or unit not in bay.docked_units or (unit is not target and mother.id not in ids):
                return reject('capability_unavailable')
    if check_claims:
        for job in jobs(galaxy):
            if job.public_id in ignore_orders:
                continue
            other = {u.id for u in job_members(job, galaxy)}
            if ids & other or actor.id in other or job.unit.id in ids:
                return reject('dismantling_conflict')
    if not in_range(actor, target):
        engines = actor.engines_component
        if not engines or not engines.is_operational:
            return reject('target_out_of_range')
        from antimatter_logistics import estimate_approach
        if estimate_approach(actor, galaxy, target, approach_range=component.build_range) is None:
            return reject('path_unavailable')
    from custom_unit_templates import CustomUnitTemplate
    from refit_validation import installed_configuration
    for unit in members:
        design = CustomUnitTemplate('Dismantling', unit.hull_size, installed_configuration(unit))
        duration = max(1, ceil(design.build_time / 2))
        refund = 0.5 * design.build_cost * unit.current_hit_points / unit.max_hit_points
        cargo = {}
        for attr, fields in (('antimatter_component', ('current_amount',)),
                             ('mining_component', ('raw_metal_cargo', 'raw_crystal_cargo')),
                             ('colony_component', ('population_cargo',)),
                             ('troop_transport_component', ('troops',))):
            comp = getattr(unit, attr, None)
            if comp:
                for name in fields:
                    value = getattr(comp, name, 0)
                    if value:
                        cargo[name] = value
        result.members.append(dict(unit_id=unit.id, name=unit.name, build_cost=design.build_cost,
                                   turns=duration, estimated_refund=refund, cargo_lost=cargo))
        result.duration += duration
        result.refund += refund
    result.waiting = any(b.constructing or b.replenishing_unit is not None for b in bays_for(actor, target))
    return result


def release(job):
    galaxy = job.unit.in_galaxy or job.unit.game.galaxy
    for unit, _ in list(iter_units(galaxy)):
        if getattr(unit, '_dismantle_job', None) is job:
            unit._dismantle_job = None
        if getattr(unit, '_dismantle_executor', None) is job:
            unit._dismantle_executor = None
        bay = unit.strikecraft_bay_component
        if bay and getattr(bay, '_dismantle_job', None) is job:
            bay._dismantle_job = None
    dirty(job.unit.game)


def dirty(game):
    game.visibility_dirty = True
    game.sidebar_needs_update = True


def interrupt(unit):
    """Release work on capture/removal immediately, before containment changes."""
    galaxy = unit.in_galaxy or getattr(unit.game, 'galaxy', None)
    for job in list(jobs(galaxy)):
        if job.unit is unit or unit in job_members(job, galaxy):
            job.fail('target_unavailable')


def process(game, player):
    for job in sorted(list(jobs(game.galaxy)), key=lambda j: j.unit.id):
        if job.unit.owner == player and job.unit.commander_component.current_order is job:
            job.advance(game.galaxy, game.turn_number)


def restore(galaxy):
    """Validate all saved claims, then restore bindings without executing jobs."""
    for job in list(jobs(galaxy)):
        job.restore_bindings(galaxy)


def state_view(unit):
    job = getattr(unit, '_dismantle_job', None) or getattr(unit, '_dismantle_executor', None)
    if job is None:
        return None
    galaxy = job.unit.in_galaxy or job.unit.game.galaxy
    target = find_unit(galaxy, job.parameters['target_unit_id'])
    waiting = job.phase if job.phase.startswith('waiting') else None
    if job.phase == 'working' and (job.unit.is_disabled or any(b.unit.is_disabled for b in bays_for(job.unit, target))):
        waiting = 'waiting_for_worker'
    members = [dict(member, cargo_lost=dict(member['cargo_lost'])) for member in
               (job.members or evaluate(job.unit, target, galaxy, ignore_orders=(job.public_id,)).members)]
    refund = 0.0
    for member in members:
        current = find_unit(galaxy, member['unit_id'])
        if current:
            refund += 0.5 * member['build_cost'] * current.current_hit_points / current.max_hit_points
    return dict(order_id=job.public_id, executor_id=job.unit.id, target_id=job.parameters['target_unit_id'],
                phase=job.phase, turns_completed=job.progress, turns_required=job.duration,
                offline=offline(unit), waiting_reason=waiting, members=members, estimated_refund=refund)
