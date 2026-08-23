from unittest.mock import MagicMock
from geometry import Position
from unit_orders import OrderStatus, ReachWaypointOrder
from unit_components import Engines, Hyperdrive, HyperdriveType
from unit_components.movement import JumpStatus
from tests.test_unit_components import MockUnit


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


def test_reach_waypoint_order_hyperdrive_error_fails_order():
    """
    When a hyperdrive jump fails (setting jump_status = JumpStatus.ERROR),
    ReachWaypointOrder must mark itself as OrderStatus.FAILED and reset hyperdrive state,
    preventing units from being stuck indefinitely in IN_PROGRESS state.
    """
    unit = MockUnit()
    hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=5)
    unit.add_component(hd)

    order = ReachWaypointOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (4, 0),
        "destination_position": Position(100.0, 100.0),
    })

    galaxy = MagicMock()
    order.execute(galaxy)
    assert order.status == OrderStatus.IN_PROGRESS

    # Simulate turn_processor setting JumpStatus.ERROR when a jump fails
    hd.jump_status = JumpStatus.ERROR

    order.check_completion_conditions()

    assert order.status == OrderStatus.FAILED
    assert hd.jump_status == JumpStatus.READY
    assert hd.hex_jump_target is None
