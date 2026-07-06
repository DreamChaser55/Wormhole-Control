import pytest
from unittest.mock import MagicMock
from entities import Unit
from game import Game
from constants import HullSize
from geometry import Position

def test_multi_unit_selection_sidebar_buttons():
    # Setup mock game and units
    mock_game = MagicMock()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = True
    mock_game.selected_objects = []
    mock_game.gui = MagicMock()
    
    player = MagicMock()
    player.name = "Player 1"
    
    unit1 = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Ship A",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    unit1.id = 101

    unit2 = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Ship B",
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    unit2.id = 102

    mock_game.selected_objects = [unit1, unit2]
    mock_game.players = [player]
    mock_game.current_player_index = 0
    mock_game.selected_component_name = None
    
    # Call update_side_bar_content
    Game.update_side_bar_content(mock_game)
    
    # Verify that gui.update_side_bar_content was called with select buttons for each unit
    mock_game.gui.update_side_bar_content.assert_called_once()
    data_list = mock_game.gui.update_side_bar_content.call_args[0][0]
    
    buttons = [d for d in data_list if d.get("type") == "button" and d.get("action_id") == "select_individual_unit"]
    assert len(buttons) == 2
    
    assert buttons[0]["text"] == "Select Ship A"
    assert buttons[0]["target_data"] == 101
    assert buttons[1]["text"] == "Select Ship B"
    assert buttons[1]["target_data"] == 102

def test_handle_gui_action_select_individual_unit():
    # Setup mock game, galaxy, and units
    mock_game = MagicMock()
    mock_game.galaxy = MagicMock()
    mock_game.sidebar_needs_update = False
    mock_game.selected_objects = []
    
    unit1 = MagicMock()
    unit1.id = 101
    
    # Mock get_unit_by_id
    mock_game.galaxy.get_unit_by_id.side_effect = lambda uid: unit1 if uid == 101 else None
    
    # Execute handle_gui_action with select_individual_unit action
    action = {
        'action': 'select_individual_unit',
        'unit_id': 101
    }
    
    Game.handle_gui_action(mock_game, action)
    
    # Verify selection is updated to only unit1, and sidebar is marked for update
    assert mock_game.selected_objects == [unit1]
    assert mock_game.sidebar_needs_update is True
