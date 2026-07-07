import pytest
from unittest.mock import MagicMock
from geometry import Position, Circle
from unit_orders import (
    OrderStatus, OrderType, ReachWaypointOrder, MoveOrder, 
    ToggleInhibitorOrder, AttackOrder, ColonizeOrder, LoadColonistsOrder,
    ConstructOrder, Order, RepairOrder, MineOrder, UnloadResourcesOrder,
    PatrolOrder, ProtectOrder
)
from unit_components import (
    Engines, Hyperdrive, HyperdriveType, Weapons, ColonyComponent, 
    HyperspaceInhibitionFieldEmitter, Constructor, RepairComponent,
    MiningComponent, MetalRefineryComponent, CrystalRefineryComponent,
    BuildableUnit, Turret, TurretType, TurretVariant, Commander
)
from tests.test_unit_components import MockUnit, MockPlayer
from constants import HullSize

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
        "destination_position": Position(100, 100)
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
    assert order.sub_orders[0].parameters["destination_position"] == Position(0, 0)
    assert order.sub_orders[1].parameters["destination_hex_coord"] == (0, 3)
    assert order.sub_orders[1].parameters["destination_position"] == Position(0, 0)
    assert order.sub_orders[2].parameters["destination_hex_coord"] == (0, 5)
    assert order.sub_orders[2].parameters["destination_position"] == Position(100, 100)

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
    galaxy.system_graph = {"Sol": {"Vega": HullSize.HUGE}, "Vega": {"Sol": HullSize.HUGE}}
    
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
         patch.object(order, "find_wormhole_to_system", side_effect=lambda current, target, g, *args: wh_sol if current == "Sol" else None):
        
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
    from unit_templates import register_template, unregister_template
    
    register_template("Station", {
        "name": "Station",
        "hull_size": HullSize.MEDIUM,
        "build_time": 3,
        "build_cost": 300
    })

    try:
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
    finally:
        unregister_template("Station")
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


def test_unload_resources_matching_refinery():
    unit = MockUnit()
    mining_comp = MiningComponent(unit, mining_rate=10, max_cargo=100, mining_range=100.0)
    mining_comp.raw_metal_cargo = 30
    mining_comp.raw_crystal_cargo = 40
    unit.add_component(mining_comp)
    
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    
    # 1. Target with metal refinery only
    target_metal = MockUnit()
    target_metal.id = 901
    target_metal.name = "Metal Refinery Station"
    target_metal.in_system = "Sol"
    target_metal.in_hex = (0, 0)
    target_metal.position = Position(10, 0)
    target_metal.owner.metal = 1000
    target_metal.owner.crystal = 1000
    
    refinery_metal = MetalRefineryComponent(target_metal, unload_range=300.0)
    target_metal.add_component(refinery_metal)
    
    galaxy = MagicMock()
    galaxy.get_unit_by_id.side_effect = lambda uid: {901: target_metal}[uid]
    
    order = UnloadResourcesOrder(unit, {"target_unit_id": 901})
    order.execute(galaxy)
    
    assert order.status == OrderStatus.COMPLETED
    assert mining_comp.raw_metal_cargo == 0.0
    assert mining_comp.raw_crystal_cargo == 40.0 # Unmatching crystal stays
    assert target_metal.owner.metal == 1030
    assert target_metal.owner.crystal == 1000
    
    # 2. Target with crystal refinery only
    mining_comp.raw_metal_cargo = 30
    mining_comp.raw_crystal_cargo = 40
    
    target_crystal = MockUnit()
    target_crystal.id = 902
    target_crystal.name = "Crystal Refinery Station"
    target_crystal.in_system = "Sol"
    target_crystal.in_hex = (0, 0)
    target_crystal.position = Position(10, 0)
    target_crystal.owner.metal = 1000
    target_crystal.owner.crystal = 1000
    
    refinery_crystal = CrystalRefineryComponent(target_crystal, unload_range=300.0)
    target_crystal.add_component(refinery_crystal)
    
    galaxy.get_unit_by_id.side_effect = lambda uid: {902: target_crystal}[uid]
    
    order2 = UnloadResourcesOrder(unit, {"target_unit_id": 902})
    order2.execute(galaxy)
    
    assert order2.status == OrderStatus.COMPLETED
    assert mining_comp.raw_metal_cargo == 30.0 # Unmatching metal stays
    assert mining_comp.raw_crystal_cargo == 0.0
    assert target_crystal.owner.metal == 1000
    assert target_crystal.owner.crystal == 1040


def test_inter_system_jump_drive_type_validation():
    from unittest.mock import patch
    
    # Test ReachWaypointOrder inter-system jump with BASIC drive fails
    unit_basic = MockUnit()
    hd_basic = Hyperdrive(unit_basic, drive_type=HyperdriveType.BASIC)
    unit_basic.add_component(hd_basic)
    
    order_reach_basic = ReachWaypointOrder(unit_basic, {
        "destination_system_name": "Vega",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(0, 0)
    })
    
    galaxy = MagicMock()
    order_reach_basic.execute(galaxy)
    assert order_reach_basic.status == OrderStatus.FAILED

    # Test ReachWaypointOrder inter-system jump with ADVANCED drive starts/proceeds
    unit_adv = MockUnit()
    hd_adv = Hyperdrive(unit_adv, drive_type=HyperdriveType.ADVANCED)
    unit_adv.add_component(hd_adv)
    
    order_reach_adv = ReachWaypointOrder(unit_adv, {
        "destination_system_name": "Vega",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(0, 0)
    })
    
    # Mock find_wormhole_to_system
    wh = MagicMock()
    wh.exit_wormhole_id = 99
    wh.in_hex = (0, 0)
    wh.position = Position(0, 0)
    wh.name = "wh1"
    
    # Patch find_wormhole_to_system for test
    with patch.object(order_reach_adv, "find_wormhole_to_system", return_value=wh):
        order_reach_adv.execute(galaxy)
        assert order_reach_adv.status == OrderStatus.IN_PROGRESS
        assert hd_adv.wormhole_jump_target == wh

    # Test MoveOrder inter-system path planning with BASIC drive fails
    order_move_basic = MoveOrder(unit_basic, {
        "destination_system_name": "Vega",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(0, 0)
    })
    order_move_basic.plan_route(galaxy)
    assert order_move_basic.status == OrderStatus.FAILED


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


def test_order_formatting():
    from game import Game
    from unit_orders import (
        ConstructOrder, RepairOrder, DockOrder, DeployUnitOrder, DeployAllWingsOrder, UseAbilityOrder
    )

    class MockGame(Game):
        def __init__(self):
            self.galaxy = MagicMock()
            self.sidebar_needs_update = False

    game = MockGame()
    unit = MockUnit()
    unit.game = game
    unit.hangar_component = None
    unit.strikecraft_bay_component = None

    # 1. ConstructOrder formatting
    construct_order = ConstructOrder(unit, {
        "unit_template_name": "TestStation",
        "target_position": Position(15.5, 25.3)
    })
    state_data = construct_order.get_state_data()
    lines = game._format_order_state_data(state_data)
    assert len(lines) == 2
    assert "Construct:" in lines[0]
    assert "TestStation" in lines[0]
    assert "Pos:" in lines[1]
    assert "(15.5, 25.3)" in lines[1]

    # 2. RepairOrder formatting
    repair_order = RepairOrder(unit, {
        "target_unit_id": 456
    })
    target_unit = MockUnit()
    target_unit.id = 456
    target_unit.name = "Friendly Ship"
    game.galaxy.get_unit_by_id.return_value = target_unit
    
    state_data = repair_order.get_state_data()
    lines = game._format_order_state_data(state_data)
    assert len(lines) == 1
    assert "Repair:" in lines[0]
    assert "Friendly Ship" in lines[0]

    # 3. DockOrder formatting
    dock_order = DockOrder(unit, {
        "target_carrier_id": 789
    })
    carrier_unit = MockUnit()
    carrier_unit.id = 789
    carrier_unit.name = "Huge Carrier"
    game.galaxy.get_unit_by_id.return_value = carrier_unit

    state_data = dock_order.get_state_data()
    lines = game._format_order_state_data(state_data)
    assert len(lines) == 1
    assert "Dock:" in lines[0]
    assert "Huge Carrier" in lines[0]

    # 4. DeployUnitOrder formatting
    deploy_order = DeployUnitOrder(unit, {
        "docked_unit_id": 101
    })
    # Set docked name inside the order's state data lookup
    state_data = deploy_order.get_state_data()
    lines = game._format_order_state_data(state_data)
    assert len(lines) == 1
    assert "Deploy:" in lines[0]

    # 5. DeployAllWingsOrder formatting
    deploy_all_order = DeployAllWingsOrder(unit, {})
    state_data = deploy_all_order.get_state_data()
    lines = game._format_order_state_data(state_data)
    assert len(lines) == 1
    assert "Deploy All Wings" in lines[0]

    # 6. UseAbilityOrder formatting
    ability_order = UseAbilityOrder(unit, {
        "ability_type": "Jump",
        "target_unit_id": 456,
        "target_position": Position(12.0, 34.0)
    })
    game.galaxy.get_unit_by_id.return_value = target_unit
    state_data = ability_order.get_state_data()
    lines = game._format_order_state_data(state_data)
    assert len(lines) == 3
    assert "Ability: Jump" in lines[0]
    assert "Target:" in lines[1]
    assert "Friendly Ship" in lines[1]
    assert "Pos:" in lines[2]
    assert "(12.0, 34.0)" in lines[2]


def test_stationary_unit_repair_order_recursion_prevention():
    from unit_orders import RepairOrder
    from unit_components import RepairComponent
    
    unit = MockUnit()
    unit.game = MagicMock()
    unit.hangar_component = None
    unit.strikecraft_bay_component = None
    
    # Give unit a RepairComponent but NO Engines
    repair_comp = RepairComponent(unit)
    unit.add_component(repair_comp)
    assert unit.engines_component is None
    
    target_unit = MockUnit()
    target_unit.id = 999
    target_unit.name = "Damaged Friendly"
    target_unit.owner = unit.owner
    target_unit.current_hit_points = 50
    target_unit.max_hit_points = 100
    target_unit.position = Position(500, 500) # Far away, so movement is required
    
    # Mock game galaxy registry
    galaxy = MagicMock()
    galaxy.get_unit_by_id.return_value = target_unit
    unit.game.galaxy = galaxy
    
    order = RepairOrder(unit, {
        "target_unit_id": 999
    })
    
    # Execute the order (this will spawn MoveOrder because target is far away)
    order.execute(galaxy)
    assert order.status == OrderStatus.IN_PROGRESS
    assert len(order.sub_orders) == 2
    assert order.sub_orders[0].order_type == OrderType.MOVE
    assert order.sub_orders[1].order_type == OrderType.REPAIR
    
    # Update the order. MoveOrder.execute will be called inside order.update.
    # Because unit has no engines, MoveOrder.execute will fail immediately.
    # Under our new propagation logic, this should fail the parent order cleanly.
    order.update(galaxy)
    
    assert order.status == OrderStatus.FAILED
    assert len(order.sub_orders) == 0


def test_order_system_handle_unload_resources():
    from order_system import OrderSystem
    from events import UnloadResourcesEvent
    from unit_components import Commander
    from unittest.mock import MagicMock
    
    # Setup two mock units. unit_metal has metal cargo. unit_crystal has crystal cargo.
    unit_metal = MockUnit()
    unit_metal.add_component(Commander(unit_metal))
    mining_metal = MiningComponent(unit_metal, max_cargo=50)
    mining_metal.raw_metal_cargo = 10
    unit_metal.add_component(mining_metal)
    
    unit_crystal = MockUnit()
    unit_crystal.add_component(Commander(unit_crystal))
    mining_crystal = MiningComponent(unit_crystal, max_cargo=50)
    mining_crystal.raw_crystal_cargo = 10
    unit_crystal.add_component(mining_crystal)
    
    # Target refinery has metal refinery only
    target_refinery = MockUnit()
    target_refinery.id = 777
    refinery_metal = MetalRefineryComponent(target_refinery)
    target_refinery.add_component(refinery_metal)
    
    # Mock game and event bus
    game = MagicMock()
    event_bus = MagicMock()
    
    order_system = OrderSystem(game, event_bus)
    
    # Event with both units targeting the metal refinery
    event = UnloadResourcesEvent(
        units=[unit_metal, unit_crystal],
        target_unit=target_refinery,
        shift_pressed=False
    )
    
    order_system.handle_unload_resources(event)
    
    # unit_metal has metal cargo (matching), so it should get an unload order
    assert unit_metal.commander_component.current_order is not None
    assert unit_metal.commander_component.current_order.order_type == OrderType.UNLOAD_RESOURCES
    
    # unit_crystal has crystal cargo (unmatching), so it should NOT get an unload order
    assert unit_crystal.commander_component.current_order is None


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
    
    # Should spawn follow MoveOrder to (100, 10)
    assert len(order.sub_orders) == 1
    move_sub = order.sub_orders[0]
    assert move_sub.order_type == OrderType.MOVE
    assert move_sub.parameters["destination_position"] == Position(100, 10)
    
    # Simulate target moving to (150, 10)
    target.position = Position(150, 10)
    order.update(galaxy)
    
    # Since destination is far, it should cancel previous and spawn a new move to (150, 10)
    assert len(order.sub_orders) == 1
    move_sub = order.sub_orders[0]
    assert move_sub.parameters["destination_position"] == Position(150, 10)
    
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
    assert order.sub_orders[0].parameters["destination_position"] == Position(50, 10)


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







