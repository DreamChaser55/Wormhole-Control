"""Shared wormhole support rules; natural stability is never modified."""
from dataclasses import dataclass

from geometry import distance
from unit_orders.base import OrderStatus, OrderType

STABILIZER_HULL_COST = 15.0
DESTABILIZER_HULL_COST = 15.0
SUPPORT_RANGE = STABILIZER_RANGE = 500.0
SUPPORT_UPKEEP = STABILIZER_UPKEEP = 5.0
DESTABILIZATION_PENALTY = 30
FUEL_LOSS_PER_STABILITY_POINT = 0.25


@dataclass(frozen=True)
class SupportMode:
    order_type: OrderType
    capability: str
    operation: str

    @property
    def command(self):
        return self.order_type.name.lower()

    def component(self, unit):
        return getattr(unit, f'{self.capability}_component', None)


STABILIZE = SupportMode(OrderType.STABILIZE_WORMHOLE, 'wormhole_stabilizer', 'stabilization')
DESTABILIZE = SupportMode(OrderType.DESTABILIZE_WORMHOLE, 'wormhole_destabilizer', 'destabilization')
SUPPORT_COMMANDS = {mode.command: mode for mode in (STABILIZE, DESTABILIZE)}


def in_range(unit, target):
    return bool(target is not None and unit.in_system == target.in_system
                and unit.in_hex == target.in_hex
                and distance(unit.position, target.position) <= SUPPORT_RANGE)


def current_order(unit, mode=None):
    order = getattr(getattr(unit, 'commander_component', None), 'current_order', None)
    order_mode = getattr(order, 'support_mode', None)
    if order_mode is not None and (mode is None or order_mode is mode) and order.status == OrderStatus.IN_PROGRESS:
        return order
    return None


def equipment_ready(unit, mode=STABILIZE):
    from constants import HullSize
    return (unit.hull_size in (HullSize.MEDIUM, HullSize.LARGE, HullSize.HUGE, HullSize.TITAN)
            and all(c is not None and not c.is_destroyed for c in
                    (mode.component(unit), unit.antimatter_component)))


def target_valid(galaxy, target):
    from domain.celestials import Wormhole
    if not isinstance(target, Wormhole) or galaxy.wormholes.get(target.id) is not target:
        return False
    other = galaxy.wormholes.get(target.exit_wormhole_id)
    return (isinstance(other, Wormhole) and other.exit_wormhole_id == target.id
            and other.in_system == target.exit_system_name and other.exit_system_name == target.in_system)


def blocker(game, player, unit, target, *, mode=STABILIZE, check_path=True):
    from campaign_graph import is_deployed
    from dismantling import offline
    from game_ai.rules import body_is_public
    if not target_valid(game.galaxy, target) or not body_is_public(game, player, target):
        return 'target_unavailable'
    if (unit.owner != player or unit.current_hit_points <= 0
            or unit.is_hidden_in_gas_giant or offline(unit) or not is_deployed(unit, game.galaxy)):
        return 'unit_unavailable'
    if not equipment_ready(unit, mode):
        return 'capability_unavailable'
    if check_path and not in_range(unit, target):
        from antimatter_logistics import estimate_approach
        if estimate_approach(unit, game.galaxy, target, approach_range=SUPPORT_RANGE, known_only=True) is None:
            return 'path_unavailable'
    return None


def operating(unit, galaxy):
    from campaign_graph import is_deployed
    from dismantling import offline
    order = current_order(unit)
    if (order is None or not order.powered or unit.current_hit_points <= 0
            or unit.is_disabled or unit.is_hidden_in_gas_giant
            or not equipment_ready(unit, order.support_mode) or offline(unit) or not is_deployed(unit, galaxy)):
        return False
    if order.support_mode.component(unit).last_paid_owner_id != unit.owner.id:
        return False
    target = galaxy.wormholes.get(order.parameters.get('target_id'))
    return target_valid(galaxy, target) and in_range(unit, target)


@dataclass(frozen=True)
class ConnectionStability:
    status: str
    effective_stability: float

    @property
    def crossing_fuel_loss(self):
        return crossing_fuel_loss(self.effective_stability)

    def public_fields(self):
        return dict(stability_status=self.status, effective_stability=self.effective_stability,
                    stabilized=self.status == 'stabilized', crossing_fuel_loss=self.crossing_fuel_loss)


def connection_stability(galaxy, wormhole):
    """Resolve both endpoints into a public status without identifying operators."""
    modes = set()
    if galaxy is not None:
        for endpoint_id in (wormhole.id, wormhole.exit_wormhole_id):
            endpoint = galaxy.wormholes.get(endpoint_id)
            if endpoint is None:
                continue
            system = galaxy.systems.get(endpoint.in_system)
            sector = system.hexes.get(endpoint.in_hex) if system else None
            for unit in getattr(sector, 'units', ()):
                order = current_order(unit)
                if order and order.parameters.get('target_id') == endpoint_id and operating(unit, galaxy):
                    modes.add(order.support_mode)
                    if len(modes) == 2:
                        return ConnectionStability('contested', wormhole.stability)
    if STABILIZE in modes:
        return ConnectionStability('stabilized', 100)
    if DESTABILIZE in modes:
        return ConnectionStability('destabilized', max(0, wormhole.stability - DESTABILIZATION_PENALTY))
    return ConnectionStability('natural', wormhole.stability)


def is_stabilized(galaxy, wormhole):
    return connection_stability(galaxy, wormhole).status == 'stabilized'


def effective_stability(galaxy, wormhole):
    return connection_stability(galaxy, wormhole).effective_stability


def crossing_fuel_loss(stability):
    return max(0, 100 - stability) * FUEL_LOSS_PER_STABILITY_POINT


def interrupt(unit, reason='capability_unavailable', *, mode=None):
    order = current_order(unit, mode)
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
        mode = order.support_mode
        target = game.galaxy.wormholes.get(order.parameters.get('target_id'))
        error = blocker(game, player, unit, target, mode=mode, check_path=False)
        if error:
            order.fail(error)
            continue
        component = mode.component(unit)
        if unit.is_disabled or not in_range(unit, target):
            order.powered = False
            order.phase = 'disabled' if unit.is_disabled else 'approach'
            continue
        if (component.last_paid_round, component.last_paid_owner_id) != (game.turn_number, player.id):
            if not unit.antimatter_component.consume(SUPPORT_UPKEEP):
                if order.phase != 'waiting_for_antimatter':
                    unit_event(unit, 'problem', f'Wormhole {mode.operation} stopped due to insufficient antimatter',
                               private=True)
                order.powered = False
                order.phase = 'waiting_for_antimatter'
                continue
            component.last_paid_round = game.turn_number
            component.last_paid_owner_id = player.id
        order.powered = True
        order.phase = 'maintaining'


def state_view(unit, *, mode=STABILIZE, order=None):
    active = current_order(unit, mode)
    order = order or active
    phase = order.phase if order else 'idle'
    if active is not None and order is active:
        target = unit.game.galaxy.wormholes.get(order.parameters.get('target_id'))
        if unit.is_disabled:
            phase = 'disabled'
        elif not in_range(unit, target):
            phase = 'approach'
    state = dict(range=SUPPORT_RANGE, ongoing_antimatter=SUPPORT_UPKEEP, phase=phase,
                 operational=active is not None and order is active and operating(unit, unit.game.galaxy),
                 payment_timing='owner_turn_before_movement_or_after_arrival')
    if mode is DESTABILIZE:
        state.update(affects='all_ships_both_directions', stability_penalty=DESTABILIZATION_PENALTY)
    else:
        state['benefits'] = 'all_ships_both_directions'
    return state


def command_options(game, player, unit, bodies, *, mode=STABILIZE):
    if not mode.component(unit):
        return None
    from domain.celestials import Wormhole
    targets = []
    for body in bodies:
        if isinstance(body, Wormhole):
            target = dict(target_id=body.id, blocker=blocker(game, player, unit, body, mode=mode),
                          natural_stability=body.stability, **connection_stability(game.galaxy, body).public_fields())
            if mode is STABILIZE:
                target['already_stable'] = body.stability == 100
            targets.append(target)
    storage = unit.antimatter_component
    return dict(targets=targets[:32], omitted_count=max(0, len(targets) - 32),
                enough_fuel_for_upkeep=bool(storage and not storage.is_destroyed
                                           and storage.current_amount >= SUPPORT_UPKEEP),
                **state_view(unit, mode=mode))


def reconcile(game):
    """Validate saved support without spending fuel or executing orders."""
    from campaign_graph import iter_units
    player_ids = {player.id for player in game.players}
    for unit, _ in iter_units(game.galaxy):
        for mode in SUPPORT_COMMANDS.values():
            component = mode.component(unit)
            if component and (component.last_paid_round > game.turn_number or (
                    component.last_paid_round and component.last_paid_owner_id not in player_ids)):
                raise ValueError(f'Invalid wormhole {mode.operation} payment')
        order = current_order(unit)
        if order and order.powered:
            component = order.support_mode.component(unit)
            if component is None or component.last_paid_round == 0 or component.last_paid_owner_id != unit.owner.id:
                raise ValueError(f'Powered wormhole {order.support_mode.operation} has no payment')
            if not operating(unit, game.galaxy):
                order.powered = False
                order.phase = 'disabled' if unit.is_disabled else 'approach'
