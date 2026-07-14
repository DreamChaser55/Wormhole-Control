import pytest
from unittest.mock import MagicMock
from pygame import Color
from game import Game
from entities import Player

class DummyGame(Game):
    def __init__(self):
        self.players = []
        self.current_player_index = 0
        self.gui = MagicMock()

def test_update_player_turn_display():
    game = DummyGame()
    player1 = Player("Player 1", (0, 0, 255)) # BLUE
    game.players = [player1]
    game.current_player_index = 0
    
    game.update_player_turn_display()
    
    # Assert turn label is called with blue color hex code
    game.gui.update_turn_label.assert_called_once_with("<font color='#0000ff'>Player 1</font>'s Turn")
    # Assert player color indicator called
    game.gui.update_player_color_indicator.assert_called_once_with(Color(0, 0, 255))
    # Assert update_resource_display called
    game.gui.update_resource_display.assert_called_once_with(player1)

def test_update_player_turn_display_missing_color():
    game = DummyGame()
    # Mock player that has no color attribute
    class MockPlayerNoColor:
        def __init__(self):
            self.name = "Mock No Color"
    
    player = MockPlayerNoColor()
    game.players = [player]
    game.current_player_index = 0
    
    game.update_player_turn_display()
    
    # Assert default white color is used
    game.gui.update_turn_label.assert_called_once_with("<font color='#ffffff'>Mock No Color</font>'s Turn")
