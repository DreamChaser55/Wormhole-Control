"""Minefields domain objects and ownership rules."""
from __future__ import annotations

import logging
import typing

from constants import (
    MINEFIELD_DEFAULT_DAMAGE,
    MINEFIELD_DEFAULT_MINES,
    MINEFIELD_DETONATION_RADIUS,
    HullSize,
)
from domain.coordinates import HexCoord
from domain.identity import GameObject
from domain.players import Player
from domain.units import Unit
from geometry import Position
from unit_components.defenses import Defenses
from unit_components.enums import MinefieldType

logger = logging.getLogger(__name__)

class Minefield(GameObject):
    """Represents a deployed minefield hazard in a hex."""
    def __init__(self, owner: Player, position: Position, in_hex: HexCoord, in_system: str,
                 mines_remaining: int = int(MINEFIELD_DEFAULT_MINES),
                 mine_damage: float = MINEFIELD_DEFAULT_DAMAGE,
                 detonation_radius: float = MINEFIELD_DETONATION_RADIUS,
                 minefield_type: typing.Union[MinefieldType, str] = MinefieldType.ANTI_SHIP):
        super().__init__(position, in_hex, in_system)
        self.owner = owner
        if isinstance(minefield_type, str):
            try:
                self.minefield_type = MinefieldType(minefield_type)
            except ValueError:
                self.minefield_type = MinefieldType.ANTI_SHIP
        else:
            self.minefield_type = minefield_type
        self.name = f"{self.minefield_type.display_name} Minefield {self.id}"
        self.mines_remaining = mines_remaining
        self.mine_damage = mine_damage
        self.detonation_radius = detonation_radius
        self.revealed_to_player_ids: typing.Set[int] = set()

    def reveal_to(self, player: typing.Optional[Player]) -> None:
        """Permanently marks this minefield as revealed to the given player."""
        if player is not None:
            self.revealed_to_player_ids.add(player.id)

    def is_revealed_to(self, player: typing.Optional[Player]) -> bool:
        """Return True if this minefield has been revealed to the given player."""
        if player is None:
            return False
        return player.id in self.revealed_to_player_ids

    def can_target(self, unit: 'Unit') -> bool:
        """Return True if unit is a valid target for this minefield type."""
        if self.owner and (unit.owner == self.owner or self.owner.is_allied_with(unit.owner)):
            return False
        if unit.current_hit_points <= 0:
            return False
        if self.minefield_type == MinefieldType.ANTI_SHIP:
            return unit.hull_size != HullSize.STRIKECRAFT_WING
        elif self.minefield_type == MinefieldType.ANTI_STRIKECRAFT:
            return unit.hull_size == HullSize.STRIKECRAFT_WING
        return True

    def detonate_against(self, unit: 'Unit') -> float:
        """Detonates a mine against an enemy unit, applying net damage and reducing mine count."""
        if self.mines_remaining <= 0:
            return 0.0

        defenses = unit.get_component(Defenses)
        armor = defenses.armor if defenses else 0
        shields = defenses.shields if defenses else 0

        mitigation = (armor * 0.5) + (shields * 0.25)
        effective_damage = max(10.0, self.mine_damage - mitigation)

        if getattr(unit, 'damage_reduction', 0) > 0:
            effective_damage *= (1.0 - min(0.9, unit.damage_reduction))
        if getattr(unit, 'damage_amplification', 0) > 0:
            effective_damage *= (1.0 + unit.damage_amplification)

        damage_int = int(round(effective_damage))
        unit.current_hit_points = max(0, unit.current_hit_points - damage_int)
        self.mines_remaining -= 1

        logger.debug(f"{self.name} (Owner: {self.owner.name}) detonated against {unit.name}! Dealt {damage_int} damage. Mines remaining: {self.mines_remaining}")
        if unit.current_hit_points <= 0:
            unit.destroy()
        return damage_int
