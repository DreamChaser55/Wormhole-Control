import pytest
from unittest.mock import MagicMock
from geometry import Position, Circle
from unit_orders import (
    OrderStatus, OrderType, ReachWaypointOrder, MoveOrder, 
    ToggleInhibitorOrder, AttackOrder, ColonizeOrder, LoadColonistsOrder
)
from unit_components import Engines, Hyperdrive, HyperdriveType, Weapons, ColonyComponent, HyperspaceInhibitionFieldEmitter
from tests.test_unit_components import MockUnit, MockPlayer

def test_reach_waypoint_order_validation():
    unit = MockUnit()
    # Missing/None parameters -> FAILED
    order = ReachWaypointOrder(unit, {
        "destination_system_name": None,
        "destination_hex_coord": None,
        "destination_position": None
    })
    order.execute(MagicMock())
    assert order.status == OrderStatus.FAILED


def test_reach_waypoint_order_sublight():
    unit = MockUnit()
    engines = Engines(unit, speed=100.0)
    unit.add_component(engines)
    
    dest_pos = Position(10, 20)
    order = ReachWaypointOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": dest_pos
    })
    
    order.execute(MagicMock())
    assert order.status == OrderStatus.IN_PROGRESS
    assert engines.move_target == dest_pos

def test_reach_waypoint_order_hex_jump():
    unit = MockUnit()
    hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC)
    unit.add_component(hd)
    
    dest_pos = Position(0, 0)
    order = ReachWaypointOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 1),
        "destination_position": dest_pos
    })
    
    order.execute(MagicMock())
    assert order.status == OrderStatus.IN_PROGRESS
    assert hd.hex_jump_target == ((0, 1), dest_pos)

def test_move_order_plan_route_same_hex():
    unit = MockUnit()
    engines = Engines(unit, speed=50.0)
    unit.add_component(engines)
    
    order = MoveOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(10, 0)
    })
    
    galaxy = MagicMock()
    order.execute(galaxy)
    
    assert len(order.sub_orders) == 1
    sub = order.sub_orders[0]
    assert sub.order_type == OrderType.REACH_WAYPOINT
    assert sub.parameters["destination_position"] == Position(10, 0)

def test_move_order_plan_route_hex_jump_within_range():
    unit = MockUnit()
    hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=5)
    unit.add_component(hd)
    
    order = MoveOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 2),
        "destination_position": Position(0, 0)
    })
    
    mock_hex = MagicMock()
    mock_hex.get_all_inhibition_zones.return_value = []
    
    galaxy = MagicMock()
    galaxy.systems = {"Sol": MagicMock()}
    galaxy.systems["Sol"].hexes = {(0, 2): mock_hex}
    
    order.execute(galaxy)
    
    assert len(order.sub_orders) == 1
    sub = order.sub_orders[0]
    assert sub.order_type == OrderType.REACH_WAYPOINT
    assert sub.parameters["destination_hex_coord"] == (0, 2)

def test_move_order_plan_route_multi_stage_hex_jump():
    unit = MockUnit()
    hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=2)
    unit.add_component(hd)
    
    order = MoveOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 5),
        "destination_position": Position(0, 0)
    })
    
    mock_hex = MagicMock()
    mock_hex.get_all_inhibition_zones.return_value = []
    
    galaxy = MagicMock()
    galaxy.systems = {"Sol": MagicMock()}
    # Populate the intermediate hexes in system map
    galaxy.systems["Sol"].hexes = {
        (0, 1): mock_hex,
        (0, 2): mock_hex,
        (0, 3): mock_hex,
        (0, 4): mock_hex,
        (0, 5): mock_hex
    }
    
    order.execute(galaxy)
    # The jump from (0,0) to (0,5) of range 2 should result in 3 jumps:
    # (0,2), (0,3), and (0,5)
    assert len(order.sub_orders) == 3
    assert order.sub_orders[0].parameters["destination_hex_coord"] == (0, 2)
    assert order.sub_orders[1].parameters["destination_hex_coord"] == (0, 3)
    assert order.sub_orders[2].parameters["destination_hex_coord"] == (0, 5)

def test_toggle_inhibitor_order():
    unit = MockUnit()
    emitter = MagicMock()
    emitter.radius = 100.0
    unit.components[HyperspaceInhibitionFieldEmitter] = emitter
    
    order = ToggleInhibitorOrder(unit, {"turn_on": True})
    
    # Mock system structures
    mock_hex = MagicMock()
    mock_hex.boundary_circle = Circle(Position(0, 0), 500.0)
    mock_hex.dynamic_inhibition_zones = {}
    mock_hex.get_all_inhibition_zones.return_value = []
    
    galaxy = MagicMock()
    galaxy.systems = {"Sol": MagicMock()}
    galaxy.systems["Sol"].hexes = {(0, 0): mock_hex}
    
    order.execute(galaxy)
    assert order.status == OrderStatus.COMPLETED
    emitter.turn_on.assert_called_once()
    assert unit.id in mock_hex.dynamic_inhibition_zones

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
    weapons.set_target.assert_called_once_with(target)
    # Should not spawn movement orders since in range
    assert len(order.sub_orders) == 0

def test_colonize_order():
    unit = MockUnit()
    colony = MagicMock()
    colony.population_cargo = 50
    unit.components[ColonyComponent] = colony
    
    planet = MagicMock()
    planet.in_system = "Sol"
    planet.in_hex = (0, 0)
    planet.position = Position(0, 0)
    planet.owner = None
    
    galaxy = MagicMock()
    galaxy.get_celestial_body_by_id.return_value = planet
    
    order = ColonizeOrder(unit, {"target_id": 999})
    
    # Unit is at location
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    
    colony.unload_population.return_value = True
    
    order.execute(galaxy)
    assert order.status == OrderStatus.COMPLETED
    colony.unload_population.assert_called_once_with(planet, 50)
