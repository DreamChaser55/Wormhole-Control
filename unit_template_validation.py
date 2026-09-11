"""Read-only validation of external designs against current Designer rules.

Storage decoding remains permissive for historical libraries. This module does
not load or publish a user's library, initialize the GUI, or write files.
"""
import dataclasses
import json
import math

from constants import HullSize, get_min_antimatter_capacity
from unit_components.enums import (
    AbilityType, CloakingType, HyperdriveType, TurretType, TurretVariant, WingType,
)


# Minimums used by both the Designer input readers and design validation.
PARAMETER_MINIMUMS = {
    'engine_speed': 0.0, 'hyperdrive_jump_range': 1,
    'armor': 0, 'shields': 0, 'point_defense': 0,
    'sensor_short_range': 0.0, 'sensor_long_range_hexes': 0,
    'repair_rate': 0.0, 'repair_range': 0.0,
    'mining_rate': 0.0, 'mining_range': 0.0, 'max_mining_cargo': 0.0,
    'hangar_slots': 1, 'strikecraft_bay_slots': 1,
    'inhibitor_radius': 0.0, 'marines_count': 1,
    'cloaking_radius': 0.0, 'intelligence_agents_count': 1,
}


def sensor_hull_errors(hull_size, long_range_hexes, field="sensor_long_range_hexes"):
    """Equipment eligibility shared by design saves and field refits."""
    if hull_size == HullSize.STRIKECRAFT_WING and long_range_hexes != 0:
        return [f"{field}: strikecraft wing Sensors are intra-sector only; must be 0."]
    return []


def parameter_minimum(field, hull_size):
    if field == 'antimatter_capacity':
        return get_min_antimatter_capacity(hull_size)
    return PARAMETER_MINIMUMS[field]


def number_is_valid(value, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if integer and not isinstance(value, int):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def component_value_errors(values):
    """Check supplied values before any loader coercion or cost arithmetic.

    Deliberately apply no new balance bounds to turret stats or fixed costs:
    the current Designer imposes no such numeric bounds.
    """
    from custom_unit_templates import ComponentConfig

    errors = []
    fields = {field.name: field.type for field in dataclasses.fields(ComponentConfig)}
    fields.update(has_counter_intelligence=bool, has_fighter_bay=bool,
                  fighter_bay_slots=int, has_scanner=bool)
    for name, kind in fields.items():
        if name not in values:
            continue
        value = values[name]
        if kind is bool and not isinstance(value, bool):
            errors.append(f'{name}: must be a boolean.')
        elif kind in (int, float) and not number_is_valid(value, integer=kind is int):
            expected = 'integer' if kind is int else 'number'
            errors.append(f'{name}: must be a finite {expected} (booleans are not numbers).')
        elif kind is str and not isinstance(value, str):
            errors.append(f'{name}: must be a string.')

    choices = {
        'hyperdrive_type': set(HyperdriveType.__members__),
        'cloaking_type': set(CloakingType.__members__),
        'wing_type': set(WingType.__members__),
    }
    for name, options in choices.items():
        if name in values and (not isinstance(values[name], str) or values[name] not in options):
            errors.append(f'{name}: must be one of {", ".join(sorted(options))}.')

    abilities = values.get('abilities', [])
    if not isinstance(abilities, list):
        errors.append('abilities: must be a list.')
    else:
        known = {ability.value for ability in AbilityType}
        seen = set()
        for index, ability in enumerate(abilities):
            if not isinstance(ability, str) or ability not in known:
                errors.append(f'abilities[{index}]: unknown ability {ability!r}.')
            elif ability in seen:
                errors.append(f'abilities[{index}]: duplicate ability {ability!r}.')
            else:
                seen.add(ability)

    turrets = values.get('turrets', [])
    if not isinstance(turrets, list):
        errors.append('turrets: must be a list.')
    else:
        for index, turret in enumerate(turrets):
            prefix = f'turrets[{index}]'
            if not isinstance(turret, dict):
                errors.append(f'{prefix}: must be an object.')
                continue
            for field, options, default in (
                ('type', {item.name for item in TurretType}, None),
                ('variant', {item.name for item in TurretVariant}, 'STANDARD'),
            ):
                value = turret.get(field, default)
                if not isinstance(value, str) or value not in options:
                    errors.append(f'{prefix}.{field}: must be one of {", ".join(sorted(options))}.')
            for field in ('damage', 'range', 'cooldown'):
                if not number_is_valid(turret.get(field), integer=field == 'cooldown'):
                    errors.append(f'{prefix}.{field}: must be a finite {"integer" if field == "cooldown" else "number"}.')
    return errors


def parameter_errors(components, hull_size):
    """Validate a ComponentConfig without changing its values."""
    from custom_unit_templates import ComponentConfig, TurretConfig

    if not isinstance(components, ComponentConfig):
        return ['components: must be a ComponentConfig.']
    if isinstance(components.turrets, list) and any(
        not isinstance(turret, TurretConfig) for turret in components.turrets
    ):
        return ['turrets: entries must be TurretConfig objects.']
    values = {field.name: getattr(components, field.name)
              for field in dataclasses.fields(components)}
    if isinstance(components.turrets, list):
        values['turrets'] = [
            dict(type=t.turret_type, damage=t.damage, range=t.range,
                 cooldown=t.cooldown, variant=t.variant)
            for t in components.turrets
        ]
    errors = component_value_errors(values)
    if errors:
        return errors
    # Keep established save-validation messages, adding the JSON field path.
    labels = {
        'hyperdrive_jump_range': 'Hyperdrive jump range',
        'marines_count': 'Marines count',
        'intelligence_agents_count': 'Intelligence agents count',
    }
    for field in PARAMETER_MINIMUMS:
        minimum = parameter_minimum(field, hull_size)
        if values[field] < minimum:
            label = f'{labels[field]} ' if field in labels else ''
            errors.append(f'{field}: {label}must be at least {minimum:g}.')
    if components.has_sensors:
        errors.extend(sensor_hull_errors(hull_size, components.sensor_long_range_hexes))
    return errors


def parse_library(payload):
    """Parse JSON without silently discarding duplicate object keys."""
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'Duplicate JSON key: {key!r}.')
            result[key] = value
        return result

    # Python's nonstandard NaN/Infinity literals reach field validation, so one
    # bad record need not prevent diagnostics for the remaining designs.
    return json.loads(payload, object_pairs_hook=object_pairs)


def validate_library(raw, is_builtin: bool = False):
    """Return {library key: [errors]} for every invalid record, without mutation."""
    from custom_unit_templates import template_from_dict
    from unit_templates import builtin_template_names

    if not isinstance(raw, dict):
        return {'<library>': ['must be a JSON object mapping names to templates.']}
    reserved, seen, issues = builtin_template_names(), set(), {}
    for key, data in raw.items():
        if not isinstance(data, dict):
            issues[key] = ['must be a JSON object.']
            continue
        errors = component_value_errors(data)
        name = data.get('name', key)
        if not isinstance(name, str) or not name.strip():
            errors.append('name: must be a nonempty string.')
        else:
            canonical = name.strip().lower()
            if canonical in seen:
                dup_label = 'another template' if is_builtin else 'another custom template'
                errors.append(f'name: duplicates {dup_label} (ignoring case and surrounding whitespace).')
            if not is_builtin and canonical in reserved:
                errors.append('name: reserved by a built-in template.')
            seen.add(canonical)
        hull = data.get('hull_size', 'MEDIUM')
        if not isinstance(hull, str) or hull.upper() not in HullSize.__members__:
            errors.append('hull_size: must be a recognized hull name.')
        if not errors:
            try:
                errors.extend(template_from_dict(key, data).validate())
            except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
                errors.append(f'could not validate template: {exc}')
        if errors:
            issues[key] = errors
    return issues


def equipment_errors(hull_size, components):
    """Validate a complete equipment configuration without GUI or live mutation."""
    from custom_unit_templates import (
        CustomUnitTemplate, HULL_RESTRICTIONS, ADVANCED_HYPERDRIVE_MIN_HULL,
        ADVANCED_CLOAKING_MIN_HULL, ABILITY_REQUIRED_COMPONENTS,
    )
    if not isinstance(hull_size, HullSize):
        return ["hull_size: must be a HullSize."]
    errors = []
    design = CustomUnitTemplate("Equipment", hull_size, components)
    errors.extend(parameter_errors(components, hull_size))
    if errors:
        return errors
    try:
        total = design.total_hull_cost
        if not math.isfinite(total):
            return ["total_hull_cost: must be finite."]
    except (OverflowError, ValueError):
        return ["total_hull_cost: cannot be computed from these parameters."]
    if total > design.hull_capacity:
        errors.append(
            f"Hull over capacity: {total:g} / {design.hull_capacity:g} used."
        )
    # Check hull-size restrictions
    restricted = HULL_RESTRICTIONS.get(hull_size, set())
    c = components
    for flag in sorted(restricted):
        if getattr(c, flag, False):
            errors.append(
                f"Component '{flag}' is not allowed on {hull_size.name} hull."
            )

    # Validate Strikecraft Wing wing_type and turret variants
    if hull_size == HullSize.STRIKECRAFT_WING:
        wing_type_upper = c.wing_type.upper() if hasattr(c, "wing_type") else "FIGHTER"
        if wing_type_upper not in ("FIGHTER", "BOMBER"):
            errors.append(f"Invalid strikecraft wing role: {c.wing_type}. Must be FIGHTER or BOMBER.")
        else:
            for idx, turret in enumerate(c.turrets):
                variant_upper = turret.variant.upper()
                if wing_type_upper == "FIGHTER":
                    if variant_upper != "ANTI_STRIKECRAFT":
                        errors.append(f"Fighter Wing turret {idx + 1} must be ANTI_STRIKECRAFT (got {variant_upper}).")
                elif wing_type_upper == "BOMBER":
                    if variant_upper == "ANTI_STRIKECRAFT":
                        errors.append(f"Bomber Wing turret {idx + 1} cannot be ANTI_STRIKECRAFT.")
    # Advanced hyperdrive restriction
    hull_sizes = list(HullSize)
    min_idx = hull_sizes.index(ADVANCED_HYPERDRIVE_MIN_HULL)
    if c.has_hyperdrive and c.hyperdrive_type == "ADVANCED":
        if hull_sizes.index(hull_size) < min_idx:
            errors.append(
                f"ADVANCED hyperdrive requires at least {ADVANCED_HYPERDRIVE_MIN_HULL.name} hull."
            )
    # Advanced cloaking restriction
    min_cloak_idx = hull_sizes.index(ADVANCED_CLOAKING_MIN_HULL)
    if c.has_cloaking_device and str(c.cloaking_type).upper() == "ADVANCED":
        if hull_sizes.index(hull_size) < min_cloak_idx:
            errors.append(
                f"ADVANCED cloaking device requires at least {ADVANCED_CLOAKING_MIN_HULL.name} hull."
            )
    # Antimatter capacity must be at least min cap for hull size
    min_am_cap = get_min_antimatter_capacity(hull_size)
    if c.has_antimatter_storage and c.antimatter_capacity < min_am_cap:
        errors.append(f"Antimatter storage capacity must be at least {min_am_cap} for {hull_size.name} hull.")

    # Ability component requirements
    if c.has_ability_component and c.abilities:
        for ab_key in c.abilities:
            if ab_key in ('tracking_lock', 'flak_barrage') and not any(
                    getattr(t.variant, 'name', str(t.variant)).upper() == 'ANTI_STRIKECRAFT' for t in c.turrets):
                errors.append(f"Ability '{ab_key.replace('_', ' ').title()}' requires an anti-strikecraft turret.")
            reqs = ABILITY_REQUIRED_COMPONENTS.get(ab_key, [])
            for req_comp in reqs:
                if not getattr(c, req_comp, False):
                    ab_name = ab_key.replace('_', ' ').title()
                    errors.append(f"Ability '{ab_name}' requires component '{req_comp}'.")

    # Trade component engine requirement
    if c.has_trade_component and not c.has_engine:
        errors.append("Trade component requires an Engine component.")

    # At least one meaningful component
    any_component = any([
        c.has_engine, c.has_antimatter_storage, c.has_antimatter_harvester, c.has_hyperdrive, c.has_weapon_bays,
        c.has_defenses,
        c.has_constructor_component, c.has_repair_component,
        c.has_colony_component, c.has_civilian_habitat_component, c.has_orbital_defense_component, c.has_trade_component, c.has_mining_component,
        c.has_metal_refinery_component, c.has_crystal_refinery_component,
        c.has_hangar, c.has_strikecraft_bay, c.has_inhibitor, c.has_ability_component,
        c.has_sensors, c.has_minelayer_component, c.has_marines_component,
        c.has_cloaking_device, c.has_intelligence_component,
    ])


    if not any_component:
        errors.append("At least one component must be enabled.")
    return errors
