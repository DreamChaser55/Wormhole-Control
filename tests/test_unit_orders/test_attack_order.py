from unittest.mock import MagicMock
from geometry import Position
from unit_orders.base import OrderStatus, OrderType
from unit_orders.combat import AttackOrder
from unit_components.weapons import Weapons
from tests.support.combat import create_test_galaxy, create_combat_ship


def combatants():
    galaxy, owner, enemy = create_test_galaxy()
    unit = create_combat_ship(galaxy, owner, 'Attacker', (0, 0))
    target = create_combat_ship(galaxy, enemy, 'Target', (0, 0))
    weapons = MagicMock(hull_cost=0)
    unit.components[Weapons] = weapons
    return unit, target, galaxy, weapons


def test_attack_order():
    unit, target, galaxy, weapons = combatants()
    
    order = AttackOrder(unit, {"target_unit_id": target.id})
    
    # Target is in same hex and in range of turret
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    
    target.in_system = "Sol"
    target.in_hex = (0, 0)
    target.position = Position(20, 0)
    
    turret = MagicMock()
    turret.range = 50.0
    weapons.turrets = [turret]
    
    order.execute(galaxy)
    weapons.set_target.assert_called_once_with(target, None)
    # Should not spawn movement orders since in range
    assert len(order.sub_orders) == 0


def test_attack_order_pursuit():
    unit, target, galaxy, weapons = combatants()
    
    # Setup weapons and range
    turret = MagicMock()
    turret.range = 50.0
    weapons.turrets = [turret]

    
    # 1. Target starts in same hex and in range (distance 20.0 < 50.0)
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    
    target.in_system = "Sol"
    target.in_hex = (0, 0)
    target.position = Position(20, 0)
    
    order = AttackOrder(unit, {"target_unit_id": target.id})
    order.execute(galaxy)
    
    assert order.status == OrderStatus.IN_PROGRESS
    assert len(order.sub_orders) == 0
    weapons.set_target.assert_called_once_with(target, None)
    
    # 2. Target moves within same hex/system beyond range (distance 100.0 > 50.0)
    target.position = Position(100, 0)
    order.update(galaxy)
    
    # A MoveOrder should have been spawned and set to IN_PROGRESS
    assert len(order.sub_orders) == 1
    move_sub = order.sub_orders[0]
    assert move_sub.order_type == OrderType.MOVE
    assert move_sub.status == OrderStatus.IN_PROGRESS
    assert move_sub.parameters["destination_system_name"] == "Sol"
    assert move_sub.parameters["destination_hex_coord"] == (0, 0)
    # Target position should be: target_pos (100, 0) minus (min_turret_range - 5.0 = 45.0) along the vector from target to unit
    # Unit is at (0, 0), target is at (100, 0), direction from target to unit is (-1, 0)
    # destination = (100, 0) + (-1, 0) * 45.0 = (55, 0)
    assert move_sub.parameters["destination_position"] == Position(55.0, 0.0)
    
    # 3. Target moves again while MoveOrder is in progress (e.g. to (150, 0))
    target.position = Position(150, 0)
    order.update(galaxy)
    
    # The old move order should be cancelled and popped, and a new one spawned and set to IN_PROGRESS
    assert len(order.sub_orders) == 1
    new_move_sub = order.sub_orders[0]
    assert new_move_sub.local_order_id != move_sub.local_order_id
    assert new_move_sub.status == OrderStatus.IN_PROGRESS
    assert new_move_sub.parameters["destination_position"] == Position(105.0, 0.0)
    
    # 4. Target jumps to a different hex
    galaxy.systems['Sol'].hexes[(0, 0)].units.remove(target)
    target.in_hex = (0, 1)
    galaxy.systems['Sol'].hexes[(0, 1)].units.append(target)
    create_combat_ship(galaxy, unit.owner, 'Forward scout', (0, 1))
    order.update(galaxy)
    
    assert len(order.sub_orders) == 1
    hex_jump_move_sub = order.sub_orders[0]
    assert hex_jump_move_sub.local_order_id != new_move_sub.local_order_id
    assert hex_jump_move_sub.status == OrderStatus.IN_PROGRESS
    assert hex_jump_move_sub.parameters["destination_hex_coord"] == (0, 1)
    
    # 5. Target moves back within range (attacker is at (0, 0), target moves to (20, 0) in (0, 0))
    galaxy.systems['Sol'].hexes[(0, 1)].units.remove(target)
    target.in_hex = (0, 0)
    galaxy.systems['Sol'].hexes[(0, 0)].units.append(target)
    target.position = Position(20, 0)
    order.update(galaxy)
    
    # The movement sub-order should be cancelled and popped
    assert len(order.sub_orders) == 0
