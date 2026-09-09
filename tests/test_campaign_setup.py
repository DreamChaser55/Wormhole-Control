

import random
from unittest.mock import Mock
import pytest
from constants import PlanetType
from domain.celestials import Planet
from domain.players import Player
from domain.identity import GameObject
from game_settings import GameSettings, PlayerConfig, SpawnProfile
from game_setup import prepare_new_campaign, start_new_game
from unit_orders.base import Order
from tests.support.campaigns import campaign
from tests.support.scenarios import settings_for


@pytest.mark.parametrize('kind', list(PlanetType))
def test_homeworld_selection_and_caps(kind):
    game = campaign()
    for name, system in game.galaxy.systems.items():
        system.add_celestial_body(Planet((0, 0), name, kind))
    settings = settings_for(game.galaxy)
    settings.starting_population = 1000
    prepared = prepare_new_campaign(settings)
    for player in prepared.state.players:
        world = prepared.state.galaxy.get_celestial_body_by_id(player.homeworld_id)
        assert world.is_colonizable and world.planet_type != PlanetType.GAS_GIANT
        assert world.population == world.max_population
        assert world.planet_type == (PlanetType.TERRAN if kind == PlanetType.GAS_GIANT else kind)
    assert all(body.owner is None for system in game.galaxy.systems.values() for _, body in system.get_all_celestial_bodies())


def test_population_clamp_precedes_sabotage(atmosphere, monkeypatch):
    game, _, _ = atmosphere
    world = Planet((1, 0), 'Sol', PlanetType.GREENHOUSE)
    world.owner, world.population = game.players[0], 50
    monkeypatch.setattr(world, 'is_sabotaged', lambda kind: True)
    world.update_population()
    assert world.population == 35


def test_start_validation_rechecks_mutable_settings_and_preserves_campaign(monkeypatch):
    game = campaign()
    game.gui, game.ai_coordinator = Mock(), Mock()
    settings = settings_for(game.galaxy)
    snapshot = dict(vars(game))
    counters = GameObject.object_counter, Player.player_counter, Order.order_counter
    settings.player_configs[1].home_system_name = 'Sol'
    assert not start_new_game(game, settings)
    assert 'distinct' in game.last_setup_error
    assert {key: value for key, value in vars(game).items() if key != 'last_setup_error'} == snapshot
    assert (GameObject.object_counter, Player.player_counter, Order.order_counter) == counters
    game.ai_coordinator.reset.assert_not_called()
    game.gui.show_game_ui.assert_not_called()
    settings.player_configs[1].home_system_name = 'Beta'
    monkeypatch.setattr('game_setup.spawn_units', lambda *args, **kwargs: None)
    assert not start_new_game(game, settings)
    assert (GameObject.object_counter, Player.player_counter, Order.order_counter) == counters
    assert not any(body.owner for system in game.galaxy.systems.values() for _, body in system.get_all_celestial_bodies())


def test_normal_count_and_negative_population_rejected():
    configs = [PlayerConfig(str(i), (10, 20, 30), team_id=i+1) for i in range(6)]
    with pytest.raises(ValueError, match='distinct'):
        GameSettings(num_systems=5, player_configs=configs)
    with pytest.raises(ValueError, match='non-negative'):
        GameSettings(starting_population=-1)


def test_testing_allows_shared_systems_and_normal_mixed_starts():
    from galaxy import Hex
    game = campaign()
    game.galaxy.systems['Sol'].hexes[(0, 1)] = Hex(0, 1, 'Sol')
    settings = settings_for(game.galaxy, SpawnProfile.TESTING)
    settings.player_configs[1].home_system_name = 'Sol'
    prepared = prepare_new_campaign(settings)
    assert {home[0] for home in prepared.state.player_homeworlds.values()} == {'Sol'}
    settings = settings_for(game.galaxy)
    settings.player_configs[1].home_system_name = None
    prepared = prepare_new_campaign(settings)
    assert len({home[0] for home in prepared.state.player_homeworlds.values()}) == 2


def test_setup_rejects_shortfall_missing_system_and_no_homeworld_space(monkeypatch):
    game = campaign()
    settings = settings_for(game.galaxy)
    settings.num_systems = 6
    with pytest.raises(ValueError, match='contains 5'):
        prepare_new_campaign(settings)
    settings.num_systems = 5
    settings.player_configs[1].home_system_name = 'Missing'
    with pytest.raises(ValueError, match='does not exist'):
        prepare_new_campaign(settings)
    settings.player_configs[1].home_system_name = 'Beta'
    for name, system in game.galaxy.systems.items():
        for coord in system.hexes:
            system.add_celestial_body(Planet(coord, name, PlanetType.GAS_GIANT))
    with pytest.raises(ValueError, match='No valid homeworld'):
        prepare_new_campaign(settings)


def test_generation_shortfall_is_an_error(monkeypatch):
    from galaxy import Galaxy
    monkeypatch.setattr(random, 'randint', lambda a, b: a)
    with pytest.raises(ValueError, match='Could place only 1 of 2'):
        Galaxy(num_systems=2)


def test_setup_presentation_failure_does_not_reject_commit():
    game = campaign()
    settings = settings_for(game.galaxy)
    preview = game.galaxy
    game.gui, game.ai_coordinator = Mock(), Mock()
    game.gui.show_game_ui.side_effect = RuntimeError('broken presentation')
    game.check_and_schedule_ai_turn = Mock()
    assert start_new_game(game, settings)
    assert game.galaxy is not preview and game.last_setup_error is None
    game.ai_coordinator.reset.assert_called_once()
    game.check_and_schedule_ai_turn.assert_called_once()
    settings.player_configs[0].home_system_name = 'Changed later'
    assert game.settings.player_configs[0].home_system_name == 'Sol'


def test_wizard_stays_open_when_preparation_fails():
    from game_actions.app_actions import handle_start_new_game_with_settings
    game = campaign()
    game.gui = Mock()
    game.start_new_game = lambda settings: start_new_game(game, settings)
    settings = settings_for(game.galaxy)
    settings.starting_population = -1
    handle_start_new_game_with_settings(game, {'settings': settings})
    game.gui.close_new_game_wizard.assert_not_called()
    game.gui.show_warning_dialog.assert_called_once()


def test_control_protocol_uses_normal_topology_validation():
    from game_control_protocol import _parse_new_game_settings, ProtocolError
    players = [{'name': str(i), 'controller': 'codex' if i == 0 else 'human', 'team_id': i+1} for i in range(6)]
    with pytest.raises(ProtocolError, match='distinct'):
        _parse_new_game_settings({'num_systems': 5, 'players': players})
    players = players[:2]
    for player in players:
        player['home_system_name'] = 'Sol'
    with pytest.raises(ProtocolError, match='distinct'):
        _parse_new_game_settings({'num_systems': 5, 'players': players})
