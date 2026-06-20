import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import HullSize
from unit_components import HangarComponent
from unit_orders import OrderStatus, OrderType, DockOrder, DeployUnitOrder
from tests.test_unit_components import MockUnit as BaseMockUnit, MockPlayer

class MockUnit(BaseMockUnit):
    @property
    def hangar_component(self):
        return self.get_component(HangarComponent)

def test_hangar_component_capacity():
    carrier = MockUnit()
    hangar = HangarComponent(carrier, max_slots=4)
    carrier.add_component(hangar)

    ship_tiny = MockUnit()
    ship_tiny.hull_size = HullSize.TINY

    ship_small = MockUnit()
    ship_small.hull_size = HullSize.SMALL

    ship_medium = MockUnit()
    ship_medium.hull_size = HullSize.MEDIUM

    # Can dock tiny and small
    assert hangar.can_dock(ship_tiny)
    assert hangar.can_dock(ship_small)
    # Cannot dock medium
    assert not hangar.can_dock(ship_medium)

    # Test slots usage: 4 slots max
    # Dock tiny: takes 1 slot. 3 slots remaining.
    assert hangar.dock(ship_tiny, carrier.in_galaxy)
    assert hangar.get_used_slots() == 1

    # Dock small: takes 2 slots. 1 slot remaining.
    assert hangar.dock(ship_small, carrier.in_galaxy)
    assert hangar.get_used_slots() == 3

    # Try to dock another small (needs 2, but only 1 free) -> should fail
    ship_small2 = MockUnit()
    ship_small2.hull_size = HullSize.SMALL
    assert not hangar.can_dock(ship_small2)
    assert not hangar.dock(ship_small2, carrier.in_galaxy)

    # Dock another tiny: takes 1 slot. 0 slots remaining.
    ship_tiny2 = MockUnit()
    ship_tiny2.hull_size = HullSize.TINY
    assert hangar.dock(ship_tiny2, carrier.in_galaxy)
    assert hangar.get_used_slots() == 4

    # Full hangar cannot dock any more
    assert not hangar.can_dock(ship_tiny)

def test_hangar_dock_and_deploy():
    carrier = MockUnit()
    hangar = HangarComponent(carrier, max_slots=4)
    carrier.add_component(hangar)

    ship = MockUnit()
    ship.hull_size = HullSize.TINY
    ship.in_system = "Sol"
    ship.in_hex = (0, 0)
    ship.position = Position(10, 20)

    # Mock galaxy and systems
    galaxy = MagicMock()
    mock_system = MagicMock()
    galaxy.systems = {"Sol": mock_system}
    carrier.in_galaxy = galaxy

    # Dock
    success = hangar.dock(ship, galaxy)
    assert success
    assert ship in hangar.docked_units
    mock_system.remove_unit.assert_called_once_with(ship)
    assert ship.in_system == carrier.in_system
    assert ship.in_hex == carrier.in_hex

    # Deploy
    success_deploy = hangar.deploy(ship, galaxy)
    assert success_deploy
    assert ship not in hangar.docked_units
    mock_system.add_unit.assert_called_once_with(ship)

def test_dock_order():
    carrier = MockUnit()
    carrier.id = 100
    carrier.in_system = "Sol"
    carrier.in_hex = (0, 0)
    carrier.position = Position(0, 0)
    hangar = HangarComponent(carrier, max_slots=4)
    carrier.add_component(hangar)

    ship = MockUnit()
    ship.hull_size = HullSize.TINY
    ship.in_system = "Sol"
    ship.in_hex = (0, 0)
    ship.position = Position(200, 0) # Out of docking range (100)

    galaxy = MagicMock()
    galaxy.get_unit_by_id.side_effect = lambda uid: carrier if uid == carrier.id else ship
    ship.game.galaxy = galaxy

    order = DockOrder(ship, {"target_carrier_id": carrier.id})
    order.execute(galaxy)

    # Since it is out of range, it should spawn MoveOrder and DockOrder suborders
    assert len(order.sub_orders) == 2
    assert order.sub_orders[0].order_type == OrderType.MOVE
    assert order.sub_orders[1].order_type == OrderType.DOCK

    # In range
    ship.position = Position(50, 0) # within 100 range
    order_in_range = DockOrder(ship, {"target_carrier_id": carrier.id})
    order_in_range.execute(galaxy)
    assert order_in_range.status == OrderStatus.COMPLETED
    assert ship in hangar.docked_units

def test_deploy_order():
    carrier = MockUnit()
    carrier.id = 100
    hangar = HangarComponent(carrier, max_slots=4)
    carrier.add_component(hangar)

    ship = MockUnit()
    ship.id = 200
    ship.hull_size = HullSize.TINY
    
    # Dock the ship first
    galaxy = MagicMock()
    hangar.dock(ship, galaxy)
    assert ship in hangar.docked_units

    deploy_order = DeployUnitOrder(carrier, {"docked_unit_id": ship.id})
    deploy_order.execute(galaxy)
    assert deploy_order.status == OrderStatus.COMPLETED
    assert ship not in hangar.docked_units

def test_cascading_destruction():
    from entities import Unit
    
    # We will use real Unit instance to test cascade destruction
    game_mock = MagicMock()
    galaxy_mock = MagicMock()
    game_mock.galaxy = galaxy_mock
    
    owner = MockPlayer()
    
    carrier = Unit(
        owner=owner,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Carrier",
        hull_size=HullSize.MEDIUM,
        game=game_mock
    )
    hangar = HangarComponent(carrier, max_slots=4)
    carrier.add_component(hangar)
    
    docked1 = Unit(
        owner=owner,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Fighter 1",
        hull_size=HullSize.TINY,
        game=game_mock
    )
    
    docked2 = Unit(
        owner=owner,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Fighter 2",
        hull_size=HullSize.TINY,
        game=game_mock
    )
    
    hangar.dock(docked1, galaxy_mock)
    hangar.dock(docked2, galaxy_mock)
    
    # Destroy carrier
    carrier.destroy()
    
    # Verify carrier's destroy() triggers destroy() on docked ships, calling remove_unit
    galaxy_mock.remove_unit.assert_any_call(docked1)
    galaxy_mock.remove_unit.assert_any_call(docked2)
