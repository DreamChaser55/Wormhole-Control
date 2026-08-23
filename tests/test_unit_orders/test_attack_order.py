from unittest.mock import MagicMock
from geometry import Position
from unit_orders import OrderStatus, OrderType, AttackOrder
from unit_components import Engines, Hyperdrive, HyperdriveType, Weapons
from tests.test_unit_components import MockUnit


def test_attack_order():
    unit = MockUnit()
    weapons = MagicMock()
    unit.components[Weapons] = weapons
    
    target = MockUnit()
    unit.game.galaxy.get_unit_by_id.return_value = target
    
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
    
    order.execute(MagicMock())
    weapons.set_target.assert_called_once_with(target, None)
    # Should not spawn movement orders since in range
    assert len(order.sub_orders) == 0


def test_attack_order_pursuit():
    unit = MockUnit()
    weapons = MagicMock()
    unit.components[Weapons] = weapons
    
    # Add engines and hyperdrive to allow route planning and hex jumps
    engines = Engines(unit, speed=100.0)
    unit.add_component(engines)
    hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=5)
    unit.add_component(hd)
    
    target = MockUnit()
    target.id = 456
    target.name = "TargetUnit"
    
    galaxy = MagicMock()
    unit.game.galaxy = galaxy
    galaxy.get_unit_by_id.return_value = target
    
    # Mock system hexes to allow pathfinding
    mock_hex = MagicMock()
    mock_hex.get_all_inhibition_zones.return_value = []
    galaxy.systems = {"Sol": MagicMock()}
    galaxy.systems["Sol"].hexes = {
        (0, 0): mock_hex,
        (0, 1): mock_hex
    }
    
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
    assert new_move_sub.order_id != move_sub.order_id
    assert new_move_sub.status == OrderStatus.IN_PROGRESS
    assert new_move_sub.parameters["destination_position"] == Position(105.0, 0.0)
    
    # 4. Target jumps to a different hex
    target.in_hex = (0, 1)
    order.update(galaxy)
    
    assert len(order.sub_orders) == 1
    hex_jump_move_sub = order.sub_orders[0]
    assert hex_jump_move_sub.order_id != new_move_sub.order_id
    assert hex_jump_move_sub.status == OrderStatus.IN_PROGRESS
    assert hex_jump_move_sub.parameters["destination_hex_coord"] == (0, 1)
    
    # 5. Target moves back within range (attacker is at (0, 0), target moves to (20, 0) in (0, 0))
    target.in_hex = (0, 0)
    target.position = Position(20, 0)
    order.update(galaxy)
    
    # The movement sub-order should be cancelled and popped
    assert len(order.sub_orders) == 0
