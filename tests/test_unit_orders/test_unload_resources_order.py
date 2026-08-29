from unittest.mock import MagicMock
from geometry import Position
from unit_orders import OrderStatus, OrderType, UnloadResourcesOrder
from unit_components import (
    MiningComponent, MetalRefineryComponent, CrystalRefineryComponent, Commander
)
from tests.test_unit_components import MockUnit
from order_system import OrderSystem
from events import UnloadResourcesEvent


def test_unload_resources_order():
    unit = MockUnit()
    mining_comp = MiningComponent(unit, mining_rate=10, max_cargo=50, mining_range=100.0)
    mining_comp.raw_metal_cargo = 20
    unit.add_component(mining_comp)
    
    target = MockUnit()
    target.id = 999
    target.name = "Refinery Station"
    target.in_system = "Sol"
    target.in_hex = (0, 0)
    target.position = Position(0, 0)
    
    refinery_comp = MetalRefineryComponent(target, unload_range=300.0)
    target.add_component(refinery_comp)
    
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(50, 0) # within 300 range
    
    galaxy = MagicMock()
    galaxy.get_unit_by_id.return_value = target
    
    order = UnloadResourcesOrder(unit, {"target_unit_id": target.id})
    order.execute(galaxy)
    
    assert order.status == OrderStatus.COMPLETED
    assert mining_comp.raw_metal_cargo == 0
    assert target.owner.metal == 1000 + 20 # MockPlayer starts with 1000 metal
    
    # Test out of range
    unit.position = Position(400, 0)
    mining_comp.raw_metal_cargo = 20
    order_out_of_range = UnloadResourcesOrder(unit, {"target_unit_id": target.id})
    order_out_of_range.execute(galaxy)
    
    assert len(order_out_of_range.sub_orders) == 2
    assert order_out_of_range.sub_orders[0].order_type == OrderType.MOVE
    assert order_out_of_range.sub_orders[0].parameters["target_unit_id"] == target.id
    assert order_out_of_range.sub_orders[0].parameters["standoff_distance"] == 295.0
    assert order_out_of_range.sub_orders[1].order_type == OrderType.UNLOAD_RESOURCES


def test_unload_resources_matching_refinery():
    unit = MockUnit()
    mining_comp = MiningComponent(unit, mining_rate=10, max_cargo=100, mining_range=100.0)
    mining_comp.raw_metal_cargo = 30
    mining_comp.raw_crystal_cargo = 40
    unit.add_component(mining_comp)
    
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    
    # 1. Target with metal refinery only
    target_metal = MockUnit()
    target_metal.id = 901
    target_metal.name = "Metal Refinery Station"
    target_metal.in_system = "Sol"
    target_metal.in_hex = (0, 0)
    target_metal.position = Position(10, 0)
    target_metal.owner.metal = 1000
    target_metal.owner.crystal = 1000
    
    refinery_metal = MetalRefineryComponent(target_metal, unload_range=300.0)
    target_metal.add_component(refinery_metal)
    
    galaxy = MagicMock()
    galaxy.get_unit_by_id.side_effect = lambda uid: {901: target_metal}[uid]
    
    order = UnloadResourcesOrder(unit, {"target_unit_id": 901})
    order.execute(galaxy)
    
    assert order.status == OrderStatus.COMPLETED
    assert mining_comp.raw_metal_cargo == 0.0
    assert mining_comp.raw_crystal_cargo == 40.0 # Unmatching crystal stays
    assert target_metal.owner.metal == 1030
    assert target_metal.owner.crystal == 1000
    
    # 2. Target with crystal refinery only
    mining_comp.raw_metal_cargo = 30
    mining_comp.raw_crystal_cargo = 40
    
    target_crystal = MockUnit()
    target_crystal.id = 902
    target_crystal.name = "Crystal Refinery Station"
    target_crystal.in_system = "Sol"
    target_crystal.in_hex = (0, 0)
    target_crystal.position = Position(10, 0)
    target_crystal.owner.metal = 1000
    target_crystal.owner.crystal = 1000
    
    refinery_crystal = CrystalRefineryComponent(target_crystal, unload_range=300.0)
    target_crystal.add_component(refinery_crystal)
    
    galaxy.get_unit_by_id.side_effect = lambda uid: {902: target_crystal}[uid]
    
    order2 = UnloadResourcesOrder(unit, {"target_unit_id": 902})
    order2.execute(galaxy)
    
    assert order2.status == OrderStatus.COMPLETED
    assert mining_comp.raw_metal_cargo == 30.0 # Unmatching metal stays
    assert mining_comp.raw_crystal_cargo == 0.0
    assert target_crystal.owner.metal == 1000
    assert target_crystal.owner.crystal == 1040


def test_order_system_handle_unload_resources():
    # Setup two mock units. unit_metal has metal cargo. unit_crystal has crystal cargo.
    unit_metal = MockUnit()
    unit_metal.add_component(Commander(unit_metal))
    mining_metal = MiningComponent(unit_metal, max_cargo=50)
    mining_metal.raw_metal_cargo = 10
    unit_metal.add_component(mining_metal)
    
    unit_crystal = MockUnit()
    unit_crystal.add_component(Commander(unit_crystal))
    mining_crystal = MiningComponent(unit_crystal, max_cargo=50)
    mining_crystal.raw_crystal_cargo = 10
    unit_crystal.add_component(mining_crystal)
    
    # Target refinery has metal refinery only
    target_refinery = MockUnit()
    target_refinery.id = 777
    refinery_metal = MetalRefineryComponent(target_refinery)
    target_refinery.add_component(refinery_metal)
    
    # Mock game and event bus
    game = MagicMock()
    event_bus = MagicMock()
    galaxy = MagicMock()
    galaxy.get_unit_by_id.return_value = target_refinery
    game.galaxy = galaxy
    for unit in (unit_metal, unit_crystal):
        unit.in_galaxy = galaxy
        unit.game.galaxy = galaxy
    
    order_system = OrderSystem(game, event_bus)
    
    # Event with both units targeting the metal refinery
    event = UnloadResourcesEvent(
        units=[unit_metal, unit_crystal],
        target_unit=target_refinery,
        shift_pressed=False
    )
    
    order_system.handle_unload_resources(event)
    
    # unit_metal has metal cargo (matching), so it should get an unload order
    assert unit_metal.commander_component.current_order is not None
    assert unit_metal.commander_component.current_order.order_type == OrderType.UNLOAD_RESOURCES
    
    # unit_crystal has crystal cargo (unmatching), so it should NOT get an unload order
    assert unit_crystal.commander_component.current_order is None
