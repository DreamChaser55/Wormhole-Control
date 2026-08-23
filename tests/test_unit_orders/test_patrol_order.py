from unittest.mock import MagicMock
from geometry import Position
from unit_orders import OrderStatus, OrderType, PatrolOrder
from unit_components import Engines, Weapons, Turret, TurretType, TurretVariant
from constants import HullSize
from tests.test_unit_components import MockUnit


def test_patrol_order_movement_loop():
    unit = MockUnit()
    engines = Engines(unit, speed=50.0)
    unit.add_component(engines)

    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(10, 10)

    patrol_order = PatrolOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(100, 10)
    })

    galaxy = MagicMock()
    mock_hex = MagicMock()
    mock_hex.get_all_inhibition_zones.return_value = []
    mock_sys = MagicMock()
    mock_sys.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_sys}

    patrol_order.execute(galaxy)

    assert patrol_order.status == OrderStatus.IN_PROGRESS
    assert patrol_order.patrol_phase == "TO_TARGET"
    assert patrol_order.start_position == Position(10, 10)
    
    # Active suborder is MoveOrder to (100, 10)
    assert len(patrol_order.sub_orders) == 1
    move_sub = patrol_order.sub_orders[0]
    assert move_sub.order_type == OrderType.MOVE
    assert move_sub.parameters["destination_position"] == Position(100, 10)

    # Complete the MoveOrder sub-order
    move_sub.status = OrderStatus.COMPLETED
    # Clear sub_orders of MoveOrder (simulate all completed)
    move_sub.sub_orders.clear()
    
    patrol_order.update(galaxy)
    
    # Phase should transition to TO_START and spawn MoveOrder to start (10, 10)
    assert patrol_order.patrol_phase == "TO_START"
    assert len(patrol_order.sub_orders) == 1
    move_sub = patrol_order.sub_orders[0]
    assert move_sub.parameters["destination_position"] == Position(10, 10)

    # Complete returning to start
    move_sub.status = OrderStatus.COMPLETED
    move_sub.sub_orders.clear()

    patrol_order.update(galaxy)

    # Phase should transition back to TO_TARGET and spawn MoveOrder to (100, 10)
    assert patrol_order.patrol_phase == "TO_TARGET"
    assert len(patrol_order.sub_orders) == 1
    move_sub = patrol_order.sub_orders[0]
    assert move_sub.parameters["destination_position"] == Position(100, 10)


def test_patrol_order_multiple_waypoints():
    unit = MockUnit()
    engines = Engines(unit, speed=50.0)
    unit.add_component(engines)

    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(10, 10)

    patrol_order = PatrolOrder(unit, {
        "waypoints": [
            {
                "system_name": "Sol",
                "hex_coord": (0, 0),
                "position": Position(100, 10)
            },
            {
                "system_name": "Sol",
                "hex_coord": (0, 0),
                "position": Position(200, 10)
            }
        ]
    })

    galaxy = MagicMock()
    mock_hex = MagicMock()
    mock_hex.get_all_inhibition_zones.return_value = []
    mock_sys = MagicMock()
    mock_sys.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_sys}

    patrol_order.execute(galaxy)

    # Check initially moving to WP1 (index 0)
    assert patrol_order.status == OrderStatus.IN_PROGRESS
    assert patrol_order.current_waypoint_index == 0
    assert patrol_order.patrol_phase == "TO_TARGET"
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].parameters["destination_position"] == Position(100, 10)

    # Complete move to WP1
    patrol_order.sub_orders[0].status = OrderStatus.COMPLETED
    patrol_order.sub_orders[0].sub_orders.clear()
    patrol_order.update(galaxy)

    # Should transition to WP2 (index 1)
    assert patrol_order.current_waypoint_index == 1
    assert patrol_order.patrol_phase == "TO_TARGET"
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].parameters["destination_position"] == Position(200, 10)

    # Complete move to WP2
    patrol_order.sub_orders[0].status = OrderStatus.COMPLETED
    patrol_order.sub_orders[0].sub_orders.clear()
    patrol_order.update(galaxy)

    # Should transition to Start position (index 2)
    assert patrol_order.current_waypoint_index == 2
    assert patrol_order.patrol_phase == "TO_START"
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].parameters["destination_position"] == Position(10, 10)

    # Complete returning to start
    patrol_order.sub_orders[0].status = OrderStatus.COMPLETED
    patrol_order.sub_orders[0].sub_orders.clear()
    patrol_order.update(galaxy)

    # Should loop back to WP1 (index 0)
    assert patrol_order.current_waypoint_index == 0
    assert patrol_order.patrol_phase == "TO_TARGET"
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].parameters["destination_position"] == Position(100, 10)

    # Test dynamic add_waypoint while moving to WP1 (index 0). Add WP3.
    patrol_order.add_waypoint("Sol", (0, 0), Position(300, 10))
    assert patrol_order.current_waypoint_index == 0
    
    # Complete move to WP1
    patrol_order.sub_orders[0].status = OrderStatus.COMPLETED
    patrol_order.sub_orders[0].sub_orders.clear()
    patrol_order.update(galaxy)
    
    # Next should be WP2
    assert patrol_order.current_waypoint_index == 1

    # Complete move to WP2
    patrol_order.sub_orders[0].status = OrderStatus.COMPLETED
    patrol_order.sub_orders[0].sub_orders.clear()
    patrol_order.update(galaxy)
    
    # Next should be WP3 (the new one)
    assert patrol_order.current_waypoint_index == 2
    assert patrol_order.sub_orders[0].parameters["destination_position"] == Position(300, 10)

    # Complete move to WP3
    patrol_order.sub_orders[0].status = OrderStatus.COMPLETED
    patrol_order.sub_orders[0].sub_orders.clear()
    patrol_order.update(galaxy)
    
    # Next should be Start (index 3)
    assert patrol_order.current_waypoint_index == 3
    assert patrol_order.sub_orders[0].parameters["destination_position"] == Position(10, 10)

    # Test dynamic add_waypoint while moving to Start (current_waypoint_index is 3, which is len(waypoints))
    # We add WP4. Length of waypoints becomes 4.
    # Index should adjust to 4.
    patrol_order.add_waypoint("Sol", (0, 0), Position(400, 10))
    assert patrol_order.current_waypoint_index == 4

    # Complete move to Start
    patrol_order.sub_orders[0].status = OrderStatus.COMPLETED
    patrol_order.sub_orders[0].sub_orders.clear()
    patrol_order.update(galaxy)

    # Should loop back to WP1 (index 0)
    assert patrol_order.current_waypoint_index == 0


def test_patrol_order_combat_engagement_and_resumption():
    unit = MockUnit()
    engines = Engines(unit, speed=50.0)
    unit.add_component(engines)

    weapons = Weapons(unit)
    turret = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=10,
        range=100.0,
        cooldown=2,
        parent_unit=unit
    )
    weapons.add_turret(turret)
    unit.add_component(weapons)

    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)

    enemy = MockUnit()
    enemy.id = 999
    enemy.name = "Enemy Ship"
    enemy.owner.id = unit.owner.id + 1  # Make it an enemy
    enemy.in_system = "Sol"
    enemy.in_hex = (0, 0)
    enemy.position = Position(150, 0) # Out of turret range of 100

    patrol_order = PatrolOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(200, 0)
    })

    galaxy = MagicMock()
    mock_hex = MagicMock()
    mock_hex.units = [unit, enemy]
    mock_hex.get_all_inhibition_zones.return_value = []
    
    mock_sys = MagicMock()
    mock_sys.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_sys}
    
    galaxy.get_unit_by_id.return_value = enemy
    unit.game.galaxy = galaxy

    patrol_order.execute(galaxy)

    # Initially, active suborder is MoveOrder
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].order_type == OrderType.MOVE

    # 1. Update when enemy is out of range
    patrol_order.update(galaxy)
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].order_type == OrderType.MOVE

    # 2. Move enemy within turret range (50, 0)
    enemy.position = Position(50, 0)
    patrol_order.update(galaxy)

    # Active order should now be AttackOrder
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].order_type == OrderType.ATTACK
    assert patrol_order.sub_orders[0].parameters["target_unit_id"] == enemy.id

    # 3. Simulate target fleeing to another hex
    enemy.in_hex = (0, 1)
    mock_hex.units = [unit]
    patrol_order.update(galaxy)

    # AttackOrder should cancel and patrol should resume
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].order_type == OrderType.MOVE

    # 4. Move enemy back to range (50, 0) and in hex (0,0)
    enemy.in_hex = (0, 0)
    mock_hex.units = [unit, enemy]
    patrol_order.update(galaxy)
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].order_type == OrderType.ATTACK

    # 5. Simulate enemy target destroyed
    enemy.current_hit_points = 0
    patrol_order.update(galaxy)

    # AttackOrder should clear and patrol should resume
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].order_type == OrderType.MOVE


def test_patrol_order_combat_engagement_strikecraft():
    unit = MockUnit()
    engines = Engines(unit, speed=50.0)
    unit.add_component(engines)

    # Standard turret: cannot target strikecraft
    weapons = Weapons(unit)
    turret = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=10,
        range=100.0,
        cooldown=2,
        parent_unit=unit,
        variant=TurretVariant.STANDARD
    )
    weapons.add_turret(turret)
    unit.add_component(weapons)

    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)

    # Enemy is a strikecraft wing and is close (50, 0)
    enemy = MockUnit()
    enemy.id = 999
    enemy.name = "Enemy Strikecraft"
    enemy.hull_size = HullSize.STRIKECRAFT_WING
    enemy.owner.id = unit.owner.id + 1  # Make it an enemy
    enemy.in_system = "Sol"
    enemy.in_hex = (0, 0)
    enemy.position = Position(50, 0)

    patrol_order = PatrolOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(200, 0)
    })

    galaxy = MagicMock()
    mock_hex = MagicMock()
    mock_hex.units = [unit, enemy]
    mock_hex.get_all_inhibition_zones.return_value = []
    
    mock_sys = MagicMock()
    mock_sys.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_sys}
    
    galaxy.get_unit_by_id.return_value = enemy
    unit.game.galaxy = galaxy

    patrol_order.execute(galaxy)

    # 1. Update with standard turret: should NOT engage strikecraft, active suborder remains MOVE
    patrol_order.update(galaxy)
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].order_type == OrderType.MOVE

    # 2. Swap standard turret for anti-strikecraft turret
    weapons.turrets.clear()
    turret_as = Turret(
        turret_type=TurretType.MASS_DRIVER,
        damage=10,
        range=100.0,
        cooldown=2,
        parent_unit=unit,
        variant=TurretVariant.ANTI_STRIKECRAFT
    )
    weapons.add_turret(turret_as)

    # 3. Update with anti-strikecraft turret: should engage strikecraft
    patrol_order.update(galaxy)
    assert len(patrol_order.sub_orders) == 1
    assert patrol_order.sub_orders[0].order_type == OrderType.ATTACK
