import math
import pytest
from geometry import Vector, Position, Circle, clamp_point_to_circle, clamp_vector_magnitude, position_at_distance_from_target
from sector_utils import (
    get_sector_pixel_center, get_sector_pixel_radius, get_sector_pixel_circle,
    sector_radius_to_pixels, pixels_to_sector_radius, sector_coords_to_pixels,
    pixels_to_sector_coords, is_pixel_in_sector, is_position_in_sector, clamp_position_to_sector
)
from constants import SECTOR_CIRCLE_RADIUS_LOGICAL, SECTOR_CIRCLE_CENTER_IN_PX, SECTOR_CIRCLE_RADIUS_IN_PX

def test_clamp_point_to_circle_inside():
    circle = Circle(Position(0, 0), 100.0)
    pt = Position(30, 40)
    clamped = clamp_point_to_circle(pt, circle)
    assert clamped.x == 30 and clamped.y == 40

def test_clamp_point_to_circle_outside():
    circle = Circle(Position(0, 0), 100.0)
    pt = Position(150, 0)
    clamped = clamp_point_to_circle(pt, circle)
    assert math.isclose(clamped.x, 100.0)
    assert math.isclose(clamped.y, 0.0)

def test_clamp_vector_magnitude():
    v = Vector(30, 40) # length 50
    v_clamped = clamp_vector_magnitude(v, 25.0)
    assert math.isclose(v_clamped.magnitude(), 25.0)
    assert math.isclose(v_clamped.x, 15.0)
    assert math.isclose(v_clamped.y, 20.0)

def test_position_at_distance_from_target():
    current = Position(0, 0)
    target = Position(100, 0)
    dest = position_at_distance_from_target(current, target, 20.0)
    # Along line target to current (-x direction), target + direction*20 => Position(80, 0)
    assert math.isclose(dest.x, 80.0)
    assert math.isclose(dest.y, 0.0)

def test_sector_pixel_center_and_radius():
    pan = Position(50, -30)
    center = get_sector_pixel_center(pan)
    assert center.x == SECTOR_CIRCLE_CENTER_IN_PX.x + 50
    assert center.y == SECTOR_CIRCLE_CENTER_IN_PX.y - 30

    radius = get_sector_pixel_radius(zoom=2.0)
    assert radius == SECTOR_CIRCLE_RADIUS_IN_PX * 2.0

    circle = get_sector_pixel_circle(zoom=1.5, pan_offset=pan)
    assert circle.center.x == center.x and circle.center.y == center.y
    assert circle.radius == SECTOR_CIRCLE_RADIUS_IN_PX * 1.5

def test_sector_radius_conversion():
    log_r = 500.0
    px_r = sector_radius_to_pixels(log_r, zoom=1.5)
    log_back = pixels_to_sector_radius(px_r, zoom=1.5)
    assert math.isclose(log_r, log_back)

def test_is_pixel_in_sector():
    center = get_sector_pixel_center()
    assert is_pixel_in_sector(center)
    outside = Position(center.x + SECTOR_CIRCLE_RADIUS_IN_PX + 10, center.y)
    assert not is_pixel_in_sector(outside)

def test_is_position_in_sector_and_clamping():
    inside = Position(100, 100)
    assert is_position_in_sector(inside)
    
    outside = Position(SECTOR_CIRCLE_RADIUS_LOGICAL + 500, 0)
    assert not is_position_in_sector(outside)

    clamped = clamp_position_to_sector(outside)
    assert is_position_in_sector(clamped)
    assert math.isclose(clamped.x, SECTOR_CIRCLE_RADIUS_LOGICAL)
    assert math.isclose(clamped.y, 0.0)
