"""Numeric draft parsing and field feedback shared by the equipment editors.

Text belongs to the widgets until it is valid. This module never coerces library
JSON or changes gameplay state; equipment validation remains authoritative.
"""
from dataclasses import dataclass, fields
import re

from custom_unit_templates import ComponentConfig, TurretConfig
from unit_template_validation import number_is_valid, parameter_minimum


@dataclass(frozen=True)
class InputField:
    widget: str
    component: str
    label: str


INPUT_FIELDS = {
    'engine_speed': InputField('_engine_speed_entry', 'has_engine', 'Engines / Speed'),
    'antimatter_capacity': InputField('_am_capacity_entry', 'has_antimatter_storage', 'Antimatter Storage / Capacity'),
    'hyperdrive_jump_range': InputField('_hd_jump_range_entry', 'has_hyperdrive', 'Hyperdrive / Jump range'),
    'armor': InputField('_armor_entry', 'has_defenses', 'Defenses / Armor'),
    'shields': InputField('_shields_entry', 'has_defenses', 'Defenses / Shields'),
    'point_defense': InputField('_pd_entry', 'has_defenses', 'Defenses / Point defense'),
    'sensor_short_range': InputField('_sensor_short_range_entry', 'has_sensors', 'Sensors / Short-range radius'),
    'sensor_long_range_hexes': InputField('_sensor_long_range_entry', 'has_sensors', 'Sensors / Long-range hexes'),
    'repair_rate': InputField('_repair_rate_entry', 'has_repair_component', 'Repair / Rate'),
    'repair_range': InputField('_repair_range_entry', 'has_repair_component', 'Repair / Range'),
    'mining_rate': InputField('_mining_rate_entry', 'has_mining_component', 'Mining / Rate'),
    'mining_range': InputField('_mining_range_entry', 'has_mining_component', 'Mining / Range'),
    'max_mining_cargo': InputField('_mining_max_cargo_entry', 'has_mining_component', 'Mining / Cargo capacity'),
    'hangar_slots': InputField('_hangar_slots_entry', 'has_hangar', 'Hangar / Slots'),
    'strikecraft_bay_slots': InputField('_strikecraft_bay_slots_entry', 'has_strikecraft_bay', 'Strikecraft Bay / Slots'),
    'inhibitor_radius': InputField('_inhibitor_radius_entry', 'has_inhibitor', 'Inhibitor / Radius'),
    'troop_capacity': InputField('_troop_capacity_entry', 'has_troop_transport_component', 'Troop Transport / Capacity'),
    'marines_count': InputField('_marines_count_entry', 'has_marines_component', 'Marines / Count'),
    'cloaking_radius': InputField('_cloaking_radius_entry', 'has_cloaking_device', 'Cloaking / Area radius'),
    'intelligence_agents_count': InputField('_intel_agents_entry', 'has_intelligence_component', 'Intelligence / Agent capacity'),
    'turret.damage': InputField('_turret_dmg_entry', 'has_weapon_bays', 'Weapons / Turret damage'),
    'turret.range': InputField('_turret_range_entry', 'has_weapon_bays', 'Weapons / Turret range'),
    'turret.cooldown': InputField('_turret_cd_entry', 'has_weapon_bays', 'Weapons / Turret cooldown'),
}
_NUMBER_TYPES = {f.name: f.type for f in fields(ComponentConfig)}
_NUMBER_TYPES.update({f'turret.{f.name}': f.type for f in fields(TurretConfig)})


def parse_number(text: str, field: str, hull_size, *, storage_enabled=True):
    """Return (value, error) without changing text; invalid values return None.

    Integer syntax is deliberately stricter than float syntax. Disabled settings
    keep their normal minimums; only the storage minimum depends on installation,
    exactly as in complete equipment validation.
    """
    integer = _NUMBER_TYPES[field] is int
    minimum = (0 if field.startswith('turret.') else
               None if field == 'antimatter_capacity' and not storage_enabled else
               parameter_minimum(field, hull_size))
    accepted = f"a finite {'integer' if integer else 'number'}"
    if minimum is not None:
        accepted += f' >= {minimum:g}'
    error = f'{INPUT_FIELDS[field].label}: enter {accepted}.'
    try:
        if integer and not re.fullmatch(r'[+-]?[0-9]+', text.strip()):
            return None, error
        value = int(text) if integer else float(text)
        if not number_is_valid(value, integer=integer) or (minimum is not None and value < minimum):
            return None, error
    except (ValueError, OverflowError):
        return None, error
    return value, None


def install_feedback_theme(manager):
    """Install a colour-only rule, also for standalone/default-theme managers."""
    manager.get_theme().load_theme({'#equipment_input_error': {'colours': {
        'normal_border': '#FF6666', 'selected_border': '#FF6666',
        'disabled_border': '#FF6666',
    }}})


def mark_entry(entry, error):
    """Change feedback only when necessary, preserving the live typing widget."""
    if entry is None or not hasattr(entry, 'change_object_id'):
        return
    previous = getattr(entry, '_equipment_input_error', None)
    if previous == error:
        return
    if not hasattr(entry, '_equipment_original_id'):
        from pygame_gui.core import ObjectID
        entry._equipment_original_id = ObjectID(entry.object_ids[-1], entry.class_ids[-1])
    entry._equipment_input_error = error
    if bool(previous) != bool(error):
        entry.change_object_id('#equipment_input_error' if error else entry._equipment_original_id)
        # Theme changes rebuild the drawable, including its cursor/selection.
        # Restore those visual states without refocusing or replacing the text.
        if entry.is_focused:
            layout = entry.drawable_shape.text_box_layout
            layout.set_cursor_position(entry.edit_position)
            entry.select_range = entry.select_range[:]
            layout.turn_on_cursor()
    entry.set_tooltip(error)


def capacity_excess(used, capacity):
    """Format the actual excess without rounding a small violation down to zero."""
    return f'Over by {used - capacity:g} hull' if used > capacity else ''
