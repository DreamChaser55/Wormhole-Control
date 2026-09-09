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
        if player.controller == PlayerController.HUMAN and gui:
            if self.game.get_unread_messages_for_player(player.id):
                gui.open_communications_window()
            elif gui.is_communications_window_open():
                gui.communications_window.refresh_message_log()

    def schedule_ai_turn(self) -> None:
        import pygame

        if not self.game.players or not 0 <= self.game.current_player_index < len(self.game.players):
            return
        player = self.game.players[self.game.current_player_index]
        self.game.pending_ai_turn_end_time = (
            pygame.time.get_ticks() + 500 if player.controller == PlayerController.OPENAI else 0
        )

    def warn_human(self, player: Any, message: str, *, title: str) -> None:
        gui = getattr(self.game, "gui", None)
        if gui and player.controller == PlayerController.HUMAN:
            gui.show_warning_dialog(message, title=title)
