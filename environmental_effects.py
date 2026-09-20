"""Read-only environmental combat modifiers shared by gameplay and presentation.

Queries use the deployed unit's current sector and inclusive body boundaries.
No modifier is persisted: turret base/reset state remains owned by the turret.
"""
from dataclasses import asdict, dataclass
from decimal import Decimal

from constants import HullSize
from celestial_descriptions import describe_body
from geometry import distance


@dataclass(frozen=True)
class EnvironmentalModifiers:
    cooldown_reduction: int = 0
    splash_damage_multiplier: float = 1.0
    fuel_multiplier: float = 1.0
    sensor_multiplier: float = 1.0
    speed_multiplier: float = 1.0
    beam_cover: float = 0.0
    kinetic_missile_cover: float = 0.0
    blocks_long_range_sensors: bool = False


def effects_for_body(body):
    """Return public numeric effects and hazards for an already-visible body."""
    return describe_body(body).environmental_effects()


def modifiers_for_unit(unit):
    """Compute strongest overlapping modifiers, excluding hidden/docked/dead units."""
    neutral = EnvironmentalModifiers()
    if getattr(unit, 'is_hidden_in_gas_giant', False) or getattr(unit, 'current_hit_points', 0) <= 0:
        return neutral
    galaxy = getattr(unit, 'in_galaxy', None) or getattr(getattr(unit, 'game', None), 'galaxy', None)
    if galaxy is None or getattr(unit, 'position', None) is None:
        return neutral
    system = galaxy.systems.get(getattr(unit, 'in_system', None))
    sector = system.hexes.get(getattr(unit, 'in_hex', None)) if system else None
    if sector is None or unit not in sector.units and unit not in getattr(sector, 'deployables', ()):
        return neutral
    values = asdict(neutral)
    wing = getattr(unit, 'hull_size', None) == HullSize.STRIKECRAFT_WING
    for body in sector.celestial_bodies:
        description = describe_body(body)
        if description.effect_radius is None or distance(unit.position, body.position) > description.effect_radius:
            continue
        effects = dict(description.effects)
        for key in ('cooldown_reduction', 'splash_damage_multiplier', 'beam_cover', 'kinetic_missile_cover'):
            values[key] = max(values[key], effects.get(key, values[key]))
        for key in ('fuel_multiplier', 'sensor_multiplier', 'speed_multiplier'):
            if key != 'speed_multiplier' or not wing:
                values[key] = min(values[key], effects.get(key, values[key]))
        values['blocks_long_range_sensors'] |= effects.get('blocks_long_range_sensors', False)
    from tactical_abilities import catalyst_effects
    enhanced = catalyst_effects(unit, galaxy)
    for key in ('cooldown_reduction', 'splash_damage_multiplier'):
        values[key] = max(values[key], enhanced.get(key, values[key]))
    for key in ('fuel_multiplier', 'sensor_multiplier'):
        values[key] = min(values[key], enhanced.get(key, values[key]))
    return EnvironmentalModifiers(**values)


def sublight_speed(unit):
    """Current movement speed: engine modifiers followed by terrain drag once."""
    engines = getattr(unit, 'engines_component', None)
    if engines is None or engines.is_destroyed:
        return 0.0
    return engines.effective_speed * modifiers_for_unit(unit).speed_multiplier


def long_range_sensor_hexes(unit):
    """Current long-range projection, including magnetic suppression."""
    from dismantling import offline
    if offline(unit):
        return 0
    sensors = getattr(unit, 'sensors_component', None)
    if sensors is None or sensors.is_destroyed or modifiers_for_unit(unit).blocks_long_range_sensors:
        return 0
    return sensors.effective_long_range_hexes


def splash_damage(amount, unit):
    """Scale positive, post-falloff splash once, truncating exact decimal multiplication."""
    if amount <= 0:
        return amount
    multiplier = modifiers_for_unit(unit).splash_damage_multiplier
    return int(Decimal(amount) * Decimal(str(multiplier)))


def sensor_radius(unit):
    """Actual short-range radius, shared by visibility, overlays, UI and agents."""
    from dismantling import offline
    if offline(unit):
        return 0.0
    sensors = getattr(unit, 'sensors_component', None)
    if sensors is None or sensors.is_destroyed:
        return 0.0
    base = getattr(sensors, 'effective_short_range_radius', None)
    if not isinstance(base, (int, float)):
        base = sensors.short_range_radius
    return base * modifiers_for_unit(unit).sensor_multiplier
