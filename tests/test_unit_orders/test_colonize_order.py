from unittest.mock import MagicMock
from geometry import Position
from unit_orders import OrderStatus, ColonizeOrder
from unit_components import ColonyComponent
from tests.test_unit_components import MockUnit


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
