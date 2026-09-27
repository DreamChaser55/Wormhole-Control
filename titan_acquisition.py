"""Titan capacity derived from ownership and accepted acquisition work."""
from constants import HullSize
from campaign_graph import iter_units, find_unit


def hull_name(template):
    value = (template or {}).get('hull_size')
    return getattr(value, 'name', value)


def intended_hull(parameters, owner):
    if 'construction_hull_size' in parameters:
        return parameters['construction_hull_size']
    from unit_templates import get_template
    return hull_name(get_template(parameters.get('unit_template_name'), owner))


def acquisition(kind, parameters, owner, galaxy):
    if kind.lower() == 'construct':
        return intended_hull(parameters, owner) == 'TITAN'
    if kind.lower() == 'use_ability' and parameters.get('ability_type') == 'capture_unit':
        target = find_unit(galaxy, parameters.get('target_unit_id', parameters.get('target_id')))
        return bool(target and target.hull_size == HullSize.TITAN and target.current_hit_points > 0 and target.owner != owner)
    return False


def root_of(order):
    while order is not None and order.parent_order is not None:
        order = order.parent_order
    return order


def capacity(galaxy, owner, *, exclude_order=None, exclude_constructor=None, ledger=None):
    """A ledger replaces live roots during transactional batch preflight."""
    owned, reserved = [], []
    excluded = root_of(exclude_order)
    for unit, _ in iter_units(galaxy):
        if unit.owner != owner or unit.current_hit_points <= 0:
            continue
        if unit.hull_size == HullSize.TITAN:
            owned.append(unit.id)
        commander = unit.commander_component
        roots = [commander.current_order, *commander.orders_queue] if commander else []
        if ledger is None:
            for root in roots:
                if root and root is not excluded and root.status.name in ('PENDING', 'IN_PROGRESS') and acquisition(root.order_type.name, root.parameters, owner, galaxy):
                    reserved.append({'unit_id': unit.id, 'order_id': root.public_id, 'kind': root.order_type.name.lower()})
        else:
            for entry in ledger.get(unit.id, ()):
                if not entry.get('settled') and acquisition(entry['type'], entry['parameters'], owner, galaxy):
                    reserved.append({'unit_id': unit.id, 'order_id': entry['id'], 'kind': entry['type']})
        constructor = unit.constructor_component
        if constructor and constructor is not exclude_constructor and constructor.current_construction_target:
            job = constructor.current_construction_target
            job_order = constructor._owning_construction_order()
            # A paid job is the same acquisition as its root/approach work.
            if job.get('construction_hull_size') == 'TITAN' and job_order is None:
                reserved.append({'unit_id': unit.id, 'order_id': None, 'kind': 'construction_job'})
    return {'limit': 1, 'owned_unit_ids': owned, 'reservations': reserved,
            'available': max(0, 1 - len(owned) - len(reserved))}


def blocker(galaxy, owner, **kwargs):
    return None if capacity(galaxy, owner, **kwargs)['available'] else 'titan_limit_reached'


def construction_blocker(game, player, builders, *, queue):
    from game_ai.commands import _BatchProjection
    from game_ai.contracts import Command
    projection = _BatchProjection.from_game(game, player)
    projection.before(Command(type='construct', unit_ids=tuple(u.id for u in builders), queue=queue), builders)
    state = capacity(game.galaxy, player, ledger=projection._order_ledger)
    return 'titan_limit_reached' if len(builders) > state['available'] else None


def validate_campaign(galaxy):
    owners = {}
    for unit, _ in iter_units(galaxy):
        from titan_balance import TITAN_ABILITIES, CORE_HULL_COST
        from unit_components.abilities import AbilityComponent
        from refit_validation import installed_configuration
        from custom_unit_templates import get_ability_required_components
        core = unit.titan_component
        abilities = unit.ability_component
        kinds = {kind.value for kind in abilities.abilities} if abilities else set()
        titan_kinds = kinds & TITAN_ABILITIES
        if core and (unit.hull_size != HullSize.TITAN or core.hull_cost != CORE_HULL_COST):
            raise ValueError('Invalid Titan Core equipment')
        if titan_kinds:
            if unit.hull_size != HullSize.TITAN or not core:
                raise ValueError('Titan abilities require a Titan hull and Core')
            config = installed_configuration(unit)
            if any(not getattr(config, flag) for kind in titan_kinds for flag in get_ability_required_components(kind)):
                raise ValueError('Missing Titan ability equipment')
            if abilities.hull_cost != AbilityComponent.calc_hull_cost(list(kinds)):
                raise ValueError('Invalid Titan ability hull cost')
        if unit.hull_size == HullSize.TITAN and (unit.current_hull_usage > unit.hull_capacity
                or unit.antimatter_component and unit.antimatter_component.max_capacity < 1000):
            raise ValueError('Invalid Titan capacity or storage')
        if unit.owner is not None:
            owners[unit.owner.id] = unit.owner
    for owner in owners.values():
        state = capacity(galaxy, owner)
        if len(state['owned_unit_ids']) + len(state['reservations']) > 1:
            raise ValueError('Titan ownership/acquisition limit exceeded')
