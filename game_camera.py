"""Sector view camera math and smooth zoom/pan controller."""
import math
import pygame

from constants import SECTOR_ZOOM_MIN, SECTOR_ZOOM_MAX, SECTOR_CIRCLE_CENTER_IN_PX
from geometry import Position

CAMERA_SMOOTH_SPEED = 12.0  # Exponential decay speed for zoom smoothing (~95% at 0.25s)


def reset_sector_camera(game) -> None:
    """Resets the sector camera zoom and pan offset.

    Snaps both leader and follower camera state instantly to default zoom (1.0)
    and clears any active zoom anchor point.

    Args:
        game: Target game instance.
    """
    game.sector_zoom = 1.0
    game.sector_pan_offset = Position(0, 0)
    game.sector_target_zoom = 1.0
    game.zoom_anchor_pixel = None
    game.zoom_anchor_logical = None


def update_sector_camera(game, dt: float) -> None:
    """Smoothly interpolates the sector camera zoom and pan offset.

    Uses framerate-independent exponential decay to transition ``sector_zoom`` toward
    ``sector_target_zoom`` and locks ``sector_pan_offset`` to the active zoom anchor to prevent
    anchor-point drift and visual jitter.

    Args:
        game: Target game instance.
        dt (float): Elapsed time since last frame in seconds.
    """
    if not getattr(game, 'game_started', False) or getattr(game, 'view_mode', None) != 'sector':
        return
    t = 1.0 - math.exp(-CAMERA_SMOOTH_SPEED * dt)
    game.sector_zoom += (game.sector_target_zoom - game.sector_zoom) * t

    if game.zoom_anchor_pixel is not None and game.zoom_anchor_logical is not None:
        game.sector_pan_offset.x = game.zoom_anchor_pixel.x - game.zoom_anchor_logical.x * game.sector_zoom
        game.sector_pan_offset.y = game.zoom_anchor_pixel.y - game.zoom_anchor_logical.y * game.sector_zoom

        # Clear the anchor once the zoom animation is virtually complete
        if abs(game.sector_zoom - game.sector_target_zoom) < 1e-4:
            game.sector_zoom = game.sector_target_zoom
            game.zoom_anchor_pixel = None
            game.zoom_anchor_logical = None


def handle_mouse_wheel(game, scroll_y: int) -> None:
    """Processes mouse scroll wheel input for smooth sector camera zooming.

    Args:
        game: Target game instance.
        scroll_y (int): Mouse wheel scroll delta (+1 for zoom in, -1 for zoom out).
    """
    if getattr(game, 'view_mode', None) == 'sector' and getattr(game, 'game_started', False):
        mouse_pos_tuple = pygame.mouse.get_pos()
        mouse_pos = Position(mouse_pos_tuple[0], mouse_pos_tuple[1])

        if hasattr(game, 'gui') and game.gui and game.gui.is_mouse_over_gui_panels(mouse_pos):
            return

        zoom_factor = 1.1 if scroll_y > 0 else 0.9
        old_target_zoom = game.sector_target_zoom
        new_zoom = old_target_zoom * zoom_factor

        # Constrain new_zoom
        if new_zoom < SECTOR_ZOOM_MIN:
            new_zoom = SECTOR_ZOOM_MIN
        elif new_zoom > SECTOR_ZOOM_MAX:
            new_zoom = SECTOR_ZOOM_MAX

        if new_zoom != old_target_zoom:
            rx = mouse_pos.x - SECTOR_CIRCLE_CENTER_IN_PX.x
            ry = mouse_pos.y - SECTOR_CIRCLE_CENTER_IN_PX.y

            # Establish/update the zoom anchor logical coordinates based on the CURRENT follower camera view
            lx = (rx - game.sector_pan_offset.x) / game.sector_zoom
            ly = (ry - game.sector_pan_offset.y) / game.sector_zoom

            game.zoom_anchor_pixel = Position(rx, ry)
            game.zoom_anchor_logical = Position(lx, ly)

            game.sector_target_zoom = new_zoom
