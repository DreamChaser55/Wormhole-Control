"""Population advice discourages stripping new colonies without changing legality."""
from copy import deepcopy
import json

import pytest

from domain.celestials import Moon
from game_ai.contracts import Command, CommandBatch, TurnPlan
from game_ai.observation import build_observation
from geometry import Position
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from unit_components.colony import ColonyComponent
from unit_components.movement import Engines
from unit_components.sensors import Sensors


@pytest.mark.parametrize('approaching', [False, True])
def test_loading_records_actual_facts_once_and_preserves_them_on_load(approaching):
    from order_history import history_view
    from save_manager import serialize_game_state, deserialize_game_state
    from turn_processor import TurnProcessor
    from unit_components.antimatter import AntimatterStorage

    game = campaign()
    game.galaxy.game = game
    source = Moon((0, 0), 'Sol')
    source.owner, source.population = game.players[0], 50
    game.galaxy.systems['Sol'].add_celestial_body(source)
    unit = ship(game, 'Colonizer')
    for component in (ColonyComponent(unit), Engines(unit, speed=100),
                      AntimatterStorage(unit, max_capacity=200)):
        unit.add_component(component)
    unit.position = Position(1000 if approaching else 260, 0)
    result = issue(game, unit.owner, Command('load_colonists', (unit.id,), target_id=source.id, amount=25))
    assert result.accepted, result.errors
    if approaching:
        assert not history_view(unit.owner)['events']
        for _ in range(15):
            unit.commander_component.prepare_for_movement()
            TurnProcessor(game)._process_movement(unit.owner)
            unit.update()
    events = history_view(unit.owner)['events']
    assert len(events) == 1 and events[0]['outcome'] == 'completed'
    assert events[0]['loading_outcome'] == {
        'requested_amount': 25, 'loaded_amount': 25, 'retained_population': 25,
    }
    source.population *= 1.01
    observation = build_observation(game, unit.owner)
    assert observation['order_history']['events'] == events
    assert build_observation(game, game.players[1])['order_history']['events'] == []
    data = json.loads(json.dumps(serialize_game_state(game)))
    assert deserialize_game_state(game, data)
    assert history_view(game.players[0])['events'] == events


def test_forecast_evaluation_scores_memory_facts_not_just_legal_commands():
    from game_ai.evaluation import colony_load_forecast_case, score_plan
    case = colony_load_forecast_case()
    correct = TurnPlan((), CommandBatch(), {'beliefs': ['Loaded 25 colonists, retained 25 at execution; source is now 25.25 after growth.']})
    false = TurnPlan((), CommandBatch(), {'lessons': ['Loading the maximum left only 0.25 population and a long recovery.']})
    assert score_plan(case, correct).passed
    assert not score_plan(case, false).passed
    assert not score_plan(case, TurnPlan((), CommandBatch(), {})).passed


@pytest.mark.parametrize('population, recommended, retained', [(10.1, 0, 10), (50, 25, 25), (0.1, 0, 0.1)])
def test_current_source_exposes_growth_tradeoff_without_mutation(population, recommended, retained):
    game = campaign()
    game.galaxy.game = game
    source = Moon((0, 0), 'Sol')
    source.owner, source.population = game.players[0], population
    game.galaxy.systems['Sol'].add_celestial_body(source)
    unit = ship(game, 'Colonizer')
    unit.position = Position(260, 0)
    for component in (ColonyComponent(unit), Engines(unit, speed=100), Sensors(unit, short_range_radius=2000)):
        unit.add_component(component)
    before = deepcopy(unit.owner.ai_memory)
    observation = build_observation(game, unit.owner)
    actor = next(actor for actor in observation['units'] if actor['id'] == unit.id)
    target = next(t for t in actor['command_options']['load_colonists']['targets'] if t['target_id'] == source.id)
    advice = target['population_advice']
    assert advice['recommended_amount'] == recommended
    assert advice['recommended_retained_population'] == retained
    assert advice['growth_rate_per_round'] == 0.01
    assert advice['current_population'] == population
    assert source.population == population and unit.owner.ai_memory == before
    if population == 10.1:
        forecast = advice['hypothetical_next_maximum_load']
        assert forecast['population_after_load'] == 0.1
        assert forecast['hypothetical_load_amount'] == 10
        assert forecast['recovery_rounds_to_current_population'] > 400
        result = issue(game, unit.owner, Command('load_colonists', (unit.id,), target_id=source.id, amount=10))
        assert result.accepted  # Evacuation/expansion remains a legal strategic exception.
        assert source.population == pytest.approx(0.1)
