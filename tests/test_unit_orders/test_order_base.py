import pytest
from unittest.mock import MagicMock
from geometry import Position
from unit_orders import (
    OrderStatus, ReachWaypointOrder, MoveOrder,
    ConstructOrder, RepairOrder, DockOrder, DeployUnitOrder,
    DeployAllWingsOrder, UseAbilityOrder
)
from tests.test_unit_components import MockUnit
from game import Game


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


def test_order_formatting():
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
