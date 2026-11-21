"""Compact planning preserves disclosed information and reduces real payloads."""
from copy import deepcopy
import json
from dataclasses import replace

import pytest

from game_ai.adapters.base import PlanningRequest, RepairContext
from game_ai.observation import build_observation
from game_ai.prompt_context import planning_context, expand_shared_values
from game_settings import GameSettings, PlayerConfig
from game_setup import prepare_new_campaign
from tests.support.campaigns import campaign, ship
from unit_components.strikecraft import StrikecraftBayComponent


@pytest.mark.parametrize('profile', ['normal', 'testing'])
@pytest.mark.parametrize('seed', [20261031, 20260930, 42])
def test_compact_messages_restore_identical_catalogs_and_tactical_information(profile, seed):
    settings = GameSettings(seed=seed, spawn_profile=profile, num_systems=2,
                            system_radius_min=3, system_radius_max=3,
                            player_configs=[PlayerConfig('One', (0, 100, 0), team_id=1), PlayerConfig('Two', (100, 0, 0), team_id=2)])
    game = prepare_new_campaign(settings).state
    observation = build_observation(game, game.players[0])
    request = PlanningRequest('compact', 'agent', 'One', 1, observation, {})
    before = deepcopy(request.to_dict())
    compact, metrics = planning_context(request)
    full, full_metrics = planning_context(request, compact=False)
    for index in (0, 1):
        packed = json.loads(compact[index]['content'].split('\n', 1)[-1])
        original = json.loads(full[index]['content'].split('\n', 1)[-1])
        assert expand_shared_values(packed) == original
    assert request.to_dict() == before
    assert metrics['content_input_chars'] < full_metrics['content_input_chars'] * 0.95
    assert metrics['shared_value_savings_chars'] > 0
    # Dynamic changes do not invalidate the catalog prefix.
    observation['turn_number'] += 1
    later, _ = planning_context(request)
    assert later[0] == compact[0]


def test_quiet_prompt_trims_only_alternate_quotes_for_healthy_busy_units():
    options = {'colonize': {'target_ids': [10, 11, 12], 'approach_quotes': {
        str(i): {'estimated_owner_turns': i, 'estimated_antimatter': 1.5 * i} for i in (10, 11, 12)}},
        'give_antimatter': {'target_ids': [20], 'approach_quotes': {'20': {'estimated_owner_turns': 2}}}}
    active = {'status': 'in_progress', 'active': True, 'target_id': 10,
              'progress': {'journey': {'estimated_remaining_owner_turns': 6}}}
    units = [
        {'id': 1, 'relation': 'self', 'current_order': active, 'queued_orders': [{'target_id': 11}]},
        {'id': 2, 'relation': 'self', 'current_order': active},
        {'id': 3, 'relation': 'self', 'current_order': None},
    ]
    for unit in units:
        unit['command_options'] = deepcopy(options)
    observation = {'units': units, 'turn_summary': {'from_turn': 6, 'entries': []},
                   'logistics': {'fuel_needs': [{'unit_id': 2}]}}
    request = PlanningRequest('quiet', 'agent', 'One', 7, observation, {})
    baseline, _ = planning_context(request, trim_quiet=False)
    messages, metrics = planning_context(request)
    assert messages[0] == baseline[0]
    assert metrics['quiet_quote_rows_omitted'] == 1
    projected = expand_shared_values(json.loads(messages[-1]['content']))['observation']['units']
    busy, stalled, idle = projected
    assert busy['current_order'] == active
    assert busy['command_options']['colonize']['target_ids'] == [10, 11, 12]
    assert set(busy['command_options']['colonize']['approach_quotes']) == {'10', '11'}
    assert busy['command_options']['give_antimatter'] == options['give_antimatter']
    assert stalled == units[1] and idle == units[2]
    assert units[0]['command_options'] == options
    repaired, _ = planning_context(replace(request, repair_context=RepairContext(None, ())))
    assert expand_shared_values(json.loads(repaired[-1]['content']))['observation']['units'] == units
    observation['undetailed_enemy_presence'] = [{'system_name': 'Sol', 'hex_coord': [1, 0]}]
    _, contacted = planning_context(request)
    assert contacted['quiet_quote_rows_omitted'] == 0


def test_carrier_dismantling_omits_ship_targets_without_constructor_capability():
    game = campaign()
    game.galaxy.game = game
    carrier = ship(game, 'Carrier')
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=2))
    other = ship(game, 'Ship')
    observed = build_observation(game, game.players[0])
    actor = next(actor for actor in observed['units'] if actor['id'] == carrier.id)
    assert 'dismantle_unit' in actor['supported_commands']
    assert 'dismantle_unit' in observed['command_catalog']['commands']
    assert actor['command_options']['dismantle_unit']['targets'] == []
    assert other.id in {actor['id'] for actor in observed['units']}


def test_quiet_prompt_trims_non_committed_dismantle_previews_and_colonist_advice():
    active = {'status': 'in_progress', 'active': True, 'target_id': 10,
              'progress': {'phase': 'building'}}
    busy = {
        'id': 1, 'relation': 'self', 'current_order': active, 'queued_orders': [],
        'command_options': {
            'dismantle_unit': {'targets': [
                {'target_id': 10, 'blocker': None, 'duration': 5},
                {'target_id': 20, 'blocker': None, 'duration': 8, 'members': [{'unit_id': 20}]},
                {'target_id': 21, 'blocker': None, 'duration': 4, 'members': [{'unit_id': 21}]},
            ]},
            'load_colonists': {'targets': [
                {'target_id': 10, 'maximum_amount': 20, 'population_advice': {'recommended_amount': 15}},
                {'target_id': 30, 'maximum_amount': 20, 'population_advice': {'recommended_amount': 10}},
            ]},
        },
    }
    idle = {'id': 2, 'relation': 'self', 'current_order': None, 'command_options': deepcopy(busy['command_options'])}
    observation = {'units': [busy, idle], 'turn_summary': {'from_turn': 5, 'entries': []}, 'logistics': {'fuel_needs': []}}
    request = PlanningRequest('quiet', 'agent', 'One', 6, observation, {})
    messages, metrics = planning_context(request)
    assert metrics['quiet_quote_rows_omitted'] == 3
    projected_busy, projected_idle = expand_shared_values(json.loads(messages[-1]['content']))['observation']['units']
    assert [t['target_id'] for t in projected_busy['command_options']['dismantle_unit']['targets']] == [10]
    assert projected_busy['command_options']['dismantle_unit']['omitted_targets'] == 2
    assert 'population_advice' in projected_busy['command_options']['load_colonists']['targets'][0]
    assert 'population_advice' not in projected_busy['command_options']['load_colonists']['targets'][1]
    assert projected_idle['command_options'] == idle['command_options']
    assert metrics['active_unit_count'] == 2
    assert metrics['visible_unit_count'] == 2
    assert metrics['memory_chars'] == 2
