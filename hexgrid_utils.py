import math
import typing
from constants import SQRT3, SYSTEM_CENTER_IN_PX, HEX_SIZE
from geometry import Vector, Position
from utils import HexCoord

# --- Hex Grid Utility Functions ---

def hex_to_pixel(q: int, r: int) -> Position:
    """Converts axial hex coordinates (q, r) to pixel coordinates (x, y), relative to system center. Formula for a grid of pointy-top hexagons.
    """
    x = HEX_SIZE * (SQRT3 * q + SQRT3 / 2. * r)
    y = HEX_SIZE * (3. / 2. * r)
    return Position(int(x + SYSTEM_CENTER_IN_PX.x), int(y + SYSTEM_CENTER_IN_PX.y))

def pixel_to_hex(x: int, y: int) -> HexCoord:
    """Converts pixel coordinates (x, y) to approximate axial hex coordinates (q, r), relative to system center. Formula for a grid of pointy-top hexagons.
    """
    x_adj = float(x) - SYSTEM_CENTER_IN_PX.x
    y_adj = float(y) - SYSTEM_CENTER_IN_PX.y
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

    return q, r

def get_hex_vertices(q: int, r: int) -> typing.List[Position]: # Returns a list of pixel Positions
    """Calculates the 6 vertices of a hexagon at axial coordinates (q, r), relative to system center."""
    center_point = hex_to_pixel(q, r)
    vertices = []
    for i in range(6):
        angle_deg = 60 * i + 30
        angle_rad = math.pi / 180 * angle_deg
        vertices.append(Position(int(center_point.x + HEX_SIZE * math.cos(angle_rad)),
                              int(center_point.y + HEX_SIZE * math.sin(angle_rad))))
    return vertices

def hex_distance(q1: int, r1: int, q2: int, r2: int) -> int:
    """Calculates the distance between two hexes in axial coordinates."""
    dq = q1 - q2
    dr = r1 - r2
    ds = (-q1 - r1) - (-q2 - r2)
    return (abs(dq) + abs(dr) + abs(ds)) // 2
