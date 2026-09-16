"""Compact human terrain summaries; complete rules remain in the shared descriptor."""
from dataclasses import dataclass
from typing import Literal

from celestial_descriptions import BodyDescription, EnvironmentalHazard
from constants import PlanetType
from domain.celestials import CelestialBody, Planet, Wormhole


Tone = Literal['neutral', 'benefit', 'restriction', 'hazard']


@dataclass(frozen=True)
class SummaryRow:
    text: str
    tone: Tone = 'neutral'

    def panel_row(self) -> dict:
        return {'type': 'label', 'text': self.text, 'height': 20,
                'object_id': f'#sidebar_effect_{self.tone}_label'}


def rules_section_key(game, body: CelestialBody) -> str:
    return f'celestial_rules:{game.campaign_id}:{body.id}'


def _hazard_summary(hazard: EnvironmentalHazard, effect_radius: float | None) -> SummaryRow:
    if hazard.kind == 'debris':
        text = (f'Abrasion: {hazard.amount:g} base hull damage / owner turn; end inside '
                f'after sublight movement at post-drag speed > {hazard.speed_threshold:g}.')
    elif hazard.kind == 'magnetic':
        text = f'AM drain: up to {hazard.amount:g} / owner turn'
    elif hazard.amount_basis == 'fraction_of_current_antimatter':
        text = f'AM drain: {hazard.amount:.0%} of current fuel / owner turn'
    elif hazard.target == 'random_non_destroyed_component':
        text = f'Radiation: {hazard.amount:g} damage to one random surviving component / owner turn'
    else:
        targets = 'ships & deployables' if hazard.affects_deployables else 'ships'
        text = f'{hazard.amount:g} base hull damage / owner turn ({targets})'
    if hazard.scope == 'sector':
        text += '; whole sector'
    elif hazard.radius != effect_radius:
        text += f'; radius {hazard.radius:g}'
    return SummaryRow(text, 'hazard')


def body_summary(body: CelestialBody, description: BodyDescription) -> list[SummaryRow]:
    rows = []
    for label, radius in (('Collision radius', description.collision_radius),
                          ('Jump inhibition', description.inhibition_radius),
                          ('Effect radius', description.effect_radius)):
        if radius is not None and radius > 0:
            rows.append(SummaryRow(f'{label}: {radius:g}'))
    effects = dict(description.effects)
    if 'speed_multiplier' in effects:
        rows.extend((
            SummaryRow(f'Density: {body.density.name.title()}'),
            SummaryRow(f'Max hull: {body.max_hull_size.name.title()}', 'restriction'),
            SummaryRow(f'Sublight speed: {effects["speed_multiplier"]:.0%}', 'restriction'),
        ))
    if effects.get('strikecraft_ignores_drag'):
        exemption = 'drag or abrasion' if effects.get('strikecraft_ignores_abrasion') else 'drag'
        rows.append(SummaryRow(f'Wings: any density; no {exemption}', 'benefit'))
    if effects.get('long_range_concealment'):
        rows.append(SummaryRow('Hidden from long-range sensors; short-range detection still works', 'benefit'))
    if 'harvest_multiplier' in effects:
        rows.append(SummaryRow(f'AM harvesting: {effects["harvest_multiplier"]:g}× base rate (Harvester required)'))
    if 'fuel_multiplier' in effects:
        rows.append(SummaryRow(f'Sublight propulsion AM: {effects["fuel_multiplier"]:.0%}', 'benefit'))
    if 'sensor_multiplier' in effects:
        rows.append(SummaryRow(f'Short-range sensor radius: {effects["sensor_multiplier"]:.0%}', 'restriction'))
    for key, label in (('beam_cover', 'Beam'), ('kinetic_missile_cover', 'Kinetic/missile')):
        if key in effects:
            rows.append(SummaryRow(f'{label} damage taken: −{effects[key]:.0%}', 'benefit'))
    if 'cooldown_reduction' in effects:
        reduction = effects['cooldown_reduction']
        turns = 'turn' if reduction == 1 else 'turns'
        rows.append(SummaryRow(f'Turret cooldown reset: −{reduction:g} {turns} when firing', 'benefit'))
    if 'splash_damage_multiplier' in effects:
        rows.append(SummaryRow(f'Cluster Warhead splash taken: {effects["splash_damage_multiplier"]:g}×', 'hazard'))
    if effects.get('blocks_long_range_sensors'):
        rows.extend((
            SummaryRow('Long-range sensors: disabled', 'restriction'),
            SummaryRow('Short-range sensors work; no radar concealment'),
        ))
    blocked = []
    if effects.get('strikecraft_entry_blocked'):
        blocked.append('entry')
    if effects.get('strikecraft_launch_blocked'):
        blocked.append('launch')
    if blocked:
        rows.append(SummaryRow(f'Wings: {" and ".join(blocked)} blocked', 'restriction'))
    rows.extend(_hazard_summary(hazard, description.effect_radius) for hazard in description.hazards)
    if any(h.timing == 'after_movement_each_owner_turn' for h in description.hazards):
        rows.append(SummaryRow('Hazards apply after movement.'))
    if isinstance(body, Planet) and body.planet_type == PlanetType.GAS_GIANT:
        rows.extend((
            SummaryRow('Atmospheric hiding: hidden from enemy sensors', 'benefit'),
            SummaryRow('Entry: Tiny–Huge ships with working Engines; no wings or stations', 'restriction'),
            SummaryRow('Submerged: no outside interaction; Leave must be first in queue', 'restriction'),
        ))
    if isinstance(body, Wormhole):
        rows.append(SummaryRow(f'Traversal: Advanced Hyperdrive; max hull {body.diameter.name.title()}', 'restriction'))
    return rows


def catalyst_summary(patch: dict, owner_name: str) -> list[SummaryRow]:
    """Recipients are relative to the patch owner, never implicitly the viewer."""
    rows = [SummaryRow(f'Catalyst: {owner_name}'),
            SummaryRow(f'Patch radius: {patch["radius"]:g}; expires owner round {patch["expires_on_owner_round"]}')]
    friendly, enemy = patch['friendly_effects'], patch['enemy_effects']
    if 'hydrogen_fuel_multiplier' in friendly:
        rows.append(SummaryRow(f'Owner’s allies: sublight propulsion AM {friendly["hydrogen_fuel_multiplier"]:.0%}', 'benefit'))
    if 'nitrogen_cooldown_reduction' in friendly:
        rows.append(SummaryRow(f'Owner’s allies: turret cooldown reset −{friendly["nitrogen_cooldown_reduction"]:g} turns when firing', 'benefit'))
    if 'oxygen_splash_multiplier' in enemy:
        rows.append(SummaryRow(f'Owner’s enemies: Cluster Warhead splash taken {enemy["oxygen_splash_multiplier"]:g}×', 'hazard'))
    if 'dust_sensor_multiplier' in enemy:
        rows.append(SummaryRow(f'Owner’s enemies: short-range sensor radius {enemy["dust_sensor_multiplier"]:.0%}', 'restriction'))
    return rows
