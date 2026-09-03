import math
import typing
from constants import SQRT3, SYSTEM_CENTER_IN_PX, HEX_SIZE
from geometry import Vector, Position
from utils import HexCoord

# --- Hex Grid Utility Functions ---

def hex_to_pixel(q: int, r: int, zoom: float = 1.0,
                 pan_offset: typing.Optional[Position] = None) -> Position:
    """Convert axial coordinates to system-view screen coordinates.

    ``zoom`` and ``pan_offset`` are optional so gameplay callers that only need
    the original, untransformed hex geometry retain their existing behaviour.
    """
    if pan_offset is None:
        pan_offset = Position(0, 0)
    x = HEX_SIZE * (SQRT3 * q + SQRT3 / 2. * r)
    y = HEX_SIZE * (3. / 2. * r)
    return Position(
        int(SYSTEM_CENTER_IN_PX.x + pan_offset.x + x * zoom),
        int(SYSTEM_CENTER_IN_PX.y + pan_offset.y + y * zoom),
    )

def pixel_to_hex(x: int, y: int, zoom: float = 1.0,
                 pan_offset: typing.Optional[Position] = None) -> HexCoord:
    """Convert system-view screen coordinates to the nearest axial hex."""
    if pan_offset is None:
        pan_offset = Position(0, 0)
    if not isinstance(zoom, (int, float)) or zoom <= 0:
        zoom = 1.0
    x_adj = (float(x) - SYSTEM_CENTER_IN_PX.x - pan_offset.x) / zoom
    y_adj = (float(y) - SYSTEM_CENTER_IN_PX.y - pan_offset.y) / zoom
    q_approx = (SQRT3 / 3. * x_adj - 1. / 3. * y_adj) / HEX_SIZE
    r_approx = (2. / 3. * y_adj) / HEX_SIZE
    return hex_round(q_approx, r_approx)

def hex_round(q_frac: float, r_frac: float) -> HexCoord:
    """Rounds fractional axial coordinates to the nearest hex coordinates."""
    s_frac = -q_frac - r_frac

    q = round(q_frac)
    r = round(r_frac)
    s = round(s_frac)

    q_diff = abs(q - q_frac)
    r_diff = abs(r - r_frac)
    s_diff = abs(s - s_frac)

    if q_diff > r_diff and q_diff > s_diff:
        q = -r - s
    elif r_diff > s_diff:
        r = -q - s
    else:
        s = -q - r

    return HexCoord(q, r)

def get_hex_vertices(q: int, r: int, zoom: float = 1.0,
                     pan_offset: typing.Optional[Position] = None) -> typing.List[Position]:
    """Calculate the six transformed vertices of a system-view hex."""
    center_point = hex_to_pixel(q, r, zoom, pan_offset)
    radius = HEX_SIZE * zoom
    vertices = []
    for i in range(6):
        angle_deg = 60 * i + 30
        angle_rad = math.pi / 180 * angle_deg
        vertices.append(Position(int(center_point.x + radius * math.cos(angle_rad)),
                              int(center_point.y + radius * math.sin(angle_rad))))
    return vertices

def hex_distance(q1: int, r1: int, q2: int, r2: int) -> int:
    """Calculates the distance between two hexes in axial coordinates."""
    dq = q1 - q2
    dr = r1 - r2
    ds = (-q1 - r1) - (-q2 - r2)
    return (abs(dq) + abs(dr) + abs(ds)) // 2

HEX_DIRECTIONS: typing.List[HexCoord] = [
    HexCoord(1, 0), HexCoord(1, -1), HexCoord(0, -1),
    HexCoord(-1, 0), HexCoord(-1, 1), HexCoord(0, 1)
]

def hex_neighbors(coord: HexCoord) -> typing.List[HexCoord]:
    """Return the 6 axial neighbours of a hex coordinate."""
    q, r = coord.q, coord.r
    return [HexCoord(q + dq.q, r + dq.r) for dq in HEX_DIRECTIONS]

def hexes_within_range(coord: HexCoord, n: int) -> typing.List[HexCoord]:
    """Return all hex coords within `n` rings of `coord`, INCLUDING `coord`
    itself (ring 0). n <= 0 returns just [coord]."""
    hex_c = coord if isinstance(coord, HexCoord) else HexCoord(coord[0], coord[1])
    if n <= 0:
        return [hex_c]
    results = []
    for dq in range(-n, n + 1):
        for dr in range(max(-n, -dq - n), min(n, -dq + n) + 1):
            results.append(HexCoord(hex_c.q + dq, hex_c.r + dr))
    return results

