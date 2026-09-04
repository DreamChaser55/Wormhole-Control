import typing
import pygame
from geometry import Vector, Position
from constants import LOGICAL_GALAXY_SIZE

def logical_to_screen_galaxy(logical_pos: Vector, render_rect: pygame.Rect) -> Vector:
    """
    Maps a logical galaxy coordinate to a screen pixel coordinate within the given render_rect.
    Maintains aspect ratio and centers the logical space within the rect.
    """
    if render_rect is None:
        # Fallback if no rect is provided
        return Vector(logical_pos.x, logical_pos.y)

    x_scale = render_rect.width / LOGICAL_GALAXY_SIZE.x
    y_scale = render_rect.height / LOGICAL_GALAXY_SIZE.y
    scale = min(x_scale, y_scale)

    scaled_width = LOGICAL_GALAXY_SIZE.x * scale
    scaled_height = LOGICAL_GALAXY_SIZE.y * scale

    offset_x = render_rect.left + (render_rect.width - scaled_width) / 2
    offset_y = render_rect.top + (render_rect.height - scaled_height) / 2

    screen_x = offset_x + logical_pos.x * scale
    screen_y = offset_y + logical_pos.y * scale
    return Vector(screen_x, screen_y)

def screen_to_logical_galaxy(screen_pos: Position, render_rect: pygame.Rect) -> Vector:
    """
    Maps a screen pixel coordinate within the render_rect back to a logical galaxy coordinate.
    """
    if render_rect is None:
        return Vector(screen_pos.x, screen_pos.y)

    x_scale = render_rect.width / LOGICAL_GALAXY_SIZE.x
    y_scale = render_rect.height / LOGICAL_GALAXY_SIZE.y
    scale = min(x_scale, y_scale)

    scaled_width = LOGICAL_GALAXY_SIZE.x * scale
    scaled_height = LOGICAL_GALAXY_SIZE.y * scale

    offset_x = render_rect.left + (render_rect.width - scaled_width) / 2
    offset_y = render_rect.top + (render_rect.height - scaled_height) / 2

    logical_x = (screen_pos.x - offset_x) / scale
    logical_y = (screen_pos.y - offset_y) / scale
    return Vector(logical_x, logical_y)


def get_home_systems_mapping(game: typing.Any) -> typing.Dict[str, typing.List[typing.Any]]:
    """Returns a mapping of star system name to a list of Player instances
    whose homeworld is located in that system.
    """
    if not game or not getattr(game, "players", None):
        return {}

    home_systems_map: typing.Dict[str, typing.List[typing.Any]] = {}
    galaxy = getattr(game, "galaxy", None)

    for player in game.players:
        system_name = None
        # 1. Primary lookup via player.homeworld_id
        hw_id = getattr(player, "homeworld_id", None)
        if hw_id is not None and galaxy and hasattr(galaxy, "get_celestial_body_by_id"):
            hw_body = galaxy.get_celestial_body_by_id(hw_id)
            if hw_body and getattr(hw_body, "in_system", None):
                system_name = hw_body.in_system

        # 2. Fallback: check game.player_homeworlds if available
        if not system_name and hasattr(game, "player_homeworlds") and isinstance(game.player_homeworlds, dict):
            hw_info = game.player_homeworlds.get(player)
            if isinstance(hw_info, tuple) and len(hw_info) > 0 and isinstance(hw_info[0], str):
                system_name = hw_info[0]
            elif hasattr(hw_info, "in_system"):
                system_name = hw_info.in_system

        # 3. Fallback: scan galaxy for any planet owned by the player
        if not system_name and galaxy and hasattr(galaxy, "systems") and isinstance(galaxy.systems, dict):
            for sys_name, sys_obj in galaxy.systems.items():
                hexes = getattr(sys_obj, "hexes", {})
                if isinstance(hexes, dict):
                    for hex_obj in hexes.values():
                        bodies = getattr(hex_obj, "celestial_bodies", [])
                        for body in bodies:
                            if getattr(body, "owner", None) == player:
                                system_name = getattr(body, "in_system", sys_name)
                                if getattr(player, "homeworld_id", None) is None:
                                    player.homeworld_id = getattr(body, "id", None)
                                break
                        if system_name:
                            break
                if system_name:
                    break

        if system_name:
            home_systems_map.setdefault(system_name, []).append(player)

    return home_systems_map

