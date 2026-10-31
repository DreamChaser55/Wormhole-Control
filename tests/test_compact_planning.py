"""Compact planning preserves disclosed information and reduces real payloads."""
from copy import deepcopy
import json

import pytest

from game_ai.adapters.base import PlanningRequest
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
