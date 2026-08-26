from types import SimpleNamespace
from unittest.mock import MagicMock
from geometry import Position, Circle
from unit_orders import OrderStatus, ToggleInhibitorOrder
from unit_components import HyperspaceInhibitionFieldEmitter
from tests.test_unit_components import MockUnit


def test_toggle_inhibitor_order():
    unit = MockUnit()
    emitter = MagicMock()
    emitter.radius = 100.0
    emitter.set_active.return_value = SimpleNamespace(allowed=True)
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
    emitter.set_active.assert_called_once_with(True, galaxy)
