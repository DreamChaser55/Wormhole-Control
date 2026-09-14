"""Immutable public terrain descriptions, independent of UI and visibility."""
from dataclasses import asdict, dataclass
from typing import Any

import constants as balance
from constants import NebulaType, PlanetType, StarType, StormType
from geometry import distance


@dataclass(frozen=True)
class EnvironmentalHazard:
    kind: str
    amount: float
    target: str
    scope: str
    radius: float | None = None
    amount_basis: str = 'flat'
    speed_threshold: float | None = None
    affects_strikecraft: bool = True
    affects_deployables: bool = False
    timing: str = 'after_movement_each_owner_turn'
    requires_sublight_movement: bool = False
    speed_basis: str | None = None

    def contains(self, position, body) -> bool:
        return self.scope == 'sector' or (self.radius is not None and distance(position, body.position) <= self.radius)


@dataclass(frozen=True)
class BodyDescription:
    collision_radius: float
    inhibition_radius: float
    effect_radius: float | None
    effects: tuple[tuple[str, float | bool], ...]
    hazards: tuple[EnvironmentalHazard, ...]
    rules: tuple[str, ...]

    def environmental_effects(self) -> dict[str, Any]:
        result: dict[str, Any] = dict(self.effects)
        if self.hazards:
            result['hazards'] = [asdict(hazard) for hazard in self.hazards]
        return result


def catalyst_profile(body) -> tuple[str, dict[str, float], str]:
    """Only the enhancement applicable to this nebula, from gameplay balance."""
    import tactical_balance as tactical
    kind = getattr(body, 'nebula_type', None)
    if kind == NebulaType.HYDROGEN:
        value = tactical.CATALYST_HYDROGEN_FUEL
        return 'friendly', {'hydrogen_fuel_multiplier': value}, f'Allies: sublight propulsion AM consumption {value:.0%} of normal.'
    if kind == NebulaType.NITROGEN:
        value = tactical.CATALYST_NITROGEN_COOLING
        return 'friendly', {'nitrogen_cooldown_reduction': value}, f'Allies: turret cooldown reset reduced by {value:g} turns, using the normal cooling floor.'
    if kind == NebulaType.OXYGEN:
        value = tactical.CATALYST_OXYGEN_SPLASH
        return 'enemy', {'oxygen_splash_multiplier': value}, f'Enemies: Cluster Warhead splash damage taken {value:g}x.'
    if kind == NebulaType.DUST:
        value = tactical.CATALYST_DUST_SENSORS
        return 'enemy', {'dust_sensor_multiplier': value}, f'Enemies: short-range sensor radius {value:.0%} of normal.'
    return 'friendly', {}, ''


def describe_body(body) -> BodyDescription:
    """Describe an already-exposed body without consulting hidden state."""
    from domain.celestials import AsteroidField, DebrisField, IceField, Nebula, Planet, Star, Storm, Wormhole
    collision = float(getattr(body, 'collision_radius', 0))
    inhibition = float(getattr(body, 'inhibition_field_radius', 0))
    radius = float(body.effect_radius) if not getattr(body, 'is_solid', True) else None
    effects: dict[str, float | bool] = {}
    hazards: list[EnvironmentalHazard] = []
    rules: list[str] = []
    if collision:
        rules.append(f'Collision radius: {collision:g} units (solid surface).')
    if inhibition:
        rules.append(f'Hyperspace inhibition radius: {inhibition:g} units; blocks ordinary jump entry and exit.')
    if radius is not None:
        rules.append(f'Effect radius: {radius:g} units; includes the boundary.')
    if isinstance(body, (AsteroidField, DebrisField, IceField)):
        effects.update(speed_multiplier=body.speed_multiplier, strikecraft_ignores_drag=True)
        rules.extend((
            f'Density: {body.density.name.title()}; largest permitted hull: {body.max_hull_size.name.title()}. Larger hulls must route around; cannot jump or deploy inside.',
            f'Sublight speed: {body.speed_multiplier:.0%} of engine speed after other modifiers. Overlapping drag uses the strongest penalty.',
            'Wings can enter every field density and ignore drag; they retain cover and cooling benefits.',
        ))
    if isinstance(body, (AsteroidField, Nebula)):
        effects['long_range_concealment'] = True
        rules.append('Conceals units inside from enemy long-range detection; short-range sensors can still reveal them.')
    if isinstance(body, IceField):
        effects.update(cooldown_reduction=body.cooldown_reduction, beam_cover=body.beam_defense_bonus)
    elif isinstance(body, DebrisField):
        effects.update(kinetic_missile_cover=body.defense_bonus, strikecraft_ignores_abrasion=True)
        hazards.append(EnvironmentalHazard('debris', body.hazard_damage, 'hull', 'radius', radius,
            speed_threshold=body.hazard_speed_threshold, affects_strikecraft=False,
            requires_sublight_movement=True, speed_basis='post_drag_speed_used_for_movement'))
    elif isinstance(body, Nebula):
        if body.nebula_type == NebulaType.HYDROGEN:
            effects.update(fuel_multiplier=balance.HYDROGEN_NEBULA_AM_BURN_MOD, harvest_multiplier=body.harvest_multiplier)
            rules.extend((
                f'A functional Antimatter Harvester collects at {body.harvest_multiplier:g}x its base rate within its harvesting range of the cloud center.',
                f'Sublight propulsion AM consumption: {balance.HYDROGEN_NEBULA_AM_BURN_MOD:.0%} of normal; no savings for jumps or other equipment. Overlapping clouds do not stack.',
            ))
        elif body.nebula_type == NebulaType.DUST:
            effects['sensor_multiplier'] = balance.DUST_NEBULA_SENSOR_MOD
            rules.append(f'Short-range sensor radius: {balance.DUST_NEBULA_SENSOR_MOD:.0%} of normal for observers inside. Overlapping clouds do not stack.')
        elif body.nebula_type == NebulaType.NITROGEN:
            effects['cooldown_reduction'] = balance.NITROGEN_NEBULA_COOLDOWN_REDUCTION
        elif body.nebula_type == NebulaType.OXYGEN:
            effects['splash_damage_multiplier'] = balance.OXYGEN_NEBULA_SPLASH_DAMAGE_MOD
            rules.extend((
                f'Cluster Warhead splash damage taken: {balance.OXYGEN_NEBULA_SPLASH_DAMAGE_MOD:g}x. Ordinary missiles, mines, hazards and component spillover are unaffected.',
                'Apply once after distance falloff and before mitigation; truncate to an integer. Overlapping clouds do not stack.',
            ))
    elif isinstance(body, Storm):
        if body.storm_type == StormType.PLASMA:
            hazards.append(EnvironmentalHazard('plasma', balance.STORM_PLASMA_DAMAGE_PER_TURN,
                'hull', 'radius', radius, affects_deployables=True))
        elif body.storm_type == StormType.MAGNETIC:
            effects.update(blocks_long_range_sensors=True, strikecraft_entry_blocked=True, strikecraft_launch_blocked=True)
            rules.extend(('Disables the affected ship\'s long-range sensor projection; does not conceal it from enemy radar. Short-range sensors still work.',
                          'Wings cannot enter; carriers cannot launch wings from inside.'))
            hazards.append(EnvironmentalHazard('magnetic', balance.STORM_MAGNETIC_AM_DRAIN_PER_TURN,
                'antimatter', 'radius', radius))
        elif body.storm_type == StormType.RADIATION:
            hazards.append(EnvironmentalHazard('radiation', balance.STORM_RADIATION_COMPONENT_DAMAGE_PER_TURN,
                'random_non_destroyed_component', 'radius', radius))
    elif isinstance(body, Star):
        effects['harvest_multiplier'] = body.harvest_multiplier
        rules.append(f'A functional Antimatter Harvester collects at {body.harvest_multiplier:g}x its base rate within its harvesting range of the star center.')
        if body.star_type == StarType.BLACK_HOLE:
            hazards.append(EnvironmentalHazard('black_hole', balance.BLACK_HOLE_EVENT_HORIZON_DAMAGE,
                'hull', 'radius', balance.BLACK_HOLE_EVENT_HORIZON_RADIUS, affects_deployables=True))
        elif body.star_type == StarType.PULSAR:
            hazards.append(EnvironmentalHazard('pulsar', balance.PULSAR_ANTIMATTER_DRAIN_PERCENT,
                'antimatter', 'sector', amount_basis='fraction_of_current_antimatter'))
    elif isinstance(body, Planet) and body.planet_type == PlanetType.GAS_GIANT:
        rules.extend(('Atmospheric hiding: Tiny through Huge ships with operational Engines may enter. Wings and stationary stations cannot.',
                      'Submerged ships are hidden from enemy sensors and cannot interact with outside space. Only a Leave at the front of the queue can execute; upkeep and existing ability timers continue.'))
    elif isinstance(body, Wormhole):
        rules.append(f'Advanced Hyperdrive traversal; maximum hull: {body.diameter.name.title()}. The traversal order handles the wormhole approach.')
    for key, label in (('beam_cover', 'beam'), ('kinetic_missile_cover', 'kinetic/missile')):
        if key in effects:
            rules.append(f'Cover reduces incoming {label} damage by {effects[key]:.0%} before equipment defenses. Strongest overlapping cover applies; it does not add.')
    if 'cooldown_reduction' in effects:
        rules.extend((
            f'Turret cooling: -{effects["cooldown_reduction"]:g} turn from cooldown reset when firing, after variant scaling.',
            'Minimum reset is 1 for positive cooldowns; zero stays zero. Running and ability cooldowns are unaffected. Coolant sources do not stack; all hulls and turret types benefit.',
        ))
    for hazard in hazards:
        area = 'anywhere in this star\'s sector' if hazard.scope == 'sector' else f'within {hazard.radius:g} units (boundary included)'
        if hazard.kind == 'debris':
            rules.append(f'Abrasion: {hazard.amount:g} base hull damage per owner turn if ending {area} after positive sublight movement at post-drag speed > {hazard.speed_threshold:g}. Arrivals count; wings, stationary ships, jumps and tractor-only movement are exempt. Crossing without ending inside is safe.')
        elif hazard.kind == 'magnetic':
            rules.append(f'Drains up to {hazard.amount:g} AM from functioning storage {area}, after movement each owner turn; limited to available fuel.')
        elif hazard.kind == 'pulsar':
            rules.append(f'Drains {hazard.amount:.0%} of current AM from functioning storage {area}, after movement each owner turn.')
        elif hazard.kind == 'radiation':
            rules.append(f'Radiation: {hazard.amount:g} damage to one random non-destroyed component {area}, after movement each owner turn; excess component damage is discarded.')
        else:
            rules.append(f'{hazard.kind.replace("_", " ").title()}: {hazard.amount:g} base hull damage to ships and deployables {area}, after movement each owner turn. Bypasses equipment defenses; active hull damage reduction still applies.')
    if effects or hazards:
        rules.append('Hidden and docked units receive no external environmental effects.')
    if hazards:
        rules.append('Each overlapping hazard source applies separately.')
    return BodyDescription(collision, inhibition, radius, tuple(effects.items()), tuple(hazards), tuple(rules))
