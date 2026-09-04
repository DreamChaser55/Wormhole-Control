"""Spatial entity hover state tracking across galaxy, system, and sector views."""
import typing
import logging
from constants import (
    STAR_RADIUS, PLANET_RADIUS, WORMHOLE_RADIUS, HULL_BASE_ICON_SCALES,
    SECTOR_VIEW_BASE_ICON_SIZE, MOON_RADIUS, ASTEROID_RADIUS, COMET_RADIUS,
    CELESTIAL_FIELD_RADIUS, SECTOR_OBJECT_CLICK_RADIUS_MULT
)
from geometry import Position, distance_sq
from hexgrid_utils import pixel_to_hex
import sys
from sector_utils import (
    get_minefield_dot_pixel_positions,
    get_minefield_dot_radius_px,
)
from entities import (
    Unit, Star, Planet, Moon, ColonizableAsteroid, MetalAsteroid, Comet,
    Wormhole, AsteroidField, IceField, DebrisField, Nebula, Storm
)
from galaxy_utils import logical_to_screen_galaxy

logger = logging.getLogger(__name__)


def sector_coords_to_pixels(*args, **kwargs):
    mod = sys.modules.get('input_processor')
    fn = getattr(mod, 'sector_coords_to_pixels', None) if mod else None
    if fn is not None and fn is not sector_coords_to_pixels:
        return fn(*args, **kwargs)
    import sector_utils
    return sector_utils.sector_coords_to_pixels(*args, **kwargs)


def sector_radius_to_pixels(*args, **kwargs):
    mod = sys.modules.get('input_processor')
    fn = getattr(mod, 'sector_radius_to_pixels', None) if mod else None
    if fn is not None and fn is not sector_radius_to_pixels:
        return fn(*args, **kwargs)
    import sector_utils
    return sector_utils.sector_radius_to_pixels(*args, **kwargs)



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
        if not game.galaxy or not game.galaxy.systems:
            return
        hover_dist_sq = 22**2
        for sys_name, system in game.galaxy.systems.items():
            screen_pos = logical_to_screen_galaxy(system.position, gui.galaxy_generation_rect)
            if distance_sq(mouse_pos, screen_pos) < hover_dist_sq:
                game.galaxy_view_mouse_hover_system_name = sys_name
                break

    elif game.view_mode == 'system':
        if not game.current_system_name:
            return
        system = game.galaxy.systems[game.current_system_name]
        if system:
            zoom = game.system_zoom if isinstance(getattr(game, 'system_zoom', 1.0), (int, float)) else 1.0
            pan_offset = game.system_pan_offset if isinstance(getattr(game, 'system_pan_offset', None), Position) else Position(0, 0)
            hover_hex = pixel_to_hex(mouse_pos.x, mouse_pos.y, zoom, pan_offset)
            if hover_hex in system.hexes:
                game.system_view_mouse_hover_hex = hover_hex

    elif game.view_mode == 'sector':
        if not game.current_system_name or game.current_sector_coord is None:
            return
        system = game.galaxy.systems[game.current_system_name]
        if system:
            zoom = game.sector_zoom
            if not isinstance(zoom, (int, float)):
                zoom = 1.0
            pan_offset = game.sector_pan_offset
            if not isinstance(pan_offset, Position):
                pan_offset = Position(0, 0)

            min_dist_sq = float('inf')
            hovered_obj = None
            hex_obj = system.hexes[game.current_sector_coord]
            if hex_obj:
                bodies = hex_obj.celestial_bodies
                units = hex_obj.units
                for obj in units + bodies:
                    if isinstance(obj, Unit) and not game.is_unit_visible(obj):
                        continue
                    if not getattr(obj, 'is_solid', True):
                        continue
                    pixel_pos = sector_coords_to_pixels(obj.position, zoom, pan_offset)

                    obj_radius_logical = 0
                    if isinstance(obj, Star):
                        obj_radius_logical = STAR_RADIUS
                    elif isinstance(obj, Planet):
                        obj_radius_logical = PLANET_RADIUS
                    elif isinstance(obj, Wormhole):
                        obj_radius_logical = WORMHOLE_RADIUS
                    elif isinstance(obj, Unit):
                        scale_factor = HULL_BASE_ICON_SCALES[obj.hull_size]
                        effective_icon_size = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
                        obj_radius_logical = effective_icon_size
                    elif isinstance(obj, Moon):
                        obj_radius_logical = MOON_RADIUS
                    elif isinstance(obj, (ColonizableAsteroid, MetalAsteroid)):
                        obj_radius_logical = ASTEROID_RADIUS
                    elif isinstance(obj, Comet):
                        obj_radius_logical = COMET_RADIUS
                    else:
                        obj_radius_logical = 13.89

                    obj_radius = sector_radius_to_pixels(obj_radius_logical, zoom)
                    actual_click_radius = obj_radius * SECTOR_OBJECT_CLICK_RADIUS_MULT
                    click_radius_sq = (max(actual_click_radius, 5.0))**2
                    if click_radius_sq < 5**2:
                        click_radius_sq = 5**2
                    dist_sq_val = distance_sq(mouse_pos, pixel_pos)

                    if dist_sq_val < click_radius_sq and dist_sq_val < min_dist_sq:
                        min_dist_sq = dist_sq_val
                        hovered_obj = obj

                # Check Minefield mine count icons (dots/diamonds)
                visible_minefields = [mf for mf in getattr(hex_obj, 'minefields', []) if game.is_minefield_visible(mf)]
                dot_radius_px = get_minefield_dot_radius_px(zoom)
                dot_click_radius = max(dot_radius_px * SECTOR_OBJECT_CLICK_RADIUS_MULT, 5.0)
                dot_click_radius_sq = dot_click_radius ** 2
                for mf in visible_minefields:
                    dot_positions = get_minefield_dot_pixel_positions(mf.position, mf.mines_remaining, zoom, pan_offset)
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

    zoom = game.sector_zoom if isinstance(getattr(game, 'sector_zoom', 1.0), (int, float)) else 1.0
    pan_offset = game.sector_pan_offset if isinstance(getattr(game, 'sector_pan_offset', None), Position) else Position(0, 0)

    matching_units: typing.List[typing.Tuple[float, Unit]] = []
    for unit in hex_obj.units:
        if not game.is_unit_visible(unit):
            continue
        pixel_pos = sector_coords_to_pixels(unit.position, zoom, pan_offset)
        scale_factor = HULL_BASE_ICON_SCALES[unit.hull_size]
        effective_icon_size = SECTOR_VIEW_BASE_ICON_SIZE * scale_factor
        obj_radius = sector_radius_to_pixels(effective_icon_size, zoom)
        actual_click_radius = obj_radius * SECTOR_OBJECT_CLICK_RADIUS_MULT
        click_radius_sq = (max(actual_click_radius, 5.0)) ** 2
        if click_radius_sq < 5 ** 2:
            click_radius_sq = 5 ** 2
        dist_sq_val = distance_sq(mouse_pos, pixel_pos)

        if dist_sq_val < click_radius_sq:
            matching_units.append((dist_sq_val, unit))

    matching_units.sort(key=lambda item: item[0])
    return [unit for _, unit in matching_units]
