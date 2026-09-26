"""Alpha accepts one save schema and one canonical design vocabulary."""
from copy import deepcopy
import json
import random

import pytest

from campaign_persistence import prepare_campaign
from custom_unit_templates import (
    ComponentConfig, CustomTemplateManager, CustomUnitTemplate,
    TemplatePersistenceError, template_from_dict,
)
from constants import HullSize
from domain.identity import GameObject
from display_config import DisplayConfig, display_config_for
from save_manager import (
    CURRENT_SAVE_VERSION, _decode_order_value, deserialize_game_state,
    serialize_game_state,
)
from tests.support.campaigns import campaign, ship
from unit_orders.base import Order
from unit_orders.movement import MoveOrder
from unit_templates import PRIVATE_TEMPLATES
from unit_template_validation import validate_library


@pytest.mark.parametrize('version', [None, '3.0', '3.1', '3.2', '4.0', '4.1', '4.2', '4.3', '4.4', '4.5', '4.10', '4.14', '4.15', '4.16', '9.0', 'unknown', 4.4])
def test_unsupported_versions_reject_before_hydration(monkeypatch, version):
    import save_manager
    game = campaign()
    ship(game)
    data = serialize_game_state(game)
    if version is None:
        data.pop('version')
    else:
        data['version'] = version
    original = deepcopy(data)
    objects = dict(vars(game))
    counters = GameObject.object_counter, Order.order_counter
    rng = random.getstate()
    def forbidden(*args):
        pytest.fail('An unsupported save reached hydration')
    monkeypatch.setattr(save_manager, 'deserialize_player', forbidden)
    errors = []
    assert not deserialize_game_state(game, data, on_error=errors.append)
    assert f'expected {CURRENT_SAVE_VERSION}' in errors[0]
    assert data == original
    assert all(vars(game)[key] is value for key, value in objects.items())
    assert (GameObject.object_counter, Order.order_counter) == counters
    assert random.getstate() == rng


@pytest.mark.parametrize('field', ['public_id', 'charged_credits', 'charged_player_id', 'schema_version', 'density'])
def test_missing_current_fields_are_not_reconstructed(field):
    from domain.celestials import AsteroidField
    game = campaign()
    unit = ship(game)
    body = AsteroidField((0, 0), 'Sol')
    game.galaxy.systems['Sol'].add_celestial_body(body)
    order = MoveOrder(unit, {'destination_system_name': unit.in_system, 'destination_hex_coord': unit.in_hex, 'destination_position': unit.position})
    unit.commander_component.orders_queue.append(order)
    data = serialize_game_state(game)
    sector = data['galaxy']['systems'][0]['hexes'][0]
    raw_unit = sector['units'][0]
    raw_order = raw_unit['components']['Commander']['runtime']['orders_queue'][0]
    target = (raw_order if field == 'public_id' else raw_unit if field == 'schema_version'
              else sector['celestial_bodies'][0] if field == 'density' else raw_order['runtime_state'])
    target.pop(field)
    before = serialize_game_state(game)
    assert not deserialize_game_state(game, data)
    after = serialize_game_state(game)
    before.pop("timestamp")
    after.pop("timestamp")
    assert after == before


def test_current_storage_schema_and_empty_current_slot_round_trip():
    game = campaign()
    unit = ship(game)
    queued = MoveOrder(unit, {'destination_system_name': unit.in_system, 'destination_hex_coord': unit.in_hex, 'destination_position': unit.position})
    unit.commander_component.orders_queue.append(queued)
    data = serialize_game_state(game)
    storage = data['galaxy']['systems'][0]['hexes'][0]['units'][0]['components']['AntimatterStorage']
    assert data['version'] == '4.18'
    assert storage['schema_version'] == 2
    assert storage['configuration'] == {'max_capacity': unit.antimatter_component.max_capacity}
    restored = prepare_campaign(data).state.galaxy.get_unit_by_id(unit.id)
    assert restored.commander_component.current_order is None
    assert restored.commander_component.orders_queue[0].public_id == queued.public_id
    assert not hasattr(restored.antimatter_component, 'regen_rate')


def test_order_codec_does_not_infer_untagged_coordinates_or_enum_names():
    assert _decode_order_value({'destination_position': [1, 2]}) == {'destination_position': [1, 2]}
    with pytest.raises(ValueError):
        _decode_order_value({'__type__': 'enum', 'enum': 'UnitStance', 'value': 'UnitStance.DO_NOTHING'})
    with pytest.raises(TypeError):
        ship(campaign()).commander_component.set_stance('do_nothing')


@pytest.mark.parametrize('field,value', [
    ('has_scanner', True), ('has_fighter_bay', True), ('fighter_bay_slots', 2),
    ('counter_intelligence', True), ('unknown_component', True),
])
def test_obsolete_and_unknown_template_fields_reject_every_entry_point(tmp_path, field, value):
    raw = {'name': 'Old', 'has_engine': True, field: value}
    assert field in ' '.join(validate_library({'Old': raw})['Old'])
    with pytest.raises(ValueError, match=field):
        template_from_dict('Old', raw)
    path = tmp_path / 'library.json'
    path.write_text(json.dumps({'Old': raw}))
    manager = CustomTemplateManager(path)
    manager.load_from_file()
    assert field in str(manager.last_load_error)
    assert manager.designs == {}


@pytest.mark.parametrize('invalid', [
    '{"Old": {}, "Old": {}}',
    '{"Invalid": {"has_engine": true, "engine_speed": 10000}}',
    '{"Invalid": {"has_engine": "yes"}}',
])
def test_library_failure_is_atomic_and_recoverable(tmp_path, invalid):
    path = tmp_path / 'library.json'
    manager = CustomTemplateManager(path)
    design = CustomUnitTemplate('Valid', HullSize.MEDIUM, ComponentConfig(has_engine=True))
    assert manager.save_design(design) == []
    valid = path.read_bytes()
    before = dict(manager.designs), deepcopy(PRIVATE_TEMPLATES)
    path.write_text(invalid)
    manager.load_from_file()
    assert manager.last_load_error is not None
    assert manager.designs == before[0] and PRIVATE_TEMPLATES == before[1]
    assert path.read_text() == invalid
    with pytest.raises(TemplatePersistenceError):
        manager.save_to_file()
    with pytest.raises(TemplatePersistenceError):
        manager.delete_design('Valid')
    path.write_bytes(valid)
    manager.load_from_file()
    assert manager.last_load_error is None
    assert manager.delete_design('Valid')


def test_display_requires_an_explicit_configuration():
    from types import SimpleNamespace
    from geometry import Position
    config = DisplayConfig(1920, 1080)
    assert display_config_for(SimpleNamespace(display_config=config)) is config
    for adapter in (SimpleNamespace(), SimpleNamespace(screen_res=Position(1920, 1080))):
        with pytest.raises(AttributeError):
            display_config_for(adapter)


@pytest.mark.parametrize('encoding', ['component_schema', 'regen_rate', 'stance', 'order_enum'])
def test_obsolete_saved_encodings_reject_without_committing(encoding):
    game = campaign()
    unit = ship(game)
    unit.commander_component.orders_queue.append(MoveOrder(unit, {'destination_system_name': unit.in_system, 'destination_hex_coord': unit.in_hex, 'destination_position': unit.position}))
    data = serialize_game_state(game)
    components = data['galaxy']['systems'][0]['hexes'][0]['units'][0]['components']
    if encoding == 'component_schema':
        components['AntimatterStorage']['schema_version'] = 1
    elif encoding == 'regen_rate':
        components['AntimatterStorage']['configuration']['regen_rate'] = 1
    elif encoding == 'stance':
        components['Commander']['configuration']['stance'] = 'UnitStance.DO_NOTHING'
    else:
        order = components['Commander']['runtime']['orders_queue'][0]
        order['parameters']['stance'] = {'__type__': 'enum', 'enum': 'UnitStance', 'value': 'DO_NOTHING'}
    before = game.galaxy, game.players, GameObject.object_counter, Order.order_counter, random.getstate()
    assert not deserialize_game_state(game, data)
    assert game.galaxy is before[0] and game.players is before[1]
    assert (GameObject.object_counter, Order.order_counter, random.getstate()) == before[2:]
