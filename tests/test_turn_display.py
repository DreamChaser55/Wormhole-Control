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
    
    # Assert turn label is called with blue color hex code and compact format
    game.gui.update_turn_label.assert_called_once_with("<font color='#0000ff'>Turn 1: Player 1</font>")
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
    game.gui.update_turn_label.assert_called_once_with("<font color='#ffffff'>Turn 1: Mock No Color</font>")

def test_update_player_turn_display_multiplayer():
    game = DummyGame()
    p1 = Player("Federation", (0, 0, 255))
    p2 = Player("Empire", (255, 0, 0))
    game.players = [p1, p2]
    game.turn_number = 3
    
    # Player 1 turn in round 3
    game.current_player_index = 0
    game.update_player_turn_display()
    game.gui.update_turn_label.assert_called_with("<font color='#0000ff'>Turn 3: Federation</font>")
    
    # Player 2 turn in round 3
    game.current_player_index = 1
    game.update_player_turn_display()
    game.gui.update_turn_label.assert_called_with("<font color='#ff0000'>Turn 3: Empire</font>")

def test_update_player_turn_display_ai_status():
    game = DummyGame()
    ai_player = Player("AI Opponent", (255, 0, 0), is_human=False)
    game.players = [ai_player]
    game.turn_number = 2
    game.ai_coordinator = MagicMock()

    # Case 1: thinking
    game.ai_coordinator.status_message = "thinking…"
    game.update_player_turn_display()
    game.gui.update_turn_label.assert_called_with("<font color='#ff0000'>Turn 2: AI Opponent (thinking…)</font>")

    # Case 2: revising
    game.ai_coordinator.status_message = "revising…"
    game.update_player_turn_display()
    game.gui.update_turn_label.assert_called_with("<font color='#ff0000'>Turn 2: AI Opponent (revising…)</font>")

    # Case 3: issuing
    game.ai_coordinator.status_message = "issuing…"
    game.update_player_turn_display()
    game.gui.update_turn_label.assert_called_with("<font color='#ff0000'>Turn 2: AI Opponent (issuing…)</font>")

    # Case 4: attention
    game.ai_coordinator.status_message = "attention"
    game.update_player_turn_display()
    game.gui.update_turn_label.assert_called_with("<font color='#ff0000'>Turn 2: AI Opponent (attention)</font>")

    # Case 5: default AI status fallback
    game.ai_coordinator.status_message = ""
    game.update_player_turn_display()
    game.gui.update_turn_label.assert_called_with("<font color='#ff0000'>Turn 2: AI Opponent (AI)</font>")
