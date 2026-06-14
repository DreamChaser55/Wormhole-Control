import pytest
from constants import (
    SCREEN_RES, INFO_BOX_WIDTH, TOP_BAR_HEIGHT, CONTEXT_MENU_WIDTH, CONTEXT_MENU_ITEM_HEIGHT,
    PLANET_RADIUS, WORMHOLE_RADIUS, STAR_RADIUS, HEX_SIZE
)
from sector_utils import sector_coords_to_pixels, pixels_to_sector_coords
from geometry import Position

def test_dynamic_gui_constants():
    # Verify that constants scale proportionally based on SCREEN_RES.
    # At 1280x720 (baseline):
    # scale_x = 1.0, scale_y = 1.0
    if SCREEN_RES.x == 1280 and SCREEN_RES.y == 720:
        assert INFO_BOX_WIDTH == 250
        assert TOP_BAR_HEIGHT == 35
        assert CONTEXT_MENU_WIDTH == 180
        assert CONTEXT_MENU_ITEM_HEIGHT == 25
        assert HEX_SIZE == 25

def test_logical_radii():
    # Check that logical radii are set correctly in constants
    assert PLANET_RADIUS == 125.0
    assert WORMHOLE_RADIUS == 97.22
    assert STAR_RADIUS == 166.67

def test_coordinate_roundtrip():
    # Verify logical coordinates map to pixels and back without losing alignment
    logical_pos = Position(500.0, -250.0)
    pixel_pos = sector_coords_to_pixels(logical_pos)
    logical_back = pixels_to_sector_coords(pixel_pos)
    
    # Assert they are reasonably close (due to integer truncation in pixel conversion)
    assert abs(logical_pos.x - logical_back.x) <= 5.0
    assert abs(logical_pos.y - logical_back.y) <= 5.0
