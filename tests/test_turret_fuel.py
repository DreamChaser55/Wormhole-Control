"""Live turret payment, resupply, and disclosure across game entry points."""
from unittest.mock import Mock

import pytest

from antimatter_logistics import exchange
from constants import DEFAULT_ANTIMATTER_CAPACITY, HullSize
from domain.players import Player
from game_ai.contracts import Command
from game_ai.observation import build_observation
from geometry import Position, distance
from save_manager import deserialize_game_state, serialize_game_state
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from turn_processor import TurnProcessor
from unit_components.abilities import AbilityComponent
from unit_components.antimatter import AntimatterStorage
from unit_components.defenses import Defenses
from unit_components.enums import AbilityType, TurretType, TurretVariant
from unit_components.movement import Engines
from unit_components.sensors import Sensors
from unit_components.weapons import Turret, Weapons


def arm(unit, count=1, variant=TurretVariant.STANDARD):
    weapons = Weapons(unit)
    for _ in range(count):
        weapons.add_turret(Turret(TurretType.MASS_DRIVER, 10, 300, 2, unit, variant))
    unit.add_component(weapons)
    return weapons


def attack(game, actor, target, *, kind='attack', queue=False):
    return issue(game, actor.owner, Command(kind, (actor.id,), target_id=target.id, queue=queue))


@pytest.fixture
def battle():
    game = campaign()
    game.galaxy.game = game
    attacker = ship(game, hull=HullSize.MEDIUM)
    target = ship(game, owner=1)
    target.position = Position(250, 0)
    return game, attacker, target


def test_a_fully_absorbed_shot_spends_the_last_am(battle, monkeypatch):
    game, attacker, target = battle
    turret, = arm(attacker).turrets
    tank = attacker.antimatter_component
    tank.current_amount = 1
    target.add_component(Defenses(target, armor=10))
    monkeypatch.setattr('unit_components.defenses.random.uniform', lambda _low, high: high)
    before = target.current_hit_points
    assert attack(game, attacker, target).accepted

    attacker.update()

    assert tank.current_amount == 0
    assert target.current_hit_points == before
    assert attacker.experience_points == 0
    assert turret.current_cooldown == 2


@pytest.mark.parametrize('target_hp, cooldowns', [(400, [2, 2, 0]), (5, [2, 0, 0])])
def test_volley_spends_in_installed_order_until_out_of_fuel_or_target_destroyed(battle, target_hp, cooldowns):
    game, attacker, target = battle
    weapons = arm(attacker, count=3)
    attacker.antimatter_component.current_amount = 2.5
    target.current_hit_points = target_hp
    assert attack(game, attacker, target).accepted

    attacker.update()

    shots = sum(cooldown > 0 for cooldown in cooldowns)
    assert [turret.current_cooldown for turret in weapons.turrets] == cooldowns
    assert attacker.antimatter_component.current_amount == 2.5 - shots
    assert target.current_hit_points == max(0, target_hp - shots * 10)


@pytest.mark.parametrize('problem, blocker', [
    ('missing', 'antimatter_storage_unavailable'),
    ('destroyed', 'antimatter_storage_unavailable'),
    ('low', 'insufficient_antimatter'),
])
def test_fuel_blocked_attack_retains_its_order_and_resumes(battle, problem, blocker):
    game, attacker, target = battle
    weapons = arm(attacker, variant=TurretVariant.LONG_RANGE)
    turret, = weapons.turrets
    tank = attacker.antimatter_component
    if problem == 'missing':
        attacker.remove_component(AntimatterStorage)
    elif problem == 'destroyed':
        attacker.take_component_damage(AntimatterStorage, tank.max_hit_points)
    else:
        tank.current_amount = 0.5
    fuel = tank.current_amount
    assert weapons.firing_fuel() == (1, blocker)
    assert attack(game, attacker, target, kind='attack_long_range').accepted
    assert attack(game, attacker, target, queue=True).accepted
    commander = attacker.commander_component
    order = commander.current_order
    before = target.current_hit_points

    attacker.update()

    assert tank.current_amount == fuel
    assert target.current_hit_points == before
    assert attacker.experience_points == 0
    assert turret.current_cooldown == 0
    assert commander.current_order is order
    assert len(commander.orders_queue) == 1

    if problem == 'missing':
        attacker.add_component(tank)
    elif problem == 'destroyed':
        assert attacker.heal_components(1) == 1
    else:
        assert exchange(ship(game), attacker, limit=1) == 1
    fuel = tank.current_amount
    attacker.update()

    assert tank.current_amount == fuel - 1
    assert target.current_hit_points == before - 10
    assert commander.current_order is order
    assert len(commander.orders_queue) == 1


def test_a_refused_debit_leaves_the_turret_ready(battle, monkeypatch):
    game, attacker, target = battle
    turret, = arm(attacker).turrets
    tank = attacker.antimatter_component
    consume = Mock(return_value=False)
    monkeypatch.setattr(tank, 'consume', consume)
    assert attack(game, attacker, target).accepted
    before = target.current_hit_points

    assert turret.fire() is False

    consume.assert_called_once_with(1)
    assert target.current_hit_points == before
    assert attacker.experience_points == 0
    assert turret.current_cooldown == 0


def test_movement_can_spend_the_last_am_before_turrets_fire(battle):
    game, attacker, target = battle
    turret, = arm(attacker).turrets
    attacker.add_component(Engines(attacker, speed=100))
    attacker.add_component(Sensors(attacker, short_range_radius=500))
    attacker.antimatter_component.current_amount = 1
    target.position = Position(450, 0)
    assert attack(game, attacker, target).accepted
    before = target.current_hit_points

    TurnProcessor(game).process_player_turn(attacker.owner)

    assert distance(attacker.position, target.position) < turret.range
    assert attacker.antimatter_component.current_amount == 0
    assert target.current_hit_points == before
    assert turret.current_cooldown == 0


def test_tankless_strikecraft_fires_for_free(battle):
    game, _, target = battle
    wing = ship(game, hull=HullSize.STRIKECRAFT_WING)
    wing.remove_component(AntimatterStorage)
    weapons = arm(wing)
    before = target.current_hit_points
    assert weapons.firing_fuel() == (0, None)
    assert attack(game, wing, target).accepted

    wing.update()

    assert target.current_hit_points == before - 10
    assert weapons.turrets[0].current_cooldown == 2


def test_missile_batteries_fire_using_their_own_inherited_tanks(battle):
    game, caster, target = battle
    arm(caster)
    kind = AbilityType.MISSILE_BATTERIES
    abilities = AbilityComponent(caster, [kind])
    caster.add_component(abilities)
    caster_fuel = caster.antimatter_component.current_amount
    before = target.current_hit_points
    assert abilities.activate(kind, game.galaxy)
    cast = abilities.abilities[kind]
    assert len(cast.spawned_unit_ids) == 3
    abilities.update(game.galaxy)

    for unit_id in cast.spawned_unit_ids:
        platform = game.galaxy.get_unit_by_id(unit_id)
        tank = platform.antimatter_component
        assert tank.current_amount == DEFAULT_ANTIMATTER_CAPACITY
        platform.update()
        assert tank.current_amount == DEFAULT_ANTIMATTER_CAPACITY - 1

    assert target.current_hit_points == before - 30
    assert caster.antimatter_component.current_amount == caster_fuel - cast.definition.antimatter_cost


def test_save_round_trip_retains_fuel_cooldown_and_engagement(battle):
    game, attacker, target = battle
    arm(attacker)
    attacker.antimatter_component.current_amount = 1.5
    assert attack(game, attacker, target).accepted
    attacker.update()
    order_id = attacker.commander_component.current_order.public_id
    assert deserialize_game_state(game, serialize_game_state(game))
    restored = game.galaxy.get_unit_by_id(attacker.id)
    restored_target = game.galaxy.get_unit_by_id(target.id)
    turret, = restored.weapons_component.turrets
    tank = restored.antimatter_component
    before = restored_target.current_hit_points

    assert tank.current_amount == 0.5
    assert turret.current_cooldown == 2
    restored.update()
    assert turret.current_cooldown == 1
    restored.update()
    assert turret.current_cooldown == 0
    assert restored_target.current_hit_points == before
    tank.add(1)
    restored.update()
    assert restored.commander_component.current_order.public_id == order_id
    assert restored_target.current_hit_points == before - 10
    assert tank.current_amount == 0.5


def test_weapons_fuel_is_visible_only_to_owners_and_allies(battle):
    game, attacker, target = battle
    ally = Player('Ally', (0, 0, 200), team_id=attacker.owner.team_id)
    game.players.append(ally)
    weapons = arm(attacker)
    tank = attacker.antimatter_component
    tank.current_amount = 0.5
    price = '1 AM per shot'
    warning = 'Insufficient antimatter to fire'
    for index, player in enumerate(game.players):
        game.current_player_index = index
        view = next(unit for unit in build_observation(game, player)['units'] if unit['id'] == attacker.id)
        info = view['capability_details']['weapons']
        details = [row['text'] for row in weapons.get_sidebar_data(game)]
        basic = [row['text'] for row in weapons.get_basic_sidebar_data(game)]
        if player is target.owner:
            assert 'antimatter_per_shot' not in info and 'firing_fuel_blocker' not in info
            assert price not in details and warning not in details and warning not in basic
        else:
            assert info['antimatter_per_shot'] == 1
            assert info['firing_fuel_blocker'] == 'insufficient_antimatter'
            assert price in details and warning in details and warning in basic
    assert tank.current_amount == 0.5
