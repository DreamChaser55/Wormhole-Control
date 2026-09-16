"""Shared fuel exchange rules and read-only transport journey estimates."""

from dataclasses import dataclass
import math

from constants import (
    ANTIMATTER_TRANSFER_RANGE,
    ANTIMATTER_TRANSFER_RATE,
    XP_JUMP_RANGE_BONUS,
)
from domain.players import are_allies
from geometry import (
    Position,
    Circle,
    distance,
    position_at_distance_from_target,
    compute_avoidance_waypoints,
    NoSafePathError,
    is_point_in_circle,
    get_closest_point_on_circle_edge,
    segment_intersects_circle,
)


def storage_ready(unit):
    storage = getattr(unit, "antimatter_component", None)
    return bool(storage and not storage.is_destroyed)


def endpoint_ready(unit, galaxy):
    if (
        unit is None
        or not storage_ready(unit)
        or unit.current_hit_points <= 0
        or unit.is_hidden_in_gas_giant
    ):
        return False
    system = galaxy.systems.get(unit.in_system)
    sector = system.hexes.get(unit.in_hex) if system else None
    return bool(sector and unit in sector.units)


def exchange_blocker(actor, target, galaxy):
    if not endpoint_ready(actor, galaxy) or actor.is_disabled:
        return "capability_unavailable"
    if (
        actor is target
        or not endpoint_ready(target, galaxy)
        or not are_allies(actor.owner, target.owner)
    ):
        return "target_unavailable"
    return None


def in_transfer_range(actor, target):
    return (
        actor.in_system == target.in_system
        and actor.in_hex == target.in_hex
        and distance(actor.position, target.position) <= ANTIMATTER_TRANSFER_RANGE
    )


def exchange(source, receiver, reserve=0.0):
    """Debit before credit, with one conserved, capacity-limited transfer."""
    if source is receiver or not storage_ready(source) or not storage_ready(receiver):
        return 0.0
    donor, tank = source.antimatter_component, receiver.antimatter_component
    amount = min(
        ANTIMATTER_TRANSFER_RATE,
        max(0.0, donor.current_amount - reserve),
        max(0.0, tank.max_capacity - tank.current_amount),
    )
    if amount <= 0 or not donor.consume(amount):
        return 0.0
    added = tank.add(amount)
    if added < amount:
        donor.add(amount - added)
    return added


def equipment_upkeep(unit):
    from environmental_resistance import upkeep
    result = upkeep(unit)
    for name in ("cloaking_component", "inhibitor_component"):
        component = getattr(unit, name, None)
        if component and not component.is_destroyed and component.is_active:
            result += component.get_antimatter_cost_per_turn()
    from tactical_abilities import get_instance

    tether = get_instance(unit, "tractor_tether")
    if tether and tether.is_active:
        result += 5
    return result


def buffered_fuel(cost):
    return math.ceil(cost * 1.25) + 10 if cost > 0 else 0.0


@dataclass(frozen=True)
class JourneyEstimate:
    fuel: float
    turns: int
    system: str
    hex_coord: tuple
    position: Position


def estimate_approach(unit, galaxy, target, origin=None):
    """Estimate a deterministic feasible approach without orders, IDs or mutations.

    Uses navigation's topology, jump waypoints, collision avoidance and fuel costs.
    Terrain drag is conservatively charged for an entire intersecting leg. Future
    harvesting, propulsion discounts and multiplication never finance a route.
    """
    from unit_orders.movement import get_hex_collision_obstacles
    from pathfinding import find_intersystem_path, find_hex_jump_path
    from custom_unit_templates import (
        get_sublight_antimatter_cost_per_turn,
        get_hyperdrive_hex_jump_cost,
        get_hyperdrive_system_jump_cost,
    )
    from unit_components.enums import HyperdriveType
    from celestial_descriptions import describe_body
    from constants import HullSize, SECTOR_CIRCLE_RADIUS_LOGICAL

    system, coord, point = origin or (unit.in_system, unit.in_hex, unit.position)
    fuel, turns = 0.0, 0
    upkeep = equipment_upkeep(unit)
    engine, drive = unit.engines_component, unit.hyperdrive_component
    speed = engine.effective_speed if engine and engine.is_operational else 0.0
    jump_range = (
        int(drive.jump_range * unit.xp_multiplier(XP_JUMP_RANGE_BONUS))
        if drive and drive.is_functional
        else 0
    )
    boundary = Circle(Position(0, 0), SECTOR_CIRCLE_RADIUS_LOGICAL)

    def sector():
        return galaxy.systems[system].hexes[coord]

    def sublight(destination):
        nonlocal point, fuel, turns
        if distance(point, destination) < 0.01:
            return
        if speed <= 0:
            raise NoSafePathError("No operational engines")
        waypoints = compute_avoidance_waypoints(
            point,
            destination,
            get_hex_collision_obstacles(galaxy, system, coord, unit),
            boundary=boundary,
        )
        for end in [*waypoints, destination]:
            drag = 1.0
            if unit.hull_size != HullSize.STRIKECRAFT_WING:
                for body in sector().celestial_bodies:
                    description = describe_body(body)
                    if description.effect_radius and (
                        is_point_in_circle(
                            point, Circle(body.position, description.effect_radius)
                        )
                        or segment_intersects_circle(
                            point, end, Circle(body.position, description.effect_radius)
                        )
                    ):
                        drag = min(
                            drag, dict(description.effects).get("speed_multiplier", 1.0)
                        )
            duration = math.ceil(distance(point, end) / (speed * drag))
            fuel += duration * (
                get_sublight_antimatter_cost_per_turn(unit.hull_size, speed) + upkeep
            )
            turns += duration
            point = end

    def escape():
        for zone in sector().get_all_inhibition_zones():
            if is_point_in_circle(point, zone):
                edge = get_closest_point_on_circle_edge(point, zone)
                sublight(edge)

    def local(destination_hex, destination):
        nonlocal coord, point, fuel, turns
        if coord != destination_hex:
            if jump_range <= 0:
                raise NoSafePathError("No operational hyperdrive")
            inhibitor = unit.inhibitor_component
            if inhibitor and not inhibitor.is_destroyed and inhibitor.is_active:
                # A moving ship cannot escape its own inhibition field.
                raise NoSafePathError("Active onboard inhibitor")
            escape()
            for waypoint in find_hex_jump_path(coord, destination_hex, jump_range):
                coord = waypoint
                landing = destination if waypoint == destination_hex else Position(0, 0)
                for zone in sector().get_all_inhibition_zones():
                    if is_point_in_circle(landing, zone):
                        landing = get_closest_point_on_circle_edge(landing, zone)
                duration = max(1, drive.RECHARGE_DURATION + 1)
                fuel += get_hyperdrive_hex_jump_cost(unit.hull_size) + duration * upkeep
                turns += duration
                point = landing
        sublight(destination)

    try:
        if (
            system == target.in_system
            and coord == target.in_hex
            and distance(point, target.position) <= ANTIMATTER_TRANSFER_RANGE
        ):
            return JourneyEstimate(0.0, 0, system, coord, point)
        if system != target.in_system:
            if jump_range <= 0 or drive.drive_type != HyperdriveType.ADVANCED:
                return None
            route = find_intersystem_path(
                galaxy.system_graph, system, target.in_system, unit.hull_size
            )
            if not route:
                return None
            for next_system in route[1:]:
                from unit_orders.base import Order

                wormhole = Order.find_wormhole_to_system(
                    None, system, next_system, galaxy, unit.hull_size
                )
                if (
                    wormhole is None
                    or wormhole.exit_wormhole_id not in galaxy.wormholes
                ):
                    return None
                local(wormhole.in_hex, wormhole.position)
                exit_wormhole = galaxy.wormholes[wormhole.exit_wormhole_id]
                duration = max(1, drive.RECHARGE_DURATION + 1)
                fuel += (
                    get_hyperdrive_system_jump_cost(unit.hull_size) + duration * upkeep
                )
                turns += duration
                system, coord, point = (
                    next_system,
                    exit_wormhole.in_hex,
                    exit_wormhole.position,
                )
                escape()
        endpoint = position_at_distance_from_target(
            point, target.position, ANTIMATTER_TRANSFER_RANGE - 5
        )
        local(target.in_hex, endpoint)
        return JourneyEstimate(fuel, turns, system, coord, point)
    except (NoSafePathError, KeyError, ValueError, ZeroDivisionError):
        return None


def route_budget(unit, source, destination, galaxy):
    origin = (
        (unit.in_system, unit.in_hex, unit.position)
        if in_transfer_range(unit, source)
        else (source.in_system, source.in_hex, source.position)
    )
    outward = estimate_approach(unit, galaxy, destination, origin)
    if outward is None:
        return None
    returning = estimate_approach(
        unit, galaxy, source, (outward.system, outward.hex_coord, outward.position)
    )
    if returning is None:
        return None
    return buffered_fuel(outward.fuel) + buffered_fuel(returning.fuel)
