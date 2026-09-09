"""Axial sector coordinates; distinct from logical positions and screen pixels."""
from typing import NamedTuple


class HexCoord(NamedTuple):
    """Axial column q and diagonal r identifying a sector within a star system."""
    q: int
    r: int
