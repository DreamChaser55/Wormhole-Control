import pytest

from geometry import Position
from tests.test_unit_components import MockUnit
from unit_components import Commander, Turret, TurretType, Weapons
from unit_orders import AttackOrder, Order, OrderStatus, OrderType


def _combatants():
    attacker = MockUnit()
    attacker.id = 100
    attacker.position = Position(0, 0)
    attacker.add_component(Commander(attacker))

    weapons = Weapons(attacker)
    turret = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=10,
        range=100.0,
        cooldown=2,
        parent_unit=attacker,
    )
    weapons.add_turret(turret)
    attacker.add_component(weapons)

    target = MockUnit()
    target.id = 200
    target.position = Position(50, 0)
    target.current_hit_points = 100
    target.max_hit_points = 100
    return attacker, target, weapons, turret


def _set_current_order(commander, order):
    order.status = OrderStatus.IN_PROGRESS
    commander.current_order = order


def test_turrets_stop_when_attack_is_replaced_by_move():
    attacker, target, weapons, turret = _combatants()
    commander = attacker.commander_component

    attack = AttackOrder(attacker, {"target_unit_id": target.id})
    _set_current_order(commander, attack)
    weapons.set_target(target)
    weapons.update(None)
    assert target.current_hit_points == 90

    turret.current_cooldown = 0
    commander.clear_orders()
    move = Order(attacker, OrderType.MOVE)
    commander.add_order(move)
    assert commander.current_order is move
    assert turret.target is None

    # Even a stale target restored by another caller cannot bypass current-order authority.
    weapons.set_target(target)
    weapons.update(None)
    assert target.current_hit_points == 90
    assert turret.target is None

    turret.current_cooldown = 2
    weapons.update(None)
    assert turret.current_cooldown == 1


def test_queued_attack_does_not_authorize_turret_fire():
    attacker, target, weapons, turret = _combatants()
    commander = attacker.commander_component

    move = Order(attacker, OrderType.MOVE)
    commander.add_order(move)
    commander.add_order(AttackOrder(attacker, {"target_unit_id": target.id}))
    weapons.set_target(target)

    weapons.update(None)

    assert commander.current_order is move
    assert len(commander.orders_queue) == 1
    assert target.current_hit_points == 100
    assert turret.target is None


def test_direct_attack_authorizes_fire_while_approach_move_is_active():
    attacker, target, weapons, _ = _combatants()
    commander = attacker.commander_component
    attack = AttackOrder(attacker, {"target_unit_id": target.id})
    attack.status = OrderStatus.IN_PROGRESS
    approach = Order(attacker, OrderType.MOVE, parent_order=attack)
    approach.status = OrderStatus.IN_PROGRESS
    attack.add_sub_order(approach)
    commander.current_order = attack
    weapons.set_target(target)

    weapons.update(None)

    assert commander.get_active_attack_order() is attack
    assert target.current_hit_points == 90


@pytest.mark.parametrize(
    "parent_order_type",
    [OrderType.PATROL, OrderType.PROTECT, OrderType.DEFEND],
)
def test_automated_combat_authorizes_active_front_attack_sub_order(parent_order_type):
    attacker, target, weapons, _ = _combatants()
    commander = attacker.commander_component
    parent = Order(attacker, parent_order_type)
    parent.status = OrderStatus.IN_PROGRESS
    attack = AttackOrder(attacker, {"target_unit_id": target.id}, parent_order=parent)
    attack.status = OrderStatus.IN_PROGRESS
    parent.add_sub_order(attack)
    commander.current_order = parent
    weapons.set_target(target)

    weapons.update(None)

    assert commander.get_active_attack_order() is attack
    assert target.current_hit_points == 90


def test_active_attack_cannot_fire_at_a_different_cached_target():
    attacker, target, weapons, turret = _combatants()
    authorized_target = MockUnit()
    authorized_target.id = 300
    commander = attacker.commander_component
    attack = AttackOrder(attacker, {"target_unit_id": authorized_target.id})
    _set_current_order(commander, attack)
    weapons.set_target(target)

    weapons.update(None)

    assert target.current_hit_points == 100
    assert turret.target is None
