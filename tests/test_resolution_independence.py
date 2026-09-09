import pytest
from sector_utils import sector_coords_to_pixels, pixels_to_sector_coords
from geometry import Position


@pytest.mark.parametrize("pixel_radius", [300, 360, 384, 540, 720])
@pytest.mark.parametrize("logical_pos", [Position(500.0, -250.0), Position(-4000.0, 3000.0)])
def test_coordinate_roundtrip(monkeypatch, pixel_radius, logical_pos):
    # Verify logical coordinates map to pixels and back without losing alignment
    import sector_utils

    monkeypatch.setattr(sector_utils, "SECTOR_CIRCLE_RADIUS_IN_PX", pixel_radius)
    pixel_pos = sector_coords_to_pixels(logical_pos)
    logical_back = pixels_to_sector_coords(pixel_pos)
    
    # Integer pixel conversion loses less than one pixel on each axis.
    logical_units_per_pixel = sector_utils.SECTOR_CIRCLE_RADIUS_LOGICAL / pixel_radius
    assert abs(logical_pos.x - logical_back.x) < logical_units_per_pixel
    assert abs(logical_pos.y - logical_back.y) < logical_units_per_pixel


def test_fullscreen_resolution_autodetect():
    import importlib
    from unittest.mock import patch, MagicMock
    import os
    import constants

    orig_env = os.environ.get("WORMHOLE_FULLSCREEN")
    orig_dict = constants.__dict__.copy()

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
            mock_init.assert_called_once()
            mock_quit.assert_called_once()

        # 2. Test when FULLSCREEN is False (using environment variable override)
        os.environ["WORMHOLE_FULLSCREEN"] = "False"
        
        with patch('pygame.display.init') as mock_init, \
             patch('pygame.display.quit') as mock_quit:
            
            importlib.reload(constants)
            
            assert constants.FULLSCREEN is False
            assert constants.SCREEN_RES.x > 0 and constants.SCREEN_RES.y > 0
            mock_init.assert_not_called()
            mock_quit.assert_not_called()
            
    finally:
        if orig_env is None:
            if "WORMHOLE_FULLSCREEN" in os.environ:
                del os.environ["WORMHOLE_FULLSCREEN"]
        else:
            os.environ["WORMHOLE_FULLSCREEN"] = orig_env

        importlib.reload(constants)
        constants.__dict__.update(orig_dict)
