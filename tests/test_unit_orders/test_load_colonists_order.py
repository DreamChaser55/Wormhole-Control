from unittest.mock import MagicMock
from geometry import Position
from unit_orders import OrderStatus, OrderType, LoadColonistsOrder
from unit_components import ColonyComponent
from tests.test_unit_components import MockUnit


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
