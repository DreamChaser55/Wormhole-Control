"""Bounded, read-only placement search for craft leaving a carrier."""

import math
import random

from constants import HullSize, SECTOR_CIRCLE_RADIUS_LOGICAL
from geometry import GEOMETRY_TOLERANCE, NAVIGATION_CLEARANCE, Position, distance


def find_deployment_position(carrier, craft, galaxy):
    """Return a safe nearby position, or None without changing containment.

    Candidates use the craft's navigation restrictions in the carrier's actual
    sector. Randomness is consumed only during deployment, never discovery or
    preflight. Exhausting the bounded search is an ordinary deployment failure.
    """
    from domain.celestials import (
        is_position_blocked_by_celestial_field,
        is_position_in_magnetic_storm,
    )
    from unit_orders.movement import get_hex_collision_obstacles

    system = galaxy.systems.get(carrier.in_system)
    if system is None or carrier.in_hex not in system.hexes:
        return None
    if not all(math.isfinite(v) for v in carrier.position.to_tuple()):
        return None
    if is_position_blocked_by_celestial_field(
        galaxy, carrier.in_system, carrier.in_hex, carrier.position, craft
    ):
        return None
    if craft.hull_size == HullSize.STRIKECRAFT_WING and is_position_in_magnetic_storm(
        galaxy, carrier.in_system, carrier.in_hex, carrier.position
    ):
        return None
    obstacles = get_hex_collision_obstacles(
        galaxy, carrier.in_system, carrier.in_hex, unit=craft
    )
    for _ in range(100):
        angle = random.uniform(0, 2 * math.pi)
        offset = random.uniform(20.0, 50.0)
        candidate = carrier.position + Position(math.cos(angle), math.sin(angle)) * offset
        if candidate.magnitude() > SECTOR_CIRCLE_RADIUS_LOGICAL:
            continue
        if any(distance(candidate, obstacle.center)
               < obstacle.radius + NAVIGATION_CLEARANCE - GEOMETRY_TOLERANCE
               for obstacle in obstacles):
            continue
        return candidate
    return None
