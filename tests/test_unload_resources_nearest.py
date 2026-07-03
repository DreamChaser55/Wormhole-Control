import pytest
from unittest.mock import MagicMock
from geometry import Position
from unit_components import MiningComponent, MetalRefineryComponent, CrystalRefineryComponent, Commander
from tests.test_unit_components import MockUnit, MockPlayer
from unit_orders import OrderType, UnloadResourcesOrder
from constants import HullSize

class DummyGame:
    def __init__(self):
        self.galaxy = MagicMock()
        self.sidebar_needs_update = False
        self.selected_component_name = None

def test_unload_resources_nearest_no_cargo():
    # Setup mock unit, mining component with 0 cargo
    unit = MockUnit()
    mining_comp = MiningComponent(unit, max_cargo=100.0)
    unit.add_component(mining_comp)
    
    # Get sidebar data: should not contain the unload button
    game = DummyGame()
    sidebar_data = mining_comp.get_sidebar_data(game)
    buttons = [item for item in sidebar_data if item.get('type') == 'button']
    unload_btn = next((b for b in buttons if b.get('action_id') == 'unload_resources_nearest'), None)
    assert unload_btn is None

def test_unload_resources_nearest_with_cargo():
    # Setup mock unit, mining component with cargo
    unit = MockUnit()
    mining_comp = MiningComponent(unit, max_cargo=100.0)
    mining_comp.raw_metal_cargo = 20.0
    unit.add_component(mining_comp)
    
    # Get sidebar data: should contain the unload button
    game = DummyGame()
    sidebar_data = mining_comp.get_sidebar_data(game)
    buttons = [item for item in sidebar_data if item.get('type') == 'button']
    unload_btn = next((b for b in buttons if b.get('action_id') == 'unload_resources_nearest'), None)
    assert unload_btn is not None
    assert unload_btn['target_data'] == unit.id

def test_handle_gui_action_unload_resources_nearest():
    # Setup player
    player = MockPlayer()
    
    # Setup miner unit
    miner = MockUnit()
    miner.id = 1
    miner.owner = player
    miner.in_system = "Sol"
    miner.in_hex = (0, 0)
    miner.position = Position(0, 0)
    miner.hull_size = HullSize.SMALL
    
    commander = Commander(miner)
    miner.add_component(commander)
    
    mining_comp = MiningComponent(miner, max_cargo=100.0)
    mining_comp.raw_metal_cargo = 50.0
    mining_comp.raw_crystal_cargo = 50.0
    miner.add_component(mining_comp)

    # Setup close metal refinery
    ref_metal = MockUnit()
    ref_metal.id = 2
    ref_metal.owner = player
    ref_metal.in_system = "Sol"
    ref_metal.in_hex = (0, 1)
    ref_metal.position = Position(0, 0)
    ref_metal.add_component(MetalRefineryComponent(ref_metal))
    
    # Setup far metal refinery
    ref_metal_far = MockUnit()
    ref_metal_far.id = 3
    ref_metal_far.owner = player
    ref_metal_far.in_system = "Vega"
    ref_metal_far.in_hex = (0, 0)
    ref_metal_far.position = Position(0, 0)
    ref_metal_far.add_component(MetalRefineryComponent(ref_metal_far))

    # Setup crystal refinery
    ref_crystal = MockUnit()
    ref_crystal.id = 4
    ref_crystal.owner = player
    ref_crystal.in_system = "Sol"
    ref_crystal.in_hex = (0, 2)
    ref_crystal.position = Position(0, 0)
    ref_crystal.add_component(CrystalRefineryComponent(ref_crystal))
    
    # Mock systems and units
    system_sol = MagicMock()
    hex_sol_00 = MagicMock()
    hex_sol_00.units = [miner]
    hex_sol_01 = MagicMock()
    hex_sol_01.units = [ref_metal]
    hex_sol_02 = MagicMock()
    hex_sol_02.units = [ref_crystal]
    system_sol.hexes = {
        (0, 0): hex_sol_00,
        (0, 1): hex_sol_01,
        (0, 2): hex_sol_02,
    }
    
    system_vega = MagicMock()
    hex_vega_00 = MagicMock()
    hex_vega_00.units = [ref_metal_far]
    system_vega.hexes = {
        (0, 0): hex_vega_00
    }
    
    game = DummyGame()
    
    # Mock Galaxy structure
    units_dict = {1: miner, 2: ref_metal, 3: ref_metal_far, 4: ref_crystal}
    game.galaxy.get_unit_by_id.side_effect = lambda uid: units_dict.get(uid)
    game.galaxy.systems = {
        "Sol": system_sol,
        "Vega": system_vega
    }
    game.galaxy.system_graph = {
        "Sol": {"Vega": HullSize.HUGE},
        "Vega": {"Sol": HullSize.HUGE}
    }
    
    # Execute handle_gui_action with shift_pressed=False
    from game import Game
    action = {
        'action': 'unload_resources_nearest',
        'unit_id': miner.id,
        'shift_pressed': False
    }
    
    # Run handle_gui_action
    Game.handle_gui_action(game, action)
    
    # Should have cleared previous orders and added 2 orders (1 active, 1 queued)
    assert commander.get_active_orders_count() == 2
    order_metal = commander.current_order
    order_crystal = commander.orders_queue[0]
    
    assert order_metal.order_type == OrderType.UNLOAD_RESOURCES
    # Nearest metal refinery is ref_metal (Sol, (0,1)), not ref_metal_far (Vega)
    assert order_metal.parameters['target_unit_id'] == ref_metal.id
    
    assert order_crystal.order_type == OrderType.UNLOAD_RESOURCES
    assert order_crystal.parameters['target_unit_id'] == ref_crystal.id

def test_handle_gui_action_unload_resources_nearest_shift():
    # Setup player and miner with cargo and one refinery
    player = MockPlayer()
    miner = MockUnit()
    miner.id = 1
    miner.owner = player
    miner.in_system = "Sol"
    miner.in_hex = (0, 0)
    miner.position = Position(0, 0)
    miner.hull_size = HullSize.SMALL
    
    commander = Commander(miner)
    miner.add_component(commander)
    
    # Pre-add a dummy order to order queue
    dummy_order = MagicMock()
    commander.add_order(dummy_order)
    assert commander.get_active_orders_count() == 1
    assert commander.current_order == dummy_order
    
    mining_comp = MiningComponent(miner, max_cargo=100.0)
    mining_comp.raw_metal_cargo = 50.0
    miner.add_component(mining_comp)

    # Setup metal refinery
    ref_metal = MockUnit()
    ref_metal.id = 2
    ref_metal.owner = player
    ref_metal.in_system = "Sol"
    ref_metal.in_hex = (0, 1)
    ref_metal.position = Position(0, 0)
    ref_metal.add_component(MetalRefineryComponent(ref_metal))
    
    # Mock systems and units
    system_sol = MagicMock()
    hex_sol_00 = MagicMock()
    hex_sol_00.units = [miner]
    hex_sol_01 = MagicMock()
    hex_sol_01.units = [ref_metal]
    system_sol.hexes = {
        (0, 0): hex_sol_00,
        (0, 1): hex_sol_01,
    }
    
    game = DummyGame()
    units_dict = {1: miner, 2: ref_metal}
    game.galaxy.get_unit_by_id.side_effect = lambda uid: units_dict.get(uid)
    game.galaxy.systems = {"Sol": system_sol}
    game.galaxy.system_graph = {"Sol": {}}
    
    # Shift pressed is True
    from game import Game
    action = {
        'action': 'unload_resources_nearest',
        'unit_id': miner.id,
        'shift_pressed': True
    }
    Game.handle_gui_action(game, action)
    
    # Queue length should be 2 (dummy_order + new unload order)
    assert commander.get_active_orders_count() == 2
    assert commander.current_order == dummy_order
    assert commander.orders_queue[0].order_type == OrderType.UNLOAD_RESOURCES
