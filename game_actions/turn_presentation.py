"""Application adapter for turn notifications and delayed AI startup."""
from typing import Any

from player_controller import PlayerController


class ApplicationTurnPresentation:
    def __init__(self, game: Any) -> None:
        self.game = game

    def refresh_player_turn(self, player: Any) -> None:
        self.game.update_player_turn_display()
        self.game.update_side_bar_content()
        gui = getattr(self.game, "gui", None)
        if gui:
            from gui.turn_briefing_window import close_briefing, show_briefing
            close_briefing(gui)
            gui.close_communications_window()
            gui.close_unit_editor()
            gui.close_retrofit_wizard()
            if gui.unit_catalog_window:
                gui.unit_catalog_window.kill()
                gui.unit_catalog_window = None
            gui.close_context_menu()
            gui.close_ai_settings_dialog()
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

    def schedule_ai_turn(self) -> None:
        import pygame

        if not self.game.players or not 0 <= self.game.current_player_index < len(self.game.players):
            return
        player = self.game.players[self.game.current_player_index]
        # Also used after new-campaign setup and load, where no handoff occurs.
        gui = getattr(self.game, "gui", None)
        if gui:
            from gui.turn_briefing_window import show_briefing
            show_briefing(gui, player)
        self.game.pending_ai_turn_end_time = (
            pygame.time.get_ticks() + 500 if player.controller == PlayerController.OPENAI else 0
        )

    def warn_human(self, player: Any, message: str, *, title: str) -> None:
        gui = getattr(self.game, "gui", None)
        if gui and player.controller == PlayerController.HUMAN:
            gui.show_warning_dialog(message, title=title)
