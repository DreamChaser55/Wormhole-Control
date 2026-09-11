"""Pure catalog descriptions shared by players, controllers and reference tables."""
from custom_unit_templates import template_from_dict, template_to_dict
from constants import (
    DEFAULT_ANTIMATTER_HARVEST_RATE, DEFAULT_SENSOR_SHORT_RANGE,
    INHIBITOR_ANTIMATTER_COST_PER_50_RADIUS, CLOAKING_BASIC_ANTIMATTER_COST_PER_TURN,
    CLOAKING_ADVANCED_ANTIMATTER_COST_PER_RADIUS,
)

CATEGORIES = ('Combat', 'Carriers', 'Economy', 'Logistics', 'Reconnaissance', 'Special Operations')
WING_TEMPLATES = ('FIGHTER_WING', 'BOMBER_WING')


def describe_template(key, raw):
    source = dict(raw)
    if hasattr(source.get('hull_size'), 'name'):
        source['hull_size'] = source['hull_size'].name
    design = template_from_dict(key, source)
    data = template_to_dict(design)
    kind = ('wing' if design.hull_size.name == 'STRIKECRAFT_WING' else
            'ship' if data['has_engine'] or data['has_hyperdrive'] else 'station')
    weapons = []
    for turret in data['turrets'] if data['has_weapon_bays'] else []:
        scale = 3 if turret['variant'] == 'LONG_RANGE' else 1
        targets = ['ship', 'station', 'wing'] if turret['variant'] == 'ANTI_STRIKECRAFT' else ['ship', 'station']
        if kind == 'wing':
            allowed = ['ship', 'station'] if data['wing_type'].upper() == 'BOMBER' else ['wing']
            targets = [target for target in targets if target in allowed]
        weapons.append(dict(turret, range=turret['range'] * scale,
                            cooldown=turret['cooldown'] * scale,
                            target_classes=targets))
    support = {}
    for flag, fields in {
        'constructor_component': (), 'colony_component': (),
        'repair_component': ('repair_rate', 'repair_range', 'credit_cost_per_hp'),
        'mining_component': ('mining_rate', 'mining_range', 'max_mining_cargo'),
        'metal_refinery_component': ('unload_range',), 'crystal_refinery_component': ('unload_range',),
        'civilian_habitat_component': ('civilian_habitat_bonus',),
        'orbital_defense_component': ('orbital_defense_radius', 'orbital_defense_attack_bonus', 'orbital_defense_defense_bonus'),
        'trade_component': ('trade_revenue_multiplier',), 'hangar': ('hangar_slots',),
        'strikecraft_bay': ('strikecraft_bay_slots',), 'inhibitor': ('inhibitor_radius',),
        'minelayer_component': (), 'marines_component': ('marines_count',),
        'cloaking_device': ('cloaking_type', 'cloaking_radius'),
        'intelligence_component': ('intelligence_agents_count', 'has_counter_intelligence'),
    }.items():
        if data.get('has_' + flag):
            support[flag] = {field: data[field] for field in fields}
    if 'cloaking_device' in support and data['cloaking_type'] == 'BASIC':
        support['cloaking_device']['cloaking_radius'] = 0
    if 'cloaking_device' in support:
        support['cloaking_device']['antimatter_cost_per_turn'] = (
            CLOAKING_BASIC_ANTIMATTER_COST_PER_TURN if data['cloaking_type'] == 'BASIC'
            else data['cloaking_radius'] * CLOAKING_ADVANCED_ANTIMATTER_COST_PER_RADIUS)
    if 'inhibitor' in support:
        support['inhibitor']['antimatter_cost_per_turn'] = data['inhibitor_radius'] / 50 * INHIBITOR_ANTIMATTER_COST_PER_50_RADIUS
    if data['has_antimatter_harvester']:
        support['antimatter_harvester'] = {'harvest_rate': raw.get('antimatter_harvest_rate', DEFAULT_ANTIMATTER_HARVEST_RATE)}
    return {
        'template_name': key, 'name': data['name'], 'category': raw.get('category', 'Custom'),
        'roles': raw.get('roles', list(support) or [kind]),
        'description': raw.get('description', 'Player design.' if raw.get('is_custom') else 'Testing design.'),
        'kind': kind, 'hull_size': design.hull_size.name,
        'hull_used': design.total_hull_cost, 'hull_capacity': design.hull_capacity,
        'hit_points': data['hull_points'], 'credit_cost': raw.get('build_cost', design.build_cost),
        'turns': raw.get('build_time', design.build_time), 'upkeep': design.predicted_upkeep,
        'movement': {'speed': data['engine_speed'] if data['has_engine'] else 0,
                     'hyperdrive': data['hyperdrive_type'] if data['has_hyperdrive'] else None,
                     'jump_range': data['hyperdrive_jump_range'] if data['has_hyperdrive'] else 0},
        'fuel_capacity': data['antimatter_capacity'] if data['has_antimatter_storage'] else 0,
        'sensors': {'short_range': data['sensor_short_range'] if data['has_sensors'] else DEFAULT_SENSOR_SHORT_RANGE,
                    'long_range_hexes': data['sensor_long_range_hexes'] if data['has_sensors'] else 0},
        'weapons': weapons,
        'defenses': {field: data[field] if data['has_defenses'] else 0 for field in ('armor', 'shields', 'point_defense')},
        'abilities': data['abilities'] if data['has_ability_component'] else [], 'support': support,
    }


def validate_builtin_catalog(raw):
    """Check authored metadata and derived fields in addition to Designer legality."""
    from unit_template_validation import validate_library
    issues = validate_library(raw, is_builtin=True)
    if not isinstance(raw, dict):
        return issues
    for key, data in raw.items():
        if key in issues:
            continue
        errors = []
        if data.get('category') not in CATEGORIES:
            errors.append('category: choose a catalog category.')
        if not isinstance(data.get('description'), str) or not data['description'].strip():
            errors.append('description: must be nonempty text.')
        roles = data.get('roles')
        if not isinstance(roles, list) or not roles or any(not isinstance(r, str) or not r.strip() for r in roles):
            errors.append('roles: must be a nonempty list of nonempty strings.')
        canonical = template_to_dict(template_from_dict(key, data))
        for field, expected in canonical.items():
            if field in ('build_cost', 'build_time', 'hull_points') or field.endswith('_hull_cost'):
                if data.get(field) != expected:
                    errors.append(f'{field}: expected canonical value {expected}.')
        if errors:
            issues[key] = errors
    return issues
