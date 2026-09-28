"""Shared, player-scoped colony ownership disclosure and remembered intelligence."""
from dataclasses import dataclass

from domain.players import are_allies


def is_colony_body(body):
    from domain.celestials import Planet, Moon, ColonizableAsteroid
    return isinstance(body, (Planet, Moon, ColonizableAsteroid)) and body.is_colonizable


def current_ownership(galaxy, viewer, body, snapshot=None):
    """Authorize current colony information, independently of known geography."""
    if viewer is None or not is_colony_body(body):
        return False
    if are_allies(viewer, body.owner):
        return True
    if snapshot is None or getattr(snapshot, 'viewer', None) is not viewer:
        from visibility import VisibilityService
        snapshot = VisibilityService.compute(galaxy, viewer, record_intel=False)
    return body.id in getattr(snapshot, 'sensed_colony_ids', ())


@dataclass(frozen=True)
class OwnershipView:
    status: str
    owner_id: int | None
    relation: str
    observed_turn: int | None


def ownership_view(game, viewer, body, snapshot=None):
    """Return current, remembered or unknown ownership; never write intelligence."""
    if viewer is None or not is_colony_body(body):
        return OwnershipView('unknown', None, 'unknown', None)
    if current_ownership(game.galaxy, viewer, body, snapshot):
        owner = body.owner
        return OwnershipView('current', owner.id if owner is not None else None,
                             relation_to(viewer, owner), getattr(game, 'turn_number', 1))
    record = getattr(viewer, 'planetary_intel', {}).get(body.id)
    if record is None:
        return OwnershipView('unknown', None, 'unknown', None)
    owner_id = record['owner_id']
    owner = next((p for p in game.players if p.id == owner_id), None)
    relation = relation_to(viewer, owner)
    return OwnershipView('last_known', owner_id, relation, record['observed_turn'])


def relation_to(viewer, owner):
    if owner is None:
        return 'neutral'
    if viewer is owner or viewer.id == owner.id:
        return 'self'
    return 'ally' if are_allies(viewer, owner) else 'enemy'


def colony_target_blocker(game, viewer, body, kind, snapshot=None):
    """Authorize intent using only disclosed ownership, including dated history."""
    if viewer is None or not is_colony_body(body):
        return 'target_unavailable'
    view = ownership_view(game, viewer, body, snapshot)
    if kind == 'colonize':
        return None if view.status == 'unknown' or view.relation == 'neutral' else 'invalid_target'
    if view.status == 'unknown':
        return 'target_unavailable'
    if kind == 'load_colonists':
        return None if view.relation == 'self' else 'invalid_relation'
    required = 'self' if kind == 'recruit_troops' else 'enemy'
    return None if view.relation == required else 'target_unavailable'


def presentation_view(game, body):
    """Use only the active player's snapshot, including while UI is refreshing."""
    players = getattr(game, 'players', ())
    index = getattr(game, 'current_player_index', 0)
    viewer = players[index] if players and isinstance(index, int) and 0 <= index < len(players) else None
    snapshot = None if getattr(game, 'visibility_dirty', False) else getattr(game, 'visibility', None)
    return ownership_view(game, viewer, body, snapshot)


def displayed_owner(game, body):
    view = presentation_view(game, body)
    return next((p for p in game.players if p.id == view.owner_id), None)


def decode_records(records, *, turn=None, player_ids=None, bodies=None):
    """Strict save decoding; historical owners need not match current owners."""
    if not isinstance(records, list):
        raise ValueError('planetary_intel: expected array')
    result = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {'body_id', 'owner_id', 'observed_turn'}:
            raise ValueError('planetary_intel: invalid record')
        body_id, owner_id, observed = record['body_id'], record['owner_id'], record['observed_turn']
        if type(body_id) is not int or body_id < 0 or body_id in result:
            raise ValueError('planetary_intel: invalid or duplicate body ID')
        if owner_id is not None and (type(owner_id) is not int or owner_id < 0 or
                                    (player_ids is not None and owner_id not in player_ids)):
            raise ValueError('planetary_intel: unknown owner')
        if type(observed) is not int or observed < 1 or (turn is not None and observed > turn):
            raise ValueError('planetary_intel: invalid observation turn')
        if bodies is not None and not is_colony_body(bodies.get(body_id)):
            raise ValueError('planetary_intel: unknown colonizable body')
        result[body_id] = {'owner_id': owner_id, 'observed_turn': observed}
    return result


def encode_records(player):
    records = [dict(body_id=body_id, **record) for body_id, record in sorted(player.planetary_intel.items())]
    decode_records(records)
    return records


def refresh(game):
    """Record all players' authorized knowledge after a committed world change."""
    from visibility import VisibilityService
    VisibilityService.update_all_players_intel(game.galaxy, game.players, game.turn_number)
    game.visibility_dirty = True
    game.sidebar_needs_update = True


COLONY_ORDER_FIELDS = {
    'COLONIZE': 'target_id', 'LOAD_COLONISTS': 'target_id',
    'RECRUIT_TROOPS': 'target_id', 'BOMBARD_PLANET': 'target_id',
    'INVADE_PLANET': 'target_id', 'INFILTRATE_PLANET': 'target_body_id',
}


def validate_order_target(order, galaxy, snapshot=None):
    """Revalidate intent before movement, without treating lost contact as failure."""
    field = COLONY_ORDER_FIELDS.get(order.order_type.name)
    if field is None:
        return True
    if snapshot is None:
        # Executing/advancing an order is gameplay: retain a contact acquired here
        # even if it disappears before the next turn-wide visibility refresh.
        from visibility import VisibilityService
        snapshot = VisibilityService.compute(galaxy, order.unit.owner,
                                             turn_number=order.unit.game.turn_number)
    body = galaxy.get_celestial_body_by_id(order.parameters.get(field))
    # Physical unsuitability is public; let each order report its normal error.
    if body is not None and getattr(body, 'is_colonizable', True) is False:
        return True
    error = colony_target_blocker(order.unit.game, order.unit.owner, body,
                                 order.order_type.name.lower(), snapshot)
    if error is None:
        return True
    for child in order.sub_orders:
        child.cancel()
    order.sub_orders.clear()
    order.fail(error)
    return False


def revalidate_colony_orders(game):
    """Settle newly disclosed invalid targets without starting another owner's queue."""
    from campaign_graph import iter_units
    from visibility import VisibilityService
    snapshots = {}
    for unit, _ in iter_units(game.galaxy):
        commander = unit.commander_component
        order = commander.current_order if commander else None
        if order is None or order.status.name != 'IN_PROGRESS' or order.order_type.name not in COLONY_ORDER_FIELDS:
            continue
        if unit.owner.id not in snapshots:
            snapshots[unit.owner.id] = VisibilityService.compute(game.galaxy, unit.owner, record_intel=False)
        validate_order_target(order, game.galaxy, snapshots[unit.owner.id])


def order_phase(order, galaxy):
    """Derive colony progress without changing orders, intel or saved state."""
    kind = order.order_type.name
    field = COLONY_ORDER_FIELDS.get(kind)
    if field is None or order.status.name != 'IN_PROGRESS':
        return None
    body = galaxy.get_celestial_body_by_id(order.parameters.get(field))
    if body is None:
        return None
    unit = order.unit
    if kind in {'COLONIZE', 'LOAD_COLONISTS'}:
        from unit_orders.colony import within_colony_range
        arrived = within_colony_range(unit, body)
    elif kind == 'INFILTRATE_PLANET':
        from geometry import distance
        from unit_orders.intelligence import INTELLIGENCE_OPERATIONAL_RANGE
        arrived = (unit.in_system == body.in_system and unit.in_hex == body.in_hex
                   and distance(unit.position, body.position) <= INTELLIGENCE_OPERATIONAL_RANGE)
    else:
        from planetary_warfare import in_range
        arrived = in_range(unit, body, kind.lower())
    if not arrived:
        return 'approach'
    if not current_ownership(galaxy, unit.owner, body):
        return 'waiting_for_contact'
    return 'awaiting_owner_turn_resolution' if kind in {'RECRUIT_TROOPS', 'BOMBARD_PLANET', 'INVADE_PLANET'} else 'ready'
