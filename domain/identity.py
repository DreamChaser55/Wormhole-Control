"""Identity domain objects and ownership rules."""
from __future__ import annotations

from domain.coordinates import HexCoord
from geometry import Position


class GameObject:
    """Base class for all objects that can exist in a sector."""
    object_counter = 1

    def __init__(self, position: Position, in_hex: HexCoord, in_system: str) -> None:
        from persistence_context import allocate_id
        self.id: int = allocate_id(GameObject, "object_counter")
        self.position = position
        self.in_hex = in_hex
        self.in_system = in_system

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(ID:{self.id}, Pos:{self.position}, Hex:{self.in_hex}, System:{self.in_system})"
