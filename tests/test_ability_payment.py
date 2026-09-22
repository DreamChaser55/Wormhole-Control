"""Payment failure cannot commit ordinary ability effects or lifecycle state."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from game_ai.contracts import Command
from game_ai.rules import ability_states
from geometry import Position
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from unit_components.abilities import AbilityComponent
from unit_components.antimatter import AntimatterStorage
from unit_components.enums import AbilityType
from unit_components.weapons import Weapons
from unit_orders.abilities import UseAbilityOrder


def setup_cast(kind):
    game = campaign()
    actor, target = ship(game), ship(game, owner=1)
    target.position = Position(200, 0)
    actor.add_component(Weapons(actor))
    actor.add_component(AbilityComponent(actor, [AbilityType(kind)]))
    args = {}
    if kind in ('ion_bolt', 'capture_unit', 'drain_antimatter'):
        args['target_unit_id'] = target.id
    elif kind == 'cluster_warhead':
        args.update(target_position=Position(200, 0), target_system_name='Sol', target_hex_coord=(0, 0))
    return game, actor, target, args


def cast(game, actor, kind, args, route='direct'):
    if route == 'direct':
        return actor.ability_component.activate(AbilityType(kind), game.galaxy, **args)
    actor.commander_component.clear_explicit_orders()
    order = UseAbilityOrder(actor, dict(ability_type=kind, **args))
    actor.commander_component.add_order(order)
    assert order.status.name in ('FAILED', 'COMPLETED')
    return order.status.name == 'COMPLETED'


def gameplay_state(game, actor, target):
    return deepcopy((actor.ability_component._extra_state(), actor.position,
        target.current_hit_points, target.is_disabled, getattr(target, '_ability_effects', {}),
        [(u.id, u.current_hit_points) for u in game.galaxy.systems['Sol'].hexes[(0, 0)].units]))


@pytest.mark.parametrize('kind', ['cluster_warhead', 'ion_bolt', 'missile_batteries'])
@pytest.mark.parametrize('failure', ['destroyed', 'missing', 'insufficient', 'debit_refused'])
@pytest.mark.parametrize('route', ['direct', 'order'])
def test_repeated_failed_payment_has_no_effect(monkeypatch, kind, failure, route):
    game, actor, target, args = setup_cast(kind)
    tank = actor.antimatter_component
    if failure == 'destroyed':
        tank.current_hit_points = 0
    elif failure == 'missing':
        actor.components.pop(AntimatterStorage)
    elif failure == 'insufficient':
        tank.current_amount = actor.ability_component.abilities[AbilityType(kind)].definition.antimatter_cost - 1
    else:
        monkeypatch.setattr(tank, 'consume', Mock(return_value=False))
    before, fuel = gameplay_state(game, actor, target), tank.current_amount
    for _ in range(2):
        assert not cast(game, actor, kind, args, route)
        assert gameplay_state(game, actor, target) == before
        assert tank.current_amount == fuel
    if failure == 'debit_refused':
        assert tank.consume.call_count == 2


@pytest.mark.parametrize('kind', ['cluster_warhead', 'ion_bolt', 'missile_batteries'])
def test_success_pays_once_and_repeat_cast_has_no_effect(monkeypatch, kind):
    game, actor, target, args = setup_cast(kind)
    tank = actor.antimatter_component
    instance = actor.ability_component.abilities[AbilityType(kind)]
    monkeypatch.setattr(tank, 'consume', Mock(wraps=tank.consume))
    hp = target.current_hit_points
    assert cast(game, actor, kind, args, 'order')
    assert tank.current_amount == 100 - instance.definition.antimatter_cost
    tank.consume.assert_called_once_with(instance.definition.antimatter_cost)
    assert instance.cooldown_remaining == instance.definition.cooldown
    assert instance.duration_remaining == instance.definition.duration
    if kind == 'cluster_warhead':
        assert target.current_hit_points == hp - 80
    elif kind == 'ion_bolt':
        assert target.is_disabled and target._ability_effects
    else:
        assert len(instance.spawned_unit_ids) == 3
    before = gameplay_state(game, actor, target)
    assert not cast(game, actor, kind, args, 'order')
    assert gameplay_state(game, actor, target) == before
    assert tank.consume.call_count == 1


@pytest.mark.parametrize('failure', ['destroyed', 'missing'])
def test_storage_requirement_is_shared_by_projection_observation_and_ui(failure):
    game, actor, target, _ = setup_cast('ion_bolt')
    if failure == 'destroyed':
        actor.antimatter_component.current_hit_points = 0
    else:
        actor.components.pop(AntimatterStorage)
    assert not actor.ability_component.can_use(AbilityType.ION_BOLT, resources=False)
    assert not ability_states(actor)[0]['ready']
    button = next(row for row in actor.ability_component.get_sidebar_data(game) if row.get('action_id') == 'use_ability')
    assert not button['enabled']
    before = gameplay_state(game, actor, target)
    result = issue(game, actor.owner, Command('rename_unit', (actor.id,), new_name='Changed'),
                   Command('use_ability', (actor.id,), ability='ion_bolt', target_id=target.id))
    assert not result.accepted and result.failure_stage == 'preflight'
    assert actor.name == 'ship'
    assert gameplay_state(game, actor, target) == before


def test_projection_can_override_balance_but_not_storage_functionality():
    _, actor, _, _ = setup_cast('ion_bolt')
    actor.antimatter_component.current_amount = 0
    assert not actor.ability_component.can_use(AbilityType.ION_BOLT)
    assert actor.ability_component.can_use(AbilityType.ION_BOLT, resources=False)
    assert not ability_states(actor)[0]['ready']


@pytest.mark.parametrize('rejection', ['missing_target', 'capture_roll'])
def test_rejected_activation_refunds_once_without_cooldown(monkeypatch, rejection):
    kind = 'ion_bolt' if rejection == 'missing_target' else 'capture_unit'
    game, actor, target, args = setup_cast(kind)
    if rejection == 'missing_target':
        args['target_unit_id'] = -1
    else:
        from unit_components.marines import MarinesComponent
        actor.add_component(MarinesComponent(actor, marines_count=1))
        monkeypatch.setattr('unit_components.abilities.capture_unit.random.random', lambda: 1.0)
    tank = actor.antimatter_component
    monkeypatch.setattr(tank, 'add', Mock(wraps=tank.add))
    before = gameplay_state(game, actor, target)
    assert not cast(game, actor, kind, args)
    assert tank.current_amount == 100
    tank.add.assert_called_once_with(actor.ability_component.abilities[AbilityType(kind)].definition.antimatter_cost)
    assert gameplay_state(game, actor, target) == before
    assert target.owner is game.players[1]


def test_zero_cost_drain_does_not_attempt_payment(monkeypatch):
    game, actor, target, args = setup_cast('drain_antimatter')
    tank = actor.antimatter_component
    tank.current_amount = 0
    monkeypatch.setattr(tank, 'consume', Mock(side_effect=AssertionError('Zero-cost cast must not debit')))
    assert cast(game, actor, 'drain_antimatter', args)
    assert tank.current_amount == 30 and target.antimatter_component.current_amount == 70


def test_unexpected_effect_exception_does_not_refund_uncertain_effects(monkeypatch):
    game, actor, target, args = setup_cast('ion_bolt')
    instance = actor.ability_component.abilities[AbilityType.ION_BOLT]
    def partial_effect(**kwargs):
        target.current_hit_points -= 1
        raise RuntimeError('Interrupted effect')
    monkeypatch.setattr(instance, 'on_activate', partial_effect)
    with pytest.raises(RuntimeError, match='Interrupted effect'):
        cast(game, actor, 'ion_bolt', args)
    assert actor.antimatter_component.current_amount == 75
