from unittest.mock import MagicMock, patch
import pytest
from constants import HullSize
from geometry import Position
from entities import Unit, Player
from unit_components import Engines, Commander, AntimatterStorage
from unit_orders import OrderType, PatrolOrder, MoveOrder
from events import IssuePatrolOrderEvent, EventBus
from order_system import OrderSystem
from input_processor.context_menu_builder import build_sector_context_menu_options
from input_processor.context_actions import handle_context_menu_action


class MockGame:
    def __init__(self):
        self.sidebar_needs_update = False
        self.galaxy = MagicMock()
        self.gui = MagicMock()
        self.event_bus = EventBus()
        self.order_system = OrderSystem(self, self.event_bus)
        self.players = [Player("Player 1", (0, 255, 0))]
        self.current_player_index = 0
        self.current_system_name = "Sol"
        self.current_sector_coord = (0, 0)
        self.selected_objects = []


def _create_test_unit(player, game=None):
    unit = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Scout 1",
        hull_size=HullSize.SMALL,
        game=game
    )
    commander = Commander(unit)
    unit.add_component(commander)
    engines = Engines(unit, speed=100.0)
    unit.add_component(engines)
    am = AntimatterStorage(unit, max_capacity=100.0)
    am.current_amount = 100.0
    unit.add_component(am)
    return unit


def test_patrol_order_shift_queues_new_order_when_patrolling():
    """Verify that Shift + Patrol queues a distinct new PatrolOrder rather than appending a waypoint."""
    game = MockGame()
    unit = _create_test_unit(game.players[0])
    
    # 1. Start initial patrol to (100, 100)
    event1 = IssuePatrolOrderEvent(
        units=[unit],
        system_name="Sol",
        sector_coord=(0, 0),
        destination=Position(100, 100),
        shift_pressed=False,
        ctrl_pressed=False
    )
    game.order_system.handle_issue_patrol_order(event1)
    
    active_patrol = unit.commander_component.current_order
    assert active_patrol is not None
    assert active_patrol.order_type == OrderType.PATROL
    assert len(active_patrol.parameters.get("waypoints", [])) == 1
    assert active_patrol.parameters["waypoints"][0]["position"] == Position(100, 100)
    assert len(unit.commander_component.orders_queue) == 0

    # 2. Issue a second patrol order with SHIFT pressed (queue order)
    event2 = IssuePatrolOrderEvent(
        units=[unit],
        system_name="Sol",
        sector_coord=(0, 0),
        destination=Position(200, 200),
        shift_pressed=True,
        ctrl_pressed=False
    )
    game.order_system.handle_issue_patrol_order(event2)

    # Active patrol must be untouched (still 1 waypoint)
    assert unit.commander_component.current_order is active_patrol
    assert len(active_patrol.parameters.get("waypoints", [])) == 1

    # Queue must contain a second distinct PatrolOrder
    assert len(unit.commander_component.orders_queue) == 1
    queued_order = unit.commander_component.orders_queue[0]
    assert queued_order.order_type == OrderType.PATROL
    assert queued_order is not active_patrol
    assert len(queued_order.parameters.get("waypoints", [])) == 1
    assert queued_order.parameters["waypoints"][0]["position"] == Position(200, 200)


def test_patrol_order_no_shift_clears_and_replaces():
    """Verify that issuing Patrol without Shift clears existing orders and replaces current_order."""
    game = MockGame()
    unit = _create_test_unit(game.players[0])
    
    # 1. Initial patrol
    event1 = IssuePatrolOrderEvent(
        units=[unit],
        system_name="Sol",
        sector_coord=(0, 0),
        destination=Position(100, 100),
        shift_pressed=False,
        ctrl_pressed=False
    )
    game.order_system.handle_issue_patrol_order(event1)
    original_patrol = unit.commander_component.current_order

    # 2. Issue new patrol without Shift
    event2 = IssuePatrolOrderEvent(
        units=[unit],
        system_name="Sol",
        sector_coord=(0, 0),
        destination=Position(300, 300),
        shift_pressed=False,
        ctrl_pressed=False
    )
    game.order_system.handle_issue_patrol_order(event2)

    new_patrol = unit.commander_component.current_order
    assert new_patrol is not original_patrol
    assert new_patrol.order_type == OrderType.PATROL
    assert new_patrol.parameters["waypoints"][0]["position"] == Position(300, 300)
    assert len(unit.commander_component.orders_queue) == 0


def test_patrol_order_ctrl_adds_waypoint_to_current_patrol():
    """Verify that Ctrl + Patrol appends a waypoint to the active PatrolOrder."""
    game = MockGame()
    unit = _create_test_unit(game.players[0])
    
    # 1. Initial patrol
    event1 = IssuePatrolOrderEvent(
        units=[unit],
        system_name="Sol",
        sector_coord=(0, 0),
        destination=Position(100, 100),
        shift_pressed=False,
        ctrl_pressed=False
    )
    game.order_system.handle_issue_patrol_order(event1)
    active_patrol = unit.commander_component.current_order

    # 2. Issue patrol with Ctrl pressed
    event2 = IssuePatrolOrderEvent(
        units=[unit],
        system_name="Sol",
        sector_coord=(0, 0),
        destination=Position(200, 200),
        shift_pressed=False,
        ctrl_pressed=True
    )
    game.order_system.handle_issue_patrol_order(event2)

    # Waypoint added to active patrol
    assert unit.commander_component.current_order is active_patrol
    assert len(active_patrol.parameters["waypoints"]) == 2
    assert active_patrol.parameters["waypoints"][0]["position"] == Position(100, 100)
    assert active_patrol.parameters["waypoints"][1]["position"] == Position(200, 200)
    assert len(unit.commander_component.orders_queue) == 0


def test_patrol_order_ctrl_adds_waypoint_to_queued_patrol():
    """Verify that Ctrl + Patrol appends a waypoint to the last queued PatrolOrder if current is not Patrol."""
    game = MockGame()
    unit = _create_test_unit(game.players[0])
    
    # 1. Set current_order to MoveOrder
    move_order = MoveOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(50, 50)
    })
    unit.commander_component.add_order(move_order)

    # 2. Queue a PatrolOrder
    queued_patrol = PatrolOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(100, 100)
    })
    unit.commander_component.add_order(queued_patrol)

    # 3. Ctrl + Patrol to (200, 200)
    event = IssuePatrolOrderEvent(
        units=[unit],
        system_name="Sol",
        sector_coord=(0, 0),
        destination=Position(200, 200),
        shift_pressed=False,
        ctrl_pressed=True
    )
    game.order_system.handle_issue_patrol_order(event)

    assert unit.commander_component.current_order is move_order
    assert len(unit.commander_component.orders_queue) == 1
    assert unit.commander_component.orders_queue[0] is queued_patrol
    assert len(queued_patrol.parameters["waypoints"]) == 2
    assert queued_patrol.parameters["waypoints"][1]["position"] == Position(200, 200)


def test_patrol_order_ctrl_fallback_when_no_patrol():
    """Verify that Ctrl + Patrol gracefully creates a new PatrolOrder if unit has no active patrol."""
    game = MockGame()
    unit = _create_test_unit(game.players[0])
    
    event = IssuePatrolOrderEvent(
        units=[unit],
        system_name="Sol",
        sector_coord=(0, 0),
        destination=Position(100, 100),
        shift_pressed=False,
        ctrl_pressed=True
    )
    game.order_system.handle_issue_patrol_order(event)

    assert unit.commander_component.current_order is not None
    assert unit.commander_component.current_order.order_type == OrderType.PATROL
    assert unit.commander_component.current_order.parameters["waypoints"][0]["position"] == Position(100, 100)


def test_context_menu_add_patrol_waypoint_option():
    """Verify 'Add Patrol Waypoint' appears in context menu only when an operational unit has a Patrol order."""
    game = MockGame()
    unit = _create_test_unit(game.players[0])
    game.selected_objects = [unit]
    
    # 1. No patrol order -> only "Move Here" and "Patrol Here"
    options, _ = build_sector_context_menu_options(game, None, Position(100, 100))
    action_ids = [opt[1] for opt in options]
    assert "issue_move_order" in action_ids
    assert "issue_patrol_order" in action_ids
    assert "add_patrol_waypoint" not in action_ids

    # 2. Add patrol order -> "Add Patrol Waypoint" appears
    patrol_order = PatrolOrder(unit, {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(50, 50)
    })
    unit.commander_component.add_order(patrol_order)

    options2, _ = build_sector_context_menu_options(game, None, Position(100, 100))
    action_ids2 = [opt[1] for opt in options2]
    assert "issue_move_order" in action_ids2
    assert "issue_patrol_order" in action_ids2
    assert "add_patrol_waypoint" in action_ids2


def test_handle_context_menu_action_add_patrol_waypoint():
    """Verify selecting 'add_patrol_waypoint' from context menu dispatches IssuePatrolOrderEvent with ctrl_pressed=True."""
    game = MockGame()
    unit = _create_test_unit(game.players[0])
    game.selected_objects = [unit]

    published_events = []
    game.event_bus.publish = lambda event: published_events.append(event)

    handle_context_menu_action(game, "add_patrol_waypoint", Position(150, 150))

    assert len(published_events) == 1
    event = published_events[0]
    assert isinstance(event, IssuePatrolOrderEvent)
    assert event.destination == Position(150, 150)
    assert event.ctrl_pressed is True
    assert event.shift_pressed is False


def test_handle_context_menu_action_issue_patrol_order_with_ctrl():
    """Verify selecting 'issue_patrol_order' with Ctrl held down sets ctrl_pressed=True."""
    game = MockGame()
    unit = _create_test_unit(game.players[0])
    game.selected_objects = [unit]

    published_events = []
    game.event_bus.publish = lambda event: published_events.append(event)

    with patch('input_processor.context_actions._get_ctrl_pressed', return_value=True), \
         patch('input_processor.context_actions._get_shift_pressed', return_value=False):
        handle_context_menu_action(game, "issue_patrol_order", Position(250, 250))

    assert len(published_events) == 1
    event = published_events[0]
    assert isinstance(event, IssuePatrolOrderEvent)
    assert event.destination == Position(250, 250)
    assert event.ctrl_pressed is True
    assert event.shift_pressed is False
