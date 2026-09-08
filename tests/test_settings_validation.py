"""Shared new-campaign validation across Python, socket and wizard boundaries."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace

import pytest

from game_settings import GameSettings, PlayerConfig, SettingsValidationError
from game_control_protocol import _parse_new_game_settings, ProtocolError
from game_setup import prepare_new_campaign
from gui.layout_new_game_wizard import NewGameWizard


def players():
    return [PlayerConfig('Codex', (1, 2, 3), controller='codex', team_id=1),
            PlayerConfig('Human', (3, 2, 1), team_id=2)]


def wire_players():
    return [{'name': p.name, 'color': p.color, 'controller': p.controller.value,
             'team_id': p.team_id} for p in players()]


@pytest.mark.parametrize('field,value', [
    ('num_systems', 4), ('num_systems', 31), ('num_systems', True),
    ('num_systems', []), ('system_radius_min', 2), ('system_radius_max', 13),
    ('system_radius_max', 5.5), ('system_radius_min', None),
    ('min_system_distance', 0), ('max_system_distance', -1),
    ('wormhole_density', 1.01), ('wormhole_density', float('nan')),
    ('starting_credits', float('inf')), ('starting_metal', -1),
    ('starting_crystal', True), ('starting_credits', 10 ** 1000),
    ('starting_population', 1.5), ('starting_population', -1),
    ('starting_population', False), ('spawn_profile', 'other'),
    ('spawn_profile', {}), ('home_system_assignment_mode', []),
])
def test_python_and_protocol_reject_same_settings(field, value):
    with pytest.raises(SettingsValidationError) as direct:
        GameSettings(player_configs=players(), **{field: value})
    with pytest.raises(ProtocolError) as protocol:
        _parse_new_game_settings({'players': wire_players(), field: value})
    assert direct.value.issues[0].field == field
    assert protocol.value.code == direct.value.issues[0].code
    assert str(protocol.value) == str(direct.value)


@pytest.mark.parametrize('field,value,code', [
    ('name', '', 'invalid_player_name'), ('name', 'a\nb', 'invalid_player_name'),
    ('name', 'x' * 81, 'invalid_player_name'), ('color', [1, 2], 'invalid_color'),
    ('color', [True, 1, 2], 'invalid_color'), ('color', [0, 0, 256], 'invalid_color'),
    ('controller', [], 'invalid_controller'), ('team_id', False, 'invalid_team'),
    ('team_id', 0, 'invalid_team'), ('ai_reasoning_effort', [], 'invalid_reasoning_effort'),
    ('ai_repair_retries', 6, 'invalid_repair_retries'),
    ('ai_repair_retries', True, 'invalid_repair_retries'),
    ('home_system_name', 123, 'invalid_settings'),
])
def test_invalid_player_values_are_not_silently_normalized(field, value, code):
    config = dict(name='AI', color=(0, 1, 2), controller='openai', team_id=2)
    config[field] = value
    with pytest.raises(SettingsValidationError) as direct:
        PlayerConfig(**config)
    with pytest.raises(ProtocolError) as protocol:
        _parse_new_game_settings({'players': [wire_players()[0], config]})
    assert direct.value.issues[0].code == protocol.value.code == code


@pytest.mark.parametrize('count,radius,density', [(5, 3, 0), (30, 12, 1)])
def test_boundaries_defaults_and_normalization(count, radius, density):
    settings = _parse_new_game_settings(dict(players=wire_players(), num_systems=count,
        system_radius_min=radius, system_radius_max=radius, wormhole_density=density,
        starting_credits=0, starting_metal=0, starting_crystal=0, starting_population=0,
        spawn_profile=' TESTING ', home_system_assignment_mode=' SPECIFIED '))
    assert settings.validate() == []
    assert settings.starting_credits == settings.starting_population == 0
    assert settings.spawn_profile.value == 'testing'


def test_duplicate_names_and_mutated_roster_are_revalidated_without_mutation():
    settings = GameSettings(player_configs=players())
    settings.player_configs[1].name = ' codex '
    before = deepcopy(asdict(settings))
    assert settings.validation_issues()[0].code == 'invalid_player_name'
    assert asdict(settings) == before
    settings.player_configs[1].name = 'Human'
    settings.player_configs[1].color = 'bad'
    with pytest.raises(ValueError, match='color'):
        prepare_new_campaign(settings)


def test_preview_mode_is_explicit_and_cannot_bypass_campaign_validation():
    settings = GameSettings(player_configs=[], preview_only=True)
    assert settings.validate(for_preview=True) == []
    assert settings.validation_issues()[0].code == 'invalid_players'
    with pytest.raises(ValueError, match='2-6'):
        prepare_new_campaign(settings)
    with pytest.raises(ValueError, match='num_systems'):
        GameSettings(num_systems=4, player_configs=[], preview_only=True)


def wizard_input():
    # Exercise the real action builder without constructing display widgets.
    wizard = object.__new__(NewGameWizard)
    wizard._snapshot = lambda: None
    wizard._num_players = 2
    wizard._player_names = ['Codex', 'Human']
    wizard._player_color_indices = [0, 1]
    wizard._player_controllers = [p.controller for p in players()]
    wizard._player_ai_reasoning_efforts = ['medium', 'medium']
    wizard._player_teams = [1, 2]
    wizard._home_system_mode = 'random'
    wizard._num_systems, wizard._min_dist, wizard._max_dist = 5, 50, 350
    wizard._wormhole_density = 33
    wizard._sys_radius_min = wizard._sys_radius_max = 12
    wizard._credits_str = wizard._metal_str = wizard._crystal_str = '0'
    wizard._population_str = '0'
    wizard._spawn_profile = 'normal'
    wizard._generated_galaxy = None
    return wizard


@pytest.mark.parametrize('value', ['-1', 'nan', 'inf', 'invalid', ''])
def test_wizard_resource_errors_preserve_input(value):
    wizard = wizard_input()
    wizard._credits_str = value
    with pytest.raises(ValueError, match='finite non-negative'):
        wizard._build_start_action()
    assert wizard._credits_str == value


def test_wizard_zero_resources_are_not_replaced_by_defaults():
    settings = wizard_input()._build_start_action()['settings']
    assert settings.starting_credits == settings.starting_metal == settings.starting_crystal == 0
    assert settings.system_radius_max == 12


@pytest.mark.parametrize('invalid_input', [False, True])
def test_failed_preview_preserves_previous_map_and_allocators(monkeypatch, invalid_input):
    from entities import GameObject
    from persistence_context import allocate_id
    wizard = wizard_input()
    previous = object()
    wizard._generated_galaxy = previous
    wizard._player_home_systems = ['Sol', 'Beta']
    counter = GameObject.object_counter
    calls = []
    def fail_generation(**kwargs):
        calls.append(kwargs)
        allocate_id(GameObject, 'object_counter')
        raise ValueError('Map placement failed')
    monkeypatch.setattr('gui.layout_new_game_wizard.Galaxy', fail_generation)
    if invalid_input:
        wizard._sys_radius_min = 13
    wizard._generate_map()
    assert wizard._generated_galaxy is previous
    assert wizard._player_home_systems == ['Sol', 'Beta']
    assert GameObject.object_counter == counter
    assert wizard._map_generation_error
    assert bool(calls) != invalid_input
