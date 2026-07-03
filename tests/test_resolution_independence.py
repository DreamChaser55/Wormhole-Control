import pytest
from constants import (
    SCREEN_RES, INFO_BOX_WIDTH, TOP_BAR_HEIGHT, CONTEXT_MENU_WIDTH, CONTEXT_MENU_ITEM_HEIGHT,
    PLANET_RADIUS, WORMHOLE_RADIUS, STAR_RADIUS, HEX_SIZE, HullSize, HULL_BASE_ICON_SCALES
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

def test_strikecraft_wing_icon_scale():
    # Verify that the scale factor for strikecraft wings is set to 1.2
    assert HULL_BASE_ICON_SCALES[HullSize.STRIKECRAFT_WING] == 1.2

def test_fullscreen_resolution_autodetect():
    import importlib
    from unittest.mock import patch, MagicMock
    import os
    import constants

    orig_env = os.environ.get("WORMHOLE_FULLSCREEN")

    try:
        # 1. Test when FULLSCREEN is True and display info returns a specific resolution
        mock_info = MagicMock()
        mock_info.current_w = 1920
        mock_info.current_h = 1080
        
        if "WORMHOLE_FULLSCREEN" in os.environ:
            del os.environ["WORMHOLE_FULLSCREEN"]

        with patch('pygame.display.init') as mock_init, \
             patch('pygame.display.quit') as mock_quit, \
             patch('pygame.display.Info', return_value=mock_info), \
             patch('pygame.display.get_init', return_value=False):
            
            importlib.reload(constants)
            
            assert constants.SCREEN_RES.x == 1920
            assert constants.SCREEN_RES.y == 1080
            assert constants.HEX_SIZE == 37
            assert constants.INFO_BOX_WIDTH == 375
            mock_init.assert_called_once()
            mock_quit.assert_called_once()

        # 2. Test when FULLSCREEN is False (using environment variable override)
        os.environ["WORMHOLE_FULLSCREEN"] = "False"
        
        with patch('pygame.display.init') as mock_init, \
             patch('pygame.display.quit') as mock_quit:
            
            importlib.reload(constants)
            
            assert constants.SCREEN_RES.x == 2560
            assert constants.SCREEN_RES.y == 1440
            assert constants.HEX_SIZE == 50
            mock_init.assert_not_called()
            mock_quit.assert_not_called()
            
    finally:
        if orig_env is None:
            if "WORMHOLE_FULLSCREEN" in os.environ:
                del os.environ["WORMHOLE_FULLSCREEN"]
        else:
            os.environ["WORMHOLE_FULLSCREEN"] = orig_env
            
        importlib.reload(constants)

