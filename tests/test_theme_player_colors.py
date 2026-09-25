from display_config import DisplayConfig
from unittest.mock import MagicMock
from pygame import Color
from gui.theme_loader import create_player_scifi_theme_colors
from gui.layout_hud import update_hud_panel_colors
from game import Game
from domain.players import Player


def test_create_player_scifi_theme_colors_blue():
    bg_color, border_color = create_player_scifi_theme_colors((0, 0, 255))
    assert isinstance(bg_color, Color)
    assert isinstance(border_color, Color)
    assert bg_color.a == 255
    # Blue component should be higher in background color than red or green
    assert bg_color.b > bg_color.r
    assert bg_color.b > bg_color.g


def test_create_player_scifi_theme_colors_red():
    bg_color, border_color = create_player_scifi_theme_colors(Color(255, 0, 0))
    assert isinstance(bg_color, Color)
    assert isinstance(border_color, Color)
    assert bg_color.a == 255
    assert bg_color.r > bg_color.g


def test_create_player_scifi_theme_colors_invalid_fallback():
    bg_color, border_color = create_player_scifi_theme_colors("invalid_color_string")
    assert isinstance(bg_color, Color)
    assert isinstance(border_color, Color)
    assert bg_color.a == 255


def test_update_hud_panel_colors():
    mock_gui = MagicMock()
    mock_gui.display_config = DisplayConfig()
    mock_panel1 = MagicMock()
    mock_panel2 = MagicMock()
    mock_editor_panel = MagicMock()
    mock_gui.top_bar_panel = mock_panel1
    mock_gui.side_bar_info_panel = mock_panel2
    mock_gui.unit_editor_window._panel = mock_editor_panel
    mock_gui.bottom_bar_panel = None
    mock_gui.ingame_menu_panel = None
    mock_gui.context_menu_panel = None
    mock_gui.main_menu_panel = None
    mock_gui.about_panel = None

    player_color = Color(255, 255, 0) # Yellow
    update_hud_panel_colors(mock_gui, player_color)

    assert mock_gui.current_player_bg_color is not None
    assert mock_gui.current_player_bg_color.a == 255
    mock_panel1.rebuild.assert_called_once()
    mock_panel2.rebuild.assert_called_once()
    mock_editor_panel.rebuild.assert_called_once()


class DummyGame(Game):
    display_config = DisplayConfig()
    def __init__(self):
        self.players = []
        self.current_player_index = 0
        self.gui = MagicMock()
        self.gui.display_config = DisplayConfig()


def test_update_player_turn_display_triggers_theme_update():
    game = DummyGame()
    player1 = Player("Player 1", (0, 255, 0)) # Green
    game.players = [player1]
    game.current_player_index = 0

    game.update_player_turn_display()

    game.gui.update_player_turn_theme.assert_called_once_with(Color(0, 255, 0))


def test_turn_briefing_window_theme_color(pygame_context):
    import pygame
    from turn_briefing import BriefingState
    from gui.turn_briefing_window import TurnBriefingWindow
    from gui.theme_loader import build_ui_manager

    cfg = DisplayConfig(1280, 720)
    manager = build_ui_manager(cfg)
    mock_gui = MagicMock()
    mock_gui.manager = manager
    mock_gui.display_config = cfg
    mock_gui.screen_res = pygame.Vector2(1280, 720)
    mock_gui.scale_x = 1.0
    mock_gui.scale_y = 1.0
    mock_gui.current_player_bg_color = None
    mock_gui.current_player_border_color = None

    player = Player("Player 1", (0, 200, 255))
    player.briefing = BriefingState()
    expected_bg, expected_border = create_player_scifi_theme_colors(player.color)

    win = TurnBriefingWindow(mock_gui, player)
    try:
        assert win.window.background_colour == expected_bg
        assert win.window.border_colour == expected_border
    finally:
        win.window.kill()


def test_communications_window_theme_color(pygame_context):
    import pygame
    from gui.communications_window import CommunicationsWindow
    from gui.theme_loader import build_ui_manager

    cfg = DisplayConfig(1280, 720)
    manager = build_ui_manager(cfg)
    player = Player("Player 1", (255, 100, 50))
    player.id = 1
    mock_game = MagicMock()
    mock_game.current_player = player
    mock_game.players = [player]

    mock_gui = MagicMock()
    mock_gui.manager = manager
    mock_gui.display_config = cfg
    mock_gui.screen_res = pygame.Vector2(1280, 720)
    mock_gui.scale_x = 1.0
    mock_gui.scale_y = 1.0
    mock_gui.game_instance = mock_game
    mock_gui.current_player_bg_color = None
    mock_gui.current_player_border_color = None

    expected_bg, expected_border = create_player_scifi_theme_colors(player.color)

    win = CommunicationsWindow(mock_gui)
    try:
        assert win.window.background_colour == expected_bg
        assert win.window.border_colour == expected_border
    finally:
        win.window.kill()


def test_update_hud_panel_colors_updates_briefing_and_comms():
    mock_gui = MagicMock()
    mock_gui.display_config = DisplayConfig()
    mock_gui.unit_editor_window = None
    mock_gui.top_bar_panel = None
    mock_gui.bottom_bar_panel = None
    mock_gui.side_bar_info_panel = None
    mock_gui.ingame_menu_panel = None
    mock_gui.context_menu_panel = None
    mock_gui.main_menu_panel = None
    mock_gui.about_panel = None

    mock_briefing_win = MagicMock()
    mock_briefing_win.alive.return_value = True
    mock_gui.turn_briefing_window.window = mock_briefing_win

    mock_comms_win = MagicMock()
    mock_comms_win.alive.return_value = True
    mock_gui.communications_window.window = mock_comms_win

    player_color = Color(255, 0, 128)
    expected_bg, expected_border = create_player_scifi_theme_colors(player_color)
    update_hud_panel_colors(mock_gui, player_color)

    assert mock_briefing_win.background_colour == expected_bg
    assert mock_briefing_win.border_colour == expected_border
    mock_briefing_win.rebuild.assert_called_once()

    assert mock_comms_win.background_colour == expected_bg
    assert mock_comms_win.border_colour == expected_border
    mock_comms_win.rebuild.assert_called_once()
