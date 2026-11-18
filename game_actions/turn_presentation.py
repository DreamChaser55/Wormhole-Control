"""Application adapter for turn notifications and delayed AI startup."""
from time import perf_counter
from typing import Any, Callable

from game_ai.progress import AITurnProgress
from player_controller import PlayerController

AI_SUMMARY_SECONDS = 2.0


def ai_summary_snapshot(game: Any) -> AITurnProgress | None:
    presenter = getattr(game, "turn_presentation", None)
    return presenter.ai_summary_snapshot() if isinstance(presenter, ApplicationTurnPresentation) else None


def ai_summary_active(game: Any) -> bool:
    return ai_summary_snapshot(game) is not None


def defeat_notice(game: Any) -> tuple[str, ...]:
    """Return the public names in the current handoff notice."""
    import pygame

    notice = getattr(game, 'defeat_notice', None)
    if not isinstance(notice, tuple) or getattr(game, 'game_started', False) is not True:
        return ()
    deadline, names = notice
    return names if pygame.time.get_ticks() < deadline else ()


class ApplicationTurnPresentation:
    def __init__(self, game: Any, *, clock: Callable[[], float] = perf_counter) -> None:
        self.game = game
        self._clock = clock
        self._ai_summary: AITurnProgress | None = None
        self._summary_remaining = AI_SUMMARY_SECONDS
        self._summary_visible_since: float | None = None

    def present_ai_progress(self, progress: AITurnProgress | None) -> None:
        """Main-thread callback: paint blocking phases; retain completion after handoff."""
        if progress is None:
            self.dismiss_ai_summary()
        elif progress.phase == "complete":
            self._ai_summary = progress
            self._summary_remaining = AI_SUMMARY_SECONDS
            self._summary_visible_since = None
        elif progress.phase in {"preparing", "checking", "resolving"}:
            # Paint without pumping input or yielding between commit and End Turn.
            renderer = getattr(self.game, "renderer", None)
            if renderer is not None:
                renderer.draw()

    def dismiss_ai_summary(self) -> None:
        self._ai_summary = None
        self._summary_visible_since = None
        self._summary_remaining = AI_SUMMARY_SECONDS

    def ai_summary_snapshot(self) -> AITurnProgress | None:
        summary = self._ai_summary
        if summary is None:
            return None
        players = getattr(self.game, "players", ())
        if (not getattr(self.game, "game_started", False)
                or summary.campaign_id != str(getattr(self.game, "campaign_id", ""))
                or (players and all(getattr(player, "defeated", False) for player in players))):
            self.dismiss_ai_summary()
            return None
        now = self._clock()
        if self._summary_visible_since is not None:
            self._summary_remaining -= max(0.0, now - self._summary_visible_since)
            self._summary_visible_since = None if defeat_notice(self.game) else now
            if self._summary_remaining <= 0:
                self.dismiss_ai_summary()
                return None
        return summary

    def mark_ai_summary_visible(self) -> None:
        """Count visible time only; defeat notices can postpone or interrupt the summary."""
        if self.ai_summary_snapshot() is not None and self._summary_visible_since is None:
            self._summary_visible_since = self._clock()

    def refresh_player_turn(self, player: Any) -> None:
        self.game.recompute_visibility()
        self.game.update_player_turn_display()
        self.game.update_side_bar_content()
        gui = getattr(self.game, "gui", None)
        if gui:
            from gui.turn_briefing_window import close_briefing, show_briefing
            close_briefing(gui)
            wing_picker = getattr(gui, 'wing_production_window', None)
            if wing_picker:
                wing_picker.close()
            transport = getattr(gui, 'antimatter_transport_window', None)
            if transport:
                transport.close()
            gui.close_communications_window()
            gui.close_unit_editor()
            gui.close_retrofit_wizard()
            if gui.unit_catalog_window:
                gui.unit_catalog_window.kill()
                gui.unit_catalog_window = None
            gui.close_context_menu()
            gui.close_ai_settings_dialog()
            gui.close_settings_dialog()
            if gui.load_save_window:
                gui.load_save_window.kill()
                gui.load_save_window = None
                gui.load_save_confirm_button = gui.load_save_cancel_button = gui.load_save_selection_list = None
            for dialog in gui.active_dialogs:
                dialog.kill()
            gui.active_dialogs.clear()
            if gui.ingame_menu_panel:
                gui.ingame_menu_panel.hide()
            show_briefing(gui, player)

    def show_defeated_players(self, players: Any) -> None:
        import pygame

        names = defeat_notice(self.game) + tuple(player.name for player in players)
        self.game.defeat_notice = (pygame.time.get_ticks() + 4000, names)

    def schedule_ai_turn(self) -> None:
        import pygame

        if not self.game.players or not 0 <= self.game.current_player_index < len(self.game.players):
            return
        player = self.game.players[self.game.current_player_index]
        # Also used after new-campaign setup and load, where no handoff occurs.
        gui = getattr(self.game, "gui", None)
        if gui:
            gui.close_settings_dialog()
            from gui.turn_briefing_window import show_briefing
            show_briefing(gui, player)
        self.game.pending_ai_turn_end_time = (
            pygame.time.get_ticks() + 500
            if player.controller == PlayerController.OPENAI and not getattr(player, 'defeated', False) else 0
        )
        if self.game.pending_ai_turn_end_time:
            coordinator = getattr(self.game, "ai_coordinator", None)
            if coordinator is not None:
                coordinator.schedule_current_turn()

    def warn_human(self, player: Any, message: str, *, title: str) -> None:
        gui = getattr(self.game, "gui", None)
        if gui and player.controller == PlayerController.HUMAN:
            gui.show_warning_dialog(message, title=title)
