"""External template validation, editor parity, and read-only CLI behavior."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from constants import HullSize, get_min_antimatter_capacity
from custom_unit_templates import (
    ComponentConfig, CustomTemplateManager, CustomUnitTemplate, TurretConfig,
    template_from_dict,
)
from unit_template_validation import parse_library, validate_library
from unit_templates import UNIT_TEMPLATES, builtin_template_names


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts' / 'validate_unit_templates.py'


def record(**changes):
    return dict({'hull_size': 'MEDIUM', 'has_engine': True,
                 'has_antimatter_storage': False}, **changes)


def messages(data):
    return ' '.join(validate_library({'External design': data}).get('External design', []))


@pytest.mark.parametrize('field,value', [
    ('has_engine', 'false'), ('has_counter_intelligence', 1),
    ('engine_speed', True), ('engine_speed', '100'), ('engine_speed', None),
    ('engine_speed', float('nan')), ('engine_speed', float('inf')),
    ('engine_speed', 10 ** 400), ('sensor_long_range_hexes', 1.5),
    ('marines_count', 2.0), ('intelligence_agents_count', False),
    ('antimatter_capacity', '100'), ('constructor_hull_cost', '15'),
    ('hyperdrive_type', 'UNKNOWN'), ('cloaking_type', 'UNKNOWN'),
    ('wing_type', 'UNKNOWN'), ('hull_size', 'UNKNOWN'), ('hull_size', 3),
    ('name', ''), ('name', 5), ('turrets', {}), ('abilities', 'microjump'),
    ('abilities', ['unknown']), ('abilities', [{}]),
    ('abilities', ['microjump', 'microjump']),
    ('has_fighter_bay', 'false'), ('fighter_bay_slots', 2.5),
    ('has_scanner', 1), ('counter_intelligence', 'false'),
])
def test_invalid_external_values_are_reported_without_coercion(field, value):
    assert field in messages(record(**{field: value}))


@pytest.mark.parametrize('field,minimum', [
    ('engine_speed', 0), ('hyperdrive_jump_range', 1),
    ('armor', 0), ('shields', 0), ('point_defense', 0),
    ('sensor_short_range', 0), ('sensor_long_range_hexes', 0),
    ('repair_rate', 0), ('repair_range', 0), ('mining_rate', 0),
    ('mining_range', 0), ('max_mining_cargo', 0),
    ('hangar_slots', 1), ('strikecraft_bay_slots', 1),
    ('inhibitor_radius', 0), ('marines_count', 1),
    ('cloaking_radius', 0), ('intelligence_agents_count', 1),
])
def test_parameter_boundaries_match_editor(field, minimum):
    assert messages(record(**{field: minimum})) == ''
    assert field in messages(record(**{field: minimum - 1}))


@pytest.mark.parametrize('hull', list(HullSize))
def test_antimatter_minimum_is_hull_specific(hull):
    minimum = get_min_antimatter_capacity(hull)
    data = record(hull_size=hull.name, has_engine=False,
                  has_antimatter_storage=True, antimatter_capacity=minimum)
    assert messages(data) == ''
    assert 'Antimatter storage capacity' in messages(dict(data, antimatter_capacity=minimum - 1))


@pytest.mark.parametrize('turret,field', [
    (None, 'turrets[0]'), ({}, 'turrets[0].type'),
    ({'type': 'UNKNOWN', 'damage': 1, 'range': 1, 'cooldown': 0}, 'type'),
    ({'type': 'BEAM', 'damage': 1, 'range': 1, 'cooldown': 0, 'variant': 'UNKNOWN'}, 'variant'),
    ({'type': 'BEAM', 'damage': True, 'range': 1, 'cooldown': 0}, 'damage'),
    ({'type': 'BEAM', 'damage': 1, 'range': float('inf'), 'cooldown': 0}, 'range'),
    ({'type': 'BEAM', 'damage': 1, 'range': 1, 'cooldown': 0.5}, 'cooldown'),
])
def test_turret_schema(turret, field):
    assert field in messages(record(has_weapon_bays=True, turrets=[turret]))


def test_turret_bounds_do_not_add_unapproved_balance_rules():
    data = record(has_weapon_bays=True, turrets=[dict(type='BEAM', damage=-1, range=-1, cooldown=0)])
    assert messages(data) == ''


@pytest.mark.parametrize('field,value', [
    ('engine_speed', '100'), ('has_engine', 1), ('marines_count', 1.5),
    ('abilities', None), ('turrets', [{}]), ('turrets', None),
])
def test_direct_design_validation_reports_bad_types_before_cost_arithmetic(field, value):
    design = CustomUnitTemplate('Bad input', HullSize.MEDIUM, ComponentConfig(has_engine=True))
    setattr(design.components, field, value)
    assert any(field in error for error in design.validate())


def test_finite_parameters_with_overflowing_cost_are_invalid():
    data = record(has_weapon_bays=True, turrets=[
        dict(type='BEAM', variant='LONG_RANGE', damage=1, range=1e308, cooldown=0),
    ])
    assert 'total_hull_cost' in messages(data)


def test_design_rules_and_new_parity_fixes():
    assert 'not allowed' in messages(record(hull_size='STRIKECRAFT_WING', has_cloaking_device=True))
    assert 'not allowed' in messages(record(has_hangar=True))
    assert 'ADVANCED hyperdrive' in messages(record(hull_size='TINY', has_hyperdrive=True, hyperdrive_type='ADVANCED'))
    assert 'ADVANCED cloaking' in messages(record(hull_size='TINY', has_cloaking_device=True, cloaking_type='ADVANCED'))
    assert 'requires an Engine' in messages(record(has_engine=False, has_trade_component=True))
    assert 'At least one component' in messages(record(has_engine=False))
    assert 'requires component' in messages(record(has_ability_component=True, abilities=['microjump']))
    assert messages(record(has_ability_component=True, abilities=['microjump'], has_hyperdrive=True)) == ''


def test_intelligence_cost_counts_towards_budget_and_matches_gui():
    from gui.unit_editor_gui.cost_model import current_hull_used
    from types import SimpleNamespace

    comp = ComponentConfig(has_intelligence_component=True, intelligence_agents_count=1)
    design = CustomUnitTemplate('Intel', HullSize.SMALL, comp)
    editor = SimpleNamespace(_comp=comp, _hull_size=design.hull_size)
    assert design.total_hull_cost == comp.intelligence_hull_cost == current_hull_used(editor)
    comp.has_constructor_component = True
    comp.constructor_hull_cost = design.hull_capacity - comp.intelligence_hull_cost
    assert design.validate() == []  # Exactly at capacity.
    comp.has_counter_intelligence = True
    assert any('capacity' in error for error in design.validate())
    assert 'capacity' in messages(record(hull_size='SMALL', has_engine=False,
                                       has_intelligence_component=True,
                                       intelligence_agents_count=5,
                                       has_counter_intelligence=True))


def test_wing_turret_roles():
    data = record(hull_size='STRIKECRAFT_WING', has_engine=False, has_weapon_bays=True,
                  turrets=[dict(type='BEAM', damage=0, range=0, cooldown=0)])
    assert 'ANTI_STRIKECRAFT' in messages(data)
    data['turrets'][0]['variant'] = 'ANTI_STRIKECRAFT'
    assert messages(data) == ''
    data['wing_type'] = 'BOMBER'
    assert 'cannot be ANTI_STRIKECRAFT' in messages(data)


def test_export_and_legacy_defaults_round_trip_without_publication():
    comp = ComponentConfig(has_engine=True, has_weapon_bays=True,
                           turrets=[TurretConfig('BEAM', 1, 1, 0)])
    design = CustomUnitTemplate('Export', HullSize.MEDIUM, comp)
    manager = CustomTemplateManager()
    data = manager._template_to_dict(design)
    data['hull_size'] = data['hull_size'].name
    before = copy.deepcopy(UNIT_TEMPLATES)
    raw = {'Export': data, 'Legacy': record(has_scanner=True, sensor_long_range_hexes=1)}
    original = copy.deepcopy(raw)
    assert validate_library(raw) == {}
    assert raw == original
    assert UNIT_TEMPLATES == before
    assert template_from_dict('Legacy', raw['Legacy']).components.has_sensors
    assert messages(record(hull_size='medium')) == ''
    assert template_from_dict('Defaults', {}).components.has_antimatter_storage
    assert messages(record(has_fighter_bay=True, fighter_bay_slots=1)) == ''


def test_stored_derived_costs_are_ignored_but_fixed_costs_are_used():
    assert messages(record(engine_hull_cost=-1000, build_cost='stale',
                           build_time=-1, hull_points=-1)) == ''
    assert 'capacity' in messages(record(has_constructor_component=True, constructor_hull_cost=1000))


def test_mixed_records_and_name_collisions():
    reserved = next(iter(builtin_template_names()))
    issues = validate_library({'good': record(), 'broken': 42,
                               'one': record(name=' Same '), 'two': record(name='same'),
                               'reserved': record(name=reserved), 'bad speed': record(engine_speed=-1)})
    assert set(issues) == {'broken', 'two', 'reserved', 'bad speed'}
    assert 'duplicates' in ' '.join(issues['two'])
    assert 'reserved' in ' '.join(issues['reserved'])


@pytest.mark.parametrize('payload', ['{"a": {}, "a": {}}', '{"a": {"name": "x", "name": "y"}}'])
def test_duplicate_json_keys_are_not_silently_lost(payload):
    with pytest.raises(ValueError, match='Duplicate JSON key'):
        parse_library(payload)


def run_cli(tmp_path, *args, **env):
    return subprocess.run([sys.executable, str(CLI), *map(str, args)], cwd=tmp_path,
                          env=dict(os.environ, **env), text=True, capture_output=True,
                          stdin=subprocess.DEVNULL)


@pytest.mark.parametrize('payload,code', [
    ('{}', 0), (json.dumps({'ok': record()}), 0),
    (json.dumps({'bad': record(engine_speed=-1), 'ok': record()}), 1),
    ('[]', 1), ('{', 2), ('{"a": {}, "a": {}}', 2),
    ('{"bad": {"engine_speed": NaN}}', 1),
])
def test_cli_exit_codes_and_read_only_operation(tmp_path, payload, code):
    target = tmp_path / 'custom_unit_templates.json'
    target.write_text(payload)
    result = run_cli(tmp_path, target)
    assert result.returncode == code, result.stdout + result.stderr
    assert target.read_text() == payload
    assert list(tmp_path.iterdir()) == [target]
    assert str(target) in result.stdout


def test_cli_default_override_missing_file_and_invalid_override(tmp_path):
    target = tmp_path / 'custom_unit_templates.json'
    result = run_cli(tmp_path, WORMHOLE_USER_DATA_DIR=str(tmp_path))
    assert result.returncode == 2
    assert not target.exists()
    target.write_text('{}')
    assert run_cli(tmp_path, WORMHOLE_USER_DATA_DIR=str(tmp_path)).returncode == 0
    assert run_cli(tmp_path, WORMHOLE_USER_DATA_DIR='relative').returncode == 2
    assert run_cli(tmp_path, '--unknown-option').returncode == 2


def test_historical_library_loads_but_fails_current_validation(tmp_path):
    target = tmp_path / 'custom_unit_templates.json'
    target.write_text(json.dumps({'Historical': record(engine_speed=10000)}))
    manager = CustomTemplateManager(data_file=target)
    manager.load_from_file()
    assert manager.last_load_error is None
    assert manager.get_design('Historical') is not None
    assert 'capacity' in messages(json.loads(target.read_text())['Historical'])


def test_validation_imports_no_gui_or_game_in_clean_process(tmp_path):
    code = '''import sys
sys.path.insert(0, sys.argv[1])
from unit_template_validation import validate_library
assert validate_library({'Design': {'has_engine': True}}) == {}
assert not any(name.split('.')[0] in {'pygame', 'pygame_gui', 'gui', 'game'} for name in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', code, str(ROOT)], cwd=tmp_path,
                            capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert result.returncode == 0, result.stdout + result.stderr


def test_builtin_validation_mode_allows_builtin_names_and_catches_intra_library_duplicates():
    reserved = next(iter(builtin_template_names()))
    # In custom mode (default), reserved names are rejected.
    custom_issues = validate_library({'t1': record(name=reserved)}, is_builtin=False)
    assert 'reserved' in ' '.join(custom_issues.get('t1', []))

    # In builtin mode, reserved names are accepted.
    builtin_issues = validate_library({'t1': record(name=reserved)}, is_builtin=True)
    assert 'reserved' not in ' '.join(builtin_issues.get('t1', []))

    # In builtin mode, duplicate names within the library are still rejected.
    dup_issues = validate_library({'t1': record(name=reserved), 't2': record(name=reserved)}, is_builtin=True)
    assert 'duplicates' in ' '.join(dup_issues.get('t2', []))


def test_cli_catalogue_builtin_and_options(tmp_path):
    # Running with --catalogue builtin targets data/unit_templates.json
    res_builtin = run_cli(tmp_path, '--catalogue', 'builtin')
    assert 'data' in res_builtin.stdout and 'unit_templates.json' in res_builtin.stdout
    assert res_builtin.returncode == 0
    assert 'template(s) checked' in res_builtin.stdout
    assert '0 invalid; 0 error(s)' in res_builtin.stdout

    # Short flag -c builtin
    res_short = run_cli(tmp_path, '-c', 'builtin')
    assert res_short.returncode == 0
    assert 'data' in res_short.stdout

    # Invalid catalogue choice
    res_invalid = run_cli(tmp_path, '-c', 'unknown')
    assert res_invalid.returncode == 2

    # Providing explicit path with -c builtin
    custom_target = tmp_path / 'custom_unit_templates.json'
    reserved = next(iter(builtin_template_names()))
    custom_target.write_text(json.dumps({'t1': record(name=reserved)}))
    res_explicit = run_cli(tmp_path, '-c', 'builtin', custom_target)
    assert res_explicit.returncode == 1
    assert "category" in res_explicit.stdout  # Built-in mode requires canonical metadata and costs.



@pytest.mark.parametrize('changes,invalid', [
    ({'has_mining_component': True}, True),
    ({'has_sensors': True, 'sensor_long_range_hexes': 1}, True),
    ({'has_scanner': True, 'sensor_long_range_hexes': 1}, True),
    ({'has_sensors': True}, False),
    ({'has_sensors': True, 'sensor_long_range_hexes': 0}, False),
    ({'has_sensors': False, 'sensor_long_range_hexes': 1}, False),
])
def test_wing_equipment_validation_and_cli(tmp_path, changes, invalid):
    data = record(hull_size='STRIKECRAFT_WING', engine_speed=10, **changes)
    direct = template_from_dict('Wing', data).validate()
    assert bool(direct) is invalid
    assert bool(messages(data)) is invalid
    path = tmp_path / 'wings.json'
    payload = json.dumps({'Wing': data})
    path.write_text(payload)
    result = run_cli(tmp_path, path)
    assert result.returncode == (1 if invalid else 0), result.stdout + result.stderr
    assert path.read_text() == payload
    if invalid:
        assert ('has_mining_component' if 'has_mining_component' in changes else 'sensor_long_range_hexes') in result.stdout


@pytest.mark.parametrize('capacity,valid', [(6, True), (7, True), (7.01, False)])
def test_wing_capacity_boundary(capacity, valid):
    from constants import SENSOR_RANGE_PER_HULL_POINT
    comp = ComponentConfig(has_sensors=True, has_antimatter_storage=False,
                           sensor_short_range=capacity * SENSOR_RANGE_PER_HULL_POINT)
    design = CustomUnitTemplate('Wing', HullSize.STRIKECRAFT_WING, comp)
    assert design.hull_capacity == 7
    assert (design.validate() == []) is valid


def test_larger_hull_retains_mining_and_long_range_sensors():
    assert messages(record(hull_size='TINY', engine_speed=0, has_mining_component=True,
                           mining_rate=0, max_mining_cargo=0, has_sensors=True,
                           sensor_short_range=0, sensor_long_range_hexes=1)) == ''
