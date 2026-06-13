import math
import pytest
from geometry import Vector, Position, Circle, distance, distance_sq, hex_distance, is_point_in_circle, do_circles_intersect, is_circle_contained, get_closest_point_on_circle_edge, move_towards_position
import hexgrid_utils

def test_vector_operations():
    v1 = Vector(2.0, 3.0)
    v2 = Vector(4.0, -1.0)
    
    # Addition
    v3 = v1 + v2
    assert v3.x == 6.0
    assert v3.y == 2.0
    
    # Subtraction
    v4 = v1 - v2
    assert v4.x == -2.0
    assert v4.y == 4.0
    
    # Multiplication
    v5 = v1 * 2.5
    assert v5.x == 5.0
    assert v5.y == 7.5
    
    # Magnitude
    assert v1.magnitude_sq() == 13.0
    assert math.isclose(v1.magnitude(), math.sqrt(13.0))
    
    # Normalize
    v_zero = Vector(0, 0)
    assert v_zero.normalize() == Vector(0, 0)
    v_norm = v1.normalize()
    assert math.isclose(v_norm.magnitude(), 1.0)
    
    # Representation and tuple
    assert v1.to_tuple() == (2.0, 3.0)
    assert repr(v1) == "Vector(x=2.00, y=3.00)"

def test_distance():
    p1 = Position(0, 0)
    p2 = Position(3, 4)
    assert distance_sq(p1, p2) == 25.0
    assert distance(p1, p2) == 5.0

def test_hex_distance():
    assert hex_distance((0, 0), (0, 0)) == 0
    assert hex_distance((0, 0), (1, 0)) == 1
    assert hex_distance((0, 0), (0, 1)) == 1
    assert hex_distance((0, 0), (-1, 1)) == 1
    assert hex_distance((0, 0), (2, -2)) == 2
    assert hex_distance((0, 0), (-2, 0)) == 2

def test_circle_utilities():
    c1 = Circle(Position(0, 0), 5.0)
    c2 = Circle(Position(8, 0), 4.0)
    c3 = Circle(Position(12, 0), 2.0)
    
    # is_point_in_circle
    assert is_point_in_circle(Position(3, 3), c1)
    assert not is_point_in_circle(Position(4, 4), c1)
    
    # do_circles_intersect
    assert do_circles_intersect(c1, c2)  # distance 8 < 5 + 4
    assert not do_circles_intersect(c1, c3)  # distance 12 not < 5 + 2
    
    # is_circle_contained
    c_outer = Circle(Position(0, 0), 10.0)
    c_inner = Circle(Position(2, 0), 5.0)
    c_not_contained = Circle(Position(6, 0), 5.0)
    assert is_circle_contained(c_inner, c_outer)  # 2 + 5 <= 10
    assert not is_circle_contained(c_not_contained, c_outer)  # 6 + 5 > 10

def test_get_closest_point_on_circle_edge():
    circle = Circle(Position(0, 0), 10.0)
    
    # Point outside
    pt = Position(20, 0)
    closest = get_closest_point_on_circle_edge(pt, circle)
    # Target position should be approximately 10.001 (due to epsilon_radius = circle.radius * 1.0001)
    assert math.isclose(closest.x, 10.001)
    assert math.isclose(closest.y, 0.0)
    
    # Point at center
    closest_center = get_closest_point_on_circle_edge(Position(0, 0), circle)
    assert math.isclose(closest_center.x, 10.001)
    assert math.isclose(closest_center.y, 0.0)

def test_move_towards_position():
    current = Position(0, 0)
    target = Position(10, 0)
    
    # Move and maintain a distance of 2 from target (so end up at 8, 0)
    dest = move_towards_position(current, target, 2.0)
    assert math.isclose(dest.x, 8.0)
    assert math.isclose(dest.y, 0.0)
    
    # If starting at target
    dest_same = move_towards_position(target, target, 3.0)
    assert math.isclose(dest_same.x, 13.0)
    assert math.isclose(dest_same.y, 0.0)

def test_hexgrid_utils():
    # Convert axial to pixel and back
    q, r = 2, -1
    px = hexgrid_utils.hex_to_pixel(q, r)
    qr_back = hexgrid_utils.pixel_to_hex(int(px.x), int(px.y))
    assert qr_back == (q, r)
    
    # hex_distance function in hexgrid_utils
    assert hexgrid_utils.hex_distance(0, 0, 2, -2) == 2
    
    # get_hex_vertices
    vertices = hexgrid_utils.get_hex_vertices(0, 0)
    assert len(vertices) == 6
    for v in vertices:
        assert isinstance(v, Position)
