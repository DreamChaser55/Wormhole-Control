"""Optional presentation port for turn resolution; implementations own UI timing."""
from typing import Any, Protocol


class TurnPresentation(Protocol):
    def refresh_player_turn(self, player: Any) -> None: ...
    def schedule_ai_turn(self) -> None: ...
    def warn_human(self, player: Any, message: str, *, title: str) -> None: ...


class NullTurnPresentation:
    """Default for domain-only resolution: no GUI, timers or scheduling effects."""

    def refresh_player_turn(self, player: Any) -> None:
        pass

    def schedule_ai_turn(self) -> None:
        pass

    def warn_human(self, player: Any, message: str, *, title: str) -> None:
        pass
