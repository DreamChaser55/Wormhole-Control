"""Public planning context, journey progress and repeatable setup/lifecycle."""
import copy
import json
import random
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from game_ai.adapters.base import PlanningRequest
from game_ai.memory import AgentMemory
from game_ai.observation import build_observation
from game_ai.prompt_context import planning_context
from game_ai.command_spec import command_catalog
from game_control_protocol import ControlService, PROTOCOL_VERSION, _parse_new_game_settings, ProtocolError
from game_settings import GameSettings, PlayerConfig
from game_setup import prepare_new_campaign
from geometry import Position, Circle
from player_controller import PlayerController
from tests.support.commands import world
from unit_orders.movement import MoveOrder
from unit_components.constructor import instantiate_unit_from_template


def settings(seed=42, profile='normal'):
    return GameSettings(seed=seed, num_systems=2, system_radius_min=3, system_radius_max=3,
        spawn_profile=profile, player_configs=[PlayerConfig('One', (0, 200, 0), PlayerController.CODEX, 1),
                                             PlayerConfig('Two', (200, 0, 0), PlayerController.HUMAN, 2)])


def test_prompt_catalog_prefix_stays_stable_and_price_exceptions_keep_information():
    base = {'name': 'Scout', 'resource_cost': {'credits': 100, 'metal': 5, 'crystal': 2}, 'description': 'Scout role'}
    quotes = [dict(template_name='Scout', resource_cost=base['resource_cost'], replacement_shortfall={'credits': 0}, queued_shortfall={'metal': 0})]
    observation = {'ability_catalog': {'ion_bolt': {'range': 300}}, 'command_catalog': command_catalog(),
        'units': [{'id': i, 'command_options': {'construct': {'template_names': ['Scout'], 'prices': copy.deepcopy(quotes)}}} for i in range(10)],
        'action_catalogs': {'construction_templates': [{**base, 'resource_shortfall': {'credits': 0}}]}}
    observation['units'][1]['command_options']['construct']['prices'][0].update(
        resource_cost={'credits': 150, 'metal': 5, 'crystal': 2}, queued_shortfall={'metal': 3})
    request = PlanningRequest('campaign', 'agent', 'AI', 1, observation, {})
    original = copy.deepcopy(request.to_dict())
    messages, metrics = planning_context(request)
    compact = json.loads(messages[-1]['content'])
    assert compact['observation']['units'][0]['command_options']['construct']['price_exceptions'] == []
    assert compact['observation']['units'][1]['command_options']['construct']['price_exceptions'] == [
        {'template_name': 'Scout', 'resource_cost': {'credits': 150, 'metal': 5, 'crystal': 2}, 'queued_shortfall': {'metal': 3}}]
    assert request.to_dict() == original
    assert metrics['content_input_chars'] < metrics['original_request_chars']
    assert metrics['serialized_input_chars'] < metrics['original_serialized_input_chars']
    changed = copy.deepcopy(observation)
    changed['action_catalogs']['construction_templates'][0]['resource_shortfall']['credits'] = 50
    changed['units'][0]['position'] = [200, 0]
    later, _ = planning_context(PlanningRequest('campaign', 'agent', 'AI', 2, changed, {'lessons': ['Remember']}))
    assert later[0] == messages[0] and later[-1] != messages[-1]
    assert set(metrics['observation_sections_chars']) == set(observation)


def test_required_presence_distinguishes_nullable_slot_clear_and_lessons_accumulate():
    entry = command_catalog()['commands']['set_wing_production']
    assert entry['required_presence'] == ['type', 'unit_ids', 'slot_index', 'template_name']
    assert 'template_name' in entry['nullable_fields'] and 'slot_index' not in entry['nullable_fields']
    memory = AgentMemory(lessons=['Station stances are limited.'])
    memory.apply_patch({'lessons': ['Siege Lance requires local range.', 'Station stances are limited.']}, turn=2)
    memory.apply_patch({'lessons': [], 'objectives': ['Attack with the Titan.']}, turn=3)
    assert memory.lessons == ['Station stances are limited.', 'Siege Lance requires local range.']
    assert memory.objectives == ['Attack with the Titan.']
    memory.apply_patch({'lessons': [str(i) for i in range(16)]}, turn=4)
    assert len(memory.lessons) == 16


def test_journey_progress_advances_without_order_or_rng_mutation():
    game, player, _, unit = world()
    from unit_components.antimatter import AntimatterStorage
    unit.add_component(AntimatterStorage(unit, max_capacity=500))
    order = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
                            'destination_position': Position(800, 0)})
    unit.commander_component.add_order(order)
    before = (random.getstate(), copy.deepcopy(player.order_history), order.public_id, list(order.sub_orders))
    first = next(u for u in build_observation(game, player)['units'] if u['id'] == unit.id)['current_order']['progress']['journey']
    assert first['phase'] == 'approach' and first['remaining_approach_distance'] == 800
    assert first['estimate_conditional'] and first['estimated_remaining_owner_turns'] == 8
    assert before == (random.getstate(), player.order_history, order.public_id, list(order.sub_orders))
    unit.position = Position(400, 0)
    second = next(u for u in build_observation(game, player)['units'] if u['id'] == unit.id)['current_order']['progress']['journey']
    assert second['remaining_approach_distance'] == 400 and second['estimated_remaining_owner_turns'] == 4


def test_fleet_jump_reports_owned_known_origin_blockers_without_hidden_fields():
    game, player, enemy, _ = world()
    titan = instantiate_unit_from_template('TITAN_FLAGSHIP', player, 'Sol', (0, 0), Position(0, 0), game.galaxy, game)
    from tests.support.combat import create_combat_ship
    escort = create_combat_ship(game.galaxy, player, 'Escort', (0, 0), pos=(200, 0))
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.static_inhibition_zones = [Circle(escort.position, 50)]
    view = next(u for u in build_observation(game, player)['units'] if u['id'] == titan.id)
    state = next(a for a in view['ability_states'] if a['ability'] == 'fleet_jump')
    assert not state['ready'] and state['unavailable_reason'] == 'jump_inhibited'
    assert state['origin_blocked_participant_ids'] == [escort.id]
    sector.static_inhibition_zones = []
    hidden = create_combat_ship(game.galaxy, enemy, 'Hidden', (0, 0), pos=(2000, 0))
    from unit_components.cloaking import CloakingDevice
    hidden.add_component(CloakingDevice(hidden))
    hidden.cloaking_component.is_active = True
    sector.dynamic_inhibition_zones[hidden.id] = Circle(Position(0, 0), 500)
    # Keep the emitter outside short-range sensors: an undisclosed field must
    # not change the origin readiness preview or disclose its source identity.
    for ship in sector.units:
        if ship.owner == player:
            ship.sensors_component.short_range_radius = 100
    view = next(u for u in build_observation(game, player)['units'] if u['id'] == titan.id)
    state = next(a for a in view['ability_states'] if a['ability'] == 'fleet_jump')
    assert state['ready'] and state['origin_blocked_participant_ids'] == []
    assert hidden.id not in state['origin_blocked_participant_ids']
    assert hidden.id not in [participant['unit_id'] for participant in state['participants']]


@pytest.mark.parametrize('state', ['egress', 'recharge', 'fuel', 'storage'])
def test_travel_feedback_explains_waits_without_changing_orders_or_briefings(state):
    from unit_components.antimatter import AntimatterStorage
    from game_ai.order_view import public_journey_progress
    from gui.sidebar.order_formatting import generate_order_data_html
    from gui.turn_briefing_window import current_travel_html
    game, player, enemy, unit = world()
    game.current_player_index = 0
    unit.add_component(AntimatterStorage(unit, max_capacity=500))
    remote = state in {'egress', 'recharge'}
    if state == 'egress':
        game.galaxy.systems['Sol'].hexes[(0, 0)].static_inhibition_zones = [Circle(Position(0, 0), 1000)]
    order = MoveOrder(unit, {'destination_system_name': 'Sol',
        'destination_hex_coord': (0, 1) if remote else (0, 0), 'destination_position': Position(800, 0)})
    unit.commander_component.add_order(order)
    if state == 'recharge':
        unit.hyperdrive_component.start_recharge()
    elif state == 'fuel':
        unit.antimatter_component.current_amount = 0
    elif state == 'storage':
        unit.antimatter_component.current_hit_points = 0
    before = (random.getstate(), order.public_id, list(order.sub_orders), copy.deepcopy(player.briefing),
              copy.deepcopy(player.order_history), unit.position, unit.antimatter_component.current_amount)
    journey = public_journey_progress(game, player, unit)
    assert journey['phase'] == {'egress': 'egress', 'recharge': 'recharge',
        'fuel': 'waiting_for_fuel', 'storage': 'blocked'}[state]
    assert journey['estimated_remaining_owner_turns'] > 0
    assert journey['estimated_remaining_antimatter'] > 0
    if state in {'fuel', 'storage'}:
        assert journey['next_step_antimatter'] > 0 and journey['waiting_reason']
    if state == 'recharge':
        assert journey['drive_recharge_owner_turns'] > 0
    for html in (generate_order_data_html(order, galaxy=game.galaxy), current_travel_html(game, player)):
        assert 'Estimated travel remaining: about' in html
        assert {'egress': 'Leaving inhibition field', 'recharge': 'Waiting for drive recharge',
            'fuel': 'Waiting for antimatter', 'storage': 'Antimatter Storage unavailable'}[state] in html
    assert public_journey_progress(game, enemy, unit) is None
    assert before == (random.getstate(), order.public_id, list(order.sub_orders), player.briefing,
                      player.order_history, unit.position, unit.antimatter_component.current_amount)


@pytest.mark.parametrize('profile', ['normal', 'testing'])
def test_seed_repeats_initial_map_and_preserves_caller_random_state(profile):
    config = settings(profile=profile)
    before = random.getstate()
    first = prepare_new_campaign(config).state
    assert random.getstate() == before
    second = prepare_new_campaign(config).state
    def layout(game):
        from campaign_graph import iter_objects
        return [(type(obj).__name__, obj.id, obj.in_system, tuple(obj.in_hex), obj.position.x, obj.position.y)
                for obj, _ in iter_objects(game.galaxy)]
    assert layout(first) == layout(second)
    assert first.invasion_rng.getstate() == second.invasion_rng.getstate()
    assert first.setup_metadata['settings']['seed'] == 42
    assert not first.setup_metadata['pregenerated_map_used']
    assert random.getstate() == before and config.pregenerated_galaxy is None


@pytest.mark.parametrize('seed', [True, -1, 2**32, 1.5, '42'])
def test_setup_rejects_invalid_seed(seed):
    raw = settings().to_setup_dict()
    raw['seed'] = seed
    with pytest.raises(ProtocolError, match='seed'):
        _parse_new_game_settings(raw)


def test_seeded_preparation_failure_restores_rng_and_allocators(monkeypatch):
    from domain.identity import GameObject
    from domain.players import Player
    before = (random.getstate(), GameObject.object_counter, Player.player_counter)
    def fail_home(*args):
        random.random()
        raise RuntimeError('offline injected failure')
    monkeypatch.setattr('game_setup._homeworld', fail_home)
    with pytest.raises(RuntimeError, match='injected'):
        prepare_new_campaign(settings())
    assert before == (random.getstate(), GameObject.object_counter, Player.player_counter)


def test_explicit_save_menu_load_and_exports_round_trip_in_configured_root(tmp_path, monkeypatch):
    import save_manager
    from tests.support.campaigns import campaign, ship
    game = campaign()
    unit = ship(game)
    game.current_player = game.players[0]
    game.current_player.controller = PlayerController.CODEX
    game.setup_metadata = {'settings': settings().to_setup_dict(), 'pregenerated_map_used': False}
    game.ai_coordinator = SimpleNamespace(reset=Mock())
    monkeypatch.setattr(save_manager, 'SAVES_DIR', str(tmp_path))
    game.save_game = Mock(side_effect=lambda filename: save_manager.save_game_to_file(game, filename))
    def menu():
        game.game_started = False
        game.view_mode = 'main_menu'
        game.ai_coordinator.reset()
    game.quit_to_main_menu = Mock(side_effect=menu)
    def load(filename):
        success = save_manager.load_game_from_file(game, filename)
        game.current_player = game.players[game.current_player_index]
        return success
    game.load_game = Mock(side_effect=load)
    service = ControlService(game, port=0)
    def send(action, identifier=None, **fields):
        return service._dispatch_or_wait({'protocol_version': PROTOCOL_VERSION, 'action': action,
            'request_id': identifier or action, **fields}, Future())
    token = send('status')['state']['campaign_token']
    assert send('export_setup')['data']['setup'] == game.setup_metadata
    assert send('export_state')['data']['observation']['units'][0]['id'] == unit.id
    for i, name in enumerate(('../escape.json', 'CON.json', 'a/b.json')):
        assert send('save_game', f'unsafe-{i}', campaign_token=token, save_name=name)['error']['code'] == 'invalid_save_name'
    saved = send('save_game', campaign_token=token, save_name='playtest.json')
    assert saved['ok'] and saved['data']['saved']
    assert send('save_game', campaign_token=token, save_name='playtest.json') == saved
    assert game.save_game.call_count == 1
    assert send('save_game', 'exists', campaign_token=token, save_name='playtest.json')['error']['code'] == 'save_exists'
    assert send('load_game', save_name='playtest.json')['error']['code'] == 'campaign_active'
    assert send('list_saves')['data']['saves'] == [{'save_name': 'playtest.json', 'compatible': True, 'turn_number': 7}]
    assert send('return_to_menu', 'stale-menu', campaign_token='stale')['error']['code'] == 'stale_campaign_token'
    assert game.game_started
    returned = send('return_to_menu', campaign_token=token)
    assert returned['ok'] and not game.game_started
    assert send('return_to_menu', campaign_token=token) == returned and game.quit_to_main_menu.call_count == 1
    loaded = send('load_game', 'load-from-menu', save_name='playtest.json')
    assert loaded['ok'] and game.game_started and game.setup_metadata['settings']['seed'] == 42
    assert send('load_game', 'load-from-menu', save_name='playtest.json') == loaded and game.load_game.call_count == 1
