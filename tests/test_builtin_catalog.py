"""Catalog designs must be affordable quotes for the actual assembled equipment."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from constants import HullSize
from game_ai.contracts import Command
from game_ai.observation import build_observation
from geometry import Position, Vector
from tests.support.campaigns import campaign
from tests.support.commands import issue
from unit_catalog import describe_template, validate_builtin_catalog
from unit_components.constructor import instantiate_unit_from_template
from unit_templates import UNIT_TEMPLATES

ROOT = Path(__file__).resolve().parents[1]
BUILTINS = json.loads((ROOT / 'data/unit_templates.json').read_text(encoding='utf-8'))


def create(game, key, owner=0):
    return instantiate_unit_from_template(key, game.players[owner], 'Sol', (0, 0),
                                          Position(100, 100), game.galaxy, game)


def test_catalog_coverage_and_canonical_values():
    from scripts.generate_reference import component_rows
    from unit_components.enums import AbilityType
    assert len(BUILTINS) == 49
    assert validate_builtin_catalog(BUILTINS) == {}
    assert {a.value for a in AbilityType} == {a for t in BUILTINS.values() for a in t['abilities']}
    assert all(any(t[row['key']] for t in BUILTINS.values()) for row in component_rows())
    corrupt = json.loads(json.dumps(BUILTINS))
    corrupt['MISSILE_PLATFORM']['build_cost'] = 0
    corrupt['SCOUT']['category'] = 'Unknown'
    assert set(validate_builtin_catalog(corrupt)) == {'MISSILE_PLATFORM', 'SCOUT'}


@pytest.mark.parametrize('key', BUILTINS)
def test_runtime_equipment_matches_description(key):
    game = campaign()
    unit = create(game, key)
    entry = describe_template(key, UNIT_TEMPLATES[key])
    assert unit.current_hull_usage == pytest.approx(entry['hull_used'])
    assert unit.current_hull_usage <= unit.hull_capacity + 1e-8
    assert unit.max_hit_points == entry['hit_points']
    assert (unit.antimatter_component.max_capacity if unit.antimatter_component else 0) == entry['fuel_capacity']
    assert unit.sensors_component.short_range_radius == entry['sensors']['short_range']
    if unit.weapons_component:
        for turret, described in zip(unit.weapons_component.turrets, entry['weapons'], strict=True):
            assert (turret.damage, turret.range, turret.cooldown) == (described['damage'], described['range'], described['cooldown'])
            for kind, hull in [('ship', HullSize.SMALL), ('station', HullSize.LARGE), ('wing', HullSize.STRIKECRAFT_WING)]:
                assert unit.weapons_component.turret_accepts_hull(turret, hull) == (kind in described['target_classes'])
    if unit.inhibitor_component:
        assert unit.inhibitor_component.radius == entry['support']['inhibitor']['inhibitor_radius']
        assert unit.inhibitor_component.get_antimatter_cost_per_turn() == entry['support']['inhibitor']['antimatter_cost_per_turn']
    if unit.cloaking_component:
        assert unit.cloaking_component.area_radius == entry['support']['cloaking_device']['cloaking_radius']
        assert unit.cloaking_component.get_antimatter_cost_per_turn() == pytest.approx(entry['support']['cloaking_device']['antimatter_cost_per_turn'])


def test_revised_specialists():
    game = campaign()
    for key, radius, capacity in [('INTERDICTOR', 235, 100), ('INTERDICTION_FORTRESS', 521, 200)]:
        unit = create(game, key)
        assert unit.current_hull_usage == capacity
        assert unit.inhibitor_component.radius == radius
        assert unit.inhibitor_component.get_antimatter_cost_per_turn() > 0
    intel = create(game, 'INTELLIGENCE_SHIP')
    assert intel.current_hull_usage == 75
    assert intel.intelligence_component.agents_capacity == 2
    assert intel.intelligence_component.has_counter_intelligence
    assert intel.cloaking_component is not None


@pytest.mark.parametrize('key', ['FIGHTER_WING', 'BOMBER_WING'])
def test_production_prices_progress_complete_equipment_and_persistence(key):
    from save_manager import serialize_game_state, deserialize_game_state
    game = campaign()
    carrier = create(game, 'FLEET_CARRIER')
    player = carrier.owner
    player.credits = 10000
    bay = carrier.strikecraft_bay_component
    selection = Command('set_wing_production', (carrier.id,), template_name=key)
    assert issue(game, player, selection).accepted
    bay.update(game.galaxy)
    assert player.credits == 10000 - BUILTINS[key]['build_cost']
    assert not issue(game, player, selection).accepted
    bay.update(game.galaxy)
    assert bay.constructing and not bay.docked_units
    restored = campaign()
    deserialize_game_state(restored, serialize_game_state(game))
    saved = restored.galaxy.get_unit_by_id(carrier.id).strikecraft_bay_component
    assert saved.production_template_name == key and saved.construction_progress == 1
    saved.update(restored.galaxy)
    assert not saved.constructing and len(saved.docked_units) == 1
    wing = saved.docked_units[0]
    assert wing.antimatter_component is None
    assert wing.current_hull_usage <= 7
    assert wing.sensors_component.short_range_radius == 300
    assert wing.strikecraft_wing_component.mother_carrier is saved.unit
    assert wing not in restored.galaxy.systems['Sol'].hexes[(0, 0)].units
    assert saved.deploy(wing, restored.galaxy)
    assert wing in restored.galaxy.systems['Sol'].hexes[(0, 0)].units


def test_production_gateway_rejections_are_atomic():
    game = campaign()
    carrier = create(game, 'ESCORT_CARRIER')
    bay = carrier.strikecraft_bay_component
    valid = Command('set_wing_production', (carrier.id,), template_name='BOMBER_WING')
    for invalid in [Command('set_wing_production', (carrier.id,), template_name='SCOUT'),
                    Command('set_wing_production', (carrier.id,), template_name='BOMBER_WING', queue=True)]:
        assert not issue(game, carrier.owner, valid, invalid).accepted
        assert bay.production_template_name == 'FIGHTER_WING'
    assert not issue(game, game.players[1], valid).accepted
    bay.current_hit_points = 0
    assert not issue(game, carrier.owner, valid).accepted


def test_normal_start_builds_economy_escort_and_bomber_carrier():
    from campaign_graph import iter_units
    from game_setup import prepare_new_campaign
    from campaign_persistence import commit_campaign
    from tests.support.scenarios import settings_for
    from tactical_abilities import start_owner_turn
    from strikecraft_abilities import wing_order
    game = campaign()
    commit_campaign(game, prepare_new_campaign(settings_for(game.galaxy)))
    player = game.players[0]
    builder = next(u for u, _ in iter_units(game.galaxy) if u.owner is player and u.constructor_component)
    constructed = {}
    for key in ('CIVILIAN_HABITAT', 'MINING_SHIP_SMALL', 'METAL_REFINERY_STATION',
                'CRYSTAL_REFINERY_STATION', 'KINETIC_FRIGATE', 'FLEET_CARRIER'):
        before = {u.id for u, _ in iter_units(game.galaxy)}
        position = (builder.position.x + 100, builder.position.y)
        credits = player.credits
        result = issue(game, player, Command('construct', (builder.id,), template_name=key, position=position))
        assert result.accepted, result.errors
        assert player.credits == credits - BUILTINS[key]['build_cost']
        for _ in range(BUILTINS[key]['build_time']):
            builder.constructor_component.update(game.galaxy)
        constructed[key] = next(u for u, _ in iter_units(game.galaxy) if u.id not in before)
        builder.commander_component.update()
    carrier = constructed['FLEET_CARRIER']
    bay = carrier.strikecraft_bay_component
    assert issue(game, player, Command('set_wing_production', (carrier.id,), template_name='BOMBER_WING')).accepted
    for _ in range(1 + BUILTINS['BOMBER_WING']['build_time']):
        bay.update(game.galaxy)
    bomber = bay.docked_units[0]
    assert issue(game, player, Command('deploy_all_wings', (carrier.id,))).accepted
    assert bomber in bay.launched_units
    enemy = instantiate_unit_from_template('PATROL_CUTTER', game.players[1], carrier.in_system, carrier.in_hex,
        Position(bomber.position.x + 100, bomber.position.y), game.galaxy, game)
    attack = Command('use_ability', (carrier.id,), ability='attack_run', target_id=enemy.id)
    result = issue(game, player, attack)
    assert result.accepted, result.errors
    assert wing_order(bomber)
    health = enemy.current_hit_points
    game.turn_number += 1
    start_owner_turn(game.galaxy, player, game.turn_number)
    bomber.weapons_component.update(game.galaxy)
    assert enemy.current_hit_points < health
    assert issue(game, player, Command('use_ability', (carrier.id,), ability='emergency_recovery', target_id=bomber.id)).accepted


def test_general_intelligence_performs_both_roles():
    game = campaign()
    friendly = create(game, 'INTELLIGENCE_SHIP')
    hostile = create(game, 'INTELLIGENCE_SHIP', owner=1)
    friendly.owner.credits = 1000
    assert issue(game, friendly.owner, Command('infiltrate_unit', (friendly.id,), target_id=hostile.id)).accepted
    agent = hostile.infiltrating_agents[0]
    assert issue(game, friendly.owner, Command('sabotage', agent_id=agent.id, sabotage_type='engines')).accepted
    assert hostile.engines_component.effective_speed < hostile.engines_component.speed
    assert issue(game, hostile.owner, Command('infiltrate_unit', (hostile.id,), target_id=friendly.id)).accepted
    hostile_agent = friendly.infiltrating_agents[0]
    assert issue(game, friendly.owner, Command('ci_sweep', (friendly.id,))).accepted
    assert hostile_agent.is_discovered
    assert issue(game, friendly.owner, Command('eliminate_agent', (friendly.id,), agent_id=hostile_agent.id)).accepted
    assert hostile_agent not in friendly.infiltrating_agents


def test_observation_catalog_deduplicates_builders_and_exposes_bomber_choices():
    game = campaign()
    create(game, 'SHIPYARD_MK1')
    create(game, 'CONSTRUCTOR_MK1')
    create(game, 'FLEET_CARRIER')
    observation = build_observation(game, game.players[0])
    catalog = observation['action_catalogs']
    assert len(catalog['construction_templates']) == 47
    assert len(catalog['wing_templates']) == 2
    assert all(e['description'] and e['roles'] and 'support' in e for e in catalog['construction_templates'])
    assert observation['command_catalog']['version'] == 5


def test_catalog_window_filters_build_dispatch_and_stale_context(pygame_context):
    import pygame
    import pygame_gui
    from gui.unit_catalog_window import UnitCatalogWindow, catalog_entries
    from gui.theme_loader import build_ui_manager
    game = campaign()
    builder = create(game, 'CONSTRUCTOR_MK1')
    builder.owner.credits = 10000
    events = []
    game.event_bus = SimpleNamespace(publish=events.append)
    manager = build_ui_manager(Vector(1280, 720))
    gui = SimpleNamespace(game_instance=game, screen_res=Vector(1280, 720), manager=manager)
    window = UnitCatalogWindow(gui, [builder], Position(200, 200))
    try:
        assert [e['template_name'] for e in catalog_entries(UNIT_TEMPLATES, search='counter-intelligence')] == ['INTELLIGENCE_SHIP']
        assert all(e['credit_cost'] <= 1000 for e in catalog_entries(UNIT_TEMPLATES, affordable=True, credits=1000))
        window.show_entry(describe_template('BOMBER_WING', UNIT_TEMPLATES['BOMBER_WING']))
        assert not window.build_button.is_enabled
        window.show_entry(describe_template('SCOUT', UNIT_TEMPLATES['SCOUT']))
        window.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=window.build_button))
        assert len(events) == 1
        assert events[0].shift_pressed is False
        assert not window.window.alive()
        window = UnitCatalogWindow(gui, [builder], Position(200, 200))
        game.current_player_index = 1
        window.update()
        assert not window.window.alive()
    finally:
        window.kill()
        manager.clear_and_reset()


def test_catalog_consumes_game_hotkeys_and_camera_panning(pygame_context, monkeypatch):
    import pygame
    from unittest.mock import Mock
    from input_processor.processor import InputProcessor
    from gui.unit_catalog_window import UnitCatalogWindow
    from gui.theme_loader import build_ui_manager
    game = campaign()
    builder = create(game, 'CONSTRUCTOR_MK1')
    manager = build_ui_manager(Vector(1280, 720))
    gui = SimpleNamespace(game_instance=game, screen_res=Vector(1280, 720), manager=manager)
    window = UnitCatalogWindow(gui, [builder], Position(200, 200))
    gui.unit_catalog_window = window
    gui.process_event = lambda event: {'action': 'ui_handled'} if window.process_event(event) else None
    game.gui = gui
    game.handle_gui_action = Mock()
    processor = InputProcessor(game)
    processor.update_hover_states = Mock()
    hotkey = Mock()
    monkeypatch.setattr('input_processor.processor.handle_key_down', hotkey)
    key_state = Mock(side_effect=AssertionError('Camera polling must be blocked by the catalog'))
    monkeypatch.setattr(pygame.key, 'get_pressed', key_state)
    monkeypatch.setattr(pygame.event, 'get', lambda: [
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)])
    try:
        processor.handle_input()
        hotkey.assert_not_called()
        key_state.assert_not_called()
        assert not window.window.alive()
    finally:
        window.kill()
        manager.clear_and_reset()


@pytest.fixture
def construction_catalog(pygame_context):
    from events import EventBus, ConstructEvent
    from order_system import OrderSystem
    from gui.unit_catalog_window import UnitCatalogWindow
    from gui.theme_loader import build_ui_manager
    game = campaign()
    game.event_bus = EventBus()
    OrderSystem(game, game.event_bus)
    builders = [create(game, 'CONSTRUCTOR_MK1') for _ in range(2)]
    game.players[0].credits = 100000
    manager = build_ui_manager(Vector(1280, 720))
    game.gui = SimpleNamespace(game_instance=game, screen_res=Vector(1280, 720),
                               manager=manager)
    window = UnitCatalogWindow(game.gui, builders, Position(200, 200))
    events = []
    game.event_bus.subscribe(ConstructEvent, events.append)
    yield game, builders, window, events
    window.kill()
    manager.clear_and_reset()


def press_catalog(window, button):
    import pygame
    import pygame_gui
    window.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=button))


def test_catalog_repeated_queue_and_build_replacement(construction_catalog):
    game, builders, window, events = construction_catalog
    keys = ['SCOUT', 'FLEET_CARRIER', 'FLEET_CARRIER', 'MINELAYER']
    for key in keys:
        window.show_entry(describe_template(key, UNIT_TEMPLATES[key]))
        press_catalog(window, window.queue_button)
        assert window.window.alive()
        assert window.selected_key == key
    for builder in builders:
        commander = builder.commander_component
        orders = [commander.current_order, *commander.orders_queue]
        assert [o.parameters['unit_template_name'] for o in orders] == keys
        assert all(o.parameters['target_position'] == Position(200, 200) for o in orders)
    assert all(event.shift_pressed for event in events)
    assert game.players[0].credits == 100000 - 2 * UNIT_TEMPLATES['SCOUT']['build_cost']
    assert '2 builders' in window.price_label.text
    window.show_entry(describe_template('MINELAYER', UNIT_TEMPLATES['MINELAYER']))
    press_catalog(window, window.build_button)
    assert not window.window.alive()
    assert events[-1].shift_pressed is False
    for builder in builders:
        assert builder.commander_component.current_order.parameters['unit_template_name'] == 'MINELAYER'
        assert not builder.commander_component.orders_queue


def test_catalog_queue_preserves_browsing_and_updates_affordability(construction_catalog):
    game, builders, window, events = construction_catalog
    key = 'FLEET_CARRIER'
    window.search.set_text('carrier')
    window.refresh()
    window.show_entry(describe_template(key, UNIT_TEMPLATES[key]))
    window.gui.manager.update(.1)
    window.details.scroll_bar.set_scroll_from_start_percentage(.2)
    detail_scroll = window.details.scroll_bar.start_percentage
    selection = window.list.get_single_selection()
    game.players[0].credits = UNIT_TEMPLATES[key]['build_cost'] * len(builders)
    press_catalog(window, window.queue_button)
    window.gui.manager.update(.1)
    assert game.players[0].credits == 0
    assert not window.build_button.is_enabled
    assert window.queue_button.is_enabled
    assert window.search.get_text() == 'carrier'
    assert window.list.get_single_selection() == selection
    assert window.details.scroll_bar.start_percentage == pytest.approx(detail_scroll)
    press_catalog(window, window.build_button)
    assert len(events) == 1
    press_catalog(window, window.queue_button)
    assert len(events) == 2
    assert window.window.alive()
    assert all(len(b.commander_component.orders_queue) == 1 for b in builders)


def test_catalog_refresh_preserves_list_scroll_and_clears_filtered_selection(construction_catalog):
    game, builders, window, events = construction_catalog
    window.show_entry(describe_template('FLEET_CARRIER', UNIT_TEMPLATES['FLEET_CARRIER']))
    window.list.scroll_bar.set_scroll_from_start_percentage(.4)
    window.gui.manager.update(.1)
    scroll = window.list.scroll_bar.start_percentage
    game.players[0].credits -= 1
    window.update()
    assert window.list.scroll_bar.start_percentage == pytest.approx(scroll)
    assert window.list.get_single_selection() == 'Fleet Carrier (6998c)'
    # A changed list must also retain the highlight and viewport where possible.
    window.affordability.selected_option = 'Affordable'
    game.players[0].credits = 7500
    window.update()
    assert window.list.scroll_bar.start_percentage == pytest.approx(scroll)
    assert window.list.get_single_selection() == 'Fleet Carrier (6998c)'
    game.players[0].credits = 2 * UNIT_TEMPLATES['SCOUT']['build_cost']
    window.show_entry(describe_template('SCOUT', UNIT_TEMPLATES['SCOUT']))
    press_catalog(window, window.queue_button)
    assert window.window.alive()
    assert window.selected_key is None
    assert window.list.get_single_selection() is None
    assert not window.build_button.is_enabled and not window.queue_button.is_enabled


def test_catalog_disabled_and_stale_actions(construction_catalog):
    game, builders, window, events = construction_catalog
    for key in (None, 'BOMBER_WING'):
        window.show_entry(describe_template(key, UNIT_TEMPLATES[key]) if key else None)
        for button in (window.build_button, window.queue_button):
            assert not button.is_enabled
            press_catalog(window, button)
    assert not events
    window.show_entry(describe_template('SCOUT', UNIT_TEMPLATES['SCOUT']))
    builders[0].owner = game.players[1]
    press_catalog(window, window.queue_button)
    assert not events and not window.window.alive()


@pytest.mark.parametrize('shift', [False, True])
def test_catalog_opening_shift_does_not_change_build(construction_catalog, monkeypatch, shift):
    from input_processor.context_actions import handle_context_menu_action
    game, builders, window, events = construction_catalog
    window.kill()
    game.selected_objects = builders
    monkeypatch.setattr('input_processor.context_actions._get_shift_pressed', lambda: shift)
    handle_context_menu_action(game, 'open_unit_catalog', Position(200, 200))
    opened = game.gui.unit_catalog_window
    try:
        opened.show_entry(describe_template('SCOUT', UNIT_TEMPLATES['SCOUT']))
        press_catalog(opened, opened.build_button)
        assert not opened.window.alive()
        assert len(events) == 1 and events[0].shift_pressed is False
    finally:
        opened.kill()
