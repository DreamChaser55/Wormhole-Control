"""Draft parsing stays strict without changing the equipment persistence rules."""
from types import SimpleNamespace

import pytest

from constants import HullSize
from custom_unit_templates import ComponentConfig
from gui.equipment_input import INPUT_FIELDS, parse_number
from gui.unit_editor_gui.param_readers import read_fields
from unit_template_validation import PARAMETER_MINIMUMS, parameter_minimum


INTEGER_FIELDS = {
    'hyperdrive_jump_range', 'sensor_long_range_hexes', 'hangar_slots',
    'strikecraft_bay_slots', 'troop_capacity', 'marines_count',
    'intelligence_agents_count', 'turret.cooldown',
}


@pytest.mark.parametrize('field', INPUT_FIELDS)
@pytest.mark.parametrize('text', ['', 'abc', 'NaN', 'inf', '-Infinity', '1e999', '-1'])
def test_invalid_drafts_have_actionable_feedback_without_replacing_values(field, text):
    entry = SimpleNamespace(get_text=lambda: text)
    editor = SimpleNamespace(_comp=ComponentConfig(has_antimatter_storage=True),
                             _hull_size=HullSize.MEDIUM)
    setattr(editor, INPUT_FIELDS[field].widget, entry)
    before = getattr(editor._comp, field, None)
    read_fields(editor, [field])
    assert field in editor._field_errors
    assert INPUT_FIELDS[field].label in editor._field_errors[field]
    assert 'finite' in editor._field_errors[field]
    assert '>=' in editor._field_errors[field]
    assert entry.get_text() == text
    assert getattr(editor._comp, field, None) == before


@pytest.mark.parametrize('field', INPUT_FIELDS)
def test_numeric_boundaries_match_shared_equipment_rules(field):
    minimum = 0 if field.startswith('turret.') else parameter_minimum(field, HullSize.MEDIUM)
    assert parse_number(str(minimum), field, HullSize.MEDIUM) == (minimum, None)
    assert parse_number(str(minimum - 1), field, HullSize.MEDIUM)[0] is None
    value, error = parse_number(str(minimum + .25), field, HullSize.MEDIUM)
    if field in INTEGER_FIELDS:
        assert value is None and 'integer' in error
    else:
        assert error is None and value == minimum + .25


@pytest.mark.parametrize('field', sorted(INTEGER_FIELDS))
@pytest.mark.parametrize('text', ['2.0', '1e2', '1.5', '9' * 400])
def test_integer_drafts_never_truncate_or_overflow(field, text):
    assert parse_number(text, field, HullSize.MEDIUM)[0] is None


@pytest.mark.parametrize('hull', list(HullSize))
def test_storage_minimum_depends_on_hull_and_installation(hull):
    minimum = parameter_minimum('antimatter_capacity', hull)
    assert parse_number(str(minimum), 'antimatter_capacity', hull) == (minimum, None)
    assert parse_number(str(minimum - 1), 'antimatter_capacity', hull)[0] is None
    assert parse_number('0', 'antimatter_capacity', hull, storage_enabled=False) == (0, None)


def test_all_component_minimums_have_input_bindings():
    assert set(PARAMETER_MINIMUMS) <= INPUT_FIELDS.keys()
