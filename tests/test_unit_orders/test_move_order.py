import logging
from unittest.mock import MagicMock, patch
from geometry import Position, Circle, distance as geo_distance, is_point_in_circle as geo_in_circle
from unit_orders import OrderStatus, OrderType, MoveOrder, ReachWaypointOrder
from unit_components import Engines, Hyperdrive, HyperdriveType, Commander
from unit_components.antimatter import AntimatterStorage
from unit_components.movement import JumpStatus
from tests.test_unit_components import MockUnit
from constants import HullSize
from events import JumpInterhexEvent, EventBus
from order_system import OrderSystem
from turn_processor import TurnProcessor


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
    with patch("unit_orders.movement.find_intersystem_path", return_value=["Sol", "Vega"]), \
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


def test_inter_system_jump_drive_type_validation():
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


def test_handle_jump_interhex_same_hex_different_system():
    event_bus = EventBus()
    game = MagicMock()
    order_sys = OrderSystem(game, event_bus)
    
    unit = MockUnit()
    unit.in_system = "Sol"
    unit.in_hex = (0, 5)
    unit.add_component(Hyperdrive(unit))
    mock_commander = MagicMock()
    unit.components[Commander] = mock_commander
    
    # Event targeting same hex (0, 5) but in "Rigel" system
    event = JumpInterhexEvent(
        units=[unit],
        system_name="Rigel",
        target_hex=(0, 5),
        shift_pressed=False
    )
    
    order_sys.handle_jump_interhex(event)
    mock_commander.add_order.assert_called_once()
    added_order = mock_commander.add_order.call_args[0][0]
    assert added_order.order_type == OrderType.MOVE
    assert added_order.parameters["destination_system_name"] == "Rigel"
    assert added_order.parameters["destination_hex_coord"] == (0, 5)


def test_move_order_plan_route_clears_sub_orders_on_failure(caplog):
    unit = MockUnit()
    unit.in_system = "Sol"
    unit.in_hex = (0, 5)
    unit.hull_size = HullSize.HUGE
    hd = Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED)
    unit.add_component(hd)
    
    order = MoveOrder(unit, {
        "destination_system_name": "Rigel",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(0, 0)
    })
    
    # Setup galaxy where Sol only connects to Vega via a MEDIUM wormhole (too small for HUGE unit)
    mock_start_hex = MagicMock()
    # Mock an inhibition zone to stage an escape sub-order early in plan_route
    zone = Circle(Position(0, 0), 50.0)
    mock_start_hex.get_all_inhibition_zones.return_value = [zone]
    
    galaxy = MagicMock()
    galaxy.systems = {"Sol": MagicMock(), "Rigel": MagicMock()}
    galaxy.systems["Sol"].hexes = {(0, 5): mock_start_hex}
    
    # Topology: Sol <-> Rigel but with MEDIUM diameter edge
    galaxy.system_graph = {
        "Sol": {"Rigel": HullSize.MEDIUM},
        "Rigel": {"Sol": HullSize.MEDIUM}
    }
    
    with caplog.at_level(logging.WARNING):
        order.execute(galaxy)
        
    assert order.status == OrderStatus.FAILED
    assert len(order.sub_orders) == 0  # Staged escape sub-order must be cleared!
    assert "too large for wormhole" in caplog.text


def test_handle_inhibited_waypoint_intermediate_safe_distance():
    """
    When a multi-stage hex jump passes through an intermediate sector that has an
    inhibition field, the landing position must be placed outside the field
    (at zone.radius + 1.0), so the unit can immediately re-engage its hyperdrive.
    """
    unit = MockUnit()
    # Jump range of 2; destination at hex (0, 4) forces an intermediate stop at (0, 2).
    hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=2)
    unit.add_component(hd)

    dest_hex = (0, 4)
    dest_pos = Position(10.0, 10.0)

    galaxy = MagicMock()

    # Sector (0, 0) - starting sector, no inhibition.
    start_hex_obj = MagicMock()
    start_hex_obj.get_all_inhibition_zones.return_value = []

    # Sector (0, 2) - intermediate sector with inhibition field centred at (0, 0), radius 20.
    ZONE_RADIUS = 20.0
    inhibitor_zone = Circle(Position(0.0, 0.0), ZONE_RADIUS)
    intermediate_hex_obj = MagicMock()
    intermediate_hex_obj.get_all_inhibition_zones.return_value = [inhibitor_zone]
    # Provide a large boundary circle so clamping has no effect.
    intermediate_hex_obj.boundary_circle = Circle(Position(0.0, 0.0), 500.0)

    # Sector (0, 4) - destination sector, no inhibition.
    dest_hex_obj = MagicMock()
    dest_hex_obj.get_all_inhibition_zones.return_value = []
    dest_hex_obj.boundary_circle = Circle(Position(0.0, 0.0), 500.0)

    mock_sys = MagicMock()
    mock_sys.hexes = {
        (0, 0): start_hex_obj,
        (0, 2): intermediate_hex_obj,
        (0, 4): dest_hex_obj,
    }
    galaxy.systems = {"Sol": mock_sys}

    order = MoveOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": dest_hex,
        "destination_position": dest_pos,
    })

    order.execute(galaxy)

    # With jump_range=2 and total distance=4, find_hex_jump_path produces two hops:
    #   hop 1 -> (0, 2)  [intermediate]
    #   hop 2 -> (0, 4)  [final]
    # The intermediate hop sub-order must land outside the inhibition zone.
    intermediate_sub_order = next(
        (so for so in order.sub_orders if so.parameters["destination_hex_coord"] == (0, 2)),
        None
    )

    assert intermediate_sub_order is not None, "No sub-order for intermediate hex (0, 2) found."

    landing_pos = intermediate_sub_order.parameters["destination_position"]
    dist_from_zone_centre = geo_distance(landing_pos, inhibitor_zone.center)

    # Landing must be strictly outside the zone (radius + 1.0 = 21.0).
    assert dist_from_zone_centre > ZONE_RADIUS, (
        "Intermediate waypoint is inside or on the inhibition zone "
        "(dist=" + str(round(dist_from_zone_centre, 4)) + ", zone_radius=" + str(ZONE_RADIUS) + ")."
    )
    assert abs(dist_from_zone_centre - (ZONE_RADIUS + 1.0)) < 0.01, (
        "Expected landing at exactly zone.radius + 1.0 = " + str(ZONE_RADIUS + 1.0) +
        ", got " + str(round(dist_from_zone_centre, 4)) + "."
    )


def test_handle_inhibited_waypoint_intermediate_multiple_zones():
    """
    When multiple inhibition zones exist in an intermediate sector, the landing
    position must clear every zone, not just the first one encountered.

    Zone layout - both zones cover the default landing position at the origin:
      zone_a: centre (0, 0), radius 10
      zone_b: centre (5, 0), radius 8
    Both cleared by moving along +x past x = 14 (5 + 8 + 1 safe margin).
    The net escape direction (sum of unit vectors away from each zone) points
    roughly along +x, so the algorithm converges in at most two passes.
    """
    unit = MockUnit()
    hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=2)
    unit.add_component(hd)

    dest_hex = (0, 4)
    dest_pos = Position(10.0, 10.0)

    galaxy = MagicMock()

    zone_a = Circle(Position(0.0, 0.0), 10.0)
    zone_b = Circle(Position(5.0, 0.0), 8.0)

    start_hex_obj = MagicMock()
    start_hex_obj.get_all_inhibition_zones.return_value = []

    intermediate_hex_obj = MagicMock()
    intermediate_hex_obj.get_all_inhibition_zones.return_value = [zone_a, zone_b]
    intermediate_hex_obj.boundary_circle = Circle(Position(0.0, 0.0), 500.0)

    dest_hex_obj = MagicMock()
    dest_hex_obj.get_all_inhibition_zones.return_value = []
    dest_hex_obj.boundary_circle = Circle(Position(0.0, 0.0), 500.0)

    mock_sys = MagicMock()
    mock_sys.hexes = {
        (0, 0): start_hex_obj,
        (0, 2): intermediate_hex_obj,
        (0, 4): dest_hex_obj,
    }
    galaxy.systems = {"Sol": mock_sys}

    order = MoveOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": dest_hex,
        "destination_position": dest_pos,
    })

    order.execute(galaxy)

    intermediate_sub_order = next(
        (so for so in order.sub_orders if so.parameters["destination_hex_coord"] == (0, 2)),
        None
    )

    assert intermediate_sub_order is not None, "No sub-order for intermediate hex (0, 2) found."

    landing_pos = intermediate_sub_order.parameters["destination_position"]

    # The landing position must be outside both zones.
    assert not geo_in_circle(landing_pos, zone_a), (
        "Landing position is still inside zone_a."
    )
    assert not geo_in_circle(landing_pos, zone_b), (
        "Landing position is still inside zone_b."
    )


def test_turn_processor_failed_hex_jump_does_not_mutate_position():
    """
    When a hex jump fails in turn_processor (e.g. due to insufficient antimatter),
    the unit's position should NOT be mutated to target_pos.
    """
    unit = MockUnit()
    unit.position = Position(0.0, 0.0)
    unit.in_hex = (0, 0)
    unit.in_system = "Sol"

    hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=5)
    unit.add_component(hd)
    
    # Add antimatter component with 0 antimatter (insufficient for jump)
    am = AntimatterStorage(unit, max_capacity=100.0)
    am.current_amount = 0.0
    unit.add_component(am)

    hd.hex_jump_target = ((2, 2), Position(500.0, 500.0))
    hd.jump_status = JumpStatus.READY

    game = MagicMock()
    start_hex = MagicMock()
    start_hex.get_all_inhibition_zones.return_value = []
    dest_hex = MagicMock()
    dest_hex.get_all_inhibition_zones.return_value = []

    mock_sys = MagicMock()
    mock_sys.name = "Sol"
    mock_sys.hexes = {(0, 0): start_hex, (2, 2): dest_hex}
    mock_sys.get_all_units.return_value = [(unit, (0, 0))]
    
    game.galaxy.systems = {"Sol": mock_sys}
    game.players = [unit.owner]
    game.current_player_index = 0

    processor = TurnProcessor(game)
    processor._process_movement(unit.owner)

    # Position must NOT be mutated to (500.0, 500.0)
    assert unit.position == Position(0.0, 0.0)
    assert hd.jump_status == JumpStatus.ERROR


def test_direct_wormhole_same_sector_destination_sublight_move():
    """
    When jumping to a destination in another system via a direct wormhole, and the destination
    is in the same sector as the exit wormhole but at a different (x, y) coordinate,
    MoveOrder must schedule the wormhole jump followed by a sub-light move to the final coordinates.
    """
    unit = MockUnit()
    unit.position = Position(100.0, 100.0)
    unit.in_hex = (1, 1)
    unit.in_system = "Sol"

    hd = Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5)
    engines = Engines(unit, speed=50.0)
    unit.add_component(hd)
    unit.add_component(engines)

    dest_system = "Alpha Centauri"
    dest_hex = (0, 0)
    dest_pos = Position(300.0, 300.0)

    wh_entry = MagicMock()
    wh_entry.id = 1
    wh_entry.name = "Sol WH"
    wh_entry.in_system = "Sol"
    wh_entry.in_hex = (1, 1)
    wh_entry.position = Position(100.0, 100.0)
    wh_entry.exit_wormhole_id = 2

    wh_exit = MagicMock()
    wh_exit.id = 2
    wh_exit.name = "AC WH"
    wh_exit.in_system = "Alpha Centauri"
    wh_exit.in_hex = (0, 0) # Same hex as dest_hex!
    wh_exit.position = Position(0.0, 0.0) # Different position from dest_pos (300, 300)

    galaxy = MagicMock()
    galaxy.wormholes = {1: wh_entry, 2: wh_exit}

    mock_ac_hex = MagicMock()
    mock_ac_hex.get_all_inhibition_zones.return_value = []
    mock_ac_hex.celestial_bodies = []

    mock_ac_sys = MagicMock()
    mock_ac_sys.hexes = {(0, 0): mock_ac_hex}

    mock_sol_hex = MagicMock()
    mock_sol_hex.get_all_inhibition_zones.return_value = []
    mock_sol_sys = MagicMock()
    mock_sol_sys.hexes = {(1, 1): mock_sol_hex}

    galaxy.systems = {"Sol": mock_sol_sys, "Alpha Centauri": mock_ac_sys}

    order = MoveOrder(unit, {
        "destination_system_name": dest_system,
        "destination_hex_coord": dest_hex,
        "destination_position": dest_pos
    })

    with patch.object(order, "find_wormhole_to_system", return_value=wh_entry):
        order.execute(galaxy)

    # Sub-orders expected:
    # 1. ReachWaypointOrder: move to entry wormhole in Sol (1, 1) at pos (100, 100)
    # 2. ReachWaypointOrder: wormhole system jump to Alpha Centauri (0, 0) at exit WH pos (0, 0)
    # 3. ReachWaypointOrder: sub-light move from (0, 0) to dest_pos (300, 300) in Alpha Centauri (0, 0)
    assert len(order.sub_orders) == 3
    assert order.sub_orders[0].parameters["destination_system_name"] == "Sol"
    assert order.sub_orders[0].parameters["destination_hex_coord"] == (1, 1)
    assert order.sub_orders[0].parameters["destination_position"] == Position(100.0, 100.0)

    assert order.sub_orders[1].parameters["destination_system_name"] == "Alpha Centauri"
    assert order.sub_orders[1].parameters["destination_hex_coord"] == (0, 0)
    assert order.sub_orders[1].parameters["destination_position"] == Position(0.0, 0.0)

    assert order.sub_orders[2].parameters["destination_system_name"] == "Alpha Centauri"
    assert order.sub_orders[2].parameters["destination_hex_coord"] == (0, 0)
    assert order.sub_orders[2].parameters["destination_position"] == Position(300.0, 300.0)

