"""Income previews and turn settlement must agree without preview side effects."""
from dataclasses import FrozenInstanceError
import random
from types import SimpleNamespace

import pytest

from constants import DEFAULT_CIVILIAN_HABITAT_BONUS, DEFAULT_STANDOFF_DISTANCE, TAX_RATE, PlanetType
from domain.celestials import Planet, Moon, ColonizableAsteroid
from domain.players import Player
from economy import IncomeBreakdown, calculate_income_breakdown, calculate_player_income, calculate_player_upkeep
from galaxy import Hex
from geometry import Position
from save_manager import deserialize_game_state, serialize_game_state
from tests.support.campaigns import campaign, ship
from turn_processor import TurnProcessor
from unit_components.civilian_habitat import CivilianHabitatComponent
from unit_components.enums import SabotageType
from unit_components.intelligence import Agent


def add_colony(game, owner, kind=Planet, population=80, *,
               coord=(0, 0), system_name='Sol', planet_type=PlanetType.TERRAN):
    system = game.galaxy.systems[system_name]
    if coord not in system.hexes:
        system.hexes[coord] = Hex(*coord, in_system=system_name)
    body = kind(coord, system_name, planet_type) if kind is Planet else kind(coord, system_name)
    body.owner, body.population = owner, population
    system.add_celestial_body(body)
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


@pytest.mark.parametrize('moon_count, first_bonus, second_bonus', [
    (0, 0.0, 0.0), (1, 8.0, 3.25), (2, 16.0, 3.25),
])
@pytest.mark.parametrize('load_save', [False, True], ids=['new', 'loaded'])
def test_moon_bonus_stacks_for_each_adjacent_planet(moon_count, first_bonus, second_bonus, load_save):
    game = campaign()
    owner = game.players[0]
    first = add_colony(game, owner)
    second = add_colony(game, owner, population=32.5, coord=(-1, 1))
    moons = [add_colony(game, owner, Moon, population=12.5, coord=coord)
             for coord in ((0, 1), (1, 0))[:moon_count]]

    if load_save:
        treasury = owner.credits
        assert deserialize_game_state(game, serialize_game_state(game))
        owner = game.players[0]
        assert owner.credits == treasury

    income = calculate_income_breakdown(game.galaxy, owner, details=True)
    rows = {row['body_id']: (row['credits'], row['moon_bonus_credits']) for row in income.colonies}
    assert rows[first.id] == pytest.approx((40.0 + first_bonus, first_bonus))
    assert rows[second.id] == pytest.approx((16.25 + second_bonus, second_bonus))
    assert all(rows[moon.id] == (6.25, 0.0) for moon in moons)
    assert_settlement(game, owner, IncomeBreakdown(
        colony_credits=56.25 + first_bonus + second_bonus + 6.25 * moon_count))


def test_moon_bonus_requires_populated_colonies_of_the_same_owner_one_hex_apart():
    game = campaign()
    owner, enemy = game.players
    ally = Player('Ally', (10, 20, 30), team_id=owner.team_id)
    game.players.append(ally)
    add_colony(game, owner, coord=(-1, 0))
    add_colony(game, owner, Moon, population=10, coord=(-1, 0))
    add_colony(game, owner, Moon, population=10, coord=(1, 0))
    add_colony(game, owner, Moon, population=0, coord=(0, 0))
    add_colony(game, enemy, Moon, population=10, coord=(-1, 1))
    add_colony(game, ally, Moon, population=10, coord=(0, -1))
    add_colony(game, None, Moon, population=0, coord=(-1, -1))
    add_colony(game, owner, Moon, population=20, coord=(0, -1), system_name='Beta')
    add_colony(game, None, population=0, system_name='Beta', planet_type=PlanetType.GAS_GIANT)
    add_colony(game, owner, ColonizableAsteroid, population=10)
    add_colony(game, owner, population=0, coord=(0, 1))

    income = calculate_income_breakdown(game.galaxy, owner, details=True)
    assert income.colony_credits == 65.0
    assert all(row['moon_bonus_credits'] == 0.0 for row in income.colonies)


def test_economy_sabotage_halves_only_base_tax_and_siphons_only_base_tax():
    game = campaign()
    owner, enemy = game.players
    planet = add_colony(game, owner)
    moon = add_colony(game, owner, Moon, population=20, coord=(1, 0))
    spy(planet, enemy)
    spy(moon, enemy)

    assert_settlement(game, owner, IncomeBreakdown(colony_credits=33.0))  # 20 tax + 8 bonus + 5 moon tax
    assert_settlement(game, enemy, IncomeBreakdown(siphoned_credits=12.5))


@pytest.mark.parametrize('approach_distance', [0, 50], ids=['in-range', 'approach'])
def test_moon_colonization_pays_bonus_at_first_income_phase_after_settlement(approach_distance):
    from game_ai.commands import CommandGateway
    from game_ai.contracts import Command, CommandBatch
    from unit_components.antimatter import AntimatterStorage
    from unit_components.colony import ColonyComponent
    from unit_components.movement import Engines

    game = campaign()
    owner, enemy = game.players
    planet = add_colony(game, owner)
    moon = add_colony(game, None, Moon, population=0, coord=(1, 0))
    add_colony(game, enemy, system_name='Beta')
    colonizer = ship(game, 'Colonizer', sector=moon.in_hex)
    colonizer.position = Position(moon.collision_radius + DEFAULT_STANDOFF_DISTANCE + approach_distance, 0)
    colonizer.add_component(ColonyComponent(colonizer))
    colonizer.colony_component.population_cargo = 20
    colonizer.add_component(Engines(colonizer, speed=100))
    colonizer.add_component(AntimatterStorage(colonizer, max_capacity=200))
    colonizer.antimatter_component.current_amount = 200
    upkeep = calculate_player_upkeep(game.galaxy, owner)
    starting_credits = owner.credits

    command = Command(type='colonize', unit_ids=(colonizer.id,), target_id=moon.id, queue=False)
    assert CommandGateway(game).apply_batch(owner, CommandBatch((command,))).accepted
    settled_on_issue = approach_distance == 0
    assert (moon.owner is owner) == settled_on_issue
    assert owner.credits == starting_credits

    turns = TurnProcessor(game)
    turns.end_turn()
    assert moon.owner is owner
    assert owner.credits - starting_credits == pytest.approx((58.0 if settled_on_issue else 40.0) - upkeep)

    turns.end_turn()
    starting_credits = owner.credits
    expected_income = (planet.population * 1.20 + moon.population) * TAX_RATE
    turns.end_turn()
    assert owner.credits - starting_credits == pytest.approx(expected_income - upkeep)


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
    moon = add_colony(game, owner, Moon, population=20, coord=(1, 0))
    add_colony(game, enemy, system_name='Beta')
    add_colony(game, enemy, Moon, population=20, coord=(1, 0), system_name='Beta')
    vessel = ship(game, 'Depot')
    vessel.add_component(CivilianHabitatComponent(vessel))
    ship(game, 'Enemy vessel', owner=1)
    treasury = owner.credits
    resources = build_observation(game, owner)['active_player']['resources']
    rows = resources['income_breakdown']['colonies']
    assert {row['body_id']: row['moon_bonus_credits'] for row in rows} == {colony.id: 8.0, moon.id: 0.0}
    assert {row['body_id']: row['credits'] for row in rows} == {colony.id: 48.0, moon.id: 10.0}
    assert [entry['unit_id'] for entry in resources['upkeep_breakdown']] == [vessel.id]
    assert resources['income'] == pytest.approx(calculate_player_income(game.galaxy, owner))
    assert resources['resource_budget']['available']['credits'] == owner.credits == treasury


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
