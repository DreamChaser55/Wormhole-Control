"""Catalogue visibility follows successful campaign transitions, not UI previews."""
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from campaign_graph import find_unit, iter_units
from campaign_persistence import commit_campaign, prepare_campaign
from constants import HullSize
from custom_unit_templates import CustomTemplateManager, CustomUnitTemplate
from game_settings import SpawnProfile
from game_setup import prepare_new_campaign, start_new_game
from geometry import Position
from save_manager import deserialize_game_state, serialize_game_state
from tests.support.campaigns import campaign, legacy_document, ship
from tests.support.scenarios import settings_for
from unit_components.constructor import Constructor, instantiate_unit_from_template
from unit_orders.base import OrderStatus
from unit_orders.construction import ConstructOrder
from player_controller import PlayerController
from unit_templates import (
    PRIVATE_TEMPLATES, TESTING_TEMPLATE_KEYS, UNIT_TEMPLATES, load_testing_templates,
    publish_testing_templates,
)


def test_catalogue_files_are_disjoint_and_import_starts_normal(tmp_path):
    root = Path(__file__).resolve().parents[1]
    normal = json.loads((root / 'data/unit_templates.json').read_text(encoding='utf-8'))
    testing = json.loads((root / 'data/test_unit_templates.json').read_text(encoding='utf-8'))
    assert set(testing) == TESTING_TEMPLATE_KEYS and len(testing) == 11
    assert not normal.keys() & testing.keys()
    assert {'FIGHTER_WING', 'BOMBER_WING'} <= normal.keys()
    code = ('import sys; sys.path.insert(0, sys.argv[1]); '
            'from unit_templates import UNIT_TEMPLATES, TESTING_TEMPLATE_KEYS; '
            'assert not UNIT_TEMPLATES.keys() & TESTING_TEMPLATE_KEYS')
    subprocess.run([sys.executable, '-c', code, str(root)], cwd=tmp_path, check=True)
    assert all(isinstance(t['hull_size'], HullSize) for t in load_testing_templates().values())


def test_prepare_and_commit_profile_transitions_preserve_custom_designs():
    game = campaign()
    manager = CustomTemplateManager()
    design = CustomUnitTemplate('Persistent Custom', HullSize.MEDIUM)
    design.components.has_engine = True
    assert manager.save_design(design) == []
    assert 'Persistent Custom' not in UNIT_TEMPLATES
    custom = PRIVATE_TEMPLATES['Persistent Custom']
    registry = UNIT_TEMPLATES
    for profile, count in [(SpawnProfile.NORMAL, 4), (SpawnProfile.TESTING, 11),
                           (SpawnProfile.TESTING, 11), (SpawnProfile.NORMAL, 4)]:
        before = dict(registry)
        settings = settings_for(campaign().galaxy, profile)
        prepared = prepare_new_campaign(settings)
        assert registry == before
        commit_campaign(game, prepared)
        assert registry is UNIT_TEMPLATES
        assert 'Persistent Custom' not in registry
        assert PRIVATE_TEMPLATES['Persistent Custom'] is custom
        expected = TESTING_TEMPLATE_KEYS if profile == SpawnProfile.TESTING else set()
        assert registry.keys() & TESTING_TEMPLATE_KEYS == expected
        for player in game.players:
            assert sum(unit.owner is player for unit, _ in iter_units(game.galaxy)) == count
        builder = next(unit for unit, _ in iter_units(game.galaxy) if unit.constructor_component)
        buildables = {entry.unit_template_name for entry in builder.constructor_component.buildable_units}
        assert buildables & TESTING_TEMPLATE_KEYS == expected
        assert 'Persistent Custom' in buildables


@pytest.mark.parametrize('ai_controller', [PlayerController.OPENAI, PlayerController.CODEX])
def test_ai_players_cannot_access_or_build_private_templates(ai_controller):
    game = campaign()
    manager = CustomTemplateManager()
    design = CustomUnitTemplate('Private Frigate', HullSize.MEDIUM)
    design.components.has_engine = True
    assert manager.save_design(design) == []
    assert 'Private Frigate' in PRIVATE_TEMPLATES
    assert 'Private Frigate' not in UNIT_TEMPLATES

    human_player = game.players[0]
    human_player.controller = PlayerController.HUMAN
    ai_player = game.players[1]
    ai_player.controller = ai_controller

    human_builder = ship(game, 'human_builder', owner=0)
    human_builder.add_component(Constructor(human_builder))
    ai_builder = ship(game, 'ai_builder', owner=1)
    ai_builder.add_component(Constructor(ai_builder))

    # Human constructor sees both built-in and private templates
    human_buildables = {e.unit_template_name for e in human_builder.constructor_component.buildable_units}
    assert 'Private Frigate' in human_buildables
    assert 'CONSTRUCTOR_MK1' in human_buildables
    assert human_builder.constructor_component.can_build('Private Frigate') is not None

    # AI constructor sees ONLY built-in templates
    ai_buildables = {e.unit_template_name for e in ai_builder.constructor_component.buildable_units}
    assert 'Private Frigate' not in ai_buildables
    assert 'CONSTRUCTOR_MK1' in ai_buildables
    assert ai_builder.constructor_component.can_build('Private Frigate') is None
    assert ai_builder.constructor_component.can_build('CONSTRUCTOR_MK1') is not None

    # instantiate_unit_from_template allows human to instantiate private template
    human_unit = instantiate_unit_from_template(
        'Private Frigate', human_player, 'Sol', (0, 0), Position(0, 0), game.galaxy, game
    )
    assert human_unit is not None

    # instantiate_unit_from_template forbids AI from instantiating private template
    ai_unit = instantiate_unit_from_template(
        'Private Frigate', ai_player, 'Sol', (0, 0), Position(0, 0), game.galaxy, game
    )
    assert ai_unit is None


@pytest.mark.parametrize('active_testing', [False, True])
def test_failed_setup_and_load_preserve_catalogue(active_testing, monkeypatch):
    game = campaign()
    publish_testing_templates(load_testing_templates() if active_testing else {})
    before, galaxy = dict(UNIT_TEMPLATES), game.galaxy
    settings = settings_for(campaign().galaxy, SpawnProfile.TESTING)
    monkeypatch.setattr('game_setup.spawn_units', lambda *args, **kwargs: None)
    assert not start_new_game(game, settings)
    assert UNIT_TEMPLATES == before and game.galaxy is galaxy
    assert not deserialize_game_state(game, {})
    assert UNIT_TEMPLATES == before and game.galaxy is galaxy


def test_missing_testing_file_rejects_testing_only(monkeypatch):
    import unit_templates
    load = unit_templates._load_templates

    def missing(filename='unit_templates.json'):
        if filename == 'test_unit_templates.json':
            raise FileNotFoundError(filename)
        return load(filename)

    monkeypatch.setattr(unit_templates, '_load_templates', missing)
    before = dict(UNIT_TEMPLATES)
    prepare_new_campaign(settings_for(campaign().galaxy))
    with pytest.raises(FileNotFoundError):
        prepare_new_campaign(settings_for(campaign().galaxy, SpawnProfile.TESTING))
    assert UNIT_TEMPLATES == before


@pytest.mark.parametrize('use_display_name', [False, True])
def test_inactive_testing_names_are_reserved(tmp_path, use_display_name):
    testing = load_testing_templates()
    key = 'SPAWN_SHIP_TINY'
    name = testing[key]['name'] if use_display_name else key
    assert not UNIT_TEMPLATES.keys() & TESTING_TEMPLATE_KEYS
    manager = CustomTemplateManager(data_file=tmp_path / 'custom.json')
    design = CustomUnitTemplate(name.swapcase(), HullSize.MEDIUM)
    design.components.has_engine = True
    assert any('already exists' in error for error in manager.save_design(design))
    assert not manager.data_file.exists()
    manager.data_file.write_text(json.dumps({name: {'name': name, 'hull_size': 'MEDIUM'}}))
    manager.load_from_file()
    assert manager.last_load_error is not None
    assert not UNIT_TEMPLATES.keys() & TESTING_TEMPLATE_KEYS


def test_quit_to_menu_clears_testing_but_wizard_cancel_does_not():
    from game import Game
    from game_actions.app_actions import handle_cancel_new_game_wizard
    game = campaign()
    game.gui, game.ai_coordinator = Mock(), Mock()
    publish_testing_templates(load_testing_templates())
    before = dict(UNIT_TEMPLATES)
    handle_cancel_new_game_wizard(game, {})
    assert UNIT_TEMPLATES == before
    Game.quit_to_main_menu(game)
    assert not UNIT_TEMPLATES.keys() & TESTING_TEMPLATE_KEYS
    assert 'CONSTRUCTOR_MK1' in UNIT_TEMPLATES


@pytest.mark.parametrize('active_testing', [False, True])
def test_loading_testing_ship_keeps_components_and_uses_normal_catalogue(active_testing):
    game = campaign()
    instantiate_unit_from_template('SPAWN_SHIP_TINY', game.players[0], 'Sol', (0, 0),
                                   Position(100, 0), game.galaxy, game,
                                   templates=load_testing_templates())
    saved = serialize_game_state(game)
    publish_testing_templates(load_testing_templates() if active_testing else {})
    assert deserialize_game_state(game, saved)
    assert not UNIT_TEMPLATES.keys() & TESTING_TEMPLATE_KEYS
    restored = serialize_game_state(game)['galaxy']['systems'][0]['hexes'][0]['units'][0]
    original = saved['galaxy']['systems'][0]['hexes'][0]['units'][0]
    assert restored['components'] == original['components']
    assert restored['hull_size'] == original['hull_size']


def _testing_build():
    game = campaign()
    builder = ship(game, 'builder')
    builder.add_component(Constructor(builder))
    game.players[0].credits = 10000
    publish_testing_templates(load_testing_templates())
    order = ConstructOrder(builder, {'unit_template_name': 'SPAWN_SHIP_TINY',
                                     'target_position': Position(400, 0)})
    builder.commander_component.add_order(order)
    assert order.status == OrderStatus.IN_PROGRESS
    queued = ConstructOrder(builder, {'unit_template_name': 'SPAWN_SHIP_SMALL',
                                      'target_position': Position(400, 0)})
    builder.commander_component.add_order(queued)
    return game, builder, order, queued


def test_load_cancels_paid_testing_build_without_promoting_queue():
    game, builder, order, queued = _testing_build()
    # Payment belongs to the original payer, even after ownership changes.
    builder.owner = game.players[1]
    saved = serialize_game_state(game)
    before = dict(UNIT_TEMPLATES)
    prepared = prepare_campaign(saved)
    assert UNIT_TEMPLATES == before
    assert game.players[0].credits < 10000
    restored = find_unit(prepared.state.galaxy, builder.id)
    assert restored.constructor_component.current_construction_target is None
    assert restored.commander_component.current_order is None
    assert [o.public_id for o in restored.commander_component.orders_queue] == [queued.public_id]
    assert prepared.state.players[0].credits == 10000
    assert prepared.state.players[1].credits == game.players[1].credits
    assert any('Cancelled unavailable Testing construction' in w for w in prepared.warnings)
    commit_campaign(game, prepared)
    assert not UNIT_TEMPLATES.keys() & TESTING_TEMPLATE_KEYS
    # Saving and loading the settled job cannot refund it a second time.
    assert deserialize_game_state(game, serialize_game_state(game))
    assert game.players[0].credits == 10000
    restored = find_unit(game.galaxy, builder.id)
    queued_order = restored.commander_component.orders_queue[0]
    restored.commander_component.start_next_order()
    assert queued_order.status == OrderStatus.FAILED
    assert restored.constructor_component.current_construction_target is None


@pytest.mark.parametrize('recorded_charge', [False, True])
def test_unrecorded_or_orphaned_build_never_invents_refund(recorded_charge):
    game, builder, order, _ = _testing_build()
    saved = serialize_game_state(game)
    raw = saved['galaxy']['systems'][0]['hexes'][0]['units'][0]
    commander = raw['components']['Commander']['runtime']
    if recorded_charge:
        commander['current_order'] = None  # Orphaned actuator has no owning charge.
    else:
        runtime = commander['current_order']['runtime_state']
        runtime.pop('charged_credits')
        runtime.pop('charged_player_id')
    credits = game.players[0].credits
    assert deserialize_game_state(game, saved)
    assert game.players[0].credits == credits
    assert find_unit(game.galaxy, builder.id).constructor_component.current_construction_target is None


def test_legacy_testing_ship_migration_does_not_register_templates():
    data = legacy_document('3.2')
    raw = data['galaxy']['systems'][0]['hexes'][0]['units'][0]
    raw['template_name'] = 'SPAWN_SHIP_TINY'
    raw['components']['Weapons'] = {}
    game = campaign()
    assert not UNIT_TEMPLATES.keys() & TESTING_TEMPLATE_KEYS
    assert deserialize_game_state(game, data)
    assert find_unit(game.galaxy, 10).weapons_component.turrets
    assert not UNIT_TEMPLATES.keys() & TESTING_TEMPLATE_KEYS


def test_failure_after_candidate_refund_preserves_live_payment_and_catalogue(monkeypatch):
    import campaign_persistence
    game, builder, _, _ = _testing_build()
    saved = serialize_game_state(game)
    before = dict(UNIT_TEMPLATES)
    settle = campaign_persistence._cancel_testing_construction

    def fail_after_refund(candidate, warnings):
        settle(candidate, warnings)
        assert candidate.players[0].credits == 10000
        raise ValueError('Injected failure after isolated refund')

    monkeypatch.setattr(campaign_persistence, '_cancel_testing_construction', fail_after_refund)
    assert not deserialize_game_state(game, saved)
    after = serialize_game_state(game)
    assert {k: v for k, v in after.items() if k != 'timestamp'} == {
        k: v for k, v in saved.items() if k != 'timestamp'}
    assert UNIT_TEMPLATES == before
    assert builder.constructor_component.current_construction_target is not None
