"""Income previews and turn settlement must agree without preview side effects."""
from dataclasses import FrozenInstanceError
import random
from types import SimpleNamespace

import pytest

from constants import PlanetType
from domain.celestials import Planet, Moon, ColonizableAsteroid
from domain.players import Player
from economy import IncomeBreakdown, calculate_income_breakdown, calculate_player_income
from save_manager import serialize_game_state
from tests.support.campaigns import campaign, ship
from turn_processor import TurnProcessor
from unit_components.civilian_habitat import CivilianHabitatComponent
from unit_components.enums import SabotageType
from unit_components.intelligence import Agent


def add_colony(game, owner, kind=Planet, population=80):
    body = kind((0, 0), 'Sol', PlanetType.TERRAN) if kind is Planet else kind((0, 0), 'Sol')
    body.owner, body.population = owner, population
    game.galaxy.systems['Sol'].add_celestial_body(body)
    return body


def spy(body, player):
    agent = Agent(player, source_unit_id=0, target_type='CELESTIAL_BODY', target_id=body.id)
    agent.active_sabotage = SabotageType.ECONOMY
    body.infiltrating_agents.append(agent)
    return agent


def assert_settlement(game, player, expected):
    before = serialize_game_state(game)
    before.pop('timestamp')
    rng_before = random.getstate()
    assert calculate_income_breakdown(game.galaxy, player) == expected
    assert calculate_player_income(game.galaxy, player) == pytest.approx(expected.total_credits)
    after = serialize_game_state(game)
    after.pop('timestamp')
    assert after == before
    assert random.getstate() == rng_before
    resources = (player.credits, player.metal, player.crystal)
    TurnProcessor(game)._process_resource_generation(player)
    assert (player.credits - resources[0], player.metal - resources[1], player.crystal - resources[2]) == pytest.approx(
        (expected.total_credits, expected.metal, expected.crystal))


@pytest.mark.parametrize('kind', [Planet, Moon, ColonizableAsteroid])
@pytest.mark.parametrize('sabotaged', [False, True])
def test_colony_income_and_passive_resources(kind, sabotaged):
    game = campaign()
    owner, enemy = game.players
    body = add_colony(game, owner, kind, population=20)
    if kind is Planet:
        body.passive_metal, body.passive_crystal = 5.5, 2.25
    if sabotaged:
        spy(body, enemy)
    expected = IncomeBreakdown(colony_credits=1 if sabotaged else 2,
                               metal=5.5 if kind is Planet else 0,
                               crystal=2.25 if kind is Planet else 0)
    assert_settlement(game, owner, expected)


@pytest.mark.parametrize('relationship', ['enemy', 'ally', 'unowned'])
def test_siphoning_requires_hostility_and_does_not_stack_agents(relationship):
    game = campaign()
    viewer, host = game.players
    if relationship == 'ally':
        host.team_id = viewer.team_id
    body = add_colony(game, None if relationship == 'unowned' else host)
    spy(body, viewer)
    spy(body, viewer)
    other_spy = Player('Other infiltrator', (1, 2, 3))
    spy(body, other_spy)
    expected = IncomeBreakdown(siphoned_credits=2 if relationship == 'enemy' else 0)
    assert_settlement(game, viewer, expected)


@pytest.mark.parametrize('state,expected_habitats', [
    ('active', 100), ('capacity', 50), ('destroyed', 50), ('offline', 50),
])
def test_habitat_eligibility_and_capacity(state, expected_habitats):
    game = campaign()
    owner = game.players[0]
    body = add_colony(game, owner, population=25 if state == 'capacity' else 50)
    units = [ship(game, 'Habitat one'), ship(game, 'Habitat two')]
    for unit in units:
        unit.add_component(CivilianHabitatComponent(unit))
    if state == 'destroyed':
        units[0].civilian_habitat_component.current_hit_points = 0
    elif state == 'offline':
        units[0]._dismantle_job = SimpleNamespace(phase='working', settled=False)
    assert_settlement(game, owner, IncomeBreakdown(
        colony_credits=body.population * 0.1, habitat_credits=expected_habitats))


def test_empty_income_and_immutable_result():
    game = campaign()
    player = game.players[0]
    assert calculate_income_breakdown(None, player) == IncomeBreakdown()
    assert calculate_player_income(None, player) == 0
    assert_settlement(game, player, IncomeBreakdown())
    with pytest.raises(FrozenInstanceError):
        calculate_income_breakdown(game.galaxy, player).metal = 5
