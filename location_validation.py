"""Complete, explicit galaxy locations shared by commands, orders and saves."""
from collections.abc import Mapping
import math

from domain.coordinates import HexCoord
from geometry import Position


def location(system_name, hex_coord, position, galaxy=None):
    """Validate and copy a location; never infer any part from an actor or view."""
    if not isinstance(system_name, str) or not system_name.strip():
        raise ValueError("Location requires a nonblank system name")
    if (not isinstance(hex_coord, (tuple, list)) or len(hex_coord) != 2
            or any(type(v) is not int for v in hex_coord)):
        raise ValueError("Location requires two integer hex coordinates")
    pair = (position.x, position.y) if isinstance(position, Position) else position
    if not isinstance(pair, (tuple, list)) or len(pair) != 2:
        raise ValueError("Location requires two finite position coordinates")
    try:
        valid = all(type(v) in (int, float) and math.isfinite(v) for v in pair)
    except (OverflowError, ValueError):
        valid = False
    if not valid:
        raise ValueError("Location requires two finite position coordinates")
    coord = HexCoord(*hex_coord)
    if galaxy is not None:
        system = galaxy.systems.get(system_name)
        if system is None or coord not in system.hexes:
            raise ValueError("Location system or sector does not exist")
    return system_name, coord, Position(*pair)


def ability_target_kind(value):
    from unit_components.abilities import ABILITY_DEFINITIONS
    from unit_components.enums import AbilityType
    try:
        definition = ABILITY_DEFINITIONS[AbilityType(value)]
    except (ValueError, KeyError):
        raise ValueError("Unknown ability") from None
    return definition.target_kind


def order_locations(kind, parameters, galaxy=None):
    """Return copied parameters with validated fixed destinations, including routes."""
    if not isinstance(parameters, Mapping):
        raise ValueError("Order parameters must be an object")
    result = dict(parameters)

    def fixed(prefix):
        names = (prefix + "system_name", prefix + "hex_coord", prefix + "position")
        result.update(zip(names, location(*(result.get(n) for n in names), galaxy)))

    if kind in {"CONSTRUCT", "USE_ABILITY"}:
        positional = kind == "CONSTRUCT" or ability_target_kind(result.get("ability_type")) in {"position", "celestial_position"}
        if positional:
            fixed("target_")
    elif kind in {"MOVE", "REACH_WAYPOINT"}:
        fixed("destination_")
    elif kind == "DEFEND":
        if result.get("target_id") is None or any(result.get("destination_" + n) is not None for n in ("system_name", "hex_coord", "position")):
            fixed("destination_")
    elif kind == "PATROL":
        if "waypoints" in result:
            waypoints = result["waypoints"]
            if not isinstance(waypoints, (list, tuple)) or not waypoints:
                raise ValueError("Patrol requires complete waypoints")
            copied = []
            for waypoint in waypoints:
                if not isinstance(waypoint, Mapping):
                    raise ValueError("Invalid waypoint")
                site = location(*(waypoint.get(n) for n in ("system_name", "hex_coord", "position")), galaxy)
                copied.append(dict(zip(("system_name", "hex_coord", "position"), site)))
            result["waypoints"] = copied
        else:
            fixed("destination_")
    return result


def validate_order(order, galaxy):
    try:
        order.parameters = order_locations(order.order_type.name, order.parameters, galaxy)
    except ValueError:
        order.fail("invalid_parameters")
        return False
    return True


def format_location(system_name, hex_coord, position):
    return f"{system_name} ({hex_coord[0]}, {hex_coord[1]}) at ({position.x:g}, {position.y:g})"
