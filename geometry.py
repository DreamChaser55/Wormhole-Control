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


def compute_avoidance_waypoints(
    start: Position,
    end: Position,
    obstacles: typing.List[Circle],
    margin: float = 50.0,
) -> typing.List[Position]:
    """Computes intermediate waypoints so the path from *start* to *end* avoids
    every obstacle in the list.

    Each obstacle ``Circle`` represents the physical extent of a celestial body.
    A safety *margin* is added around each obstacle when testing for clearances
    and placing waypoints.

    Returns a (possibly empty) list of intermediate ``Position`` waypoints.
    An empty list means the direct path is already clear.
    """
    if not obstacles:
        return []

    MAX_DEPTH = 8  # Prevent infinite recursion in degenerate layouts.
    expanded = [Circle(obs.center, obs.radius + margin) for obs in obstacles]

    def _first_blocker(p1: Position, p2: Position) -> typing.Optional[typing.Tuple[Circle, Circle]]:
        """Return the first expanded obstacle hit by the segment, or None."""
        best: typing.Optional[typing.Tuple[Circle, Circle]] = None
        best_t: float = float("inf")
        for i, obs in enumerate(expanded):
            orig = obstacles[i]
            # Skip obstacles that contain either endpoint so units can land/depart
            if distance_sq(p1, orig.center) <= orig.radius * orig.radius:
                continue
            if distance_sq(p2, orig.center) <= orig.radius * orig.radius:
                continue
            if not segment_intersects_circle(p1, p2, orig):
                continue
            # Parametric entry t to find the closest blocker to p1
            dx = p2.x - p1.x
            dy = p2.y - p1.y
            fx = p1.x - orig.center.x
            fy = p1.y - orig.center.y
            a = dx * dx + dy * dy
            if a < 1e-12:
                continue
            b_val = 2.0 * (fx * dx + fy * dy)
            c_val = fx * fx + fy * fy - orig.radius * orig.radius
            disc = b_val * b_val - 4.0 * a * c_val
            if disc < 0.0:
                continue
            t_entry = max(0.0, (-b_val - math.sqrt(disc)) / (2.0 * a))
            if t_entry < best_t:
                best_t = t_entry
                best = (obs, orig)
        return best

    def _get_tangent_angle(P: Position, C: Position, R: float) -> typing.Tuple[float, float]:
        dx = P.x - C.x
        dy = P.y - C.y
        d = math.hypot(dx, dy)
        if d <= 1e-9:
            return 0.0, 0.0
        theta = math.atan2(dy, dx)
        if d <= R:
            return theta, 0.0
        alpha = math.acos(min(1.0, R / d))
        return theta, alpha

    def _generate_candidate_path(
        p1: Position, p2: Position, exp_obs: Circle, orig_obs: Circle, side_sign: float
    ) -> typing.List[Position]:
        C = exp_obs.center
        R = exp_obs.radius
        r_body = orig_obs.radius

        theta1, alpha1 = _get_tangent_angle(p1, C, R)
        theta2, alpha2 = _get_tangent_angle(p2, C, R)

        a_start = theta1 + side_sign * alpha1
        a_end = theta2 - side_sign * alpha2

        # Compute angular difference for the shortest arc
        diff = (a_end - a_start + math.pi) % (2.0 * math.pi) - math.pi

        # Maximum angular step ensuring every straight chord between waypoints satisfies:
        # R * cos(step / 2) >= r_body
        ratio = max(0.0, min(1.0, r_body / R))
        max_step = max(0.3, 2.0 * math.acos(ratio) * 0.95)

        num_steps = max(1, math.ceil(abs(diff) / max_step))
        step = diff / num_steps

        wps: typing.List[Position] = []
        for i in range(num_steps + 1):
            ang = a_start + i * step
            wp = Position(C.x + R * math.cos(ang), C.y + R * math.sin(ang))
            if not wps or distance(wps[-1], wp) > 1.0:
                wps.append(wp)
        return wps

    def _path_length(pts: typing.List[Position]) -> float:
        return sum(distance(pts[i], pts[i+1]) for i in range(len(pts)-1))

    def _solve(p1: Position, p2: Position, depth: int = 0) -> typing.List[Position]:
        if depth >= MAX_DEPTH:
            return []
        blocker_pair = _first_blocker(p1, p2)
        if blocker_pair is None:
            return []
        exp_obs, orig_obs = blocker_pair

        path_pos = _generate_candidate_path(p1, p2, exp_obs, orig_obs, +1.0)
        path_neg = _generate_candidate_path(p1, p2, exp_obs, orig_obs, -1.0)

        len_pos = _path_length([p1] + path_pos + [p2])
        len_neg = _path_length([p1] + path_neg + [p2])

        chosen_wps = path_pos if len_pos <= len_neg else path_neg

        # Recursively resolve any collisions on all sub-segments
        full_pts = [p1] + chosen_wps + [p2]
        result: typing.List[Position] = []
        for i in range(len(full_pts) - 1):
            sub_start = full_pts[i]
            sub_end = full_pts[i+1]
            sub_avoidance = _solve(sub_start, sub_end, depth + 1)
            result.extend(sub_avoidance)
            if i < len(chosen_wps):
                result.append(chosen_wps[i])
        return result

    return _solve(start, end)


