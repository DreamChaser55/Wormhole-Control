"""Read numeric drafts without discarding invalid text or silently clamping it."""
from constants import HullSize
from gui.equipment_input import INPUT_FIELDS, mark_entry, parse_number


def read_fields(editor, names):
    """Update valid fields only and retain independent errors for invalid drafts."""
    if not hasattr(editor, '_field_errors'):
        editor._field_errors = {}
    values = {}
    for field in names:
        entry = getattr(editor, INPUT_FIELDS[field].widget, None)
        if entry is None:
            continue
        if field == 'sensor_long_range_hexes' and editor._hull_size == HullSize.STRIKECRAFT_WING:
            if entry.get_text() != '0':
                entry.set_text('0')
        value, error = parse_number(entry.get_text(), field, editor._hull_size,
                                    storage_enabled=editor._comp.has_antimatter_storage)
        mark_entry(entry, error)
        if error:
            editor._field_errors[field] = error
        else:
            editor._field_errors.pop(field, None)
            values[field] = value
            if not field.startswith('turret.'):
                setattr(editor._comp, field, value)
    return values


def read_all(editor):
    """Re-read even hidden/disabled settings before publishing a design."""
    return read_fields(editor, INPUT_FIELDS)


def read_turret_params(editor):
    return read_fields(editor, ('turret.damage', 'turret.range', 'turret.cooldown'))


def read_engine_params(editor):
    read_fields(editor, ('engine_speed',))


def read_antimatter_params(editor):
    read_fields(editor, ('antimatter_capacity',))


def read_hyperdrive_params(editor):
    read_fields(editor, ('hyperdrive_jump_range',))


def read_defense_params(editor):
    read_fields(editor, ('armor', 'shields', 'point_defense'))


def read_sensor_params(editor):
    read_fields(editor, ('sensor_short_range', 'sensor_long_range_hexes'))


def read_repair_params(editor):
    read_fields(editor, ('repair_rate', 'repair_range'))


def read_mining_params(editor):
    read_fields(editor, ('mining_rate', 'mining_range', 'max_mining_cargo'))


def read_hangar_params(editor):
    read_fields(editor, ('hangar_slots',))


def read_strikecraft_bay_params(editor):
    read_fields(editor, ('strikecraft_bay_slots',))


def read_inhibitor_params(editor):
    read_fields(editor, ('inhibitor_radius',))


def read_marines_params(editor):
    read_fields(editor, ('marines_count',))


def read_cloaking_params(editor):
    read_fields(editor, ('cloaking_radius',))


def read_intelligence_params(editor):
    read_fields(editor, ('intelligence_agents_count',))


def read_troop_params(editor):
    read_fields(editor, ('troop_capacity',))
