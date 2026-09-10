"""Explicit OS/display discovery, called only when constructing the application."""
import ctypes
import logging
import os
import sys

from display_config import DEFAULT_DISPLAY_CONFIG, DisplayConfig

logger = logging.getLogger(__name__)


def configure_dpi_awareness() -> None:
    """Request physical-pixel coordinates on Windows before creating a window."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            logger.debug("DPI awareness API unavailable")


def discover_display_config() -> DisplayConfig:
    """Read startup settings and monitor size, preserving an existing SDL display.

    Discovery owns only a display it initializes itself, and releases that display
    even when querying fails. Unavailable monitor dimensions use the fixed default.
    """
    import pygame

    configure_dpi_awareness()
    fullscreen = os.environ.get("WORMHOLE_FULLSCREEN", "True").lower() == "true"
    width, height = DEFAULT_DISPLAY_CONFIG.width, DEFAULT_DISPLAY_CONFIG.height
    if fullscreen:
        owned = not pygame.display.get_init()
        try:
            if owned:
                pygame.display.init()
            info = pygame.display.Info()
            if info.current_w > 0 and info.current_h > 0:
                width, height = info.current_w, info.current_h
        except pygame.error:
            logger.debug("Monitor discovery unavailable; using default resolution")
        finally:
            if owned:
                pygame.display.quit()
    return DisplayConfig(width, height, fullscreen)
