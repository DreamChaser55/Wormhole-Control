"""System and sector view camera math and smooth zoom/pan controllers."""
import math
import pygame

from constants import (
    SECTOR_ZOOM_MIN, SECTOR_ZOOM_MAX, SECTOR_CIRCLE_CENTER_IN_PX,
    SYSTEM_ZOOM_MIN, SYSTEM_ZOOM_MAX, SYSTEM_CENTER_IN_PX,
)
from geometry import Position
from hexgrid_utils import get_hex_vertices

CAMERA_SMOOTH_SPEED = 12.0  # Exponential decay speed for zoom smoothing (~95% at 0.25s)


def _update_camera(game, dt: float, zoom_attr: str, target_attr: str,
                   pan_attr: str, anchor_pixel_attr: str,
                   anchor_logical_attr: str) -> None:
    zoom = getattr(game, zoom_attr)
    target_zoom = getattr(game, target_attr)
    t = 1.0 - math.exp(-CAMERA_SMOOTH_SPEED * dt)
    zoom += (target_zoom - zoom) * t
    setattr(game, zoom_attr, zoom)

    anchor_pixel = getattr(game, anchor_pixel_attr)
    anchor_logical = getattr(game, anchor_logical_attr)
    if anchor_pixel is None or anchor_logical is None:
        return

    pan_offset = getattr(game, pan_attr)
    pan_offset.x = anchor_pixel.x - anchor_logical.x * zoom
    pan_offset.y = anchor_pixel.y - anchor_logical.y * zoom

    if abs(zoom - target_zoom) < 1e-4:
        setattr(game, zoom_attr, target_zoom)
        setattr(game, anchor_pixel_attr, None)
        setattr(game, anchor_logical_attr, None)


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


def reset_system_camera(game, system_name=None) -> None:
    """Center and auto-fit a system inside the unobstructed gameplay viewport."""
    name = system_name or getattr(game, 'current_system_name', None)
    game.system_zoom = 1.0
    game.system_target_zoom = 1.0
    game.system_pan_offset = Position(0, 0)
    game.system_zoom_anchor_pixel = None
    game.system_zoom_anchor_logical = None
    game.system_camera_system_name = name

    gui = getattr(game, 'gui', None)
    viewport = getattr(gui, 'galaxy_generation_rect', None)
    galaxy = getattr(game, 'galaxy', None)
    system = galaxy.systems.get(name) if galaxy is not None and name else None
    if viewport is None or system is None or not getattr(system, 'hexes', None):
        return

    points = [
        point
        for q, r in system.hexes
        for point in get_hex_vertices(q, r)
    ]
    min_x = min(point.x for point in points)
    max_x = max(point.x for point in points)
    min_y = min(point.y for point in points)
    max_y = max(point.y for point in points)
    content_width = max(1.0, max_x - min_x)
    content_height = max(1.0, max_y - min_y)

    screen = getattr(game, 'screen', None)
    screen_height = screen.get_height() if screen is not None else 720
    padding = max(1.0, 5.0 * screen_height / 720.0)
    available_width = max(1.0, viewport.width - 2.0 * padding)
    available_height = max(1.0, viewport.height - 2.0 * padding)
    fit_zoom = min(1.0, available_width / content_width, available_height / content_height)
    fit_zoom = max(SYSTEM_ZOOM_MIN, min(SYSTEM_ZOOM_MAX, fit_zoom))

    content_center_x = (min_x + max_x) / 2.0
    content_center_y = (min_y + max_y) / 2.0
    game.system_zoom = fit_zoom
    game.system_target_zoom = fit_zoom
    game.system_pan_offset = Position(
        viewport.centerx - SYSTEM_CENTER_IN_PX.x
        - (content_center_x - SYSTEM_CENTER_IN_PX.x) * fit_zoom,
        viewport.centery - SYSTEM_CENTER_IN_PX.y
        - (content_center_y - SYSTEM_CENTER_IN_PX.y) * fit_zoom,
    )


def ensure_system_camera(game) -> None:
    """Auto-fit the current system if it has not been framed yet."""
    current_name = getattr(game, 'current_system_name', None)
    if getattr(game, 'system_camera_system_name', None) != current_name:
        reset_system_camera(game, current_name)


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
    _update_camera(
        game, dt, 'sector_zoom', 'sector_target_zoom', 'sector_pan_offset',
        'zoom_anchor_pixel', 'zoom_anchor_logical',
    )


def update_system_camera(game, dt: float) -> None:
    """Smoothly interpolate system zoom while keeping its cursor anchor fixed."""
    if not getattr(game, 'game_started', False) or getattr(game, 'view_mode', None) != 'system':
        return
    ensure_system_camera(game)
    _update_camera(
        game, dt, 'system_zoom', 'system_target_zoom', 'system_pan_offset',
        'system_zoom_anchor_pixel', 'system_zoom_anchor_logical',
    )


def handle_mouse_wheel(game, scroll_y: int) -> None:
    """Process mouse wheel input for smooth system or sector camera zooming.

    Args:
        game: Target game instance.
        scroll_y (int): Mouse wheel scroll delta (+1 for zoom in, -1 for zoom out).
    """
    view_mode = getattr(game, 'view_mode', None)
    if view_mode not in ('system', 'sector') or not getattr(game, 'game_started', False) or scroll_y == 0:
        return

    mouse_pos_tuple = pygame.mouse.get_pos()
    mouse_pos = Position(mouse_pos_tuple[0], mouse_pos_tuple[1])
    if hasattr(game, 'gui') and game.gui and game.gui.is_mouse_over_gui_panels(mouse_pos):
        return

    if view_mode == 'system':
        ensure_system_camera(game)
        zoom_attr = 'system_zoom'
        target_attr = 'system_target_zoom'
        pan_attr = 'system_pan_offset'
        anchor_pixel_attr = 'system_zoom_anchor_pixel'
        anchor_logical_attr = 'system_zoom_anchor_logical'
        center = SYSTEM_CENTER_IN_PX
        min_zoom, max_zoom = SYSTEM_ZOOM_MIN, SYSTEM_ZOOM_MAX
    else:
        zoom_attr = 'sector_zoom'
        target_attr = 'sector_target_zoom'
        pan_attr = 'sector_pan_offset'
        anchor_pixel_attr = 'zoom_anchor_pixel'
        anchor_logical_attr = 'zoom_anchor_logical'
        center = SECTOR_CIRCLE_CENTER_IN_PX
        min_zoom, max_zoom = SECTOR_ZOOM_MIN, SECTOR_ZOOM_MAX

    zoom_factor = 1.1 if scroll_y > 0 else 0.9
    old_target_zoom = getattr(game, target_attr)
    new_zoom = max(min_zoom, min(max_zoom, old_target_zoom * zoom_factor))
    if new_zoom == old_target_zoom:
        return

    zoom = getattr(game, zoom_attr)
    pan_offset = getattr(game, pan_attr)
    rx = mouse_pos.x - center.x
    ry = mouse_pos.y - center.y
    setattr(game, anchor_pixel_attr, Position(rx, ry))
    setattr(game, anchor_logical_attr, Position(
        (rx - pan_offset.x) / zoom,
        (ry - pan_offset.y) / zoom,
    ))
    setattr(game, target_attr, new_zoom)
