import pytest
from unittest.mock import MagicMock
from entities import Unit
from geometry import Position
from constants import HullSize
from unit_components import FighterBayComponent, FighterWingComponent
from unit_orders import DockOrder
from game import Game
from tests.test_unit_components import MockPlayer

def test_fighter_bay_gui_data_generation():
    # Mock game
    game = MagicMock()
    player = MockPlayer("Player 1")
    game.players = [player]
    game.current_player_index = 0
    game.sidebar_needs_update = True
    
    # Mock system and galaxy
    system_mock = MagicMock()
    game.galaxy.systems = {"Sol": system_mock}
    
    # Create carrier unit
    carrier = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Carrier",
        hull_size=HullSize.HUGE,
        game=game
    )
    
    # Add FighterBayComponent
    fighter_bay = FighterBayComponent(carrier, max_slots=2)
    carrier.add_component(fighter_bay)
    
    # Add a docked wing
    docked_wing = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Docked Wing",
        hull_size=HullSize.STRIKECRAFT,
        game=game
    )
    docked_wing_comp = FighterWingComponent(docked_wing)
    docked_wing.add_component(docked_wing_comp)
    fighter_bay.docked_units.append(docked_wing)
    
    # Add a launched wing
    launched_wing = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Launched Wing",
        hull_size=HullSize.STRIKECRAFT,
        game=game
    )
    launched_wing_comp = FighterWingComponent(launched_wing)
    launched_wing.add_component(launched_wing_comp)
    fighter_bay.launched_units.append(launched_wing)
    
    # Setup selection
    game.selected_objects = [carrier]
    game.selected_component_name = "Fighter Bay"
    
    # Run update_side_bar_content
    import game as game_module
    original_profile = game_module.PROFILE
    game_module.PROFILE = False
    
    try:
        game.gui.update_side_bar_content = MagicMock()
        Game.update_side_bar_content(game)
        
        # Assert side bar content updated
        game.gui.update_side_bar_content.assert_called_once()
        data_list = game.gui.update_side_bar_content.call_args[0][0]
        
        # Check that "Docked Fighter Wings:" and "Launched Fighter Wings:" are present
        labels = [d.get("text") for d in data_list if d.get("type") == "label"]
        buttons = [d for d in data_list if d.get("type") == "button"]
        
        assert "Docked Fighter Wings:" in labels
        assert "Launched Fighter Wings:" in labels
        
        # Find Deploy button
        deploy_btn = next((b for b in buttons if b["action_id"] == "deploy_ship"), None)
        assert deploy_btn is not None
        assert deploy_btn["target_data"] == (carrier.id, docked_wing.id)
        
        # Find Recall button
        recall_btn = next((b for b in buttons if b["action_id"] == "recall_ship"), None)
        assert recall_btn is not None
        assert recall_btn["target_data"] == (carrier.id, launched_wing.id)
    finally:
        game_module.PROFILE = original_profile


def test_fighter_bay_gui_data_generation_non_owner():
    # Mock game
    game = MagicMock()
    player = MockPlayer("Player 1")
    enemy = MockPlayer("Player 2")
    game.players = [player] # Active player is player
    game.current_player_index = 0
    game.sidebar_needs_update = True
    
    # Mock system and galaxy
    system_mock = MagicMock()
    game.galaxy.systems = {"Sol": system_mock}
    
    # Create carrier unit owned by enemy
    carrier = Unit(
        owner=enemy,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Enemy Carrier",
        hull_size=HullSize.HUGE,
        game=game
    )
    
    # Add FighterBayComponent
    fighter_bay = FighterBayComponent(carrier, max_slots=2)
    carrier.add_component(fighter_bay)
    
    # Add a docked wing
    docked_wing = Unit(
        owner=enemy,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Enemy Wing",
        hull_size=HullSize.STRIKECRAFT,
        game=game
    )
    docked_wing_comp = FighterWingComponent(docked_wing)
    docked_wing.add_component(docked_wing_comp)
    fighter_bay.docked_units.append(docked_wing)
    
    # Setup selection
    game.selected_objects = [carrier]
    game.selected_component_name = "Fighter Bay"
    
    # Run update_side_bar_content
    import game as game_module
    original_profile = game_module.PROFILE
    game_module.PROFILE = False
    
    try:
        game.gui.update_side_bar_content = MagicMock()
        Game.update_side_bar_content(game)
        
        data_list = game.gui.update_side_bar_content.call_args[0][0]
        buttons = [d for d in data_list if d.get("type") == "button"]
        
        # Non-owner should see labels but NOT action buttons (like Deploy)
        assert not any(b["action_id"] == "deploy_ship" for b in buttons)
    finally:
        game_module.PROFILE = original_profile


def test_recall_ship_action_handling():
    game = MagicMock()
    player = MockPlayer("Player 1")
    game.players = [player]
    game.current_player_index = 0
    
    carrier = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Carrier",
        hull_size=HullSize.HUGE,
        game=game
    )
    fighter_bay = FighterBayComponent(carrier, max_slots=2)
    carrier.add_component(fighter_bay)
    
    launched_wing = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Launched Wing",
        hull_size=HullSize.STRIKECRAFT,
        game=game
    )
    launched_wing_comp = FighterWingComponent(launched_wing)
    launched_wing.add_component(launched_wing_comp)
    fighter_bay.launched_units.append(launched_wing)
    
    # Mock galaxy.get_unit_by_id
    game.galaxy.get_unit_by_id.side_effect = lambda uid: carrier if uid == carrier.id else (launched_wing if uid == launched_wing.id else None)
    
    # Trigger handle_gui_action
    action = {
        'action': 'recall_ship',
        'carrier_id': carrier.id,
        'launched_unit_id': launched_wing.id
    }
    
    # Mock Commander.add_order
    launched_wing.commander_component.add_order = MagicMock()
    
    Game.handle_gui_action(game, action)
    
    # Verify DockOrder is added to the launched wing
    launched_wing.commander_component.add_order.assert_called_once()
    order = launched_wing.commander_component.add_order.call_args[0][0]
    assert isinstance(order, DockOrder)
    assert order.parameters["target_carrier_id"] == carrier.id
