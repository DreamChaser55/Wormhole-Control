from unittest.mock import MagicMock
from geometry import Position
from unit_orders import OrderStatus, OrderType, RepairOrder
from unit_components import RepairComponent
from tests.test_unit_components import MockUnit


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
    assert order_out_of_range.sub_orders[0].parameters["target_unit_id"] == target.id
    assert order_out_of_range.sub_orders[0].parameters["standoff_distance"] == 95.0
    assert order_out_of_range.sub_orders[1].order_type == OrderType.REPAIR


def test_stationary_unit_repair_order_recursion_prevention():
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
