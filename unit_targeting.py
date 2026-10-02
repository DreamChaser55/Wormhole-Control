"""Pure target/approach policies shared by discovery, commands and execution."""
from geometry import distance


LEGACY_UNIT_ABILITIES = frozenset({"designate_target", "capture_unit", "drain_antimatter", "ion_bolt"})
HOSTILE_LEGACY_ABILITIES = LEGACY_UNIT_ABILITIES - {"ion_bolt"}

UTILITY_BODY_COMMANDS = frozenset({"mine", "continuous_mine", "colonize", "load_colonists", "enter_gas_giant", "infiltrate_planet"})
UTILITY_UNIT_COMMANDS = frozenset({"protect", "repair", "unload_resources", "trade", "dock",
                                   "dock_in_hangar", "dock_in_strikecraft_bay", "infiltrate_unit",
                                   "transfer_antimatter", "take_antimatter"})


def intelligence_distance(first, second):
    """Intelligence works from colony surfaces without requiring ships to land."""
    from domain.celestials import CelestialBody
    radii = sum(target.collision_radius for target in (first, second) if isinstance(target, CelestialBody))
    return max(0.0, distance(first.position, second.position) - radii)


def utility_approach_blocker(unit, target, galaxy, command_type):
    """Use the job's action range when checking a disclosed utility destination.

    Check hardware/topology/known terrain, never fuel or undisclosed inhibitors.
    Temporary recharge and fuel shortages can wait during execution.
    """
    from constants import DEFAULT_STANDOFF_DISTANCE, TRADE_ARRIVAL_RANGE, ANTIMATTER_TRANSFER_RANGE
    if command_type in {"mine", "continuous_mine"}:
        reach = getattr(getattr(unit, "mining_component", None), "mining_range", 0.0)
    elif command_type == "repair":
        reach = getattr(getattr(unit, "repair_component", None), "repair_range", 0.0)
    elif command_type == "unload_resources":
        refinery = getattr(target, "metal_refinery_component", None) or getattr(target, "crystal_refinery_component", None)
        reach = getattr(refinery, "unload_range", 300.0)
    elif command_type == "trade":
        reach = TRADE_ARRIVAL_RANGE
    elif command_type in {"dock", "dock_in_hangar", "dock_in_strikecraft_bay"}:
        from unit_orders.hangar import DOCKING_RANGE
        reach = DOCKING_RANGE
    elif command_type in {"infiltrate_unit", "infiltrate_planet"}:
        from unit_orders.intelligence import INTELLIGENCE_OPERATIONAL_RANGE
        reach = INTELLIGENCE_OPERATIONAL_RANGE
        if command_type == 'infiltrate_planet':
            reach += target.collision_radius
    elif command_type in {"transfer_antimatter", "take_antimatter"}:
        reach = ANTIMATTER_TRANSFER_RANGE
    elif command_type in {"colonize", "load_colonists", "enter_gas_giant"}:
        reach = getattr(target, "collision_radius", getattr(target, "radius", 0.0)) + DEFAULT_STANDOFF_DISTANCE
    else:
        reach = DEFAULT_STANDOFF_DISTANCE
    return approach_blocker(unit, target, galaxy, reach)


def operational_engines(unit):
    engines = getattr(unit, "engines_component", None)
    if engines is None:
        return False
    operational = getattr(engines, "is_operational", None)
    if isinstance(operational, bool):
        return operational
    if getattr(engines, "is_destroyed", False) is True:
        return False
    speed = getattr(engines, "effective_speed", None)
    if not isinstance(speed, (int, float)):
        speed = getattr(engines, "speed", None)
    return speed > 0 if isinstance(speed, (int, float)) else True


def approach_blocker(unit, target, galaxy, reach, *, check_path=True):
    """Check current route feasibility without allocating orders or drawing RNG."""
    same_sector = unit.in_system == target.in_system and unit.in_hex == target.in_hex
    if same_sector and distance(unit.position, target.position) <= reach:
        return None
    drive = getattr(unit, "hyperdrive_component", None)
    if not same_sector:
        from constants import HullSize
        if unit.hull_size == HullSize.STRIKECRAFT_WING:
            return "sector_unreachable"
        if drive is None or not drive.is_functional:
            return "hyperdrive_unavailable"
        from unit_components.enums import HyperdriveType
        if unit.in_system != target.in_system and drive.drive_type != HyperdriveType.ADVANCED:
            return "system_unreachable"
    elif not operational_engines(unit):
        return "engines_unavailable"
    if not check_path:
        return None
    from antimatter_logistics import estimate_approach
    return "path_unavailable" if estimate_approach(unit, galaxy, target, approach_range=reach, known_only=True) is None else None


def attack_range(unit, target, *, long_range_only=False, target_component=None):
    from unit_components.weapons import targeting_range
    from unit_components.enums import TurretVariant
    weapons = getattr(unit, "weapons_component", None)
    if weapons is None:
        return None
    eligible = getattr(weapons, "eligible_turrets_for", None)
    turrets = eligible(target, long_range_only=long_range_only) if callable(eligible) else None
    if not isinstance(turrets, (list, tuple)):
        turrets = [t for t in getattr(weapons, "turrets", ())
                   if not long_range_only or t.variant == TurretVariant.LONG_RANGE]
    ranges = [targeting_range(t.range, target_component) for t in turrets]
    # An immobile platform can fire its usable battery without trying to close
    # for a shorter turret. Mobile ships retain the all-turrets approach policy.
    return (min(ranges) if operational_engines(unit) else max(ranges)) if ranges else None


def attack_blocker(unit, target, galaxy, *, long_range_only=False, target_component=None):
    reach = attack_range(unit, target, long_range_only=long_range_only, target_component=target_component)
    if reach is None or reach <= 0:
        return "capability_unavailable"
    same_sector = unit.in_system == target.in_system and unit.in_hex == target.in_hex
    if same_sector and distance(unit.position, target.position) < reach:
        return None
    return approach_blocker(unit, target, galaxy, max(1.0, reach - 5.0))


def legacy_target_blocker(unit, kind, target, galaxy, *, approach=True, execution=False, check_path=True):
    """Legacy Ion Bolt permits allies; the other three require hostile targets.

    Enemy fuel is private, so its presence/amount is checked only at activation.
    Discovery and preflight rely on disclosed relationships and public equipment.
    """
    if kind not in LEGACY_UNIT_ABILITIES:
        return None
    if target is None or target.current_hit_points <= 0:
        return "target_unavailable"
    from domain.players import are_allies
    if kind in HOSTILE_LEGACY_ABILITIES and are_allies(unit.owner, target.owner):
        return "invalid_relation"
    if kind == "capture_unit":
        from unit_components.defenses import Defenses
        defenses = target.get_component(Defenses)
        if ((target.engines_component and not target.engines_component.is_destroyed and not target.is_disabled)
                or (target.weapons_component and not target.weapons_component.is_destroyed)
                or (defenses and not defenses.is_destroyed)):
            return "target_not_disabled"
        marines = getattr(unit, "marines_component", None)
        if not marines or marines.is_destroyed or marines.marines_count <= 0:
            return "capability_unavailable"
    if execution and kind == "drain_antimatter":
        storage = target.antimatter_component
        if not storage or storage.is_destroyed or storage.current_amount <= 0:
            return "target_unavailable"
    from unit_components.enums import AbilityType
    instance = unit.ability_component.abilities.get(AbilityType(kind))
    if instance is None:
        return "ability_unavailable"
    reach = instance.definition.range
    same_sector = unit.in_system == target.in_system and unit.in_hex == target.in_hex
    if same_sector and distance(unit.position, target.position) <= reach:
        return None
    if not approach:
        return "target_out_of_range"
    return approach_blocker(unit, target, galaxy, reach, check_path=check_path)
