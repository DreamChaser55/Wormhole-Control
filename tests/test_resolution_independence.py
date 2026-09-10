import pytest
from sector_utils import sector_coords_to_pixels, pixels_to_sector_coords
from geometry import Position
from display_config import DisplayConfig


@pytest.mark.parametrize("pixel_radius", [300, 360, 384, 540, 720])
@pytest.mark.parametrize("logical_pos", [Position(500.0, -250.0), Position(-4000.0, 3000.0)])
def test_coordinate_roundtrip(monkeypatch, pixel_radius, logical_pos):
    # Verify logical coordinates map to pixels and back without losing alignment
    import sector_utils

    config = DisplayConfig(1280, pixel_radius * 2)
    pixel_pos = sector_coords_to_pixels(logical_pos, display_config=config)
    logical_back = pixels_to_sector_coords(pixel_pos, display_config=config)
    
    # Integer pixel conversion loses less than one pixel on each axis.
    logical_units_per_pixel = sector_utils.SECTOR_CIRCLE_RADIUS_LOGICAL / pixel_radius
    assert abs(logical_pos.x - logical_back.x) < logical_units_per_pixel
    assert abs(logical_pos.y - logical_back.y) < logical_units_per_pixel


@pytest.mark.parametrize("initialized", [False, True])
@pytest.mark.parametrize("fails", [False, True])
def test_discovery_preserves_display_ownership(monkeypatch, initialized, fails):
    from unittest.mock import Mock, patch
    import pygame
    from application_bootstrap import discover_display_config
    monkeypatch.setenv("WORMHOLE_FULLSCREEN", "true")
    with patch('pygame.display.init') as init, patch('pygame.display.quit') as quit_display, patch('pygame.display.get_init', return_value=initialized), patch('pygame.display.Info', return_value=Mock(current_w=1920, current_h=1080), side_effect=pygame.error('unavailable') if fails else None):
        config = discover_display_config()
    assert (config.width, config.height) == ((2560, 1440) if fails else (1920, 1080))
    assert init.call_count == quit_display.call_count == (0 if initialized else 1)


def test_windowed_bootstrap_skips_display_discovery(monkeypatch):
    from unittest.mock import patch
    from application_bootstrap import discover_display_config
    monkeypatch.setenv("WORMHOLE_FULLSCREEN", "false")
    with patch('pygame.display.Info') as info, patch('pygame.display.init') as init:
        config = discover_display_config()
    assert config == DisplayConfig(2560, 1440, False)
    info.assert_not_called()
    init.assert_not_called()


@pytest.mark.parametrize("modern_error", [None, AttributeError, OSError])
def test_dpi_bootstrap_falls_back_only_when_modern_api_is_unavailable(modern_error):
    from types import SimpleNamespace
    from unittest.mock import Mock, patch
    import application_bootstrap as bootstrap
    modern, legacy = Mock(side_effect=modern_error), Mock()
    windows = SimpleNamespace(shcore=SimpleNamespace(SetProcessDpiAwareness=modern),
                              user32=SimpleNamespace(SetProcessDPIAware=legacy))
    with patch.object(bootstrap.sys, 'platform', 'win32'), patch.object(bootstrap.ctypes, 'windll', windows, create=True):
        bootstrap.configure_dpi_awareness()
    modern.assert_called_once_with(2)
    if modern_error is None:
        legacy.assert_not_called()
    else:
        legacy.assert_called_once_with()


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_dpi_bootstrap_skips_windows_apis_on_other_platforms(platform):
    from unittest.mock import patch
    import application_bootstrap as bootstrap

    class UnavailableWindowsAPIs:
        @property
        def windll(self):
            raise AssertionError("Non-Windows bootstrap accessed Windows APIs")

    with patch.object(bootstrap.sys, 'platform', platform), patch.object(bootstrap, 'ctypes', UnavailableWindowsAPIs()):
        bootstrap.configure_dpi_awareness()


def test_windows_bootstrap_requests_per_monitor_physical_pixels():
    import os
    import subprocess
    import sys
    if os.name != 'nt':
        pytest.skip('Windows DPI API')
    script = '''
import ctypes
from application_bootstrap import configure_dpi_awareness
configure_dpi_awareness()
awareness = ctypes.c_int()
result = ctypes.windll.shcore.GetProcessDpiAwareness(None, ctypes.byref(awareness))
assert result == 0 and awareness.value == 2, (result, awareness.value)
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
