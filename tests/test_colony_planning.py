"""Population advice discourages stripping new colonies without changing legality."""
from copy import deepcopy

import pytest

from domain.celestials import Moon
from game_ai.contracts import Command
from game_ai.observation import build_observation
from geometry import Position
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from unit_components.colony import ColonyComponent
from unit_components.movement import Engines
from unit_components.sensors import Sensors


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
    assert source.population == population and unit.owner.ai_memory == before
    if population == 10.1:
        assert advice['population_after_maximum_load'] == 0.1
        assert advice['recovery_rounds_after_maximum_load'] > 400
        result = issue(game, unit.owner, Command('load_colonists', (unit.id,), target_id=source.id, amount=10))
        assert result.accepted  # Evacuation/expansion remains a legal strategic exception.
        assert source.population == pytest.approx(0.1)
