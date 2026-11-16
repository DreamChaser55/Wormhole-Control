"""Income previews and turn settlement must agree without preview side effects."""
from dataclasses import FrozenInstanceError
import random
from types import SimpleNamespace

import pytest

from constants import DEFAULT_CIVILIAN_HABITAT_BONUS, TAX_RATE, PlanetType
from domain.celestials import Planet, Moon, ColonizableAsteroid
from domain.players import Player
from economy import IncomeBreakdown, calculate_income_breakdown, calculate_player_income
from save_manager import deserialize_game_state, serialize_game_state
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
    expected = IncomeBreakdown(colony_credits=20 * TAX_RATE * (0.5 if sabotaged else 1),
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
    expected = IncomeBreakdown(siphoned_credits=80 * TAX_RATE * 0.25 if relationship == 'enemy' else 0)
    assert_settlement(game, viewer, expected)


@pytest.mark.parametrize('state,expected_habitats', [
    ('active', 2), ('capacity', 1), ('destroyed', 1), ('offline', 1),
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
        colony_credits=body.population * TAX_RATE,
        habitat_credits=expected_habitats * DEFAULT_CIVILIAN_HABITAT_BONUS))


def test_empty_income_and_immutable_result():
    game = campaign()
    player = game.players[0]
    assert calculate_income_breakdown(None, player) == IncomeBreakdown()
    assert calculate_player_income(None, player) == 0
    assert_settlement(game, player, IncomeBreakdown())
    with pytest.raises(FrozenInstanceError):
        calculate_income_breakdown(game.galaxy, player).metal = 5


def test_observation_itemizes_only_the_players_own_economy():
    from game_ai.observation import build_observation

    game = campaign()
    owner, enemy = game.players
    colony = add_colony(game, owner)
    add_colony(game, enemy)
    vessel = ship(game, 'Depot')
    vessel.add_component(CivilianHabitatComponent(vessel))
    ship(game, 'Enemy vessel', owner=1)
    resources = build_observation(game, owner)['active_player']['resources']
    assert [entry['body_id'] for entry in resources['income_breakdown']['colonies']] == [colony.id]
    assert [entry['unit_id'] for entry in resources['upkeep_breakdown']] == [vessel.id]
    assert resources['income'] == pytest.approx(calculate_player_income(game.galaxy, owner))


@pytest.mark.parametrize('load_save', [False, True], ids=['new', 'loaded'])
def test_barren_and_ferrous_passive_metal_income(load_save):
    from game_ai.observation import build_observation
    from gui.sidebar.panels_world import build_celestial_body_panel

    game = campaign()
    owner, enemy = game.players
    starting_metal = 37.5
    owner.metal = starting_metal
    barren = Planet((0, 0), 'Sol', PlanetType.BARREN)
    ferrous = Planet((1, 0), 'Sol', PlanetType.FERROUS)
    enemy_ferrous = Planet((0, 0), 'Beta', PlanetType.FERROUS)
    unowned_ferrous = Planet((1, 0), 'Beta', PlanetType.FERROUS)
    for body, colony_owner in (
        (barren, owner),
        (ferrous, owner),
        (enemy_ferrous, enemy),
        (unowned_ferrous, None),
    ):
        body.owner = colony_owner
        body.population = 20.0 if colony_owner is not None else 0.0
        game.galaxy.systems[body.in_system].add_celestial_body(body)

    if load_save:
        # Simulate a save made with the previous Barren yield.
        barren.passive_metal = 2.0
        assert deserialize_game_state(game, serialize_game_state(game))
        owner = game.players[0]

    assert owner.metal == starting_metal
    resources = build_observation(game, owner)['active_player']['resources']
    colonies = resources['income_breakdown']['colonies']
    assert {row['body_id']: row['metal'] for row in colonies} == {barren.id: 0.0, ferrous.id: 8.0}

    planets = game.galaxy.systems['Sol'].celestial_bodies_by_id
    barren_panel = build_celestial_body_panel(game, planets[barren.id])
    ferrous_panel = build_celestial_body_panel(game, planets[ferrous.id])
    assert not any(row.get('text', '').startswith('Passive metal:') for row in barren_panel)
    assert any(row.get('text') == 'Passive metal: +8/turn' for row in ferrous_panel)

    TurnProcessor(game).end_turn()
    assert owner.metal == starting_metal + 8.0
