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

def clamp_point_to_circle(point: Position, circle: Circle) -> Position:
    """Clamps a 2D position so that it lies inside or on the edge of a circle."""
    dist = distance(point, circle.center)
    if dist <= circle.radius:
        return point
    if dist == 0:
        return Position(circle.center.x + circle.radius, circle.center.y)
    direction = (point - circle.center).normalize()
    return circle.center + (direction * circle.radius)

def clamp_vector_magnitude(vector: Vector, max_magnitude: float) -> Vector:
    """Clamps a vector's magnitude to a maximum value."""
    mag = vector.magnitude()
    if mag <= max_magnitude or mag == 0:
        return vector
    return vector * (max_magnitude / mag)

def position_at_distance_from_target(current_pos: Position, target_pos: Position, desired_distance_from_target: float) -> Position:
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

# Backwards compatible alias for position_at_distance_from_target
move_towards_position = position_at_distance_from_target

# --- Collision Avoidance Geometry ---

def segment_intersects_circle(p1: Position, p2: Position, circle: Circle) -> bool:
    """Tests whether a line segment from p1 to p2 intersects a circle.

    Returns True if the segment crosses into, passes through, or is contained
    within the circle.  The standard parametric ray-circle test is used:
    the ray is ``P(t) = p1 + t*(p2 - p1)`` for ``t in [0, 1]``.
    """
    dx = p2.x - p1.x
    dy = p2.y - p1.y
    fx = p1.x - circle.center.x
    fy = p1.y - circle.center.y
    r = circle.radius

    a = dx * dx + dy * dy
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r

    # Zero-length segment: just check if the point is inside the circle.
    if a < 1e-12:
        return c <= 0.0

    discriminant = b * b - 4.0 * a * c
    if discriminant < 0.0:
        return False

    sqrt_disc = math.sqrt(discriminant)
    t1 = (-b - sqrt_disc) / (2.0 * a)
    t2 = (-b + sqrt_disc) / (2.0 * a)

    # The segment intersects the circle when the intervals [t1, t2] and [0, 1]
    # overlap, i.e. when t1 <= 1 AND t2 >= 0.
    return t1 <= 1.0 and t2 >= 0.0


NAVIGATION_CLEARANCE = 50.0
GEOMETRY_TOLERANCE = 1e-6


class NoSafePathError(ValueError):
    """A bounded search could not produce a verified collision-free route."""


def segment_clearance(start: Position, end: Position, center: Position) -> float:
    """Minimum center distance anywhere along a segment, including endpoints."""
    delta = end - start
    length_sq = delta.magnitude_sq()
    if length_sq <= 1e-24:
        return distance(start, center)
    offset = center - start
    t = max(0.0, min(1.0, (offset.x * delta.x + offset.y * delta.y) / length_sq))
    return distance(start + delta * t, center)


def compute_avoidance_waypoints(
    start: Position,
    end: Position,
    obstacles: typing.List[Circle],
    margin: float = NAVIGATION_CLEARANCE,
    boundary: typing.Optional[Circle] = None,
) -> typing.List[Position]:
    """Return verified intermediate waypoints, or raise NoSafePathError.

    Tangency to the expanded obstacles is legal. Only original endpoints inside
    physical bodies receive the legacy landing/departure exception. A start in
    the clearance band may escape outward; a destination in that band is invalid.
    The optional circular boundary contains the entire route, including endpoints.
    """
    eps = GEOMETRY_TOLERANCE
    if margin < 0:
        raise ValueError("Navigation clearance must be non-negative")
    expanded = [Circle(obs.center, obs.radius + margin) for obs in obstacles]

    def in_bounds(p):
        return boundary is None or distance(p, boundary.center) <= boundary.radius + eps

    if not in_bounds(start) or not in_bounds(end):
        raise NoSafePathError("Route endpoint is outside the sector")

    def endpoint_exception(a, b, original):
        return ((a == start and distance(start, original.center) <= original.radius + eps)
                or (b == end and distance(end, original.center) <= original.radius + eps))

    for original, expanded_obstacle in zip(obstacles, expanded):
        d = distance(end, original.center)
        if original.radius + eps < d < expanded_obstacle.radius - eps:
            raise NoSafePathError("Destination lies inside an obstacle clearance band")

    band = [obs for original, obs in zip(obstacles, expanded)
            if original.radius + eps < distance(start, obs.center) < obs.radius - eps]
    escape = None
    if band:
        # One outward segment must clear all bands without moving deeper into any.
        for obs in band:
            candidate = obs.center + (start - obs.center).normalize() * (obs.radius + eps * 4)
            delta = candidate - start
            if not in_bounds(candidate):
                continue
            valid = True
            for original, other in zip(obstacles, expanded):
                if other in band:
                    offset = start - other.center
                    if (distance(candidate, other.center) < other.radius - eps
                            or offset.x * delta.x + offset.y * delta.y < -eps):
                        valid = False
                elif not endpoint_exception(start, candidate, original):
                    valid = valid and segment_clearance(start, candidate, other.center) >= other.radius - eps
            if valid:
                escape = candidate
                break
        if escape is None:
            raise NoSafePathError("Cannot escape the obstacle clearance band")

    def exempt(a, b, original, obs):
        return endpoint_exception(a, b, original) or (a == start and b == escape and obs in band)

    def first_blocker(a, b):
        best, best_t = None, float('inf')
        delta = b - a
        length_sq = delta.magnitude_sq()
        for original, obs in zip(obstacles, expanded):
            if exempt(a, b, original, obs):
                continue
            if segment_clearance(a, b, obs.center) >= obs.radius - eps:
                continue
            offset = a - obs.center
            linear = 2 * (offset.x * delta.x + offset.y * delta.y)
            constant = offset.magnitude_sq() - obs.radius ** 2
            disc = max(0.0, linear ** 2 - 4 * length_sq * constant)
            entry = max(0.0, (-linear - math.sqrt(disc)) / (2 * length_sq)) if length_sq > 1e-24 else 0.0
            if entry < best_t:
                best, best_t = obs, entry
        return best

    def candidate_path(a, b, obs, direction):
        radius = obs.radius
        d1, d2 = distance(a, obs.center), distance(b, obs.center)
        if min(d1, d2) < radius - eps:
            raise NoSafePathError("Intermediate waypoint is inside an obstacle")
        theta1 = math.atan2(a.y - obs.center.y, a.x - obs.center.x)
        theta2 = math.atan2(b.y - obs.center.y, b.x - obs.center.x)
        angle1 = theta1 + direction * math.acos(min(1.0, radius / max(d1, eps)))
        angle2 = theta2 - direction * math.acos(min(1.0, radius / max(d2, eps)))
        arc = direction * ((direction * (angle2 - angle1)) % (2 * math.pi))
        steps = max(1, math.ceil(abs(arc) / math.radians(15)))
        step = arc / steps
        # Intersections of consecutive tangent lines form a circumscribed polygon.
        # Every edge has clearance radius, unlike chords between points on a circle.
        vertex_radius = radius / math.cos(step / 2)
        return [obs.center + Position(math.cos(angle1 + (i + .5) * step),
                                      math.sin(angle1 + (i + .5) * step)) * vertex_radius
                for i in range(steps)]

    def path_length(points):
        return sum(distance(a, b) for a, b in zip(points, points[1:]))

    budget = 2048

    def solve(a, b, depth=0):
        nonlocal budget
        budget -= 1
        if budget < 0:
            raise NoSafePathError("Collision search budget exhausted")
        blocker = first_blocker(a, b)
        if blocker is None:
            return []
        if depth >= 8:
            raise NoSafePathError("Collision search depth exhausted")
        candidates = [candidate_path(a, b, blocker, sign) for sign in (1, -1)]
        candidates.sort(key=lambda wps: path_length([a, *wps, b]))
        for waypoints in candidates:
            if not all(in_bounds(p) for p in waypoints):
                continue
            points = [a, *waypoints, b]
            result = []
            try:
                for index, (left, right) in enumerate(zip(points, points[1:])):
                    result.extend(solve(left, right, depth + 1))
                    if index < len(waypoints):
                        result.append(right)
            except NoSafePathError:
                continue
            return result
        raise NoSafePathError("No safe bypass fits the sector and obstacles")

    waypoints = ([escape] if escape is not None else []) + solve(escape if escape is not None else start, end)
    waypoints = [p for p in waypoints if distance(p, start) > eps and distance(p, end) > eps]
    points = [start, *waypoints, end]
    if not all(in_bounds(p) for p in points) or any(first_blocker(a, b) is not None for a, b in zip(points, points[1:])):
        raise NoSafePathError("Final route failed clearance validation")
    return waypoints
