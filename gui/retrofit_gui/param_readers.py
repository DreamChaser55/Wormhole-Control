"""Retrofit widget parsing using the Designer's shared parameter minimums."""
from constants import HullSize
from gui.equipment_input import mark_entry, parse_number


def read_number(wizard, widget, field, default):
    """Return a parsed value, recording errors without changing draft text."""
    entry = getattr(wizard, widget, None)
    text = entry.get_text() if entry is not None else str(default)
    value, error = parse_number(text, field, wizard.target_unit.hull_size)
    mark_entry(entry, error)
    if error:
        wizard._field_errors[field] = error
    return value


def read_fields(wizard, fields):
    for key, widget, field, default in fields:
        value = read_number(wizard, widget, field, default)
        if value is not None:
            wizard._comp_config[key] = value


def read_engine_params(wizard):
    read_fields(wizard, [('speed', '_engine_speed_entry', 'engine_speed', 100)])


def read_antimatter_params(wizard):
    read_fields(wizard, [('max_capacity', '_am_capacity_entry', 'antimatter_capacity', 100)])


def read_hyperdrive_params(wizard):
    read_fields(wizard, [('jump_range', '_hd_jump_range_entry', 'hyperdrive_jump_range', 5)])


def read_defense_params(wizard):
    read_fields(wizard, [(f, w, f, 0.0) for f, w in
                        [('armor', '_armor_entry'), ('shields', '_shields_entry'), ('point_defense', '_pd_entry')]])


def read_sensor_params(wizard):
    read_fields(wizard, [('short_range_radius', '_sensor_short_range_entry', 'sensor_short_range', 500)])
    if wizard.target_unit.hull_size == HullSize.STRIKECRAFT_WING:
        wizard._comp_config['long_range_hexes'] = 0
        if wizard._sensor_long_range_entry:
            wizard._sensor_long_range_entry.set_text('0')
    else:
        read_fields(wizard, [('long_range_hexes', '_sensor_long_range_entry', 'sensor_long_range_hexes', 0)])


def read_repair_params(wizard):
    read_fields(wizard, [('repair_rate', '_repair_rate_entry', 'repair_rate', 10),
                         ('repair_range', '_repair_range_entry', 'repair_range', 200)])


def read_mining_params(wizard):
    read_fields(wizard, [('mining_rate', '_mining_rate_entry', 'mining_rate', 10),
                         ('mining_range', '_mining_range_entry', 'mining_range', 200),
                         ('max_cargo', '_mining_max_cargo_entry', 'max_mining_cargo', 100)])


def read_hangar_params(wizard):
    read_fields(wizard, [('max_slots', '_hangar_slots_entry', 'hangar_slots', 2)])


def read_strikecraft_bay_params(wizard):
    read_fields(wizard, [('max_slots', '_strikecraft_bay_slots_entry', 'strikecraft_bay_slots', 2)])


def read_inhibitor_params(wizard):
    read_fields(wizard, [('radius', '_inhibitor_radius_entry', 'inhibitor_radius', 100)])


def read_marines_params(wizard):
    read_fields(wizard, [('marines_count', '_marines_count_entry', 'marines_count', 10)])


def read_cloaking_params(wizard):
    read_fields(wizard, [('area_radius', '_cloaking_radius_entry', 'cloaking_radius', 500)])


def read_intelligence_params(wizard):
    read_fields(wizard, [('agents_capacity', '_intel_agents_entry', 'intelligence_agents_count', 1)])
    wizard._comp_config['has_counter_intelligence'] = bool(wizard._intel_ci_enabled)
