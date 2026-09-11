"""Pure adapters between installed equipment, retrofit requests, and Designer rules.

No component is instantiated during evaluation: turret construction applies runtime
variant scaling, and component constructors may have other gameplay side effects.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
import math

from constants import HullSize, get_min_antimatter_capacity
from custom_unit_templates import ComponentConfig, CustomUnitTemplate, TurretConfig, HULL_RESTRICTIONS, COMPONENT_COST_PER_HULL_POINT
from unit_template_validation import equipment_errors, component_value_errors, parameter_errors


@dataclass(frozen=True)
class ComponentSpec:
    flag: str
    # Retrofit parameter/live attribute -> Designer field.
    fields: dict = field(default_factory=dict)
    fixed_cost: str | None = None


COMPONENT_SPECS = {
    'Engines': ComponentSpec('has_engine', {'speed': 'engine_speed'}),
    'Hyperdrive': ComponentSpec('has_hyperdrive', {'drive_type': 'hyperdrive_type', 'jump_range': 'hyperdrive_jump_range'}),
    'Weapons': ComponentSpec('has_weapon_bays'),
    'Defenses': ComponentSpec('has_defenses', {k: k for k in ('armor', 'shields', 'point_defense')}),
    'AntimatterStorage': ComponentSpec('has_antimatter_storage', {'max_capacity': 'antimatter_capacity'}),
    'AntimatterHarvester': ComponentSpec('has_antimatter_harvester', fixed_cost='antimatter_harvester_hull_cost'),
    'Sensors': ComponentSpec('has_sensors', {'short_range_radius': 'sensor_short_range', 'long_range_hexes': 'sensor_long_range_hexes'}),
    'Constructor': ComponentSpec('has_constructor_component', fixed_cost='constructor_hull_cost'),
    'RepairComponent': ComponentSpec('has_repair_component', {'repair_rate': 'repair_rate', 'repair_range': 'repair_range', 'credit_cost_per_hp': 'credit_cost_per_hp'}),
    'MiningComponent': ComponentSpec('has_mining_component', {'mining_rate': 'mining_rate', 'mining_range': 'mining_range', 'max_cargo': 'max_mining_cargo'}),
    'MetalRefineryComponent': ComponentSpec('has_metal_refinery_component', fixed_cost='metal_refinery_hull_cost'),
    'CrystalRefineryComponent': ComponentSpec('has_crystal_refinery_component', fixed_cost='crystal_refinery_hull_cost'),
    'ColonyComponent': ComponentSpec('has_colony_component', fixed_cost='colony_hull_cost'),
    'CivilianHabitatComponent': ComponentSpec('has_civilian_habitat_component', {'economic_bonus': 'civilian_habitat_bonus'}, 'civilian_habitat_hull_cost'),
    'OrbitalDefenseComponent': ComponentSpec('has_orbital_defense_component', {'radius': 'orbital_defense_radius', 'attack_bonus': 'orbital_defense_attack_bonus', 'defense_bonus': 'orbital_defense_defense_bonus'}, 'orbital_defense_hull_cost'),
    'TradeComponent': ComponentSpec('has_trade_component', {'trade_revenue_multiplier': 'trade_revenue_multiplier'}, 'trade_hull_cost'),
    'HangarComponent': ComponentSpec('has_hangar', {'max_slots': 'hangar_slots'}),
    'StrikecraftBayComponent': ComponentSpec('has_strikecraft_bay', {'max_slots': 'strikecraft_bay_slots'}),
    'HyperspaceInhibitionFieldEmitter': ComponentSpec('has_inhibitor', {'radius': 'inhibitor_radius'}),
    'MarinesComponent': ComponentSpec('has_marines_component', {'marines_count': 'marines_count'}),
    'CloakingDevice': ComponentSpec('has_cloaking_device', {'device_type': 'cloaking_type', 'area_radius': 'cloaking_radius'}),
    'AbilityComponent': ComponentSpec('has_ability_component'),
    'MinelayerComponent': ComponentSpec('has_minelayer_component', fixed_cost='minelayer_hull_cost'),
    'IntelligenceComponent': ComponentSpec('has_intelligence_component', {'agents_capacity': 'intelligence_agents_count', 'has_counter_intelligence': 'counter_intelligence'}),
}


def canonical_component_name(name):
    from unit_components.constructor import get_component_class_by_name
    cls = get_component_class_by_name(name) if isinstance(name, str) else None
    return cls.__name__ if cls else None


def enum_name(value):
    return value.name if isinstance(value, Enum) else value


def installed_configuration(unit):
    """Read base equipment, including damaged modules; never read temporary buffs."""
    result = ComponentConfig()
    for cls, component in unit.components.items():
        name = cls.__name__
        spec = COMPONENT_SPECS.get(name)
        if spec is None:
            continue
        setattr(result, spec.flag, True)
        for attr, dest in spec.fields.items():
            setattr(result, dest, enum_name(getattr(component, attr)))
        if spec.fixed_cost:
            setattr(result, spec.fixed_cost, component.hull_cost)
        if name == 'Weapons':
            result.turrets = []
            for turret in component.turrets:
                variant = enum_name(turret.variant)
                scale = 3 if variant == 'LONG_RANGE' else 1
                # Runtime values were multiplied by three exactly once on creation.
                cooldown = turret.cooldown // scale if turret.cooldown % scale == 0 else turret.cooldown / scale
                result.turrets.append(TurretConfig(enum_name(turret.turret_type), turret.damage,
                                                   turret.range / scale, cooldown, variant))
        elif name == 'AbilityComponent':
            result.abilities = [ability.value for ability in component.abilities]
    wing = getattr(unit, 'strikecraft_wing_component', None)
    if wing:
        result.wing_type = enum_name(wing.wing_type)
    return result


@dataclass
class RefitEvaluation:
    errors: list[str] = field(default_factory=list)
    proposed: ComponentConfig | None = None
    component_name: str | None = None
    configuration: dict = field(default_factory=dict)
    hull_cost: float = 0.0
    cost_credits: int = 0
    duration: int = 1
    salvage: int = 0


def allowed_turret_variants(hull_size, wing_type='FIGHTER'):
    from unit_components.enums import TurretVariant
    variants = [v.name for v in TurretVariant]
    if hull_size == HullSize.STRIKECRAFT_WING:
        return ['ANTI_STRIKECRAFT'] if wing_type == 'FIGHTER' else [v for v in variants if v != 'ANTI_STRIKECRAFT']
    return variants


def eligible_component(unit, name):
    name = canonical_component_name(name)
    spec = COMPONENT_SPECS.get(name)
    if not spec or any(cls.__name__ == name for cls in unit.components):
        return False
    return spec.flag not in HULL_RESTRICTIONS.get(unit.hull_size, set())


def evaluate_refit(unit, action, component_name, configuration=None):
    """Validate a request and its complete result before any arithmetic or mutation.

Derived cost hints from older events/saves are ignored. Parameter values are not
coerced: malformed numbers/enums must reach the same validation as the Designer.
"""
    result = RefitEvaluation(component_name=canonical_component_name(component_name))
    spec = COMPONENT_SPECS.get(result.component_name)
    if action not in ('ADD', 'REMOVE') or spec is None:
        result.errors = ['Unsupported retrofit action or component.']
        return result
    if configuration is not None and not isinstance(configuration, dict):
        result.errors = ['Component configuration must be an object.']
        return result
    config = deepcopy(configuration or {})
    name = result.component_name
    # Historical spellings use the same canonical capacity, never available agents.
    if name == 'IntelligenceComponent' and 'agents_count' in config:
        config.setdefault('agents_capacity', config.pop('agents_count'))
    # Strikecraft bays do not have a wing role; this was an unused legacy UI field.
    if name == 'StrikecraftBayComponent':
        config.pop('wing_type', None)
    config.pop('hull_cost', None)
    existing = next((c for cls, c in unit.components.items() if cls.__name__ == name), None)
    if (action == 'ADD' and existing is not None) or (action == 'REMOVE' and existing is None):
        result.errors = ['Component already installed.' if action == 'ADD' else 'Component is not installed.']
        return result
    if action == 'REMOVE' and getattr(existing, 'docked_units', None):
        result.errors = ['Cannot remove a bay while craft are docked.']
        return result
    try:
        proposed = installed_configuration(unit)
        single = ComponentConfig()
        # Defaults share the Designer representation, with hull-specific fuel minimum.
        single.antimatter_capacity = get_min_antimatter_capacity(unit.hull_size)
        if name == 'Weapons':
            allowed = {'turrets'}
            turrets = config.get('turrets', [])
            errors = component_value_errors({'turrets': turrets})
            if errors:
                result.errors = errors
                return result
            single.turrets = [TurretConfig(t['type'], t['damage'], t['range'], t['cooldown'], t.get('variant', 'STANDARD')) for t in turrets]
        elif name == 'AbilityComponent':
            allowed = {'ability_types'}
            single.abilities = config.get('ability_types', [])
        else:
            allowed = set(spec.fields)
        unknown = config.keys() - allowed
        if unknown:
            result.errors = [f'Unknown component parameter: {key}.' for key in sorted(unknown)]
            return result
        if action == 'ADD':
            for attr, dest in spec.fields.items():
                if attr in config:
                    setattr(single, dest, config[attr])
            setattr(single, spec.flag, True)
            setattr(proposed, spec.flag, True)
            for dest in spec.fields.values():
                setattr(proposed, dest, getattr(single, dest))
            if spec.fixed_cost:
                setattr(proposed, spec.fixed_cost, getattr(single, spec.fixed_cost))
            if name == 'Weapons':
                proposed.turrets = single.turrets
            if name == 'AbilityComponent':
                proposed.abilities = single.abilities
        else:
            setattr(proposed, spec.flag, False)
            # Clear disabled parameters too: Designer validates their types/minimums.
            for dest in spec.fields.values():
                setattr(proposed, dest, getattr(single, dest))
            if name == 'Weapons':
                proposed.turrets = []
            if name == 'AbilityComponent':
                proposed.abilities = []
        result.proposed = proposed
        # Invalid field values must never reach arithmetic; structural/capacity
        # errors still permit a useful, accurate cost preview.
        result.errors = parameter_errors(single, unit.hull_size)
        if result.errors:
            return result
        if action == 'ADD' and name == 'CloakingDevice' and single.cloaking_type == 'BASIC':
            # Basic cloaks have no projected radius at runtime.
            single.cloaking_radius = proposed.cloaking_radius = 0.0
        result.errors = equipment_errors(unit.hull_size, proposed)
        if action == 'ADD':
            result.hull_cost = CustomUnitTemplate('Component', unit.hull_size, single).total_hull_cost
            result.configuration = {attr: getattr(single, dest) for attr, dest in spec.fields.items()}
            if name == 'Weapons':
                result.configuration['turrets'] = [dict(type=t.turret_type, variant=t.variant, damage=t.damage, range=t.range, cooldown=t.cooldown) for t in single.turrets]
            if name == 'AbilityComponent':
                result.configuration['ability_types'] = list(single.abilities)
            result.configuration['hull_cost'] = result.hull_cost
            # As before, installing equipment never pays credits to the builder.
            # Do not invent new numeric bounds on Designer turret parameters.
            result.cost_credits = max(0, int(round(result.hull_cost * COMPONENT_COST_PER_HULL_POINT)))
            result.duration = max(1, int(round(result.hull_cost / 5)))
            actual = unit.current_hull_usage + result.hull_cost
        else:
            result.hull_cost = existing.hull_cost
            result.salvage = max(0, int(round(existing.hull_cost * COMPONENT_COST_PER_HULL_POINT * .5)))
            actual = unit.current_hull_usage - existing.hull_cost
        if not result.errors and (not math.isfinite(actual) or actual > unit.hull_capacity):
            result.errors.append('Insufficient hull capacity for projected installed equipment.')
    except (ValueError, TypeError, OverflowError, AttributeError, KeyError) as exc:
        result.errors = [f'Invalid equipment configuration: {exc}']
    return result
