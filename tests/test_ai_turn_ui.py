"""Dashboard privacy, responsive layout and presentation-only completion holds."""

import asyncio
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pygame
import pygame_gui
import pytest

from display_config import DisplayConfig
from game_actions.turn_presentation import ApplicationTurnPresentation, ai_summary_active, ai_summary_snapshot
from game_ai.adapters.fake import FakePlanningProvider
from game_ai.contracts import CommandBatch, TurnPlan
from game_ai.coordinator import AgentTurnCoordinator
from game_ai.progress import AIAttemptStatistics, AITurnProgress
from gui.turn_briefing_window import is_open, show_briefing
from player_controller import PlayerController
from rendering.ai_turn_renderer import AITurnRenderer
from tests.support.ai import EMPTY_PATCH
from tests.support.campaigns import campaign, ship
from tests.support.pygame_runtime import drain_events
from turn_briefing import finish_window, initialize_campaign


def progress(phase="complete", count=1, name="AI One"):
    attempts = tuple(AIAttemptStatistics.from_usage(
        attempt_index=i, started_at=10 + i, finished_at=11 + i, latency_seconds=1 + i,
        status="accepted" if i == count - 1 else "invalid_output",
        usage={"input_tokens": 1250, "output_tokens": 400, "total_tokens": 1650,
               "cached_input_tokens": 1000, "uncached_input_tokens": 250, "reasoning_tokens": 300}
              if i != 1 else {}) for i in range(count))
    return AITurnProgress(
        "integrity", "agent", 0, name, 7, "gpt-6-luna", "high", phase, 10, 21, 22,
        repair_attempt=count if phase in {"requesting", "cancelling"} else max(0, count - 1),
        repair_limit=5, attempts=attempts,
        phase_durations=(("scheduled", .5), ("preparing", .25), ("requesting", 8), ("checking", .5)),
        error_category="commit" if phase == "error" else None,
    )


class RecordingRenderer(AITurnRenderer):
    def __init__(self, game):
        super().__init__(game)
        self.captions = []

    def _text(self, text, *args, **kwargs):
        rect = super()._text(text, *args, **kwargs)
        self.captions.append((text, rect))
        return rect


@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080), (2560, 1440)])
@pytest.mark.parametrize("phase", ["scheduled", "requesting", "cancelling", "error", "complete", "waiting_for_codex"])
def test_dashboard_fits_all_states_and_resolutions(pygame_context, size, phase, tmp_path):
    screen = pygame.display.set_mode(size)
    game = SimpleNamespace(screen=screen, display_config=DisplayConfig(*size, False),
                           private_plan="SECRET PLAN", last_error="SECRET OUTPUT")
    renderer = RecordingRenderer(game)
    count = 6 if phase in {"error", "complete"} else 5 if phase in {"requesting", "cancelling"} else 0
    snapshot = progress(phase, count, "W" * 80)
    renderer.draw(snapshot)
    assert all(screen.get_rect().contains(rect) for _, rect in renderer.captions)
    names = [text for text, _ in renderer.captions if text.startswith("WW")]
    assert "".join(names) == snapshot.player_name
    text = "\n".join(text for text, _ in renderer.captions)
    assert "SECRET" not in text and snapshot.phase_label in text
    assert ("partial" in text) == (count > 1)
    assert "Available after response" in text or count > 0 or phase == "waiting_for_codex"
    fonts = tuple(renderer._fonts.values())
    renderer.draw(snapshot)
    assert tuple(renderer._fonts.values()) == fonts
    pygame.image.save(screen, str(tmp_path / f"{phase}-{size[0]}.png"))


def test_codex_waiting_uses_no_inference_counters(pygame_context):
    game = SimpleNamespace(screen=pygame.display.get_surface(), display_config=DisplayConfig(1280, 720, False),
        current_player=SimpleNamespace(name="Codex player", controller=PlayerController.CODEX, agent_id="codex"),
        campaign_id="campaign", turn_number=3)
    renderer = RecordingRenderer(game)
    renderer.draw()
    text = "\n".join(text for text, _ in renderer.captions)
    assert "Waiting for Codex" in text
    assert "External controller" in text and "Reasoning: Unavailable" in text
    assert "gpt-6-luna" not in text
    assert "Codex inference statistics are not available to the game." in text


def test_completed_dashboard_explains_known_totals_and_renders_preview(pygame_context, tmp_path):
    screen = pygame.display.set_mode((1280, 720))
    renderer = RecordingRenderer(SimpleNamespace(screen=screen, display_config=DisplayConfig(1280, 720, False)))
    snapshot = progress("complete", 1, "Orion Assembly")
    renderer.draw(snapshot)
    captions = [text for text, _ in renderer.captions]
    assert "1,250" in captions and "400" in captions and "1,650" in captions
    assert "1,000" in captions and "250" in captions and "300" in captions
    assert all("partial" not in text for text in captions)
    pygame.image.save(screen, str(tmp_path / "dashboard.png"))


@pytest.fixture
def presenter(pygame_context):
    clock = Mock(return_value=10.0)
    game = SimpleNamespace(game_started=True, campaign_id="integrity", players=[], defeat_notice=(0, ()))
    presentation = game.turn_presentation = ApplicationTurnPresentation(game, clock=clock)
    presentation.present_ai_progress(progress())
    return game, presentation, clock


def test_summary_lifetime_begins_when_drawn_and_dismissal_does_not_advance(presenter):
    game, presentation, clock = presenter
    game.end_turn = Mock()
    clock.return_value = 100
    assert ai_summary_active(game)  # Time spent resolving/behind another screen does not count.
    presentation.mark_ai_summary_visible()
    clock.return_value = 101.99
    assert ai_summary_snapshot(game).elapsed_seconds == 12
    assert ai_summary_active(game)  # Polling must not restart the deadline.
    clock.return_value = 102
    assert not ai_summary_active(game) and not game.end_turn.called
    presentation.present_ai_progress(progress())
    presentation.dismiss_ai_summary()
    assert not ai_summary_active(game) and not game.end_turn.called


def test_defeat_notice_postpones_and_pauses_summary(presenter, monkeypatch):
    game, presentation, clock = presenter
    ticks = Mock(return_value=0)
    monkeypatch.setattr(pygame.time, "get_ticks", ticks)
    game.defeat_notice = (4000, ("Defeated player",))
    clock.return_value = 20
    assert ai_summary_active(game)
    ticks.return_value = 4000
    presentation.mark_ai_summary_visible()
    clock.return_value = 20.5
    assert ai_summary_active(game)
    game.defeat_notice = (8000, ("Another player",))
    assert ai_summary_active(game)  # Pause immediately, while still retaining the summary.
    clock.return_value = 40
    assert ai_summary_active(game)
    ticks.return_value = 8000
    presentation.mark_ai_summary_visible()
    clock.return_value = 41.49
    assert ai_summary_active(game)
    clock.return_value = 41.51
    assert not ai_summary_active(game)


@pytest.mark.parametrize("change", ["campaign", "menu", "campaign_ended", "reset"])
def test_campaign_lifecycle_clears_summary(presenter, change):
    game, presentation, _ = presenter
    if change == "campaign":
        game.campaign_id = "replacement"
    elif change == "menu":
        game.game_started = False
    elif change == "campaign_ended":
        game.players = [SimpleNamespace(defeated=True)]
    else:
        presentation.present_ai_progress(None)
    assert ai_summary_snapshot(game) is None


def app(game_factory, *, controller=PlayerController.HUMAN, provider=None):
    game = game_factory(display_config=DisplayConfig(1280, 720, False))
    state = campaign()
    for key, value in vars(state).items():
        if key != "display_config":
            setattr(game, key, value)
    game.galaxy.game = game
    ship(game, owner=0)
    ship(game, owner=1)
    game.current_player.controller = controller
    initialize_campaign(game)
    finish_window(game, game.current_player)
    game.gui.show_game_ui()
    game.ai_coordinator.shutdown()
    clock = Mock(return_value=10.0)
    presentation = ApplicationTurnPresentation(game, clock=clock)
    game.turn_presentation = game.turn_processor.presentation = presentation
    game.ai_coordinator = AgentTurnCoordinator(game,
        provider=provider or FakePlanningProvider([TurnPlan((), CommandBatch((), True), EMPTY_PATCH)]),
        clock=clock, on_progress=presentation.present_ai_progress)
    drain_events()
    return game, clock


@pytest.mark.parametrize("view", ["galaxy", "system", "sector"])
def test_summary_blocks_gameplay_and_enter_cannot_end_next_turn(game_factory, monkeypatch, view):
    game, _ = app(game_factory)
    game.view_mode = view
    game.turn_presentation.present_ai_progress(progress())
    game.renderer.draw()
    ended = Mock()
    monkeypatch.setattr(game, "end_turn", ended)
    panning, mouse = Mock(), Mock()
    monkeypatch.setattr("input_processor.processor.handle_keyboard_panning", panning)
    monkeypatch.setattr("input_processor.processor.handle_mouse_button_down", mouse)
    index, turn = game.current_player_index, game.turn_number
    assert game.is_ai_input_locked()
    game.handle_gui_action({"action": "end_turn"})
    for event in (
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g),
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(500, 400)),
        pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1),
        pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=game.gui.end_turn_button),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e),
    ):
        pygame.event.post(event)
    game.input_processor.handle_input()
    assert not panning.called and not mouse.called and not ended.called
    assert game.view_mode == view and (game.current_player_index, game.turn_number) == (index, turn)
    assert not ai_summary_active(game) and not game.is_ai_input_locked()


def test_summary_enter_does_not_acknowledge_underlying_briefing(game_factory):
    game, _ = app(game_factory)
    show_briefing(game.gui, game.current_player, automatic=False)
    assert is_open(game.gui)
    game.turn_presentation.present_ai_progress(progress())
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
    game.input_processor.handle_input()
    assert not ai_summary_active(game) and is_open(game.gui)
    assert not game.current_player.briefing.acknowledged


@pytest.mark.parametrize("controller", [PlayerController.HUMAN, PlayerController.OPENAI, PlayerController.CODEX])
def test_real_handoff_resolves_once_before_showing_summary(game_factory, monkeypatch, controller):
    game, clock = app(game_factory, controller=PlayerController.OPENAI)
    game.players[1].controller = controller
    calls = Mock(wraps=game.turn_processor.end_turn)
    monkeypatch.setattr(game.turn_processor, "end_turn", calls)
    assert game.ai_coordinator.start_current_turn()
    game.ai_coordinator._future.result(timeout=2)
    clock.return_value = 15
    game.ai_coordinator.update()
    assert game.current_player_index == 1 and calls.call_count == 1
    summary = ai_summary_snapshot(game)
    assert summary.phase == "complete" and summary.player_name == "One"
    assert summary.elapsed_seconds == 5
    active = game.ai_coordinator.progress_snapshot()
    assert (active is not None) == (controller == PlayerController.OPENAI)
    if active:
        assert active.phase == "scheduled" and not active.attempts and active.player_name == "Two"
    state = game.control_service._public_state()
    assert state["current_player"]["name"] == "Two" and not state["attention_required"]
    assert state["codex_ready"] == (controller == PlayerController.CODEX)
    game.renderer.draw()
    clock.return_value = 17.01
    assert not ai_summary_active(game)
    game.ai_coordinator.update()
    assert calls.call_count == 1


def test_next_ai_submission_waits_for_summary_without_changing_handoff_delay(game_factory, monkeypatch):
    class WaitingProvider(FakePlanningProvider):
        entered = Event()

        async def plan_turn(self, request, config):
            self.requests.append(request)
            self.entered.set()
            await asyncio.Event().wait()

    provider = WaitingProvider([])
    game, clock = app(game_factory, controller=PlayerController.OPENAI, provider=provider)
    ticks = Mock(return_value=100)
    monkeypatch.setattr(pygame.time, "get_ticks", ticks)
    game.turn_presentation.schedule_ai_turn()
    assert game.pending_ai_turn_end_time == 600
    game.turn_presentation.present_ai_progress(progress())
    game.renderer.draw()
    ticks.return_value = 1000
    clock.return_value = 11.99
    game.update(0)
    assert not provider.requests and game.ai_coordinator._future is None
    assert game.control_service._public_state()["ai_lifecycle"]["phase"] == "scheduled"
    clock.return_value = 12.01
    game.update(0)
    assert provider.entered.wait(2) and len(provider.requests) == 1
    assert not ai_summary_active(game) and game.ai_coordinator.is_busy


def test_error_skip_and_quit_remain_available(game_factory):
    game, _ = app(game_factory, controller=PlayerController.OPENAI)
    game.ai_coordinator._fail("Private failed command", category="commit")
    snapshot = game.ai_coordinator.progress_snapshot()
    assert "Private" not in snapshot.safe_error
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e))
    game.input_processor.handle_input()
    assert game.current_player_index == 1
    game.turn_presentation.present_ai_progress(progress())
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    game.input_processor.handle_input()
    assert not game.is_running


def test_rejected_load_preserves_summary_and_successful_load_clears_it(game_factory, monkeypatch):
    game, _ = app(game_factory)
    game.turn_presentation.present_ai_progress(progress())
    monkeypatch.setattr("save_manager.load_game_from_file", Mock(return_value=False))
    assert not game.load_game("missing.json") and ai_summary_active(game)
    monkeypatch.setattr("save_manager.load_game_from_file", Mock(return_value=True))
    assert game.load_game("accepted.json") and not ai_summary_active(game)
    game.turn_presentation.present_ai_progress(progress())
    game.quit_to_main_menu()
    assert not ai_summary_active(game)


def test_defeat_and_campaign_end_keep_rendering_priority(pygame_context, presenter):
    from renderer import Renderer

    game, presentation, _ = presenter
    game.screen = pygame.display.get_surface()
    game.renderer = Renderer.__new__(Renderer)
    renderer = game.renderer
    renderer.game, renderer.screen = game, game.screen
    renderer.overlay_surface = pygame.Surface(game.screen.get_size(), pygame.SRCALPHA)
    renderer._draw_status, renderer.ai_turn_renderer = Mock(), Mock()
    game.defeat_notice = (pygame.time.get_ticks() + 4000, ("Defeated player",))
    renderer.draw()
    assert renderer._draw_status.call_args.args[0] == "Defeated player has been defeated."
    renderer.ai_turn_renderer.draw.assert_not_called()
    assert presentation._summary_visible_since is None
    game.defeat_notice = (0, ())
    game.players = [SimpleNamespace(defeated=True)]
    renderer.draw()
    assert renderer._draw_status.call_args.args[0] == "Campaign ended"
    assert not ai_summary_active(game)
