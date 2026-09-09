"""Read-only environmental combat modifiers shared by gameplay and presentation.

Queries use the deployed unit's current sector and inclusive body boundaries.
No modifier is persisted: turret base/reset state remains owned by the turret.
"""
from dataclasses import dataclass
from decimal import Decimal

from constants import (ICE_FIELD_COOLDOWN_REDUCTION,
                       NITROGEN_NEBULA_COOLDOWN_REDUCTION,
                       OXYGEN_NEBULA_SPLASH_DAMAGE_MOD, NebulaType)
from geometry import distance


@dataclass(frozen=True)
class EnvironmentalModifiers:
    cooldown_reduction: int = 0
    splash_damage_multiplier: float = 1.0


def effects_for_body(body):
    """Return public numeric effects for an already-visible celestial body."""
    from domain.celestials import IceField, DebrisField, Nebula
    if isinstance(body, IceField):
        return {'cooldown_reduction': ICE_FIELD_COOLDOWN_REDUCTION,
                'beam_cover': body.beam_defense_bonus}
    if isinstance(body, DebrisField):
        return {'kinetic_missile_cover': body.defense_bonus}
    if isinstance(body, Nebula):
        if body.nebula_type == NebulaType.NITROGEN:
            return {'cooldown_reduction': NITROGEN_NEBULA_COOLDOWN_REDUCTION}
        if body.nebula_type == NebulaType.OXYGEN:
            return {'splash_damage_multiplier': OXYGEN_NEBULA_SPLASH_DAMAGE_MOD}
    return {}


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
    if sector is None or unit not in sector.units:
        return neutral
    cooling, splash = 0, 1.0
    for body in sector.celestial_bodies:
        effects = effects_for_body(body)
        radius = getattr(body, 'effect_radius', getattr(body, 'radius', 0))
        if effects and distance(unit.position, body.position) <= radius:
            cooling = max(cooling, effects.get('cooldown_reduction', 0))
            splash = max(splash, effects.get('splash_damage_multiplier', 1.0))
    return EnvironmentalModifiers(cooling, splash)


def splash_damage(amount, unit):
    """Scale positive, post-falloff splash once, truncating exact decimal multiplication."""
    if amount <= 0:
        return amount
    multiplier = modifiers_for_unit(unit).splash_damage_multiplier
    return int(Decimal(amount) * Decimal(str(multiplier)))
