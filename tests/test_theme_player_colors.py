import pytest
from unittest.mock import MagicMock
from pygame import Color

from gui.theme_loader import create_player_scifi_theme_colors
from gui.layout_hud import update_hud_panel_colors
from game import Game
from entities import Player


def test_create_player_scifi_theme_colors_blue():
    bg_color, border_color = create_player_scifi_theme_colors((0, 0, 255))
    assert isinstance(bg_color, Color)
    assert isinstance(border_color, Color)
    assert bg_color.a == 200  # Semi-transparent alpha ~78%
    # Blue component should be higher in background color than red or green
    assert bg_color.b > bg_color.r
    assert bg_color.b > bg_color.g


def test_create_player_scifi_theme_colors_red():
    bg_color, border_color = create_player_scifi_theme_colors(Color(255, 0, 0))
    assert isinstance(bg_color, Color)
    assert isinstance(border_color, Color)
    assert bg_color.a == 200
    assert bg_color.r > bg_color.g


def test_create_player_scifi_theme_colors_invalid_fallback():
    bg_color, border_color = create_player_scifi_theme_colors("invalid_color_string")
    assert isinstance(bg_color, Color)
    assert isinstance(border_color, Color)
    assert bg_color.a == 200


def test_update_hud_panel_colors():
    mock_gui = MagicMock()
    mock_panel1 = MagicMock()
    mock_panel2 = MagicMock()
    mock_editor_panel = MagicMock()
    mock_gui.left_top_bar_panel = mock_panel1
    mock_gui.side_bar_info_panel = mock_panel2
    mock_gui.unit_editor_window._panel = mock_editor_panel
    mock_gui.right_top_bar_panel = None
    mock_gui.left_bottom_bar_panel = None
    mock_gui.ingame_menu_panel = None
    mock_gui.context_menu_panel = None
    mock_gui.main_menu_panel = None
    mock_gui.about_panel = None

    player_color = Color(255, 255, 0) # Yellow
    update_hud_panel_colors(mock_gui, player_color)

    assert mock_gui.current_player_bg_color is not None
    assert mock_gui.current_player_bg_color.a == 200
    mock_panel1.rebuild.assert_called_once()
    mock_panel2.rebuild.assert_called_once()
    mock_editor_panel.rebuild.assert_called_once()


class DummyGame(Game):
    def __init__(self):
        self.players = []
        self.current_player_index = 0
        self.gui = MagicMock()


def test_update_player_turn_display_triggers_theme_update():
    game = DummyGame()
    player1 = Player("Player 1", (0, 255, 0)) # Green
    game.players = [player1]
    game.current_player_index = 0

    game.update_player_turn_display()

    game.gui.update_player_turn_theme.assert_called_once_with(Color(0, 255, 0))

