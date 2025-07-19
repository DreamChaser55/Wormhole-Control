import math
import random
from geometry import Vector, distance, Position
from constants import SECTOR_CIRCLE_RADIUS_LOGICAL, SECTOR_CIRCLE_CENTER_IN_PX, SECTOR_CIRCLE_RADIUS_IN_PX

# --- Sector Utility Functions ---

def move_towards_position(current: Position, target: Position, max_distance: float) -> Position:
    """Moves from current position towards target position, limited by max_distance.
    Returns the new position after movement."""
    dist = distance(current, target)
    
    # If we're already close enough, return the target position
    if dist <= max_distance:
        return target
    
    # Calculate the direction vector
    dx = target.x - current.x
    dy = target.y - current.y
    
    # Normalize and scale by max_distance
    scale = max_distance / dist
    return Position(current.x + dx * scale, current.y + dy * scale)

def random_point_in_circle(radius: float) -> Position:
    """Generates a random Position within a circle of the given radius."""
    # Use sqrt for uniform distribution
    r_val = math.sqrt(random.random()) * radius
    angle = random.random() * 2 * math.pi
    x = r_val * math.cos(angle)
    y = r_val * math.sin(angle)
    return Position(x, y)

def random_point_in_sector() -> Position:
    """Generates a random Position within a sector circle (in logical coordinates)."""
    return random_point_in_circle(SECTOR_CIRCLE_RADIUS_LOGICAL)

def sector_coords_to_pixels(sector_pos: Position) -> Position:
    """Converts logical sector coordinates (e.g., x,y from +-SECTOR_CIRCLE_RADIUS_LOGICAL) to screen pixel coordinates."""
    pixel_x = int(SECTOR_CIRCLE_CENTER_IN_PX.x + sector_pos.x * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
    pixel_y = int(SECTOR_CIRCLE_CENTER_IN_PX.y + sector_pos.y * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
    return Position(pixel_x, pixel_y)

def pixels_to_sector_coords(pixel_pos: Position) -> Position:
    """Converts screen pixel coordinates to logical sector coordinates."""
    # Convert pixel position to relative position from center
    relative_x = pixel_pos.x - SECTOR_CIRCLE_CENTER_IN_PX.x
    relative_y = pixel_pos.y - SECTOR_CIRCLE_CENTER_IN_PX.y
    # Scale back to logical radius
    logical_x = (relative_x / SECTOR_CIRCLE_RADIUS_IN_PX) * SECTOR_CIRCLE_RADIUS_LOGICAL
    logical_y = (relative_y / SECTOR_CIRCLE_RADIUS_IN_PX) * SECTOR_CIRCLE_RADIUS_LOGICAL
    return Position(logical_x, logical_y)
