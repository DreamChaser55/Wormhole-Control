import pytest
from unittest.mock import MagicMock
from geometry import Position
from unit_components import MiningComponent, MetalRefineryComponent, CrystalRefineryComponent, Commander
from tests.test_unit_components import MockUnit, MockPlayer
from unit_orders import OrderType, OrderStatus, ContinuousMineOrder, MineOrder, UnloadResourcesOrder
from entities import Asteroid, Moon
from constants import HullSize

def test_continuous_mining_flow():
    # Setup player and unit
    player = MockPlayer()
    unit = MockUnit()
    unit.owner = player
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    unit.hull_size = HullSize.SMALL
    
    commander = Commander(unit)
    unit.add_component(commander)
    
    mining_comp = MiningComponent(unit, max_cargo=100.0)
    unit.add_component(mining_comp)

    # Setup asteroid
    asteroid = Asteroid((0, 0), "Sol")
    asteroid.position = Position(50, 0)
    asteroid.id = 999
    
    galaxy = MagicMock()
    # Mock get_celestial_body_by_id
    galaxy.get_celestial_body_by_id.side_effect = lambda bid: asteroid if bid == 999 else None

    # Mock systems structure for refinery lookup
    refinery_unit = MockUnit()
    refinery_unit.id = 1001
    refinery_unit.owner = player
    refinery_unit.in_system = "Sol"
    refinery_unit.in_hex = (0, 0)
    refinery_unit.position = Position(100, 0)
    refinery_unit.add_component(MetalRefineryComponent(refinery_unit))

    # Mock system.hexes.units
    mock_system = MagicMock()
    mock_hex = MagicMock()
    mock_hex.units = [unit, refinery_unit]
    mock_system.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_system}
    
    # Associate galaxy with game
    unit.game.galaxy = galaxy
    
    # 1. Create order: initially cargo is empty, so should spawn MineOrder
    order = ContinuousMineOrder(unit, {"target_id": 999})
    order.execute(galaxy)
    
    assert order.status == OrderStatus.IN_PROGRESS
    assert len(order.sub_orders) == 1
    assert order.sub_orders[0].order_type == OrderType.MINE
    assert order.sub_orders[0].parameters["target_id"] == 999

    # 2. Simulate MineOrder completion (cargo is full)
    mining_comp.raw_metal_cargo = 100.0
    order.sub_orders[0].status = OrderStatus.COMPLETED
    
    # Call update, which pops the completed sub-order and runs check_completion_conditions
    order.update(galaxy)
    
    # It should have popped MineOrder and spawned UnloadResourcesOrder
    assert len(order.sub_orders) == 1
    assert order.sub_orders[0].order_type == OrderType.UNLOAD_RESOURCES
    assert order.sub_orders[0].parameters["target_unit_id"] == 1001

    # 3. Simulate UnloadResourcesOrder completion (cargo is empty)
    mining_comp.raw_metal_cargo = 0.0
    order.sub_orders[0].status = OrderStatus.COMPLETED
    
    order.update(galaxy)
    
    # It should have popped UnloadResourcesOrder and spawned a new MineOrder
    assert len(order.sub_orders) == 1
    assert order.sub_orders[0].order_type == OrderType.MINE
    assert order.sub_orders[0].parameters["target_id"] == 999

def test_continuous_mining_refinery_types():
    player = MockPlayer()
    unit = MockUnit()
    unit.owner = player
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    
    commander = Commander(unit)
    unit.add_component(commander)
    
    mining_comp = MiningComponent(unit, max_cargo=100.0)
    unit.add_component(mining_comp)

    moon = Moon((0, 0), "Sol")
    moon.position = Position(50, 0)
    moon.id = 888

    galaxy = MagicMock()
    galaxy.get_celestial_body_by_id.side_effect = lambda bid: moon if bid == 888 else None

    # Setup a metal refinery and a crystal refinery
    ref_metal = MockUnit()
    ref_metal.id = 1001
    ref_metal.owner = player
    ref_metal.in_system = "Sol"
    ref_metal.in_hex = (0, 0)
    ref_metal.position = Position(100, 0)
    ref_metal.add_component(MetalRefineryComponent(ref_metal))

    ref_crystal = MockUnit()
    ref_crystal.id = 1002
    ref_crystal.owner = player
    ref_crystal.in_system = "Sol"
    ref_crystal.in_hex = (0, 0)
    ref_crystal.position = Position(200, 0)
    ref_crystal.add_component(CrystalRefineryComponent(ref_crystal))

    mock_system = MagicMock()
    mock_hex = MagicMock()
    mock_hex.units = [unit, ref_metal, ref_crystal]
    mock_system.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_system}
    
    unit.game.galaxy = galaxy

    # Cargo is full with crystal
    mining_comp.raw_crystal_cargo = 100.0
    
    order = ContinuousMineOrder(unit, {"target_id": 888})
    order.execute(galaxy)
    
    # Should spawn UnloadResourcesOrder targeting the crystal refinery (1002)
    assert len(order.sub_orders) == 1
    assert order.sub_orders[0].order_type == OrderType.UNLOAD_RESOURCES
    assert order.sub_orders[0].parameters["target_unit_id"] == 1002

def test_continuous_mining_no_refinery():
    player = MockPlayer()
    unit = MockUnit()
    unit.owner = player
    unit.in_system = "Sol"
    unit.in_hex = (0, 0)
    unit.position = Position(0, 0)
    
    commander = Commander(unit)
    unit.add_component(commander)
    
    mining_comp = MiningComponent(unit, max_cargo=100.0)
    unit.add_component(mining_comp)

    asteroid = Asteroid((0, 0), "Sol")
    asteroid.id = 999

    galaxy = MagicMock()
    galaxy.get_celestial_body_by_id.side_effect = lambda bid: asteroid if bid == 999 else None

    # Empty systems/refineries
    mock_system = MagicMock()
    mock_hex = MagicMock()
    mock_hex.units = [unit]
    mock_system.hexes = {(0, 0): mock_hex}
    galaxy.systems = {"Sol": mock_system}
    
    unit.game.galaxy = galaxy

    # Execute with full cargo -> should fail because no refinery found
    mining_comp.raw_metal_cargo = 100.0
    order = ContinuousMineOrder(unit, {"target_id": 999})
    order.execute(galaxy)
    
    assert order.status == OrderStatus.FAILED
