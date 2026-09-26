"""Authoritative, presentation-independent planetary warfare and disclosure rules."""
from __future__ import annotations

import math
import random
from resource_costs import fortification_cost, resource_balances

from planetary_balance import (
    BASE_DEFENSE, DEFENSE_PER_POPULATION, FORTIFICATION_BONUS, FORTIFICATION_COSTS,
    MIN_READINESS, RECOVERY_PER_ROUND, TROOP_CREDIT_COST, TROOP_POPULATION_COST, MIN_REMAINING_POPULATION,
    SIEGE_RANGE, SIEGE_DAMAGE, SIEGE_AM_COST, COLLATERAL_PER_DAMAGE,
    INVASION_RANGE, INVASION_AM_COST, SUCCESS_LOSSES, DEFEAT_LOSSES,
)

KINDS = ('recruit_troops', 'bombard_planet', 'invade_planet')
BODY_FIELDS = ('fortification_level', 'defense_readiness', 'last_hostile_action_round', 'last_defense_upgrade_round')


def initialize_body(body):
    body.fortification_level = 0
    body.defense_readiness = 1.0
    body.last_hostile_action_round = 0
    body.last_defense_upgrade_round = 0


def colonizable(body):
    from domain.celestials import Planet, Moon, ColonizableAsteroid
    return isinstance(body, (Planet, Moon, ColonizableAsteroid)) and body.is_colonizable


def maximum_defense(body):
    if not colonizable(body) or body.owner is None or body.population <= 0:
        return 0.0
    return max(BASE_DEFENSE, body.population * DEFENSE_PER_POPULATION) * (1 + FORTIFICATION_BONUS * body.fortification_level)


def defense_view(body):
    maximum = maximum_defense(body)
    level = body.fortification_level
    return dict(fortification_level=level, readiness=body.defense_readiness,
                maximum_defense=maximum, current_defense=maximum * body.defense_readiness,
                next_upgrade_cost=FORTIFICATION_COSTS[level] if level < len(FORTIFICATION_COSTS) else None,
                next_upgrade_resources=fortification_cost(level + 1).to_dict() if level < len(FORTIFICATION_COSTS) else None,
                recovery_per_quiet_round=RECOVERY_PER_ROUND, minimum_readiness=MIN_READINESS)


def assault_preview(body, amount):
    defense = maximum_defense(body) * body.defense_readiness
    return dict(committed_troops=amount, success_probability=amount / (amount + defense) if amount > 0 else 0.0,
                success_casualties=math.ceil(amount * SUCCESS_LOSSES),
                defeat_casualties=math.ceil(amount * DEFEAT_LOSSES), antimatter_cost=INVASION_AM_COST)


def command_options(game, player, unit, bodies):
    """Bounded choices used by observations and human dialogs."""
    options = {}
    transport = getattr(unit, 'troop_transport_component', None)
    kinds = (['recruit_troops', 'invade_planet'] if transport else [])
    if getattr(unit, 'siege_battery_component', None):
        kinds.append('bombard_planet')
    from domain.players import are_enemies
    for kind in kinds:
        targets = []
        for body in bodies:
            if not colonizable(body) or body.owner is None:
                continue
            if not (body.owner == player if kind == 'recruit_troops' else are_enemies(player, body.owner)):
                continue
            amount = None
            item = {'target_id': body.id, 'distance_from_surface': SIEGE_RANGE if kind == 'bombard_planet' else INVASION_RANGE}
            if kind == 'recruit_troops':
                limit = max(0, min(transport.capacity - transport.troops, int(player.credits // TROOP_CREDIT_COST),
                                  math.floor((body.population - MIN_REMAINING_POPULATION + 1e-9) / TROOP_POPULATION_COST)))
                item.update(max_amount=limit, credits_per_troop=TROOP_CREDIT_COST, population_per_troop=TROOP_POPULATION_COST)
                amount = max(1, limit)
            elif kind == 'invade_planet':
                amount = max(1, transport.troops)
                item.update(max_amount=transport.troops, **assault_preview(body, amount),
                            preview_note='Recomputed at arrival; defense strength can change.')
            else:
                item.update(antimatter_cost=SIEGE_AM_COST, defense_damage=SIEGE_DAMAGE,
                            minimum_readiness=MIN_READINESS, collateral_per_damage=COLLATERAL_PER_DAMAGE)
            item['blocker'] = blocker(game, player, kind, body, unit, amount)
            targets.append(item)
        options[kind] = {'targets': targets[:32], 'omitted_count': max(0, len(targets) - 32)}
    return options


def exact_body(game, player, target_id):
    """Use the existing exact celestial disclosure boundary, including remote colonies."""
    from game_ai.rules import body_is_public
    body = game.galaxy.get_celestial_body_by_id(target_id)
    return body if body is not None and body_is_public(game, player, body) else None


def in_range(unit, body, kind):
    from geometry import distance
    limit = SIEGE_RANGE if kind == 'bombard_planet' else INVASION_RANGE
    return (unit.in_system == body.in_system and unit.in_hex == body.in_hex
            and distance(unit.position, body.position) <= body.collision_radius + limit + 0.01)


def blocker(game, player, kind, body, unit=None, amount=None, *, resources=True, troops=None, population=None, credits=None, fuel=None, execution=False, budget=None):
    from domain.players import are_enemies
    from campaign_graph import is_deployed
    if not colonizable(body) or body.owner is None:
        return 'target_unavailable'
    if kind in ('recruit_troops', 'upgrade_planetary_defenses'):
        if body.owner != player:
            return 'target_unavailable'
    elif not are_enemies(player, body.owner):
        return 'target_unavailable'
    if kind == 'upgrade_planetary_defenses':
        if body.population <= 0 or body.fortification_level >= len(FORTIFICATION_COSTS):
            return 'capability_unavailable'
        if body.last_defense_upgrade_round == game.turn_number:
            return 'cooldown_active'
        available = resource_balances(player if budget is None else budget)
        if credits is not None:
            available['credits'] = credits
        return 'insufficient_resources' if not fortification_cost(body.fortification_level + 1).affordable(available) else None
    if unit is None or unit.owner != player or unit.current_hit_points <= 0 or not is_deployed(unit, game.galaxy):
        return 'unit_unavailable'
    if unit.is_disabled or getattr(unit, 'is_hidden_in_gas_giant', False):
        return 'unit_unavailable'
    component = unit.siege_battery_component if kind == 'bombard_planet' else unit.troop_transport_component
    if component is None or component.is_destroyed:
        return 'capability_unavailable'
    if execution and unit.last_planetary_action_round == game.turn_number:
        return 'cooldown_active'
    if kind != 'bombard_planet':
        if type(amount) is not int or amount <= 0:
            return 'invalid_value'
        cargo = component.troops if troops is None else troops
        if kind == 'recruit_troops':
            if cargo + amount > component.capacity:
                return 'insufficient_capacity'
            pop = body.population if population is None else population
            money = player.credits if credits is None else credits
            if resources and (pop - amount * TROOP_POPULATION_COST < MIN_REMAINING_POPULATION - 1e-9 or money < amount * TROOP_CREDIT_COST):
                return 'insufficient_resources'
        elif cargo < amount:
            return 'insufficient_troops'
    if kind != 'recruit_troops':
        tank = unit.antimatter_component
        if tank is None or tank.is_destroyed:
            return 'capability_unavailable'
        available = tank.current_amount if fuel is None else fuel
        cost = SIEGE_AM_COST if kind == 'bombard_planet' else INVASION_AM_COST
        if resources and available < cost:
            return 'insufficient_resources'
    return None


def _record(game, body, category, detail, *, private=False, player=None, amount=0):
    from turn_briefing import record
    from domain.players import are_allies
    recipient = player or body.owner
    for viewer in game.players:
        if viewer == recipient or (not private and are_allies(viewer, recipient)):
            record(game, viewer, category, detail, subject=body, amount=amount)


def upgrade(game, player, body):
    error = blocker(game, player, 'upgrade_planetary_defenses', body)
    if error:
        raise ValueError(error)
    if not fortification_cost(body.fortification_level + 1).pay(player):
        raise ValueError('insufficient_resources')
    body.fortification_level += 1
    body.last_defense_upgrade_round = game.turn_number
    _record(game, body, 'development', f'Fortifications upgraded to level {body.fortification_level}', private=True)
    dirty(game)


def dirty(game):
    game.visibility_dirty = True
    game.sidebar_needs_update = True


def capture(game, body, new_owner):
    """Ownership drives live income, habitat and orbital-support queries directly."""
    from domain.players import are_allies
    previous = body.owner
    _record(game, body, 'capture', 'Colony lost', player=previous)
    body.owner = new_owner
    body.fortification_level = max(0, body.fortification_level - 1)
    body.defense_readiness = MIN_READINESS
    for agent in body.infiltrating_agents:
        if are_allies(agent.owner, new_owner):
            agent.active_sabotage = None
    _record(game, body, 'capture', 'Colony captured', player=new_owner)
    dirty(game)


def invasion_rng(game):
    rng = getattr(game, 'invasion_rng', None)
    if rng is None:
        rng = game.invasion_rng = random.Random()
    return rng


def rng_from_state(state):
    from state_codec import decode
    rng = random.Random()
    try:
        decoded = decode(state)
        if not isinstance(decoded, tuple) or len(decoded) != 3 or type(decoded[0]) is not int or decoded[0] != 3:
            raise ValueError('Unsupported RNG state')
        words, gaussian = decoded[1:]
        if (not isinstance(words, tuple) or len(words) != 625
                or any(type(word) is not int or not 0 <= word <= 0xffffffff for word in words[:-1])
                or type(words[-1]) is not int or not 0 <= words[-1] <= 624
                or (gaussian is not None and (type(gaussian) not in (int, float) or not math.isfinite(gaussian)))):
            raise ValueError('Invalid RNG values')
        rng.setstate(decoded)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Invalid invasion RNG state') from exc
    return rng


def resolve(game, order, body):
    """Called only from the explicit planetary phase, never from order updates."""
    from unit_orders.base import OrderStatus
    unit = order.unit
    kind = order.order_type.name.lower()
    amount = order.parameters.get('amount')
    error = blocker(game, unit.owner, kind, body, unit, amount, execution=True)
    if error:
        if error != 'cooldown_active':
            order.fail(error)
        return
    if not in_range(unit, body, kind):
        return
    unit.last_planetary_action_round = game.turn_number
    if kind == 'recruit_troops':
        unit.owner.credits -= amount * TROOP_CREDIT_COST
        body.population = max(MIN_REMAINING_POPULATION, body.population - amount * TROOP_POPULATION_COST)
        unit.troop_transport_component.troops += amount
        _record(game, body, 'development', 'Troops recruited', private=True, amount=amount)
        order.status = OrderStatus.COMPLETED
    elif kind == 'bombard_planet':
        maximum = maximum_defense(body)
        damage = min(SIEGE_DAMAGE, maximum * max(0, body.defense_readiness - MIN_READINESS))
        if damage <= 1e-9:
            order.status = OrderStatus.COMPLETED
            return
        unit.antimatter_component.consume(SIEGE_AM_COST)
        body.defense_readiness = max(MIN_READINESS, body.defense_readiness - damage / maximum)
        losses = min(max(0, body.population - MIN_REMAINING_POPULATION), damage * COLLATERAL_PER_DAMAGE)
        body.population -= losses
        body.last_hostile_action_round = game.turn_number
        for recipient in (unit.owner, body.owner):
            _record(game, body, 'combat', 'Planetary defenses bombarded', player=recipient, amount=damage)
            if losses:
                _record(game, body, 'combat', 'Bombardment population losses', player=recipient, amount=losses)
        if body.defense_readiness <= MIN_READINESS + 1e-9:
            body.defense_readiness = MIN_READINESS
            order.status = OrderStatus.COMPLETED
    else:
        preview = assault_preview(body, amount)
        probability = preview['success_probability']
        roll = None if probability >= 1 else invasion_rng(game).random()
        success = roll is None or roll < probability
        casualties = preview['success_casualties' if success else 'defeat_casualties']
        unit.antimatter_component.consume(INVASION_AM_COST)
        unit.troop_transport_component.troops -= casualties
        body.last_hostile_action_round = game.turn_number
        result = 'Invasion succeeded' if success else 'Invasion repelled'
        roll_text = 'undefended; guaranteed' if roll is None else f'roll {roll:.1%}, success below {probability:.1%}'
        for recipient in (unit.owner, body.owner):
            _record(game, body, 'combat', f'{result}: {roll_text}; {casualties} of {amount} committed troops lost', player=recipient, amount=casualties)
        if success:
            capture(game, body, unit.owner)
            order.status = OrderStatus.COMPLETED
        else:
            order.fail('assault_repulsed')
    dirty(game)


def process_actions(game, player):
    from campaign_graph import iter_units, is_deployed
    from unit_orders.base import OrderStatus
    candidates = []
    for unit, _ in iter_units(game.galaxy):
        if unit.owner != player or not is_deployed(unit, game.galaxy) or not unit.commander_component:
            continue
        root = unit.commander_component.current_order
        if root and root.order_type.name.lower() in KINDS and root.status == OrderStatus.IN_PROGRESS:
            candidates.append(root)
    candidates.sort(key=lambda order: (KINDS.index(order.order_type.name.lower()), order.unit.id))
    for order in candidates:
        if order.unit.commander_component.current_order is not order or order.status != OrderStatus.IN_PROGRESS:
            continue
        body = exact_body(game, player, order.parameters.get('target_id'))
        if body is None:
            order.fail('target_unavailable')
        elif not order.has_active_sub_orders():
            resolve(game, order, body)


def recover(game):
    for system in game.galaxy.systems.values():
        for _, body in system.get_all_celestial_bodies():
            if colonizable(body) and body.owner and body.last_hostile_action_round != game.turn_number:
                body.defense_readiness = min(1.0, body.defense_readiness + RECOVERY_PER_ROUND)
