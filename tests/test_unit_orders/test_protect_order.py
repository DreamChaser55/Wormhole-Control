from unittest.mock import MagicMock
from geometry import Position
from unit_orders import OrderStatus, OrderType, ProtectOrder
from unit_components import Commander, Engines, Weapons, Turret, TurretType
from tests.test_unit_components import MockUnit, MockPlayer


def test_protect_order_validation():
    protector = MockUnit()
    protector.add_component(Commander(protector))
    
    # 1. Target doesn't exist
    order_no_target = ProtectOrder(protector, {"target_unit_id": 999})
    galaxy = MagicMock()
    galaxy.get_unit_by_id.return_value = None
    protector.game.galaxy = galaxy
    order_no_target.execute(galaxy)
    assert order_no_target.status == OrderStatus.FAILED
    
    # Setup target
    target = MockUnit()
    target.id = 123
    target.name = "TargetUnit"
    target.owner = MockPlayer("Player1")
    galaxy.get_unit_by_id.return_value = target
    
    # 2. Target hostile (protector belongs to Player2)
    protector.owner = MockPlayer("Player2")
    order_hostile = ProtectOrder(protector, {"target_unit_id": 123})
    order_hostile.execute(galaxy)
    assert order_hostile.status == OrderStatus.FAILED
    
    # 3. Target friendly (both belong to Player1)
    protector.owner = target.owner
    order_friendly = ProtectOrder(protector, {"target_unit_id": 123})
    order_friendly.execute(galaxy)
    assert order_friendly.status == OrderStatus.IN_PROGRESS


def test_protect_order_follow_movement():
    protector = MockUnit()
    protector.name = "Protector"
    protector.add_component(Commander(protector))
    engines = Engines(protector, speed=50.0)
    protector.add_component(engines)
    protector.in_system = "Sol"
    protector.in_hex = (0, 0)
    protector.position = Position(10, 10)
    
    target = MockUnit()
    target.id = 123
    target.name = "TargetUnit"
    target.owner = MockPlayer("Player1")
    target.in_system = "Sol"
    target.in_hex = (0, 0)
    target.position = Position(100, 10)
    
    protector.owner = target.owner
    
    galaxy = MagicMock()
    protector.game.galaxy = galaxy
    mock_hex = MagicMock()
    mock_hex.units = [protector, target]
    mock_hex.get_all_inhibition_zones.return_value = []
    mock_sys = MagicMock()
    mock_sys.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_sys}
    galaxy.get_unit_by_id.return_value = target
    
    order = ProtectOrder(protector, {"target_unit_id": target.id})
    order.execute(galaxy)
    order.update(galaxy)
    
    # Should spawn a follow MoveOrder 30 logical units short of the protected unit.
    assert len(order.sub_orders) == 1
    move_sub = order.sub_orders[0]
    assert move_sub.order_type == OrderType.MOVE
    assert move_sub.parameters["destination_position"] == Position(70, 10)
    
    # Simulate target moving to (150, 10)
    target.position = Position(150, 10)
    order.update(galaxy)
    
    # Since the target moved, recalculate the 30-logical-unit standoff point.
    assert len(order.sub_orders) == 1
    move_sub = order.sub_orders[0]
    assert move_sub.parameters["destination_position"] == Position(120, 10)
    
    # Simulate protector getting close (distance <= 30.0)
    protector.position = Position(130, 10)
    # The sub-order might still be in progress, updating should cancel it since we are close
    order.update(galaxy)
    assert len(order.sub_orders) == 0
    assert engines.move_target is None


def test_protect_order_combat_engagement():
    protector = MockUnit()
    protector.name = "Protector"
    protector.add_component(Commander(protector))
    engines = Engines(protector, speed=50.0)
    protector.add_component(engines)
    
    weapons = Weapons(protector)
    # Give protector a mock turret with range 100.0
    turret = Turret(turret_type=TurretType.MASS_DRIVER, damage=10, range=100.0, cooldown=1, parent_unit=protector)
    weapons.add_turret(turret)
    protector.add_component(weapons)
    
    protector.in_system = "Sol"
    protector.in_hex = (0, 0)
    protector.position = Position(10, 10)
    
    target = MockUnit()
    target.id = 123
    target.name = "TargetUnit"
    target.owner = MockPlayer("Player1")
    target.in_system = "Sol"
    target.in_hex = (0, 0)
    target.position = Position(50, 10)
    
    protector.owner = target.owner
    
    enemy = MockUnit()
    enemy.id = 666
    enemy.name = "Enemy"
    enemy.owner = MockPlayer("Player2")
    enemy.in_system = "Sol"
    enemy.in_hex = (0, 0)
    enemy.position = Position(80, 10) # within 150.0 detection range of target/protector
    
    galaxy = MagicMock()
    protector.game.galaxy = galaxy
    mock_hex = MagicMock()
    mock_hex.units = [protector, target, enemy]
    mock_hex.get_all_inhibition_zones.return_value = []
    mock_sys = MagicMock()
    mock_sys.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_sys}
    galaxy.get_unit_by_id.side_effect = lambda uid: {123: target, 666: enemy}.get(uid)
    
    order = ProtectOrder(protector, {"target_unit_id": target.id})
    order.execute(galaxy)
    
    # First update: enemy is close, should spawn AttackOrder (cancelling move)
    order.update(galaxy)
    assert len(order.sub_orders) == 1
    assert order.sub_orders[0].order_type == OrderType.ATTACK
    assert order.sub_orders[0].parameters["target_unit_id"] == enemy.id
    
    # Complete AttackOrder by destroying enemy (HP = 0)
    enemy.current_hit_points = 0
    order.update(galaxy)
    
    # Attack sub-order should be cleared, and follow MoveOrder to target should spawn
    assert len(order.sub_orders) == 1
    assert order.sub_orders[0].order_type == OrderType.MOVE
    assert order.sub_orders[0].parameters["destination_position"] == Position(20, 10)


def test_protect_order_target_range_limit():
    protector = MockUnit()
    protector.name = "Protector"
    protector.add_component(Commander(protector))
    engines = Engines(protector, speed=50.0)
    protector.add_component(engines)
    
    weapons = Weapons(protector)
    # Give protector a mock turret with range 50.0
    turret = Turret(turret_type=TurretType.MASS_DRIVER, damage=10, range=50.0, cooldown=1, parent_unit=protector)
    weapons.add_turret(turret)
    protector.add_component(weapons)
    
    protector.in_system = "Sol"
    protector.in_hex = (0, 0)
    protector.position = Position(100, 100)
    
    target = MockUnit()
    target.id = 123
    target.name = "TargetUnit"
    target.owner = MockPlayer("Player1")
    target.in_system = "Sol"
    target.in_hex = (0, 0)
    target.position = Position(100, 100)
    
    protector.owner = target.owner
    
    # Enemy 1: distance to target is 800.0 (within 1000.0, but outside protector turret range 50.0)
    enemy_near = MockUnit()
    enemy_near.id = 111
    enemy_near.name = "EnemyNear"
    enemy_near.owner = MockPlayer("Player2")
    enemy_near.in_system = "Sol"
    enemy_near.in_hex = (0, 0)
    enemy_near.position = Position(100, 900)
    
    # Enemy 2: distance to target is 1100.0 (outside 1000.0)
    enemy_far = MockUnit()
    enemy_far.id = 222
    enemy_far.name = "EnemyFar"
    enemy_far.owner = MockPlayer("Player2")
    enemy_far.in_system = "Sol"
    enemy_far.in_hex = (0, 0)
    enemy_far.position = Position(100, 1200)
    
    galaxy = MagicMock()
    protector.game.galaxy = galaxy
    mock_hex = MagicMock()
    mock_hex.units = [protector, target, enemy_near, enemy_far]
    mock_hex.get_all_inhibition_zones.return_value = []
    mock_sys = MagicMock()
    mock_sys.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_sys}
    galaxy.get_unit_by_id.side_effect = lambda uid: {123: target, 111: enemy_near, 222: enemy_far}.get(uid)
    
    order = ProtectOrder(protector, {"target_unit_id": target.id})
    order.execute(galaxy)
    
    # First update: only enemy_near should be targeted
    order.update(galaxy)
    assert len(order.sub_orders) == 1
    assert order.sub_orders[0].order_type == OrderType.ATTACK
    assert order.sub_orders[0].parameters["target_unit_id"] == enemy_near.id
    
    # Move enemy_near out of 1000.0 range (distance 1100.0)
    enemy_near.position = Position(100, 1200)
    order.update(galaxy)
    
    # Attack sub-order should be cleared (cancelled)
    assert len(order.sub_orders) == 0 or order.sub_orders[0].order_type != OrderType.ATTACK
