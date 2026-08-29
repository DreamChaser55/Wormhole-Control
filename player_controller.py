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

