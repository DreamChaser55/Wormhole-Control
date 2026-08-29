from unittest.mock import MagicMock
from geometry import Position
from unit_orders import OrderStatus, OrderType, DefendOrder
from unit_components import Commander, Engines, Weapons, Turret, TurretType, TurretVariant
from tests.test_unit_components import MockUnit, MockPlayer


def test_defend_order_travel_and_hold():
    defender = MockUnit()
    defender.name = "Defender"
    defender.add_component(Commander(defender))
    engines = Engines(defender, speed=50.0)
    defender.add_component(engines)
    defender.owner = MockPlayer("Player1")
    defender.in_system = "Sol"
    defender.in_hex = (0, 0)
    defender.position = Position(0, 0)

    galaxy = MagicMock()
    defender.game.galaxy = galaxy
    mock_hex = MagicMock()
    mock_hex.units = [defender]
    mock_hex.get_all_inhibition_zones.return_value = []
    mock_sys = MagicMock()
    mock_sys.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_sys}

    order = DefendOrder(
        defender,
        {
            "destination_system_name": "Sol",
            "destination_hex_coord": (0, 0),
            "destination_position": Position(100, 100),
            "guard_radius": 500.0,
        },
    )
    order.execute(galaxy)
    assert order.status == OrderStatus.IN_PROGRESS
    # Should spawn travel sub-order to (100, 100)
    assert len(order.sub_orders) == 1
    assert order.sub_orders[0].order_type == OrderType.MOVE

    # Defender moves close to guarded location (distance <= 30)
    defender.position = Position(90, 95)
    order.update(galaxy)
    assert len(order.sub_orders) == 0


def test_defend_order_combat_engagement_and_resume():
    player1 = MockPlayer("Player1")
    player2 = MockPlayer("Player2")

    defender = MockUnit()
    defender.name = "Defender"
    defender.owner = player1
    defender.add_component(Commander(defender))
    engines = Engines(defender, speed=50.0)
    defender.add_component(engines)

    weapons = Weapons(defender)
    turret = Turret(
        turret_type=TurretType.BEAM,
        damage=10.0,
        range=200.0,
        cooldown=1,
        parent_unit=defender,
        variant=TurretVariant.STANDARD,
    )
    weapons.turrets = [turret]
    defender.add_component(weapons)

    defender.in_system = "Sol"
    defender.in_hex = (0, 0)
    defender.position = Position(100, 100)

    enemy = MockUnit()
    enemy.id = 999
    enemy.name = "EnemyRaider"
    enemy.owner = player2
    enemy.current_hit_points = 50
    enemy.max_hit_points = 50
    enemy.in_system = "Sol"
    enemy.in_hex = (0, 0)
    enemy.position = Position(300, 100)  # 200 logical units from guarded position (inside 500-unit radius)

    galaxy = MagicMock()
    defender.game.galaxy = galaxy
    mock_hex = MagicMock()
    mock_hex.units = [defender, enemy]
    mock_hex.get_all_inhibition_zones.return_value = []
    mock_sys = MagicMock()
    mock_sys.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_sys}
    galaxy.get_unit_by_id.side_effect = lambda uid: enemy if uid == 999 else (defender if uid == defender.id else None)

    order = DefendOrder(
        defender,
        {
            "destination_system_name": "Sol",
            "destination_hex_coord": (0, 0),
            "destination_position": Position(100, 100),
            "guard_radius": 500.0,
        },
    )
    order.execute(galaxy)
    order.update(galaxy)

    # Should detect enemy within guard radius and spawn AttackOrder
    assert len(order.sub_orders) == 1
    assert order.sub_orders[0].order_type == OrderType.ATTACK
    assert order.sub_orders[0].parameters["target_unit_id"] == 999

    # Enemy destroyed
    enemy.current_hit_points = 0
    order.update(galaxy)

    # AttackOrder should clear and defender should resume defending
    assert len(order.sub_orders) == 0 or order.sub_orders[0].order_type == OrderType.MOVE


def test_defend_order_celestial_body_target():
    defender = MockUnit()
    defender.name = "Defender"
    defender.add_component(Commander(defender))
    defender.owner = MockPlayer("Player1")
    defender.in_system = "Sol"
    defender.in_hex = (0, 0)
    defender.position = Position(0, 0)

    planet = MagicMock()
    planet.id = 42
    planet.name = "Terra"
    planet.in_system = "Sol"
    planet.in_hex = (0, 1)
    planet.position = Position(200, 300)

    galaxy = MagicMock()
    defender.game.galaxy = galaxy
    galaxy.get_celestial_body_by_id.return_value = planet
    mock_hex = MagicMock()
    mock_hex.units = [defender]
    mock_hex.get_all_inhibition_zones.return_value = []
    mock_sys = MagicMock()
    mock_sys.hexes = {(0, 0): mock_hex, (0, 1): mock_hex}
    galaxy.systems = {"Sol": mock_sys}

    order = DefendOrder(defender, {"target_id": 42, "guard_radius": 800.0})
    order.execute(galaxy)

    assert order.status == OrderStatus.IN_PROGRESS
    assert len(order.sub_orders) == 1
    move_sub = order.sub_orders[0]
    assert move_sub.order_type == OrderType.MOVE
    assert move_sub.parameters["destination_hex_coord"] == (0, 1)
    assert move_sub.parameters["destination_position"] == Position(200, 300)
