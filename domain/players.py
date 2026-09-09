"""Players domain objects and ownership rules."""
from __future__ import annotations

import typing
from typing import Any, Dict, Optional, Tuple

from domain.coordinates import HexCoord
from game_ai.runtime import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_REPAIR_RETRIES,
    normalize_reasoning_effort,
    normalize_repair_retries,
)
from player_controller import PlayerController
from utils import generate_short_id


class Player:
    """Represents a player and the controller responsible for its turns."""
    player_counter = 0

    def __init__(
        self,
        name: str,
        color: tuple,
        controller: PlayerController = PlayerController.HUMAN,
        team_id: Optional[int] = None,
        persistent_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        ai_reasoning_effort: str = DEFAULT_REASONING_EFFORT,
        ai_repair_retries: int = DEFAULT_REPAIR_RETRIES,
        ai_memory: Optional[Dict[str, Any]] = None,
        homeworld_id: Optional[int] = None,
    ):
        from persistence_context import allocate_id
        self.id = allocate_id(Player, "player_counter")
        self.name = name if name else f"Player {self.id}"
        self.color = color
        self.controller = PlayerController(controller)
        self.team_id: int = team_id if team_id is not None else (self.id + 1)
        self.persistent_id: str = persistent_id or generate_short_id()
        self.agent_id: str = agent_id or generate_short_id()
        self.ai_reasoning_effort: str = normalize_reasoning_effort(
            ai_reasoning_effort
        )
        self.ai_repair_retries: int = normalize_repair_retries(
            ai_repair_retries
        )
        self.ai_memory: Dict[str, Any] = dict(ai_memory or {})
        self.homeworld_id: Optional[int] = homeworld_id
        self.order_history = []
        self.order_event_sequence = 0
        self.last_ai_report: Dict[str, Any] = {}
        self.credits = 20000
        self.metal = 10000
        self.crystal = 10000
        self.sector_intel: Dict[Tuple[str, HexCoord], int] = {}

    def is_allied_with(self, other: Optional['Player']) -> bool:
        """Returns True if other is not None and is allied with this player (same team or same instance)."""
        if other is None:
            return False
        if self is other:
            return True
        other_id = getattr(other, 'id', None)
        if isinstance(other_id, (int, str)) and self.id == other_id:
            return True
        other_team = getattr(other, 'team_id', None)
        if isinstance(other_team, (int, str)) and self.team_id is not None:
            return self.team_id == other_team
        return False

    def is_enemy_of(self, other: Optional['Player']) -> bool:
        """Returns True if other is a valid opposing player on a different team."""
        if other is None:
            return False
        if self is other:
            return False
        other_id = getattr(other, 'id', None)
        if isinstance(other_id, (int, str)) and self.id == other_id:
            return False
        return not self.is_allied_with(other)

    def relation_to(self, other: Optional['Player']) -> str:
        """Returns 'self', 'ally', or 'enemy' relationship relative to other."""
        if other is None:
            return "neutral"
        if self is other or (isinstance(getattr(other, 'id', None), (int, str)) and self.id == other.id):
            return "self"
        if self.is_allied_with(other):
            return "ally"
        return "enemy"

    def record_sector_intel(self, system_name: str, hex_coord: HexCoord, turn: int) -> None:
        """Records or updates the last turn a sector was in long-range sensor range."""
        self.sector_intel[(system_name, hex_coord)] = turn

    def get_sector_last_intel_turn(self, system_name: str, hex_coord: HexCoord) -> Optional[int]:
        """Returns the turn number when intel was last updated for a sector, or None."""
        return self.sector_intel.get((system_name, hex_coord))

    def __repr__(self):
        return f"Player({self.name}, ID:{self.id}, Team:{self.team_id}, Color:{self.color})"


def are_allies(p1: Optional[typing.Any], p2: Optional[typing.Any]) -> bool:
    """Returns True if p1 and p2 are valid allied players (or the same player)."""
    if p1 is None or p2 is None:
        return False
    if p1 is p2:
        return True
    if isinstance(p1, Player):
        return p1.is_allied_with(p2)
    if isinstance(p2, Player):
        return p2.is_allied_with(p1)
    p1_id = getattr(p1, 'id', None)
    p2_id = getattr(p2, 'id', None)
    if isinstance(p1_id, (int, str)) and isinstance(p2_id, (int, str)) and p1_id == p2_id:
        return True
    team1 = getattr(p1, 'team_id', None)
    team2 = getattr(p2, 'team_id', None)
    if isinstance(team1, (int, str)) and isinstance(team2, (int, str)):
        return team1 == team2
    return p1 == p2


def are_enemies(p1: Optional[typing.Any], p2: Optional[typing.Any]) -> bool:
    """Returns True if p1 and p2 are valid enemy players."""
    if p1 is None or p2 is None:
        return False
    if isinstance(p1, Player):
        return p1.is_enemy_of(p2)
    if isinstance(p2, Player):
        return p2.is_enemy_of(p1)
    return not are_allies(p1, p2)
