import pytest
from unittest.mock import MagicMock
from entities import Unit
from unit_components import AntimatterStorage, Engines, Hyperdrive, HyperdriveType, AbilityComponent, AbilityType
from turn_processor import TurnProcessor
from geometry import Position, Circle
from utils import HexCoord
from tests.test_unit_components import MockPlayer, MockUnit
from constants import (
    DEFAULT_ANTIMATTER_CAPACITY,
    DEFAULT_ANTIMATTER_REGEN,
    ENGINE_ANTIMATTER_COST_PER_TURN,
    HYPERDRIVE_SYSTEM_JUMP_COST,
    HYPERDRIVE_HEX_JUMP_COST,
    HullSize
)

def test_antimatter_storage_defaults():
    player = MockPlayer()
    game = MagicMock()
    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Test Ship", hull_size=HullSize.MEDIUM, game=game)
    
    am_comp = unit.antimatter_component
    assert am_comp is not None
    assert am_comp.max_capacity == DEFAULT_ANTIMATTER_CAPACITY
    assert am_comp.current_amount == DEFAULT_ANTIMATTER_CAPACITY
    assert am_comp.regen_rate == DEFAULT_ANTIMATTER_REGEN

def test_antimatter_consumption_and_regen():
    player = MockPlayer()
    game = MagicMock()
    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Test Ship", hull_size=HullSize.MEDIUM, game=game)
    
    am_comp = unit.antimatter_component
    
    # Consume successful
    assert am_comp.consume(40.0) is True
    assert am_comp.current_amount == 60.0
    
    # Consume unsuccessful
    assert am_comp.consume(70.0) is False
    assert am_comp.current_amount == 60.0
    
    # Regen
    am_comp.regenerate()
    assert am_comp.current_amount == 60.0 + DEFAULT_ANTIMATTER_REGEN
    
    # Regen up to max
    am_comp.current_amount = 95.0
    am_comp.regenerate()
    assert am_comp.current_amount == DEFAULT_ANTIMATTER_CAPACITY

def test_sublight_movement_consumes_antimatter():
    game = MagicMock()
    player = MockPlayer()
    
    # We use a MockUnit but add the required components
    unit = MockUnit()
    unit.owner = player
    unit.position = Position(0, 0)
    
    am_comp = AntimatterStorage(unit)
    engines = Engines(unit, speed=10.0)
    engines.move_target = Position(100.0, 0.0)
    
    unit.components = {
        AntimatterStorage: am_comp,
        Engines: engines
    }
    
    system = MagicMock()
    system.get_all_units.return_value = [(unit, (0, 0))]
    game.galaxy.systems = {"Sol": system}
    
    tp = TurnProcessor(game)
    
    # Initial amount
    assert am_comp.current_amount == 100.0
    
    # Process turn movement
    tp._process_movement(player)
    
    # Handled movement & consumed antimatter
    assert unit.position.x == 10.0
    assert am_comp.current_amount == 100.0 - ENGINE_ANTIMATTER_COST_PER_TURN

def test_sublight_movement_fails_without_antimatter():
    game = MagicMock()
    player = MockPlayer()
    
    unit = MockUnit()
    unit.owner = player
    unit.position = Position(0, 0)
    
    am_comp = AntimatterStorage(unit)
    am_comp.current_amount = 1.0  # Less than ENGINE_ANTIMATTER_COST_PER_TURN (2.0)
    
    engines = Engines(unit, speed=10.0)
    engines.move_target = Position(100.0, 0.0)
    
    unit.components = {
        AntimatterStorage: am_comp,
        Engines: engines
    }
    
    system = MagicMock()
    system.get_all_units.return_value = [(unit, (0, 0))]
    game.galaxy.systems = {"Sol": system}
    
    tp = TurnProcessor(game)
    
    # Process turn movement
    tp._process_movement(player)
    
    # Unit should NOT move, and antimatter should NOT be consumed
    assert unit.position.x == 0.0
    assert am_comp.current_amount == 1.0

def test_hex_jump_consumes_antimatter():
    game = MagicMock()
    player = MockPlayer()
    
    unit = MockUnit()
    unit.owner = player
    unit.position = Position(0, 0)
    unit.in_hex = (0, 0)
    
    am_comp = AntimatterStorage(unit)
    hyperdrive = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=5)
    hyperdrive.hex_jump_target = ((0, 2), Position(0, 200))
    
    unit.components = {
        AntimatterStorage: am_comp,
        Hyperdrive: hyperdrive
    }
    
    system = MagicMock()
    system.get_all_units.return_value = [(unit, (0, 0))]
    system.hexes = {
        (0, 0): MagicMock(),
        (0, 2): MagicMock()
    }
    # Mock move_unit_between_hexes to succeed
    system.move_unit_between_hexes.return_value = True
    
    game.galaxy.systems = {"Sol": system}
    
    tp = TurnProcessor(game)
    
    # Run movement
    tp._process_movement(player)
    
    # Target Hex jump should consume antimatter
    assert am_comp.current_amount == 100.0 - HYPERDRIVE_HEX_JUMP_COST

def test_hex_jump_fails_without_antimatter():
    game = MagicMock()
    player = MockPlayer()
    
    unit = MockUnit()
    unit.owner = player
    unit.position = Position(0, 0)
    unit.in_hex = (0, 0)
    
    am_comp = AntimatterStorage(unit)
    am_comp.current_amount = 10.0  # Less than HYPERDRIVE_HEX_JUMP_COST (20)
    
    hyperdrive = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=5)
    hyperdrive.hex_jump_target = ((0, 2), Position(0, 200))
    
    unit.components = {
        AntimatterStorage: am_comp,
        Hyperdrive: hyperdrive
    }
    
    system = MagicMock()
    system.get_all_units.return_value = [(unit, (0, 0))]
    system.hexes = {
        (0, 0): MagicMock(),
        (0, 2): MagicMock()
    }
    system.move_unit_between_hexes.return_value = True
    
    game.galaxy.systems = {"Sol": system}
    
    tp = TurnProcessor(game)
    
    # Run movement
    tp._process_movement(player)
    
    # Jump should fail and not consume antimatter
    assert am_comp.current_amount == 10.0
    assert hyperdrive.jump_status == hyperdrive.jump_status.ERROR

def test_ability_antimatter_consumption():
    player = MockPlayer()
    game = MagicMock()
    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Test Ship", hull_size=HullSize.MEDIUM, game=game)
    
    # Setup ability component
    ability_comp = AbilityComponent(unit, [AbilityType.ADAPTIVE_FORCEFIELD])
    unit.add_component(ability_comp)
    
    am_comp = unit.antimatter_component
    assert am_comp is not None
    
    # adaptive forcefield cost is 20
    assert ability_comp.can_use(AbilityType.ADAPTIVE_FORCEFIELD) is True
    
    # Test activate consumes antimatter
    success = ability_comp.activate(AbilityType.ADAPTIVE_FORCEFIELD, game.galaxy)
    assert success is True
    assert am_comp.current_amount == 100.0 - 20
    
    # Set antimatter low
    am_comp.current_amount = 5.0
    ability_comp.abilities[AbilityType.ADAPTIVE_FORCEFIELD].cooldown_remaining = 0
    ability_comp.abilities[AbilityType.ADAPTIVE_FORCEFIELD].is_active = False
    
    # Should not be able to use anymore
    assert ability_comp.can_use(AbilityType.ADAPTIVE_FORCEFIELD) is False
    success2 = ability_comp.activate(AbilityType.ADAPTIVE_FORCEFIELD, game.galaxy)
    assert success2 is False
    assert am_comp.current_amount == 5.0

def test_system_jump_consumes_antimatter():
    game = MagicMock()
    player = MockPlayer()
    
    unit = MockUnit()
    unit.owner = player
    unit.position = Position(0, 0)
    unit.in_hex = (1, 1)
    unit.in_system = "Sol"
    
    am_comp = AntimatterStorage(unit)
    hyperdrive = Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5)
    
    # Mock wormhole objects
    wh_sol = MagicMock()
    wh_sol.exit_system_name = "Vega"
    wh_sol.exit_wormhole_id = 2
    wh_sol.stability = 100
    
    wh_vega = MagicMock()
    wh_vega.in_system = "Vega"
    wh_vega.in_hex = (-1, -1)
    wh_vega.position = Position(10, 10)
    
    hyperdrive.wormhole_jump_target = wh_sol
    
    unit.components = {
        AntimatterStorage: am_comp,
        Hyperdrive: hyperdrive
    }
    
    sol_system = MagicMock()
    sol_system.name = "Sol"
    sol_system.get_all_units.return_value = [(unit, (1, 1))]
    
    vega_system = MagicMock()
    vega_system.name = "Vega"
    
    game.galaxy.systems = {"Sol": sol_system, "Vega": vega_system}
    game.galaxy.wormholes = {2: wh_vega}
    
    # Mock move_unit_between_systems to succeed
    game.galaxy.move_unit_between_systems.return_value = True
    
    tp = TurnProcessor(game)
    
    # Run movement
    tp._process_movement(player)
    
    # Target system jump should consume antimatter
    assert am_comp.current_amount == 100.0 - HYPERDRIVE_SYSTEM_JUMP_COST

def test_system_jump_fails_without_antimatter():
    game = MagicMock()
    player = MockPlayer()
    
    unit = MockUnit()
    unit.owner = player
    unit.position = Position(0, 0)
    unit.in_hex = (1, 1)
    unit.in_system = "Sol"
    
    am_comp = AntimatterStorage(unit)
    am_comp.current_amount = 40.0  # Less than HYPERDRIVE_SYSTEM_JUMP_COST (50)
    
    hyperdrive = Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5)
    
    # Mock wormhole objects
    wh_sol = MagicMock()
    wh_sol.exit_system_name = "Vega"
    wh_sol.exit_wormhole_id = 2
    wh_sol.stability = 100
    
    wh_vega = MagicMock()
    wh_vega.in_system = "Vega"
    wh_vega.in_hex = (-1, -1)
    wh_vega.position = Position(10, 10)
    
    hyperdrive.wormhole_jump_target = wh_sol
    
    unit.components = {
        AntimatterStorage: am_comp,
        Hyperdrive: hyperdrive
    }
    
    sol_system = MagicMock()
    sol_system.name = "Sol"
    sol_system.get_all_units.return_value = [(unit, (1, 1))]
    
    vega_system = MagicMock()
    vega_system.name = "Vega"
    
    game.galaxy.systems = {"Sol": sol_system, "Vega": vega_system}
    game.galaxy.wormholes = {2: wh_vega}
    
    # Mock move_unit_between_systems
    game.galaxy.move_unit_between_systems.return_value = True
    
    tp = TurnProcessor(game)
    
    # Run movement
    tp._process_movement(player)
    
    # Jump should fail and not consume antimatter
    assert am_comp.current_amount == 40.0
    assert hyperdrive.jump_status == hyperdrive.jump_status.ERROR
