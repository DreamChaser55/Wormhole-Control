import pygame
import pygame_gui
import pytest

from app_preferences import AppPreferences, TurnSummaryMode, load_preferences, save_preferences
from display_config import DisplayConfig
from gui.settings_dialog import MODE_LABELS, is_open
from tests.test_turn_briefing_ui import game_with_report


def press(gui, element):
    gui.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=element))


def select(gui, mode):
    gui.process_event(pygame.event.Event(pygame_gui.UI_DROP_DOWN_MENU_CHANGED,
                                       ui_element=gui.settings_dialog.dropdown, text=MODE_LABELS[mode]))


@pytest.mark.parametrize("ingame", [False, True])
def test_menu_entry_and_apply(game_factory, ingame):
    game = game_with_report(game_factory) if ingame else game_factory()
    gui = game.gui
    if ingame:
        gui.show_ingame_menu()
    press(gui, gui.ingame_settings_button if ingame else gui.settings_button)
    assert is_open(gui)
    select(gui, TurnSummaryMode.NEVER)
    press(gui, gui.settings_dialog.apply_button)
    assert not is_open(gui)
    assert game.preferences == load_preferences() == AppPreferences(TurnSummaryMode.NEVER)
    assert game_factory().preferences == game.preferences


@pytest.mark.parametrize("dismiss", ["cancel", "escape", "close"])
def test_cancel_and_input_isolation(game_factory, monkeypatch, dismiss):
    game = game_with_report(game_factory)
    gui = game.gui
    gui.show_settings_dialog()
    select(gui, TurnSummaryMode.ALWAYS)
    ended = []
    monkeypatch.setattr(game, "end_turn", lambda: ended.append(True))
    game.handle_gui_action({"action": "end_turn"})
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    pygame.event.post(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=gui.end_turn_button))
    dialog = gui.settings_dialog
    event = (pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE) if dismiss == "escape" else
             pygame.event.Event(pygame_gui.UI_WINDOW_CLOSE, ui_element=dialog.window) if dismiss == "close" else
             pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=dialog.cancel_button))
    pygame.event.post(event)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    game.input_processor.handle_input()
    assert not ended and not is_open(gui)
    assert game.preferences == AppPreferences()


def test_failed_apply_keeps_dialog_and_preference(game_factory, monkeypatch):
    game = game_factory()
    game.gui.show_settings_dialog()
    select(game.gui, TurnSummaryMode.NEVER)
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr("gui.settings_dialog.save_preferences", fail)
    press(game.gui, game.gui.settings_dialog.apply_button)
    assert is_open(game.gui)
    assert game.preferences == AppPreferences()
    assert "Could not save" in game.gui.settings_dialog.error.text


def test_campaign_transitions_preserve_preference_and_close_dialog(game_factory, tmp_path):
    from game_settings import GameSettings
    from save_manager import serialize_game_state
    import json

    save_preferences(AppPreferences(TurnSummaryMode.NEVER))
    game = game_factory()
    assert game.start_new_game(GameSettings())
    path = tmp_path / "campaign.json"
    path.write_text(json.dumps(serialize_game_state(game)))
    game.gui.show_settings_dialog()
    assert game.load_game(str(path))
    assert not is_open(game.gui)
    assert game.preferences.turn_summary_mode == TurnSummaryMode.NEVER
    game.gui.show_settings_dialog()
    assert game.start_new_game(GameSettings())
    assert not is_open(game.gui)
    assert game.preferences.turn_summary_mode == TurnSummaryMode.NEVER
    game.handle_gui_action({"action": "quit_to_main_menu"})
    assert game.preferences.turn_summary_mode == TurnSummaryMode.NEVER


@pytest.mark.filterwarnings("error:Label Rect is too small:UserWarning")
@pytest.mark.parametrize("width,height", [(960, 540), (1280, 720), (1920, 1080), (2560, 1440)])
def test_settings_layout(game_factory, tmp_path, width, height):
    game = game_factory(display_config=DisplayConfig(width, height, False))
    game.gui.show_settings_dialog()
    game.gui.manager.update(0.1)
    game.gui.manager.draw_ui(game.screen)
    dialog = game.gui.settings_dialog
    assert game.screen.get_rect().contains(dialog.window.rect)
    assert dialog.explanation.rect.bottom <= dialog.error.rect.top
    pygame.image.save(game.screen, str(tmp_path / "settings.png"))
