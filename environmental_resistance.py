"""Environmental resistance rules shared by resolution, commands and presentation."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ResistanceSpec:
    name: str
    hazards: tuple[str, ...]
    upkeep: float
    reduction: float = 0.75


SPECS = {
    'hazard_shielding': ResistanceSpec('Hazard Shielding', ('plasma', 'black_hole', 'debris'), 2),
    'radiation_hardening': ResistanceSpec('Radiation Hardening', ('radiation',), 1),
    'antimatter_containment': ResistanceSpec('Antimatter Containment', ('magnetic', 'pulsar'), 1),
}


def instances(unit):
    component = getattr(unit, 'ability_component', None)
    return {kind.value: instance for kind, instance in getattr(component, 'abilities', {}).items()
            if kind.value in SPECS}


def active_kinds(unit):
    return {kind for kind, instance in instances(unit).items() if instance.is_active}


def operational(unit):
    from dismantling import offline
    if offline(unit):
        return False
    if (getattr(unit, 'current_hit_points', 0) <= 0 or getattr(unit, 'is_disabled', False)
            or getattr(unit, 'is_hidden_in_gas_giant', False)):
        return False
    for name in ('ability_component', 'antimatter_component'):
        component = getattr(unit, name, None)
        if component is None or component.is_destroyed:
            return False
    galaxy = getattr(unit, 'in_galaxy', None) or getattr(getattr(unit, 'game', None), 'galaxy', None)
    system = galaxy.systems.get(unit.in_system) if galaxy else None
    sector = system.hexes.get(unit.in_hex) if system else None
    return sector is not None and unit in sector.units


def upkeep(unit):
    """Read-only estimate; payment belongs exclusively to the hazard phase."""
    return sum(SPECS[kind].upkeep for kind in active_kinds(unit)) if operational(unit) else 0.0


def availability(unit, kind, enabled, *, states=None, fuel=None):
    if kind not in instances(unit):
        return 'capability_unavailable'
    if not enabled:
        return None
    if not operational(unit):
        return 'capability_unavailable'
    resulting = set(active_kinds(unit) if states is None else states) | {kind}
    available = unit.antimatter_component.current_amount if fuel is None else fuel
    if available < sum(SPECS[key].upkeep for key in resulting):
        return 'insufficient_resources'
    return None


def set_enabled(unit, kind, enabled):
    """Commit a prepared state, rechecking authoritative equipment and fuel."""
    error = availability(unit, kind, enabled)
    if error:
        raise ValueError(error)
    instances(unit)[kind].is_active = enabled


def deactivate(unit):
    for instance in instances(unit).values():
        instance.is_active = False


def reconcile(unit):
    if not operational(unit):
        deactivate(unit)


def pay_upkeep(unit):
    """Called once immediately before this owner's environmental hazard phase."""
    reconcile(unit)
    cost = upkeep(unit)
    if cost and not unit.antimatter_component.consume(cost):
        deactivate(unit)
        from turn_briefing import unit_event
        unit_event(unit, 'problem', 'Environmental resistances disabled: insufficient antimatter',
                   private=True, once=True)


def retained_fraction(unit, hazard_kind):
    if operational(unit):
        for kind in active_kinds(unit):
            if hazard_kind in SPECS[kind].hazards:
                return 1.0 - SPECS[kind].reduction
    return 1.0


def details(kind):
    spec = SPECS[kind]
    return {'activation_mode': 'toggle', 'ongoing_antimatter': spec.upkeep,
            'protected_hazards': list(spec.hazards), 'reduction': spec.reduction,
            'clock': 'before_environmental_hazards_each_owner_turn'}


def description(kind):
    spec = SPECS[kind]
    hazards = ', '.join(h.replace('_', ' ') for h in spec.hazards)
    return (f'Reduces {hazards} hazards by {spec.reduction:.0%} for this unit while enabled. '
            f'Costs {spec.upkeep:g} AM each owner turn, including safe space. '
            'Requires functional Abilities and Antimatter Storage. Protection does not change terrain access, sensors or movement.')
