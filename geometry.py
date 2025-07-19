import typing
import math
import random
import dataclasses
from utils import HexCoord

# --- Vector Class ---
@dataclasses.dataclass
class Vector:
    """Represents a 2D vector, commonly used for positions, displacements, or sizes."""
    x: typing.Union[float, int]
    y: typing.Union[float, int]

    def __add__(self, other: 'Vector') -> 'Vector':
        return Vector(self.x + other.x, self.y + other.y)

    def __sub__(self, other: 'Vector') -> 'Vector':
        return Vector(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: typing.Union[float, int]) -> 'Vector':
        return Vector(self.x * scalar, self.y * scalar)

    def magnitude_sq(self) -> float:
        """Returns the squared magnitude (length) of the vector from origin."""
        return self.x**2 + self.y**2

    def magnitude(self) -> float:
        """Returns the magnitude (length) of the vector from origin."""
        return math.sqrt(self.magnitude_sq())

    def normalize(self) -> 'Vector':
        """Returns a new Vector representing the normalized vector (unit vector)."""
        mag = self.magnitude()
        if mag == 0:
            return Vector(0, 0)
        return Vector(self.x / mag, self.y / mag)

    def to_tuple(self) -> typing.Tuple[typing.Union[float, int], typing.Union[float, int]]:
        return (self.x, self.y)

    def __repr__(self) -> str:
        return f"Vector(x={self.x:.2f}, y={self.y:.2f})"

# Type Aliases
Position = Vector # Represents a logical 2D position within the game world or a pixel position on the screen.

# --- Geometric Utility Functions ---

def distance_sq(p1: Position, p2: Position) -> float:
    """Calculates the squared Euclidean distance between two Positions."""
    return (p1.x - p2.x)**2 + (p1.y - p2.y)**2

def distance(p1: Position, p2: Position) -> float:
    """Calculates the Euclidean distance between two Positions."""
    return math.sqrt(distance_sq(p1, p2))

def hex_distance(a: HexCoord, b: HexCoord) -> int:
    """
    Calculates the grid distance between two hex coordinates (axial coordinates).
    This is the number of steps required to get from one hex to another.
    """
    q1, r1 = a
    q2, r2 = b
    # Using the formula for distance on a hex grid with axial coordinates
    return (abs(q1 - q2) + abs(q1 + r1 - q2 - r2) + abs(r1 - r2)) // 2

# --- Circle Class ---
@dataclasses.dataclass
class Circle:
    """Represents a 2D circle with a center and radius."""
    center: Position
    radius: float

# --- Circle Utility Functions ---

def is_point_in_circle(point: Position, circle: Circle) -> bool:
    """Checks if a point is inside a given circle."""
    return distance_sq(point, circle.center) <= circle.radius**2

def do_circles_intersect(c1: Circle, c2: Circle) -> bool:
    """Checks if two circles intersect."""
    dist_sq = distance_sq(c1.center, c2.center)
    radii_sum_sq = (c1.radius + c2.radius)**2
    return dist_sq < radii_sum_sq

def is_circle_contained(inner: Circle, outer: Circle) -> bool:
    """Checks if the inner circle is fully contained within the outer circle."""
    dist = distance(inner.center, outer.center)
    return dist + inner.radius <= outer.radius

def get_closest_point_on_circle_edge(point: Position, circle: Circle) -> Position:
    """
    Finds the point on the edge of a circle that is closest to a given point.
    """
    # A small epsilon to push the point just outside the circle boundary
    epsilon_radius = circle.radius * 1.0001

    # If the point is at the center of the circle, any point on the edge is equidistant.
    # We can pick a random direction or a default one.
    if point == circle.center:
        return Position(circle.center.x + epsilon_radius, circle.center.y)

    # The direction from the circle's center to the point.
    direction = (point - circle.center).normalize()

    # The closest point on the edge is in this direction.
    closest_point = circle.center + (direction * epsilon_radius)
    
    return closest_point

def move_towards_position(current_pos: Position, target_pos: Position, desired_distance_from_target: float) -> Position:
    """
    Calculates a destination position that is a specific distance away from a target position,
    along the line connecting the current position and the target position.

    If current_pos is the same as target_pos, it returns a position
    desired_distance_from_target away along the positive x-axis from target_pos.

    Args:
        current_pos: The starting position.
        target_pos: The position of the target to move towards/orient relative to.
        desired_distance_from_target: The desired distance to maintain from the target_pos.

    Returns:
        A new Position.
    """
    # Vector from the target to the current unit's position
    vector_from_target_to_current = current_pos - target_pos

    if vector_from_target_to_current.magnitude_sq() < 1e-9:  # Effectively zero, current_pos is at target_pos
        # Default to moving along the positive x-axis from the target
        return target_pos + Vector(desired_distance_from_target, 0.0)
    else:
        direction_from_target = vector_from_target_to_current.normalize()
        destination = target_pos + (direction_from_target * desired_distance_from_target)
        return destination
