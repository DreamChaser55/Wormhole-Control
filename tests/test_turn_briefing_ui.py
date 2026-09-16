"""Modal input isolation, acknowledgement and shared AI presentation."""
import json
from dataclasses import replace

import pygame
import pygame_gui
import pytest

from display_config import DisplayConfig
from gui.turn_briefing_window import is_open, show_briefing, summary_html
from player_controller import PlayerController
from save_manager import serialize_game_state
from tests.support.campaigns import ship
from tests.test_turn_briefing import setup
from turn_briefing import begin_window, finish_window, initialize_campaign, record, summary_view
from app_preferences import AppPreferences, TurnSummaryMode


@pytest.mark.parametrize("mode", list(TurnSummaryMode))
@pytest.mark.parametrize("kind", ["significant", "omitted", "quiet", "economy"])
@pytest.mark.parametrize("acknowledged", [False, True])
def test_summary_mode_gate(game_factory, mode, kind, acknowledged):
    game = game_with_report(game_factory, count=int(kind == "significant"))
    game.preferences = AppPreferences(mode)
    state = game.current_player.briefing
    assert not state.acknowledged
    state.current = replace(state.current, omitted_count=int(kind == "omitted"),
                            economy=(("credits", 10 if kind == "economy" else 0),))
    state.acknowledged = acknowledged
    show_briefing(game.gui, game.current_player)
    expected = not acknowledged and (mode == TurnSummaryMode.ALWAYS or
               (mode == TurnSummaryMode.AUTOMATIC and kind in ("significant", "omitted")))
    assert is_open(game.gui) == expected
    assert state.acknowledged == acknowledged
    show_briefing(game.gui, game.current_player, automatic=False)
    assert is_open(game.gui)


def test_always_quiet_first_turn_handoff_and_load(game_factory, tmp_path):
    from game_settings import GameSettings, PlayerConfig
    game = game_factory()
    game.preferences = AppPreferences(TurnSummaryMode.ALWAYS)
    assert game.start_new_game(GameSettings(player_configs=[
        PlayerConfig("One", (0, 0, 255), team_id=1), PlayerConfig("Two", (255, 0, 0), team_id=2)]))
    assert is_open(game.gui)
    game.gui.process_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    path = tmp_path / "quiet.json"
    path.write_text(json.dumps(serialize_game_state(game)))
    assert game.load_game(str(path))
    assert not is_open(game.gui)
    game.end_turn()
    assert is_open(game.gui)

pytestmark = [
    pytest.mark.filterwarnings("error:Finding font with id:UserWarning"),
    pytest.mark.filterwarnings("error:Trying to pre-load font id:UserWarning"),
    pytest.mark.filterwarnings("error:Label Rect is too small:UserWarning"),
]


def game_with_report(game_factory, *, width=1280, height=720, count=1):
    game = game_factory(display_config=DisplayConfig(width, height, False))
    state = setup()
    for key, value in vars(state).items():
        if key != "display_config":
            setattr(game, key, value)
    game.galaxy.game = game
    unit = ship(game, name="Escort <One>")
    initialize_campaign(game)
    begin_window(game, unit.owner)
    for i in range(count):
        record(game, unit.owner, "combat", f"Hull damage (HP), engagement {i}", subject=unit, amount=4)
    finish_window(game, unit.owner)
    game.gui.show_game_ui()
    return game


@pytest.mark.parametrize("dismiss", ["escape", "continue", "close"])
def test_modal_blocks_gameplay_and_dismissal_does_not_end_turn(game_factory, monkeypatch, dismiss):
    game = game_with_report(game_factory)
    show_briefing(game.gui, game.current_player)
    dialog = game.gui.turn_briefing_window
    ended = []
    monkeypatch.setattr(game, "end_turn", lambda: ended.append(True))
    game.handle_gui_action({"action": "end_turn"})
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    pygame.event.post(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=game.gui.end_turn_button))
    pygame.event.post(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(0, 0)))
    game.input_processor.handle_input()
    assert not ended and is_open(game.gui)
    assert game.selected_objects == []
    event = (pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE) if dismiss == "escape" else
             pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=dialog.continue_button) if dismiss == "continue" else
             pygame.event.Event(pygame_gui.UI_WINDOW_CLOSE, ui_element=dialog.window))
    pygame.event.post(event)
    # A queued background action after dismissal must not execute in this frame.
    pygame.event.post(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=game.gui.end_turn_button))
    game.input_processor.handle_input()
    assert not is_open(game.gui) and game.current_player.briefing.acknowledged
    assert not ended
    game.gui.show_ingame_menu()
    game.handle_gui_action({"action": "show_turn_summary"})
    assert is_open(game.gui)
    game.gui.process_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert game.gui.end_turn_button.is_enabled


def test_comms_button_and_acknowledgement_preserve_read_semantics(game_factory):
    game = game_with_report(game_factory)
    player, sender = game.players
    game.send_message(sender, player.id, "Hello this round")
    show_briefing(game.gui, player)
    dialog = game.gui.turn_briefing_window
    assert len(game.get_unread_messages_for_player(player.id)) == 1
    game.gui.process_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert len(game.get_unread_messages_for_player(player.id)) == 1
    show_briefing(game.gui, player, automatic=False)
    dialog = game.gui.turn_briefing_window
    game.gui.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=dialog.comms_button))
    assert not is_open(game.gui)
    assert game.gui.is_communications_window_open()
    assert game.get_unread_messages_for_player(player.id) == []


def test_quiet_turn_skips_modal_but_can_be_reopened_and_handoff_closes_windows(game_factory):
    game = game_with_report(game_factory, count=0)
    show_briefing(game.gui, game.current_player)
    assert not is_open(game.gui)
    show_briefing(game.gui, game.current_player, automatic=False)
    assert is_open(game.gui)
    game.end_turn()  # Engine handoff, bypassing blocked human input.
    assert not is_open(game.gui)
    assert game.gui.communications_window is None


@pytest.mark.parametrize("mode", list(TurnSummaryMode))
@pytest.mark.parametrize("count", [0, 1])
@pytest.mark.parametrize("acknowledged", [True, False])
def test_loading_only_opens_unacknowledged_report(game_factory, tmp_path, acknowledged, mode, count):
    game = game_with_report(game_factory, count=count)
    game.preferences = AppPreferences(mode)
    game.current_player.briefing.acknowledged = acknowledged
    path = tmp_path / "briefing-save.json"
    path.write_text(json.dumps(serialize_game_state(game)))
    expected = summary_view(game.current_player)
    assert game.load_game(str(path))
    assert is_open(game.gui) is (not acknowledged and (mode == TurnSummaryMode.ALWAYS or
                                (mode == TurnSummaryMode.AUTOMATIC and count > 0)))
    assert summary_view(game.current_player) == expected


@pytest.mark.parametrize("mode", list(TurnSummaryMode))
@pytest.mark.parametrize("controller", [PlayerController.OPENAI, PlayerController.CODEX])
def test_automated_reports_remain_available_without_popup(game_factory, mode, controller):
    game = game_with_report(game_factory)
    game.preferences = AppPreferences(mode)
    game.current_player.controller = controller
    before = summary_view(game.current_player)
    show_briefing(game.gui, game.current_player)
    show_briefing(game.gui, game.current_player, automatic=False)
    assert not is_open(game.gui)
    assert summary_view(game.current_player) == before


@pytest.mark.parametrize("width,height,count", [(960, 540, 1), (1280, 720, 1), (1280, 720, 80), (1920, 1080, 80), (2560, 1440, 1), (2560, 1440, 80)])
def test_render_briefing_at_display_scales(game_factory, tmp_path, monkeypatch, width, height, count):
    game = game_with_report(game_factory, width=width, height=height, count=count)
    show_briefing(game.gui, game.current_player)
    dialog = game.gui.turn_briefing_window
    assert "&lt;One&gt;" in summary_html(game.current_player.briefing.current)
    game.gui.manager.set_visual_debug_mode(False)
    for _ in range(3):
        game.gui.manager.update(0.1)
    canvas = pygame.Surface((width, height))
    canvas.fill((8, 15, 24))
    game.gui.manager.draw_ui(canvas)
    pygame.image.save(canvas, str(tmp_path / "briefing.png"))
    assert canvas.get_rect().contains(dialog.window.get_abs_rect())
    assert dialog.window.get_abs_rect().contains(dialog.continue_button.get_abs_rect())
    if count > 1:
        assert dialog.text.scroll_bar is not None
        monkeypatch.setattr(pygame.mouse, "get_pos", lambda: dialog.text.get_abs_rect().center)
        game.gui.manager.update(0.1)
        pygame.event.post(pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-3))
        game.input_processor.handle_input()
        for _ in range(5):
            game.gui.manager.update(0.1)
        assert dialog.text.scroll_bar.start_percentage > 0
        assert is_open(game.gui)


def test_ai_request_and_repair_share_frozen_report_and_codex_observation(game_factory):
    from game_ai.adapters.base import RepairContext
    from game_ai.adapters.fake import FakePlanningProvider
    from game_ai.contracts import CommandBatch, TurnPlan
    from game_ai.coordinator import AgentTurnCoordinator
    from tests.support.ai import EMPTY_PATCH
    game = game_with_report(game_factory)
    player = game.current_player
    player.controller = PlayerController.OPENAI
    provider = FakePlanningProvider([TurnPlan((), CommandBatch((), True), EMPTY_PATCH)])
    coordinator = AgentTurnCoordinator(game, provider=provider)
    expected = summary_view(player)
    original = player.briefing.current
    try:
        assert coordinator.start_current_turn()
        coordinator._future.result(timeout=2)
        request = provider.requests[0]
        assert request.to_dict()["observation"]["turn_summary"] == expected
        repaired = coordinator._repair_request(RepairContext(None, ()))
        player.briefing.current = replace(player.briefing.current, entries=())
        assert repaired.observation["turn_summary"] == expected
        player.briefing.current = original
        player.controller = PlayerController.CODEX
        data = game.control_service._observation_data(player)
        assert data["observation"]["turn_summary"] == expected
    finally:
        coordinator.shutdown()
