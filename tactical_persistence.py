"""Strict codecs for independent tactical world objects."""
from domain.deployables import Deployable, CatalystPatch
from geometry import Position
from state_codec import fields, number


def serialize(obj):
    data = {'id': obj.id, 'owner_id': obj.owner.id, 'deploying_ship_id': obj.deploying_ship_id,
            'in_system': obj.in_system, 'in_hex': list(obj.in_hex), 'position': [obj.position.x, obj.position.y]}
    if isinstance(obj, Deployable):
        data.update(kind=obj.kind, hit_points=obj.current_hit_points, fuel=obj.fuel,
                    identified_player_ids=sorted(obj.identified_player_ids))
    else:
        data.update(nebula_id=obj.nebula_id, expires_round=obj.expires_round, radius=obj.radius)
    return data


def validate(data, player_ids, *, patch=False):
    common = ('id', 'owner_id', 'deploying_ship_id', 'in_system', 'in_hex', 'position')
    extra = ('nebula_id', 'expires_round', 'radius') if patch else ('kind', 'hit_points', 'fuel', 'identified_player_ids')
    fields(data, common + extra, 'tactical_object')
    for name in ('id', 'owner_id', 'deploying_ship_id'):
        number(data[name], name, 0, integer=True)
    if data['owner_id'] not in player_ids:
        raise ValueError('Unknown tactical owner')
    if not isinstance(data['in_system'], str):
        raise ValueError('Invalid tactical system')
    for name in ('in_hex', 'position'):
        if not isinstance(data[name], list) or len(data[name]) != 2:
            raise ValueError('Invalid tactical location')
        for value in data[name]:
            number(value, name, integer=name == 'in_hex')
    if patch:
        for name in ('nebula_id', 'expires_round'):
            number(data[name], name, 0, integer=True)
        number(data['radius'], 'radius', 0)
        if data['radius'] <= 0:
            raise ValueError('Invalid catalyst radius')
    else:
        if data['kind'] not in ('ghost_fleet', 'fuel_cache'):
            raise ValueError('Unknown deployable kind')
        number(data['hit_points'], 'hit_points', 1, integer=True)
        number(data['fuel'], 'fuel', 0)
        from tactical_balance import DEPLOYABLE_HP, CACHE_FUEL
        if data['hit_points'] > DEPLOYABLE_HP or data['fuel'] > CACHE_FUEL or (data['kind'] == 'ghost_fleet' and data['fuel'] != 0) or (data['kind'] == 'fuel_cache' and data['fuel'] <= 0):
            raise ValueError('Invalid deployable contents')
        ids = data['identified_player_ids']
        if not isinstance(ids, list) or any(type(pid) is not int or pid not in player_ids for pid in ids) or len(ids) != len(set(ids)):
            raise ValueError('Invalid emitter identification')


def deserialize(data, players, *, patch=False):
    validate(data, set(players), patch=patch)
    args = (players[data['owner_id']], Position(*data['position']), tuple(data['in_hex']), data['in_system'])
    if patch:
        obj = CatalystPatch(*args, data['deploying_ship_id'], data['nebula_id'], data['expires_round'])
        obj.radius = data['radius']
    else:
        obj = Deployable(*args, data['kind'], data['deploying_ship_id'])
        obj.current_hit_points = data['hit_points']
        obj.fuel = data['fuel']
        obj.identified_player_ids = set(data['identified_player_ids'])
    obj.id = data['id']
    return obj
