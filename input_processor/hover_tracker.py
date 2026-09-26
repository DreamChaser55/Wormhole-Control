from sector_utils import sector_coords_to_pixels, sector_radius_to_pixels
"""Spatial entity hover state tracking across galaxy, system, and sector views."""
from display_config import display_config_for
import typing
import logging
from constants import (
    STAR_RADIUS, PLANET_RADIUS, WORMHOLE_RADIUS, HULL_BASE_ICON_SCALES,
    SECTOR_VIEW_BASE_ICON_SIZE, MOON_RADIUS, ASTEROID_RADIUS, COMET_RADIUS
)
from geometry import Position, distance_sq
from hexgrid_utils import pixel_to_hex
from sector_utils import (
    get_minefield_dot_pixel_positions,
    get_minefield_dot_radius_px,
)
from domain.units import Unit
from domain.celestials import Star, Planet, Moon, ColonizableAsteroid, MetalAsteroid, Comet, Wormhole
from galaxy_utils import logical_to_screen_galaxy

logger = logging.getLogger(__name__)


def get_galaxy_system_at(game, gui, mouse_pos: Position):
    """Pick a system using the same camera and scaled radius as the map."""
    viewport = gui.galaxy_generation_rect
    if (not game.galaxy or not game.galaxy.systems or viewport is None
            or not viewport.collidepoint(mouse_pos.to_tuple())
            or gui.is_mouse_over_gui_panels(mouse_pos)
            or gui.is_mouse_over_context_menu(mouse_pos)):
        return None
    hover_dist_sq = (22 * game.galaxy_zoom) ** 2
    for sys_name, system in game.galaxy.systems.items():
        screen_pos = logical_to_screen_galaxy(
            system.position, viewport, game.galaxy_zoom, game.galaxy_pan_offset,
        )
        if distance_sq(mouse_pos, screen_pos) < hover_dist_sq:
            return sys_name
    return None


def update_hover_states(game, gui, mouse_pos: Position) -> None:
    """Updates entity hover state tracking across galaxy, system, and sector views.

    Args:
        game: Target Game instance.
        gui: Target GUI_Handler instance.
        mouse_pos (Position): Current mouse screen coordinates.
    """
    game.galaxy_view_mouse_hover_system_name = None
    game.system_view_mouse_hover_hex = None
    game.sector_view_mouse_hover_object = None

    context_menu_hover = gui.is_mouse_over_context_menu(mouse_pos)
    if context_menu_hover:
        return

    if game.view_mode == 'galaxy':
        game.galaxy_view_mouse_hover_system_name = get_galaxy_system_at(game, gui, mouse_pos)

    elif game.view_mode == 'system':
        if not game.current_system_name:
            return
        system = game.galaxy.systems[game.current_system_name]
        if system:
            zoom = game.system_zoom
            pan_offset = game.system_pan_offset
            hover_hex = pixel_to_hex(mouse_pos.x, mouse_pos.y, zoom, pan_offset, display_config=display_config_for(game))
            if hover_hex in system.hexes:
                game.system_view_mouse_hover_hex = hover_hex

    elif game.view_mode == 'sector':
        if not game.current_system_name or game.current_sector_coord is None:
            return
        system = game.galaxy.systems[game.current_system_name]
        if system:
            zoom = game.sector_zoom
            pan_offset = game.sector_pan_offset

            min_dist_sq = float('inf')
            hovered_obj = None
            hex_obj = system.hexes[game.current_sector_coord]
            if hex_obj:
                bodies = hex_obj.celestial_bodies
                units = hex_obj.units
                from domain.deployables import Deployable
                from domain.construction_job import ConstructionJob, get_sector_construction_jobs
                current_viewer = getattr(game, 'current_player', None)
                construction_jobs = get_sector_construction_jobs(hex_obj, viewer=current_viewer)
                for obj in units + bodies + list(getattr(hex_obj, 'deployables', ())) + construction_jobs:
                    if isinstance(obj, Deployable) and not game.is_unit_visible(obj):
                        continue
                    if isinstance(obj, Unit) and not game.is_unit_visible(obj):
                        continue
                    if not getattr(obj, 'is_solid', True):
                        continue
                    pixel_pos = sector_coords_to_pixels(obj.position, zoom, pan_offset, display_config=display_config_for(game))

                    obj_radius_logical = 0
                    if isinstance(obj, Star):
                        obj_radius_logical = getattr(obj, 'collision_radius', STAR_RADIUS)
                    elif isinstance(obj, Planet):
                        obj_radius_logical = getattr(obj, 'collision_radius', PLANET_RADIUS)
                    elif isinstance(obj, Wormhole):
                        obj_radius_logical = WORMHOLE_RADIUS
                    elif isinstance(obj, (Unit, ConstructionJob)):
                        scale_factor = HULL_BASE_ICON_SCALES.get(obj.hull_size, 1.0)
                        effective_icon_size = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
                        obj_radius_logical = effective_icon_size
                    elif isinstance(obj, Moon):
                        obj_radius_logical = getattr(obj, 'collision_radius', MOON_RADIUS)
                    elif isinstance(obj, (ColonizableAsteroid, MetalAsteroid)):
                        obj_radius_logical = getattr(obj, 'collision_radius', ASTEROID_RADIUS)
                    elif isinstance(obj, Comet):
                        obj_radius_logical = getattr(obj, 'collision_radius', COMET_RADIUS)
                    else:
                        obj_radius_logical = 13.89

                    obj_radius = sector_radius_to_pixels(obj_radius_logical, zoom, display_config=display_config_for(game))
                    click_radius_sq = (max(obj_radius, 5.0)) ** 2
                    dist_sq_val = distance_sq(mouse_pos, pixel_pos)

                    if dist_sq_val < click_radius_sq and dist_sq_val < min_dist_sq:
                        min_dist_sq = dist_sq_val
                        hovered_obj = obj

                # Check Minefield mine count icons (dots/diamonds)
                visible_minefields = [mf for mf in getattr(hex_obj, 'minefields', []) if game.is_minefield_visible(mf)]
                dot_radius_px = get_minefield_dot_radius_px(zoom, display_config=display_config_for(game))
                dot_click_radius = max(dot_radius_px, 5.0)
                dot_click_radius_sq = dot_click_radius ** 2
                for mf in visible_minefields:
                    dot_positions = get_minefield_dot_pixel_positions(mf.position, mf.mines_remaining, zoom, pan_offset, display_config=display_config_for(game))
                    for d_x, d_y in dot_positions:
                        dist_sq_val = (mouse_pos.x - d_x) ** 2 + (mouse_pos.y - d_y) ** 2
                        if dist_sq_val < dot_click_radius_sq and dist_sq_val < min_dist_sq:
                            min_dist_sq = dist_sq_val
                            hovered_obj = mf

            game.sector_view_mouse_hover_object = hovered_obj


def get_units_under_mouse(game, mouse_pos: Position) -> typing.List[Unit]:
    """Returns all visible units in the current sector whose selection/click circle contains mouse_pos,
    ordered by distance from mouse_pos (closest first).

    Args:
        game: Target Game instance.
        mouse_pos (Position): Mouse screen coordinates.

    Returns:
        List[Unit]: Matching visible units under the cursor.
    """
    if getattr(game, 'view_mode', None) != 'sector':
        return []
    if not getattr(game, 'current_system_name', None) or getattr(game, 'current_sector_coord', None) is None:
        return []
    if not getattr(game, 'galaxy', None) or not game.galaxy.systems:
        return []

    system = game.galaxy.systems.get(game.current_system_name)
    if not system or game.current_sector_coord not in system.hexes:
        return []

    hex_obj = system.hexes[game.current_sector_coord]
    if not hex_obj or not hex_obj.units:
        return []

    zoom = game.sector_zoom
    pan_offset = game.sector_pan_offset

    matching_units: typing.List[typing.Tuple[float, Unit]] = []
    for unit in hex_obj.units:
        if not game.is_unit_visible(unit):
            continue
        pixel_pos = sector_coords_to_pixels(unit.position, zoom, pan_offset, display_config=display_config_for(game))
        scale_factor = HULL_BASE_ICON_SCALES[unit.hull_size]
        effective_icon_size = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
        obj_radius = sector_radius_to_pixels(effective_icon_size, zoom, display_config=display_config_for(game))
        click_radius_sq = (max(obj_radius, 5.0)) ** 2
        dist_sq_val = distance_sq(mouse_pos, pixel_pos)

        if dist_sq_val < click_radius_sq:
            matching_units.append((dist_sq_val, unit))

    matching_units.sort(key=lambda item: item[0])
    return [unit for _, unit in matching_units]
