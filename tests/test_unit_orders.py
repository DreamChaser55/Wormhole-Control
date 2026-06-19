import pytest
from unittest.mock import MagicMock
from geometry import Position, Circle
from unit_orders import (
    OrderStatus, OrderType, ReachWaypointOrder, MoveOrder, 
    ToggleInhibitorOrder, AttackOrder, ColonizeOrder, LoadColonistsOrder,
    ConstructOrder, Order, RepairOrder, MineOrder, UnloadResourcesOrder
)
from unit_components import (
    Engines, Hyperdrive, HyperdriveType, Weapons, ColonyComponent, 
    HyperspaceInhibitionFieldEmitter, Constructor, RepairComponent,
    MiningComponent, MetalRefineryComponent, CrystalRefineryComponent,
    BuildableUnit
)
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
    weapons.set_target.assert_called_once_with(target, None)
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


def test_move_order_inter_system_routing():
    # Setup unit with Hyperdrive and Engines in Sol
    unit = MockUnit()
    hd = Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5)
    engines = Engines(unit, speed=50.0)
    unit.add_component(hd)
    unit.add_component(engines)

    # Destination is in Vega, hex (0, 0), Position(10, 10)
    dest_system = "Vega"
    dest_hex = (0, 0)
    dest_pos = Position(10, 10)

    # Mock galaxy structures and pathfinding
    galaxy = MagicMock()
    galaxy.system_graph = {"Sol": ["Vega"], "Vega": ["Sol"]}
    
    # We will simulate find_intersystem_path returning ["Sol", "Vega"]
    # and find_wormhole_to_system finding a wormhole in Sol at (1, 1), exit in Vega at (2, 2)
    wh_sol = MagicMock()
    wh_sol.id = 1
    wh_sol.in_system = "Sol"
    wh_sol.in_hex = (1, 1)
    wh_sol.position = Position(100, 100)
    wh_sol.exit_wormhole_id = 2
    wh_sol.name = "Wormhole-Sol"

    wh_vega = MagicMock()
    wh_vega.id = 2
    wh_vega.in_system = "Vega"
    wh_vega.in_hex = (2, 2)
    wh_vega.position = Position(200, 200)
    wh_vega.name = "Wormhole-Vega"

    galaxy.wormholes = {1: wh_sol, 2: wh_vega}
    
    # Mock systems map
    mock_sol_sys = MagicMock()
    mock_vega_sys = MagicMock()
    
    mock_sol_hex = MagicMock()
    mock_sol_hex.get_all_inhibition_zones.return_value = []
    
    mock_vega_hex = MagicMock()
    mock_vega_hex.get_all_inhibition_zones.return_value = []
    
    mock_sol_sys.hexes = {
        (0, 0): mock_sol_hex,
        (1, 1): mock_sol_hex,
    }
    mock_vega_sys.hexes = {
        (2, 2): mock_vega_hex,
        (0, 0): mock_vega_hex,
    }
    
    galaxy.systems = {"Sol": mock_sol_sys, "Vega": mock_vega_sys}

    order = MoveOrder(unit, {
        "destination_system_name": dest_system,
        "destination_hex_coord": dest_hex,
        "destination_position": dest_pos
    })

    # Mock find_intersystem_path to return the path ["Sol", "Vega"]
    from unittest.mock import patch
    with patch("unit_orders.find_intersystem_path", return_value=["Sol", "Vega"]), \
         patch.object(order, "find_wormhole_to_system", side_effect=lambda current, target, g: wh_sol if current == "Sol" else None):
        
        order.execute(galaxy)
        
        # Sub-orders expected:
        # 1. ReachWaypointOrder (hex jump) to Sol (1, 1) wormhole pos (100, 100)
        # 2. ReachWaypointOrder (wormhole jump) to Vega (2, 2) exit wh pos (200, 200)
        # 3. ReachWaypointOrder (hex jump) to Vega (0, 0) dest pos (10, 10)
        assert len(order.sub_orders) == 3
        
        assert order.sub_orders[0].parameters["destination_system_name"] == "Sol"
        assert order.sub_orders[0].parameters["destination_hex_coord"] == (1, 1)
        assert order.sub_orders[0].parameters["destination_position"] == Position(100, 100)
        
        assert order.sub_orders[1].parameters["destination_system_name"] == "Vega"
        assert order.sub_orders[1].parameters["destination_hex_coord"] == (2, 2)
        assert order.sub_orders[1].parameters["destination_position"] == Position(200, 200)
        
        assert order.sub_orders[2].parameters["destination_system_name"] == "Vega"
        assert order.sub_orders[2].parameters["destination_hex_coord"] == (0, 0)
        assert order.sub_orders[2].parameters["destination_position"] == Position(10, 10)


def test_move_order_inhibition_escape():
    # Setup unit with Hyperdrive in Sol at Position(10, 10)
    unit = MockUnit()
    unit.position = Position(10, 10)
    hd = Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5)
    unit.add_component(hd)

    # Destination is in Sol, different hex (0, 2)
    dest_system = "Sol"
    dest_hex = (0, 2)
    dest_pos = Position(0, 0)

    galaxy = MagicMock()
    
    # Setup inhibitor zone at current location
    # Inhibitor field: center (0,0), radius 20. Unit is at (10,10) which is inside since dist = sqrt(200) ~ 14.14 < 20
    current_hex_obj = MagicMock()
    inhibitor_zone = Circle(Position(0, 0), 20.0)
    current_hex_obj.get_all_inhibition_zones.return_value = [inhibitor_zone]

    dest_hex_obj = MagicMock()
    dest_hex_obj.get_all_inhibition_zones.return_value = []

    mock_sys = MagicMock()
    mock_sys.hexes = {
        (0, 0): current_hex_obj,
        (0, 2): dest_hex_obj
    }
    galaxy.systems = {"Sol": mock_sys}

    order = MoveOrder(unit, {
        "destination_system_name": dest_system,
        "destination_hex_coord": dest_hex,
        "destination_position": dest_pos
    })

    order.execute(galaxy)

    # We expect suborders:
    # 1. ReachWaypointOrder (sub-light escape move to edge of current hex's inhibition zone)
    # 2. ReachWaypointOrder (the actual hex jump to destination)
    assert len(order.sub_orders) == 2
    
    # Verify first sub-order is escape to edge
    escape_order = order.sub_orders[0]
    assert escape_order.parameters["destination_system_name"] == "Sol"
    assert escape_order.parameters["destination_hex_coord"] == (0, 0)
    # Closest point on circle edge from (10,10) with radius 20:
    # unit vector from (0,0) is (sqrt(2)/2, sqrt(2)/2) ~ (0.7071, 0.7071)
    # edge point = (20 * 0.7071, 20 * 0.7071) = (14.14, 14.14)
    assert abs(escape_order.parameters["destination_position"].x - 14.142) < 0.01
    assert abs(escape_order.parameters["destination_position"].y - 14.142) < 0.01

    # Verify second sub-order is the jump to destination
    jump_order = order.sub_orders[1]
    assert jump_order.parameters["destination_system_name"] == "Sol"
    assert jump_order.parameters["destination_hex_coord"] == (0, 2)
    assert jump_order.parameters["destination_position"] == dest_pos


def test_construct_order():
    # Setup unit and constructor component
    unit = MockUnit()
    constructor = Constructor(unit, hull_cost=10)
    unit.add_component(constructor)

    galaxy = MagicMock()
    
    # Mock player credits and matching owner ID
    player = MockPlayer()
    player.id = unit.owner.id
    player.credits = 500
    unit.game.players = [player]
    unit.owner = player

    buildable = BuildableUnit(unit_template_name="Station", time_to_build=3, cost_credits=300)
    constructor.buildable_units.append(buildable)

    # Valid order
    order = ConstructOrder(unit, {
        "unit_template_name": "Station",
        "target_position": Position(10, 10)
    })

    assert order.status == OrderStatus.PENDING

    # Execute
    order.execute(galaxy)

    assert order.status == OrderStatus.IN_PROGRESS
    assert player.credits == 200
    assert constructor.current_construction_target == ("Station", Position(10, 10))
    assert constructor.construction_progress == 0

    # Progress turn
    constructor.update(galaxy)
    assert constructor.construction_progress == 1
    order.update(galaxy)
    assert order.status == OrderStatus.IN_PROGRESS

    # Complete construction
    constructor.update(galaxy) # progress = 2
    constructor.update(galaxy) # progress = 3 -> completes
    assert constructor.current_construction_target is None

    # Check order completion
    order.update(galaxy)
    assert order.status == OrderStatus.COMPLETED

    # Cancellation refund
    player.credits = 500
    order_cancel = ConstructOrder(unit, {
        "unit_template_name": "Station",
        "target_position": Position(10, 10)
    })
    order_cancel.execute(galaxy)
    assert order_cancel.status == OrderStatus.IN_PROGRESS
    assert player.credits == 200
    assert constructor.current_construction_target == ("Station", Position(10, 10))

    order_cancel.cancel()
    assert order_cancel.status == OrderStatus.CANCELLED
    assert player.credits == 500
    assert constructor.current_construction_target is None

    # Insufficient credits case
    player.credits = 100
    order_fail = ConstructOrder(unit, {
        "unit_template_name": "Station",
        "target_position": Position(10, 10)
    })
    order_fail.execute(galaxy)
    assert order_fail.status == OrderStatus.FAILED
    assert player.credits == 100



def test_load_colonists_order():
    unit = MockUnit()
    colony = MagicMock()
    unit.components[ColonyComponent] = colony

    planet = MagicMock()
    planet.id = 999
    planet.in_system = "Sol"
    planet.in_hex = (0, 0)
    planet.position = Position(0, 0)

    galaxy = MagicMock()
    galaxy.get_celestial_body_by_id.return_value = planet

    # Case 1: Unit is at location and successfully loads colonists
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    colony.load_population.return_value = True

    order = LoadColonistsOrder(unit, {
        "target_id": 999,
        "amount": 50
    })

    order.execute(galaxy)
    assert order.status == OrderStatus.COMPLETED
    colony.load_population.assert_called_once_with(planet, 50)

    # Case 2: Unit is not at location, should spawn MoveOrder
    unit.in_system = "Vega"
    unit.in_hex = (1, 1)
    
    order_move = LoadColonistsOrder(unit, {
        "target_id": 999,
        "amount": 50
    })
    order_move.execute(galaxy)
    
    assert len(order_move.sub_orders) == 2
    assert order_move.sub_orders[0].order_type == OrderType.MOVE
    assert order_move.sub_orders[1].order_type == OrderType.LOAD_COLONISTS


def test_order_cancellation_cascade():
    unit = MockUnit()
    order = MoveOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(10, 10)
    })

    # Add a real sub-order to avoid logging/mock property issues
    sub_order = ReachWaypointOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(10, 10)
    })
    order.add_sub_order(sub_order)

    # Cancel parent order
    order.cancel()

    assert order.status == OrderStatus.CANCELLED
    assert sub_order.status == OrderStatus.CANCELLED


def test_repair_order():
    # Setup unit and repair component
    unit = MockUnit()
    repair_comp = RepairComponent(unit, repair_rate=10, repair_range=100.0, credit_cost_per_hp=1.0)
    unit.add_component(repair_comp)

    target = MockUnit()
    target.id = 999
    target.owner = unit.owner  # Friendly
    target.in_system = "Sol"
    target.in_hex = (0, 0)
    target.position = Position(0, 0)

    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(20, 0) # within 100 range

    galaxy = MagicMock()
    galaxy.get_unit_by_id.return_value = target
    unit.game.galaxy = galaxy

    order = RepairOrder(unit, {"target_unit_id": target.id})

    # Target is damaged
    target.take_damage(30)
    assert target.current_hit_points == 70

    # Execute repair order
    order.execute(galaxy)
    assert order.status == OrderStatus.IN_PROGRESS
    assert repair_comp.target == target
    assert len(order.sub_orders) == 0  # in range, no move needed

    # Test out of range case
    unit.position = Position(150, 0) # out of 100 range
    order_out_of_range = RepairOrder(unit, {"target_unit_id": target.id})
    order_out_of_range.execute(galaxy)

    # Should spawn MoveOrder and RepairOrder suborders
    assert len(order_out_of_range.sub_orders) == 2
    assert order_out_of_range.sub_orders[0].order_type == OrderType.MOVE
    assert order_out_of_range.sub_orders[1].order_type == OrderType.REPAIR


def test_mine_order():
    unit = MockUnit()
    mining_comp = MiningComponent(unit, mining_rate=10, max_cargo=50, mining_range=100.0)
    unit.add_component(mining_comp)
    
    target = MagicMock()
    target.id = 999
    target.name = "Asteroid 1"
    target.in_system = "Sol"
    target.in_hex = (0, 0)
    target.position = Position(0, 0)
    
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(50, 0) # within 100 range
    
    galaxy = MagicMock()
    galaxy.get_celestial_body_by_id.return_value = target
    
    order = MineOrder(unit, {"target_id": target.id})
    order.execute(galaxy)
    
    assert order.status == OrderStatus.IN_PROGRESS
    assert mining_comp.mining_target == target
    assert len(order.sub_orders) == 0
    
    # Test out of range
    unit.position = Position(200, 0)
    order_out_of_range = MineOrder(unit, {"target_id": target.id})
    order_out_of_range.execute(galaxy)
    
    assert len(order_out_of_range.sub_orders) == 2
    assert order_out_of_range.sub_orders[0].order_type == OrderType.MOVE
    assert order_out_of_range.sub_orders[1].order_type == OrderType.MINE


def test_unload_resources_order():
    unit = MockUnit()
    mining_comp = MiningComponent(unit, mining_rate=10, max_cargo=50, mining_range=100.0)
    mining_comp.raw_metal_cargo = 20
    unit.add_component(mining_comp)
    
    target = MockUnit()
    target.id = 999
    target.name = "Refinery Station"
    target.in_system = "Sol"
    target.in_hex = (0, 0)
    target.position = Position(0, 0)
    
    refinery_comp = MetalRefineryComponent(target, unload_range=300.0)
    target.add_component(refinery_comp)
    
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(50, 0) # within 300 range
    
    galaxy = MagicMock()
    galaxy.get_unit_by_id.return_value = target
    
    order = UnloadResourcesOrder(unit, {"target_unit_id": target.id})
    order.execute(galaxy)
    
    assert order.status == OrderStatus.COMPLETED
    assert mining_comp.raw_metal_cargo == 0
    assert target.owner.metal == 1000 + 20 # MockPlayer starts with 1000 metal
    
    # Test out of range
    unit.position = Position(400, 0)
    mining_comp.raw_metal_cargo = 20
    order_out_of_range = UnloadResourcesOrder(unit, {"target_unit_id": target.id})
    order_out_of_range.execute(galaxy)
    
    assert len(order_out_of_range.sub_orders) == 2
    assert order_out_of_range.sub_orders[0].order_type == OrderType.MOVE
    assert order_out_of_range.sub_orders[1].order_type == OrderType.UNLOAD_RESOURCES
