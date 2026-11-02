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

RECIPIENT_PRIORITIES = ('nearest', 'service_urgency')


def validate_delivery_preferences(priority, minimum_load_fraction):
    if priority not in RECIPIENT_PRIORITIES:
        raise ValueError('recipient_priority must be nearest or service_urgency.')
    try:
        finite = math.isfinite(minimum_load_fraction)
    except (TypeError, OverflowError):
        finite = False
    if (type(minimum_load_fraction) not in (int, float) or not finite
            or not 0 < minimum_load_fraction <= 1):
        raise ValueError('minimum_load_fraction must be finite, greater than zero and at most one.')


def service_fuel_horizon(unit):
    """Owner turns until active equipment/support stops; idle depots rank later."""
    if unit.is_disabled:
        return float('inf')
    upkeep = equipment_upkeep(unit)
    from wormhole_stabilization import state_view, equipment_ready, STABILIZER_UPKEEP
    if equipment_ready(unit) and state_view(unit)['phase'] in {'maintaining', 'waiting_for_antimatter'}:
        upkeep += STABILIZER_UPKEEP
    return unit.antimatter_component.current_amount / upkeep if upkeep > 0 else float('inf')


def storage_ready(unit):
    storage = getattr(unit, "antimatter_component", None)
    return bool(storage and not storage.is_destroyed)


def endpoint_ready(unit, galaxy):
    from dismantling import offline
    if (
        unit is None
        or offline(unit)
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
    recharge_owner_turns: int = 0
    readiness_fuel: float = 0.0


def estimate_approach(unit, galaxy, target, origin=None, *, approach_range=ANTIMATTER_TRANSFER_RANGE, known_only=False):
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
    from movement_costs import fuel_free_sublight

    system, coord, point = origin or (unit.in_system, unit.in_hex, unit.position)
    fuel, turns = 0.0, 0
    upkeep = equipment_upkeep(unit)
    engine, drive = unit.engines_component, unit.hyperdrive_component
    recharge = max(0, getattr(drive, 'recharge_time_remaining', 0)) if origin is None else 0
    speed = engine.effective_speed if engine and engine.is_operational else 0.0
    jump_range = (
        int(drive.jump_range * unit.xp_multiplier(XP_JUMP_RANGE_BONUS))
        if drive and drive.is_functional
        else 0
    )
    boundary = Circle(Position(0, 0), SECTOR_CIRCLE_RADIUS_LOGICAL)
    if known_only:
        from visibility import VisibilityService, known_inhibition_zones
        snapshot = VisibilityService.compute(galaxy, unit.owner, record_intel=False)

    def sector():
        return galaxy.systems[system].hexes[coord]

    def zones():
        return known_inhibition_zones(sector(), unit.owner, snapshot) if known_only else sector().get_all_inhibition_zones()

    def sublight(destination):
        nonlocal point, fuel, turns, recharge
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
                (0.0 if fuel_free_sublight(unit) else get_sublight_antimatter_cost_per_turn(unit.hull_size, speed)) + upkeep
            )
            turns += duration
            recharge = max(0, recharge - duration)
            point = end

    def jump(cost):
        nonlocal fuel, turns, recharge
        # Recharge blocks only the next jump and runs concurrently with sublight.
        # The jump's owner-turn update already ticks its new recharge once.
        duration = recharge + 1
        fuel += cost + duration * upkeep
        turns += duration
        recharge = max(0, drive.RECHARGE_DURATION - 1)

    def result():
        return JourneyEstimate(fuel, turns, system, coord, point, recharge,
                               fuel + recharge * upkeep)

    def escape():
        for zone in zones():
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
                for zone in zones():
                    if is_point_in_circle(landing, zone):
                        landing = get_closest_point_on_circle_edge(landing, zone)
                jump(get_hyperdrive_hex_jump_cost(unit.hull_size))
                point = landing
        sublight(destination)

    try:
        if (
            system == target.in_system
            and coord == target.in_hex
            and distance(point, target.position) <= approach_range
        ):
            return result()
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
                jump(get_hyperdrive_system_jump_cost(unit.hull_size))
                system, coord, point = (
                    next_system,
                    exit_wormhole.in_hex,
                    exit_wormhole.position,
                )
                escape()
        endpoint = position_at_distance_from_target(
            point, target.position, approach_range - 5
        )
        local(target.in_hex, endpoint)
        return result()
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
    return buffered_fuel(outward.readiness_fuel) + buffered_fuel(returning.readiness_fuel)


def harvest_source_ready(source, galaxy):
    from domain.celestials import Star, Nebula
    from constants import NebulaType

    if not (isinstance(source, Star) or
            isinstance(source, Nebula) and source.nebula_type == NebulaType.HYDROGEN):
        return False
    system = galaxy.systems.get(source.in_system)
    sector = system.hexes.get(source.in_hex) if system else None
    return bool(sector and source in sector.celestial_bodies)


def source_range(unit, harvesting=False):
    return unit.harvester_component.harvest_range if harvesting else ANTIMATTER_TRANSFER_RANGE


def at_source(unit, source, harvesting=False):
    return (unit.in_system == source.in_system and unit.in_hex == source.in_hex
            and distance(unit.position, source.position) <= source_range(unit, harvesting))


def continuous_source_blocker(unit, source, galaxy, *, harvesting=False):
    if not endpoint_ready(unit, galaxy) or unit.is_disabled:
        return "capability_unavailable"
    if harvesting:
        harvester = unit.harvester_component
        if not harvester or harvester.is_destroyed:
            return "capability_unavailable"
        return None if harvest_source_ready(source, galaxy) else "target_unavailable"
    if not unit.engines_component or not unit.engines_component.is_operational:
        return "capability_unavailable"
    return exchange_blocker(unit, source, galaxy)


def continuous_route_blocker(unit, source, destination, galaxy, *, harvesting=False):
    """Shared issuance rules; absence of an automatic recipient is legal."""
    blocker = continuous_source_blocker(unit, source, galaxy, harvesting=harvesting)
    if blocker:
        return blocker
    if estimate_approach(unit, galaxy, source, approach_range=source_range(unit, harvesting)) is None:
        return "path_unavailable"
    if destination is not None:
        blocker = exchange_blocker(unit, destination, galaxy)
        if blocker:
            return blocker
        if destination is source:
            return "invalid_target"
        budget = delivery_budget(unit, source, destination, galaxy,
                                 harvesting=harvesting, from_source=True)
        if budget is None:
            return "path_unavailable"
        if budget >= unit.antimatter_component.max_capacity:
            return "insufficient_capacity"
    return None


def delivery_budget(unit, source, destination, galaxy, *, harvesting=False, from_source=False):
    """Fuel needed before a productive delivery; never assumes future income."""
    from constants import ANTIMATTER_HARVESTER_RETURN_THRESHOLD

    origin = None
    if from_source and not at_source(unit, source, harvesting):
        arrival = estimate_approach(unit, galaxy, source,
                                    approach_range=source_range(unit, harvesting))
        if arrival is None:
            return None
        origin = (arrival.system, arrival.hex_coord, arrival.position)
    outward = estimate_approach(unit, galaxy, destination, origin)
    if outward is None:
        return None
    returning = estimate_approach(unit, galaxy, source,
        (outward.system, outward.hex_coord, outward.position),
        approach_range=source_range(unit, harvesting))
    if returning is None:
        return None
    reserve = (ANTIMATTER_HARVESTER_RETURN_THRESHOLD if harvesting
               else buffered_fuel(returning.readiness_fuel) + equipment_upkeep(unit))
    return buffered_fuel(outward.readiness_fuel) + reserve


def automatic_recipient(unit, source, galaxy, *, harvesting=False, excluded=(), available_fuel=None, priority='nearest'):
    """Affordable owned recipients, optionally ranked by remaining service fuel."""
    from geometry import hex_distance
    from pathfinding import find_intersystem_path

    def proximity(candidate):
        if unit.in_system == candidate.in_system:
            value = (distance(unit.position, candidate.position)
                     if unit.in_hex == candidate.in_hex else
                     hex_distance(unit.in_hex, candidate.in_hex) * 10000.0)
        else:
            path = find_intersystem_path(galaxy.system_graph, unit.in_system,
                                        candidate.in_system, unit.hull_size)
            value = (float('inf') if not path else
                     (len(path) - 1) * 1_000_000.0
                     + hex_distance(unit.in_hex, candidate.in_hex) * 10000.0)
        horizon = service_fuel_horizon(candidate) if priority == 'service_urgency' else 0
        return horizon, value, candidate.id

    candidates = [candidate for system in galaxy.systems.values()
                  for sector in system.hexes.values() for candidate in sector.units
                  if candidate is not source and candidate.id not in excluded
                  and candidate.owner is unit.owner
                  and exchange_blocker(unit, candidate, galaxy) is None
                  and candidate.antimatter_component.current_amount
                  < candidate.antimatter_component.max_capacity]
    for candidate in sorted(candidates, key=proximity):
        budget = delivery_budget(unit, source, candidate, galaxy, harvesting=harvesting)
        fuel = unit.antimatter_component.current_amount if available_fuel is None else available_fuel
        if budget is not None and fuel > budget:
            return candidate
    return None
