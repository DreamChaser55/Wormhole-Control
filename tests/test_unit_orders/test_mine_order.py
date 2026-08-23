from unittest.mock import MagicMock
from geometry import Position
from unit_orders import OrderStatus, OrderType, MineOrder
from unit_components import MiningComponent
from tests.test_unit_components import MockUnit


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
