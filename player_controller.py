"""Player ownership modes shared by the game, UI, saves, and control API."""

from enum import Enum


class PlayerController(str, Enum):
    HUMAN = "human"
    OPENAI = "openai"
    CODEX = "codex"

    @property
    def display_name(self) -> str:
        return {
            PlayerController.HUMAN: "Human",
            PlayerController.OPENAI: "AI",
            PlayerController.CODEX: "Codex",
        }[self]



def automated_turn_active(game) -> bool:
    """Whether the local display must keep the active controller's view private."""
    return getattr(game, 'game_started', False) is True and getattr(
        getattr(game, 'current_player', None), 'controller', None,
    ) in (PlayerController.OPENAI, PlayerController.CODEX)
