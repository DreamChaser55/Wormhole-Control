"""Catalogue-driven bays share validated production across UI, AI and saves."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from constants import HullSize
from construction_customization import TURRET_TYPES, DEFENSE_TYPES
from display_config import DisplayConfig
from game_ai.contracts import Command
from game_ai.observation import build_observation
from geometry import Position, Vector
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign
from tests.support.commands import issue
from unit_catalog import describe_template, wing_template_names
from unit_components.constructor import instantiate_unit_from_template
from unit_components.defenses import Defenses
from unit_templates import UNIT_TEMPLATES, PRIVATE_TEMPLATES


WINGS = ('FIGHTER_WING', 'BOMBER_WING', 'INTERCEPTOR_WING', 'LONG_RANGE_BOMBER_WING')


def create(game, key, owner=0):
    return instantiate_unit_from_template(key, game.players[owner], 'Sol', (0, 0),
                                          Position(100, 100), game.galaxy, game)


def world():
    game = campaign()
    carrier = create(game, 'FLEET_CARRIER')
    carrier.owner.credits = 10000
    return game, carrier, carrier.strikecraft_bay_component


def command(carrier, key='INTERCEPTOR_WING', **overrides):
    return Command('set_wing_production', (carrier.id,), template_name=key, **overrides)


def produce(game, bay):
    for _ in range(bay.production_template['build_time'] + 1):
        bay.update(game.galaxy)
    return bay.docked_units[-1]


@pytest.mark.parametrize('key', WINGS)
@pytest.mark.parametrize('turret', [None, *TURRET_TYPES])
@pytest.mark.parametrize('defense', [None, *DEFENSE_TYPES])
def test_complete_override_matrix_preserves_budgets_and_templates(key, turret, defense):
    game, carrier, bay = world()
    original = deepcopy(UNIT_TEMPLATES)
    template = UNIT_TEMPLATES[key]
    expected = describe_template(key, template)
    before = carrier.owner.credits
    assert issue(game, carrier.owner, command(carrier, key, turret_type_override=turret,
                                             defense_type_override=defense)).accepted
    assert carrier.owner.credits == before
    wing = produce(game, bay)
    assert carrier.owner.credits == before - template['build_cost']
    assert wing.current_hull_usage == pytest.approx(expected['hull_used'])
    assert wing.current_hull_usage <= 7
    assert wing.strikecraft_wing_component.wing_type.name == template['wing_type']
    assert wing.strikecraft_wing_component.mother_carrier is carrier
    assert wing.max_hit_points == 30 and wing.antimatter_component is None
    for actual, preset in zip(wing.weapons_component.turrets, expected['weapons']):
        assert actual.turret_type.value == (turret or preset['type'].lower())
        assert actual.variant.name == preset['variant']
        assert (actual.damage, actual.range, actual.cooldown) == (preset['damage'], preset['range'], preset['cooldown'])
    for field in DEFENSE_TYPES:
        strength = sum(expected['defenses'].values()) if field == defense else 0 if defense else expected['defenses'][field]
        assert getattr(wing.get_component(Defenses), field) == pytest.approx(strength)
    assert wing.get_component(Defenses).hull_cost == template['defenses_hull_cost']
    assert wing.weapons_component.hull_cost == template['weapon_bays_hull_cost']
    assert UNIT_TEMPLATES == original


def test_dynamic_discovery_excludes_private_and_constructor_designs(monkeypatch):
    game, carrier, bay = world()
    extra = deepcopy(UNIT_TEMPLATES['INTERCEPTOR_WING'])
    extra['name'] = 'Additional Fighter Wing'
    monkeypatch.setitem(UNIT_TEMPLATES, 'EXTRA_WING', extra)
    monkeypatch.setitem(PRIVATE_TEMPLATES, 'PRIVATE_WING', extra)
    assert 'EXTRA_WING' in wing_template_names() and 'PRIVATE_WING' not in wing_template_names()
    builder = create(game, 'CONSTRUCTOR_MK1')
    assert all(builder.constructor_component.can_build(key) is None for key in [*WINGS, 'EXTRA_WING'])
    observation = build_observation(game, carrier.owner)
    entries = {t['template_name']: t for t in observation['action_catalogs']['wing_templates']}
    assert set(entries) == {*WINGS, 'EXTRA_WING'}
    assert entries['EXTRA_WING']['wing_type'] == 'FIGHTER'
    view = next(u for u in observation['units'] if u['id'] == carrier.id)
    assert set(view['command_options']['set_wing_production']['template_names']) == set(entries)
    assert view['command_options']['set_wing_production']['turret_type_override'] == [None, *TURRET_TYPES]
    assert issue(game, carrier.owner, command(carrier, 'EXTRA_WING')).accepted
    assert produce(game, bay).name == extra['name']
    assert not issue(game, carrier.owner, command(carrier, 'PRIVATE_WING')).accepted


def test_selection_replaces_configuration_without_charges_or_existing_wing_changes():
    game, carrier, bay = world()
    assert issue(game, carrier.owner, Command('move', (carrier.id,), system_name='Sol',
                                             hex_coord=(0, 0), position=(500, 500))).accepted
    root = carrier.commander_component.current_order
    assert issue(game, carrier.owner, command(carrier, turret_type_override='missile', defense_type_override='armor')).accepted
    first = produce(game, bay)
    second = produce(game, bay)
    assert first.weapons_component.turrets[0].turret_type.value == second.weapons_component.turrets[0].turret_type.value == 'missile'
    from save_manager import serialize_unit
    before = serialize_unit(first)
    carrier.owner.credits = 0
    bay.max_slots = len(bay.docked_units)
    result = issue(game, carrier.owner, command(carrier, 'BOMBER_WING', turret_type_override='beam'),
                   command(carrier, 'LONG_RANGE_BOMBER_WING', defense_type_override='point_defense'))
    assert result.accepted and result.applied_count == 2
    assert bay.production_template_name == 'LONG_RANGE_BOMBER_WING'
    assert bay.turret_type_override is None and bay.defense_type_override == 'point_defense'
    assert carrier.owner.credits == 0
    bay.update(game.galaxy)
    assert not bay.constructing
    after = serialize_unit(first)
    assert before == after
    assert issue(game, carrier.owner, command(carrier)).accepted
    assert bay.turret_type_override is None and bay.defense_type_override is None
    assert carrier.commander_component.current_order is root


@pytest.mark.parametrize('changes', [
    {'template_name': 'SCOUT'}, {'template_name': 'MISSING'}, {'template_name': None},
    {'queue': True}, {'turret_type_override': 'BEAM'}, {'defense_type_override': 'shield'},
    {'turret_type_override': True}, {'defense_type_override': []},
])
def test_invalid_selection_rejects_entire_batch_without_mutation(changes):
    game, carrier, bay = world()
    before = bay.to_state(), carrier.owner.credits
    valid = command(carrier, turret_type_override='beam')
    invalid = replace(command(carrier), **changes)
    assert not issue(game, carrier.owner, valid, invalid).accepted
    assert (bay.to_state(), carrier.owner.credits) == before


def test_busy_destroyed_foreign_grouped_and_missing_equipment_rejections(monkeypatch):
    game, carrier, bay = world()
    other = create(game, 'ESCORT_CARRIER')
    assert not issue(game, carrier.owner, replace(command(carrier), unit_ids=(carrier.id, other.id))).accepted
    assert not issue(game, game.players[1], command(carrier)).accepted
    bay.current_hit_points = 0
    assert not issue(game, carrier.owner, command(carrier)).accepted
    bay.current_hit_points = bay.max_hit_points
    bay.update(game.galaxy)
    before = bay.to_state(), carrier.owner.credits
    assert not issue(game, carrier.owner, command(carrier)).accepted
    assert (bay.to_state(), carrier.owner.credits) == before
    bay.update(game.galaxy)
    bay.update(game.galaxy)
    for fields, override in [({'has_weapon_bays': False, 'turrets': []}, {'turret_type_override': 'beam'}),
                             ({'armor': 0, 'shields': 0, 'point_defense': 0}, {'defense_type_override': 'armor'})]:
        raw = deepcopy(UNIT_TEMPLATES['FIGHTER_WING'])
        raw.update(fields)
        monkeypatch.setitem(UNIT_TEMPLATES, 'BARE_WING', raw)
        before = bay.to_state()
        assert not issue(game, carrier.owner, command(carrier, 'BARE_WING', **override)).accepted
        assert bay.to_state() == before


def test_failed_commit_is_not_reported_as_success(monkeypatch):
    game, carrier, bay = world()
    monkeypatch.setattr(bay, 'set_production', lambda *args: False)
    result = issue(game, carrier.owner, command(carrier))
    assert not result.accepted and result.failure_stage == 'commit' and result.applied_count == 0


@pytest.mark.parametrize('key', WINGS)
def test_every_design_retains_role_docking_and_magnetic_storm_rules(key):
    from constants import StormType
    from domain.celestials import Storm
    game, carrier, bay = world()
    assert bay.set_production(key)
    wing = produce(game, bay)
    fighter = UNIT_TEMPLATES[key]['wing_type'] == 'FIGHTER'
    turret = wing.weapons_component.turrets[0]
    assert wing.weapons_component.turret_accepts_hull(turret, HullSize.STRIKECRAFT_WING) == fighter
    assert wing.weapons_component.turret_accepts_hull(turret, HullSize.SMALL) != fighter
    storm = Storm(in_system='Sol', in_hex=(0, 0), storm_type=StormType.MAGNETIC)
    storm.position = carrier.position
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.celestial_bodies.append(storm)
    assert not bay.can_deploy(wing, game.galaxy)
    assert not issue(game, carrier.owner, Command('deploy_all_wings', (carrier.id,))).accepted
    sector.celestial_bodies.remove(storm)
    assert bay.deploy(wing, game.galaxy)
    assert bay.dock(wing, game.galaxy)
    assert wing in bay.docked_units and wing not in bay.launched_units


def test_runtime_rechecks_template_before_charging_or_assembling(monkeypatch):
    game, carrier, bay = world()
    assert bay.set_production('INTERCEPTOR_WING', 'beam', 'armor')
    raw = deepcopy(UNIT_TEMPLATES['INTERCEPTOR_WING'])
    raw.update(has_weapon_bays=False, turrets=[])
    with monkeypatch.context() as patch:
        patch.setitem(UNIT_TEMPLATES, 'INTERCEPTOR_WING', raw)
        credits = carrier.owner.credits
        with pytest.raises(ValueError, match='installed turrets'):
            bay.update(game.galaxy)
        assert carrier.owner.credits == credits and not bay.constructing
    bay.update(game.galaxy)
    monkeypatch.setitem(UNIT_TEMPLATES, 'INTERCEPTOR_WING', raw)
    with pytest.raises(ValueError, match='installed turrets'):
        bay.finish_auto_construction(game.galaxy)
    assert not bay.docked_units


@pytest.mark.parametrize('phase', ['idle', 'constructing', 'replenishing', 'completed'])
def test_production_and_fractional_equipment_roundtrip(phase):
    game, carrier, bay = world()
    assert issue(game, carrier.owner, command(carrier, 'LONG_RANGE_BOMBER_WING',
                                             turret_type_override='beam', defense_type_override='armor')).accepted
    if phase == 'constructing':
        bay.update(game.galaxy)
        bay.update(game.galaxy)
    elif phase in ('replenishing', 'completed'):
        wing = produce(game, bay)
        if phase == 'replenishing':
            wing.current_hit_points -= 10
            bay.update(game.galaxy)
            assert bay.replenishing_unit is wing
            assert issue(game, carrier.owner, command(carrier, 'INTERCEPTOR_WING')).accepted
    before = bay.to_state(), carrier.owner.credits
    restored = campaign()
    assert deserialize_game_state(restored, serialize_game_state(game))
    saved = restored.galaxy.get_unit_by_id(carrier.id).strikecraft_bay_component
    assert (saved.to_state(), saved.unit.owner.credits) == before
    if phase == 'constructing':
        saved.update(restored.galaxy)
        assert len(saved.docked_units) == 1 and saved.unit.owner.credits == before[1]
    if saved.docked_units:
        wing = saved.docked_units[0]
        turret = wing.weapons_component.turrets[0]
        assert turret.range == 292.5 and turret.cooldown == 9
        assert wing.get_component(Defenses).armor == 0.3
        if phase == 'replenishing':
            saved.update(restored.galaxy)
            assert wing.current_hit_points == wing.max_hit_points
            assert wing.get_component(Defenses).armor == 0.3 and turret.turret_type.value == 'beam'
            assert saved.unit.owner.credits == before[1]


@pytest.mark.parametrize('field,value', [
    ('production_template_name', 'SCOUT'), ('production_template_name', 'PRIVATE_WING'),
    ('turret_type_override', 'laser'), ('defense_type_override', 1.5),
    ('construction_progress', 99),
])
def test_corrupt_production_save_is_transactionally_rejected(field, value):
    game, carrier, bay = world()
    data = serialize_game_state(game)
    for system in data['galaxy']['systems']:
        for sector in system['hexes']:
            for unit in sector['units']:
                for component in unit['components'].values():
                    if component['type'] == 'StrikecraftBayComponent':
                        component['runtime'][field] = value
    before = bay.to_state(), carrier.owner.credits, game.galaxy
    assert not deserialize_game_state(game, data)
    assert (bay.to_state(), carrier.owner.credits, game.galaxy) == before


def test_observations_show_selections_to_owner_and_allies_only():
    game, carrier, bay = world()
    other = create(game, 'SCOUT', owner=1)
    assert issue(game, carrier.owner, command(carrier, turret_type_override='missile', defense_type_override='armor')).accepted
    def view(player):
        return next(u for u in build_observation(game, player)['units'] if u['id'] == carrier.id)
    own = view(carrier.owner)['capability_details']['strikecraft_bay']
    assert own['production_template'] == 'INTERCEPTOR_WING'
    assert own['turret_type_override'] == 'missile' and own['defense_type_override'] == 'armor'
    assert 'strikecraft_bay' not in view(other.owner)['capability_details']
    other.owner.team_id = carrier.owner.team_id
    assert view(other.owner)['capability_details']['strikecraft_bay'] == own


@pytest.fixture(params=[(1280, 720), (1920, 1080)])
def picker(pygame_context, request):
    from gui.theme_loader import build_ui_manager
    from gui.wing_production_window import WingProductionWindow
    from gui.event_router import process_event
    game, carrier, bay = world()
    width, height = request.param
    config = DisplayConfig(width, height)
    manager = build_ui_manager(config)
    gui = SimpleNamespace(game_instance=game, screen_res=Vector(width, height), manager=manager,
                          display_config=config)
    game.gui = gui
    gui.wing_production_window = window = WingProductionWindow(gui, carrier)
    gui.process_event = lambda event: process_event(gui, event)
    yield game, carrier, bay, window
    window.close()
    manager.clear_and_reset()


def test_picker_preselects_and_applies_presets_without_affordability_gate(picker):
    import pygame
    import pygame_gui
    game, carrier, bay, window = picker
    assert window.selected_key == 'FIGHTER_WING' and set(window.entries) == set(WINGS)
    assert any(item['selected'] for item in window.list.item_list)
    assert window.list.list_item_height == max(20, int(30 * game.gui.display_config.text_scale))
    carrier.owner.credits = 0
    assert bay.set_production('FIGHTER_WING', 'beam', 'armor')
    label = next(label for label, key in window.labels.items() if key == 'LONG_RANGE_BOMBER_WING')
    window.process_event(pygame.event.Event(pygame_gui.UI_SELECTION_LIST_NEW_SELECTION, ui_element=window.list, text=label))
    assert window.select_button.is_enabled
    assert '292.5' in window._details_html and '0.3' in window._details_html
    window.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=window.select_button))
    assert not window.window.alive() and bay.production_template_name == 'LONG_RANGE_BOMBER_WING'
    assert bay.turret_type_override is None and bay.defense_type_override is None
    assert carrier.owner.credits == 0


@pytest.mark.parametrize('reason', ['cancel', 'escape', 'close', 'turn', 'owner', 'destroyed', 'busy', 'campaign'])
def test_picker_cancellation_and_stale_context_preserve_selection(picker, reason):
    import pygame
    import pygame_gui
    game, carrier, bay, window = picker
    window.selected_key = 'INTERCEPTOR_WING'
    if reason == 'cancel':
        window.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=window.cancel_button))
    elif reason == 'escape':
        window.process_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    elif reason == 'close':
        window.process_event(pygame.event.Event(pygame_gui.UI_WINDOW_CLOSE, ui_element=window.window))
    else:
        if reason == 'turn': game.turn_number += 1
        elif reason == 'owner': carrier.owner = game.players[1]
        elif reason == 'destroyed': bay.current_hit_points = 0
        elif reason == 'busy': bay.constructing = True
        elif reason == 'campaign': game.galaxy = campaign().galaxy
        window.update()
    assert not window.window.alive() and bay.production_template_name == 'FIGHTER_WING'


def test_picker_blocks_hotkeys_camera_and_events_after_close(picker, monkeypatch):
    import pygame
    from input_processor.processor import InputProcessor
    from game_camera import camera_input_blocked
    game, _, _, window = picker
    assert camera_input_blocked(game, game.gui)
    processor = InputProcessor(game)
    processor.update_hover_states = Mock()
    game.handle_gui_action = Mock()
    hotkey = Mock()
    monkeypatch.setattr('input_processor.processor.handle_key_down', hotkey)
    key_state = Mock(side_effect=AssertionError('Picker must block camera polling'))
    monkeypatch.setattr(pygame.key, 'get_pressed', key_state)
    monkeypatch.setattr(pygame.event, 'get', lambda: [
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e)])
    processor.handle_input()
    hotkey.assert_not_called()
    key_state.assert_not_called()
    assert not window.window.alive()
