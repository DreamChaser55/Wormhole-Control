"""Environmental effects at firing, damage, visibility and persistence boundaries."""
from types import SimpleNamespace
import json
import pytest
from constants import FieldDensity, HullSize, NebulaType
from domain.celestials import IceField, Nebula
from domain.players import Player
from environmental_effects import modifiers_for_unit
from geometry import Position
from turn_processor import TurnProcessor
from unit_components.weapons import Weapons, Turret
from unit_components.enums import TurretType, TurretVariant
from unit_components.commander import Commander
from unit_components.abilities.cluster_warhead import ClusterWarheadAbility
from unit_orders.combat import AttackOrder
from unit_orders.base import OrderStatus
from save_manager import serialize_game_state, deserialize_game_state
from game_ai.observation import build_observation
from tests.support.campaigns import campaign, ship


def field(game, kind, *, center=None, radius=500):
    body = (IceField((0, 0), 'Sol', FieldDensity.LOW) if kind == 'ice'
            else Nebula((0, 0), 'Sol', NebulaType[kind.upper()]))
    body.position = center or Position(0, 0)
    body.radius = radius
    game.galaxy.systems['Sol'].add_celestial_body(body)
    return body


def combatants():
    game = campaign()
    attacker, target = ship(game, 'attacker'), ship(game, 'target', owner=1)
    attacker.in_galaxy = target.in_galaxy = game.galaxy
    target.position = Position(200, 0)
    weapons = Weapons(attacker)
    attacker.add_component(weapons)
    turret = Turret(TurretType.MASS_DRIVER, 10, 1000, 3, attacker)
    weapons.add_turret(turret)
    return game, attacker, target, turret


@pytest.mark.parametrize('kind', ['ice', 'nitrogen'])
@pytest.mark.parametrize('position,expected', [(499, 2), (500, 2), (501, 3)])
def test_cooling_uses_actual_inclusive_boundary(kind, position, expected):
    game, attacker, target, turret = combatants()
    field(game, kind)
    attacker.position = Position(position, 0)
    turret.target = target
    turret.fire()
    assert turret.current_cooldown == expected
    assert turret.cooldown == 3


@pytest.mark.parametrize('base,variant,expected', [
    (0, TurretVariant.STANDARD, 0), (1, TurretVariant.STANDARD, 1),
    (3, TurretVariant.STANDARD, 2), (3, TurretVariant.LONG_RANGE, 8),
])
def test_cooling_overlap_and_variant_floor(base, variant, expected):
    game, attacker, target, _ = combatants()
    field(game, 'ice'); field(game, 'nitrogen'); field(game, 'ice')
    turret = Turret(TurretType.BEAM, 10, 1000, base, attacker, variant)
    turret.target = target
    turret.fire()
    assert turret.current_cooldown == expected
    assert turret.cooldown == base * (3 if variant == TurretVariant.LONG_RANGE else 1)


def test_moving_does_not_rewrite_remaining_cooldown_and_save_restores_exactly():
    game, attacker, target, turret = combatants()
    field(game, 'nitrogen', radius=3600)
    turret.target = target
    turret.fire()
    attacker.position = Position(4000, 0)
    assert turret.current_cooldown == 2 and turret.effective_cooldown == 3
    state = json.loads(json.dumps(serialize_game_state(game)))
    restored_game = campaign()
    assert deserialize_game_state(restored_game, state)
    loaded = restored_game.galaxy.get_unit_by_id(attacker.id)
    restored = loaded.weapons_component.turrets[0]
    assert (restored.cooldown, restored.current_cooldown, restored.effective_cooldown) == (3, 2, 3)
    loaded.position = Position(100, 0)
    assert restored.current_cooldown == 2 and restored.effective_cooldown == 2


@pytest.mark.parametrize('count', [2, 3, 6])
def test_cooling_never_adds_ticks_or_fires_outside_owner_turn(count):
    game, attacker, target, turret = combatants()
    field(game, 'ice')
    while len(game.players) < count:
        game.players.append(Player(f'Other{len(game.players)}', (1, 2, 3)))
    attacker.add_component(Commander(attacker))
    attack = AttackOrder(attacker, {'target_unit_id': target.id})
    attack.status = OrderStatus.IN_PROGRESS
    attacker.commander_component.current_order = attack
    # Real command authority remains required even inside coolant.
    attacker.weapons_component.set_target(target)
    processor = TurnProcessor(game)
    hp = target.current_hit_points
    for _ in range(3):
        for player in game.players:
            processor._process_unit_updates(player)
    assert hp - target.current_hit_points == 20
    assert turret.current_cooldown == 2


@pytest.mark.parametrize('stored', ['hidden', 'docked', 'missing', 'dead'])
def test_unavailable_or_stored_units_get_neutral_modifiers(stored):
    game, attacker, _, turret = combatants()
    field(game, 'ice'); field(game, 'oxygen')
    if stored == 'hidden':
        attacker.is_hidden_in_gas_giant = True
    elif stored == 'docked':
        game.galaxy.systems['Sol'].hexes[(0, 0)].units.remove(attacker)
    elif stored == 'dead':
        attacker.current_hit_points = 0
    else:
        attacker.in_system = 'missing'
    assert turret.effective_cooldown == 3
    assert modifiers_for_unit(attacker).splash_damage_multiplier == 1


@pytest.mark.parametrize('kind', list(TurretType))
def test_cooling_applies_to_all_weapons_and_strikecraft(kind):
    game, attacker, _, turret = combatants()
    field(game, 'nitrogen')
    attacker.hull_size = HullSize.STRIKECRAFT_WING
    turret.turret_type = kind
    assert turret.effective_cooldown == 2


@pytest.mark.parametrize('position,splash,expected', [(499, True, 115), (500, True, 115),
    (501, True, 100), (499, False, 100)])
def test_oxygen_damage_classification_and_victim_boundary(position, splash, expected):
    game, attacker, target, _ = combatants()
    field(game, 'oxygen'); field(game, 'oxygen')
    target.position = Position(position, 0)
    hp = target.current_hit_points
    target.take_damage(100, is_splash=splash)
    assert hp - target.current_hit_points == expected


@pytest.mark.parametrize('amount,reduction,expected', [(1, 0, 1), (10, .5, 5),
    (100, 1, 0), (0, 0, 0), (-1, 0, 0), (1000, 0, 400)])
def test_oxygen_rounding_absorption_and_destruction(amount, reduction, expected):
    game, _, target, _ = combatants()
    field(game, 'oxygen')
    target.damage_reduction = reduction
    hp = target.current_hit_points
    target.take_damage(amount, is_splash=True)
    assert hp - target.current_hit_points == expected
    assert bool(getattr(target, '_destroyed', False)) == (expected == hp)


def test_cluster_warhead_marks_falloff_splash_and_preserves_allies():
    game, attacker, target, _ = combatants()
    field(game, 'oxygen', center=target.position, radius=10)
    ally = ship(game, 'ally')
    ally.position = target.position
    hp, ally_hp = target.current_hit_points, ally.current_hit_points
    ability = ClusterWarheadAbility()
    ability._apply_splash_damage(SimpleNamespace(unit=attacker), game.galaxy, Position(100, 0))
    assert hp - target.current_hit_points == 46  # 80 * 0.5 falloff * 1.15
    assert ally.current_hit_points == ally_hp


def test_observations_add_effects_without_exposing_enemy_turrets():
    game, attacker, target, turret = combatants()
    ice = field(game, 'ice')
    oxygen = field(game, 'oxygen')
    observation = build_observation(game, game.players[0])
    own = next(u for u in observation['units'] if u['id'] == attacker.id)
    info = own['capability_details']['weapons']['turrets'][0]
    assert info['cooldown'] == 3 and info['effective_cooldown'] == 2
    for enemy in (u for u in observation['units'] if u['owner_id'] == target.owner.id):
        assert 'capability_details' not in enemy
    bodies = {b['id']: b for s in observation['systems'] for b in s.get('celestial_bodies', [])}
    assert bodies[ice.id]['environmental_effects']['cooldown_reduction'] == 1
    assert bodies[oxygen.id]['environmental_effects']['splash_damage_multiplier'] == 1.15
    assert observation['schema_version'] == 6
