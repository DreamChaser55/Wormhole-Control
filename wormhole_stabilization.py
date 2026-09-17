"""Shared wormhole support rules; natural stability is never modified."""
from geometry import distance

STABILIZER_HULL_COST = 15.0
STABILIZER_RANGE = 500.0
STABILIZER_UPKEEP = 5.0


def in_range(unit, target):
    return bool(target is not None and unit.in_system == target.in_system
                and unit.in_hex == target.in_hex
                and distance(unit.position, target.position) <= STABILIZER_RANGE)


def current_order(unit):
    from unit_orders.base import OrderType, OrderStatus
    order = getattr(getattr(unit, 'commander_component', None), 'current_order', None)
    return order if (order is not None and order.order_type == OrderType.STABILIZE_WORMHOLE
                     and order.status == OrderStatus.IN_PROGRESS) else None


def equipment_ready(unit):
    from constants import HullSize
    return (unit.hull_size in (HullSize.MEDIUM, HullSize.LARGE, HullSize.HUGE)
            and all(c is not None and not c.is_destroyed for c in
                    (getattr(unit, 'wormhole_stabilizer_component', None), unit.antimatter_component)))


def target_valid(galaxy, target):
    from domain.celestials import Wormhole
    if not isinstance(target, Wormhole) or galaxy.wormholes.get(target.id) is not target:
        return False
    other = galaxy.wormholes.get(target.exit_wormhole_id)
    return (other is not None and other.exit_wormhole_id == target.id
            and other.in_system == target.exit_system_name)


def blocker(game, player, unit, target, *, check_path=True):
    from campaign_graph import is_deployed
    from game_ai.rules import body_is_public
    if not target_valid(game.galaxy, target) or not body_is_public(game, player, target):
        return 'target_unavailable'
    if (unit.owner != player or unit.current_hit_points <= 0
            or unit.is_hidden_in_gas_giant or not is_deployed(unit, game.galaxy)):
        return 'unit_unavailable'
    if not equipment_ready(unit):
        return 'capability_unavailable'
    if check_path and not in_range(unit, target):
        from antimatter_logistics import estimate_approach
        if estimate_approach(unit, game.galaxy, target, approach_range=STABILIZER_RANGE) is None:
            return 'path_unavailable'
    return None


def operating(unit, galaxy):
    from campaign_graph import is_deployed
    order = current_order(unit)
    if (order is None or not order.powered or unit.current_hit_points <= 0
            or unit.is_disabled or unit.is_hidden_in_gas_giant
            or not equipment_ready(unit) or not is_deployed(unit, galaxy)):
        return False
    if unit.wormhole_stabilizer_component.last_paid_owner_id != unit.owner.id:
        return False
    target = galaxy.wormholes.get(order.parameters.get('target_id'))
    return target_valid(galaxy, target) and in_range(unit, target)


def is_stabilized(galaxy, wormhole):
    """Public route status does not reveal the source's identity or location."""
    if galaxy is None:
        return False
    endpoints = {wormhole.id, wormhole.exit_wormhole_id}
    for endpoint_id in endpoints:
        endpoint = galaxy.wormholes.get(endpoint_id)
        if endpoint is None:
            continue
        system = galaxy.systems.get(endpoint.in_system)
        sector = system.hexes.get(endpoint.in_hex) if system else None
        for unit in getattr(sector, 'units', ()):
            order = current_order(unit)
            if order and order.parameters.get('target_id') in endpoints and operating(unit, galaxy):
                return True
    return False


def effective_stability(galaxy, wormhole):
    return 100 if is_stabilized(galaxy, wormhole) else wormhole.stability


def interrupt(unit, reason='capability_unavailable'):
    order = current_order(unit)
    if order:
        order.fail(reason)


def process_support(game, player):
    """Pay before movement; a second pass starts arrivals without a double charge."""
    from campaign_graph import iter_units
    from turn_briefing import unit_event
    for unit, _ in sorted(iter_units(game.galaxy), key=lambda item: item[0].id):
        order = current_order(unit)
        if unit.owner != player or order is None:
            continue
        target = game.galaxy.wormholes.get(order.parameters.get('target_id'))
        error = blocker(game, player, unit, target, check_path=False)
        if error:
            order.fail(error)
            continue
        component = unit.wormhole_stabilizer_component
        if unit.is_disabled or not in_range(unit, target):
            order.powered = False
            order.phase = 'disabled' if unit.is_disabled else 'approach'
            continue
        if (component.last_paid_round, component.last_paid_owner_id) != (game.turn_number, player.id):
            if not unit.antimatter_component.consume(STABILIZER_UPKEEP):
                if order.phase != 'waiting_for_antimatter':
                    unit_event(unit, 'problem', 'Wormhole stabilization stopped: insufficient antimatter', private=True)
                order.powered = False
                order.phase = 'waiting_for_antimatter'
                continue
            component.last_paid_round = game.turn_number
            component.last_paid_owner_id = player.id
        order.powered = True
        order.phase = 'maintaining'


def state_view(unit, *, order=None):
    order = order or current_order(unit)
    phase = order.phase if order else 'idle'
    if order is current_order(unit) and order is not None:
        target = unit.game.galaxy.wormholes.get(order.parameters.get('target_id'))
        if unit.is_disabled:
            phase = 'disabled'
        elif not in_range(unit, target):
            phase = 'approach'
    return dict(range=STABILIZER_RANGE, ongoing_antimatter=STABILIZER_UPKEEP,
                phase=phase,
                operational=order is current_order(unit) and operating(unit, unit.game.galaxy),
                payment_timing='owner_turn_before_movement_or_after_arrival',
                benefits='all_ships_both_directions')


def command_options(game, player, unit, bodies):
    if not getattr(unit, 'wormhole_stabilizer_component', None):
        return None
    from domain.celestials import Wormhole
    targets = [dict(target_id=body.id, blocker=blocker(game, player, unit, body),
                    natural_stability=body.stability, effective_stability=effective_stability(game.galaxy, body),
                    already_stable=body.stability == 100) for body in bodies if isinstance(body, Wormhole)]
    storage = unit.antimatter_component
    return dict(targets=targets[:32], omitted_count=max(0, len(targets) - 32),
                enough_fuel_for_upkeep=bool(storage and not storage.is_destroyed
                                           and storage.current_amount >= STABILIZER_UPKEEP),
                **state_view(unit))


def reconcile(game):
    """Validate saved support without spending fuel or executing orders."""
    from campaign_graph import iter_units
    for unit, _ in iter_units(game.galaxy):
        component = getattr(unit, 'wormhole_stabilizer_component', None)
        if component and component.last_paid_round > game.turn_number:
            raise ValueError('Stabilizer payment is in the future')
        order = current_order(unit)
        if order and order.powered:
            if component is None or component.last_paid_round == 0 or component.last_paid_owner_id != unit.owner.id:
                raise ValueError('Powered stabilizer has no payment')
            if not operating(unit, game.galaxy):
                order.powered = False
                order.phase = 'approach'
