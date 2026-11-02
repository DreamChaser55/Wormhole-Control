"""Travel advice precedes issuance without prohibiting deliberate low-fuel work."""
from copy import deepcopy
import random

from constants import PlanetType
from domain.celestials import Planet
from game_ai.contracts import Command
from game_ai.observation import build_observation
from game_ai.order_view import public_journey_progress
from geometry import Position
from tests.support.campaigns import campaign
from tests.support.commands import issue
from unit_components.constructor import instantiate_unit_from_template
from unit_orders.base import Order


def test_gas_giant_quote_warns_before_replacement_and_matches_issued_journey():
    game = campaign()
    game.galaxy.game = game
    unit = instantiate_unit_from_template('SCOUT', game.players[0], 'Sol', (0, 0), Position(100, 0), game.galaxy, game)
    unit.antimatter_component.current_amount = 22
    giant = Planet((1, 0), 'Sol', PlanetType.GAS_GIANT)
    system = game.galaxy.systems['Sol']
    system.add_celestial_body(giant)
    system.hexes[giant.in_hex].update_static_inhibition_zones()
    def quote():
        actor = next(u for u in build_observation(game, unit.owner)['units'] if u['id'] == unit.id)
        assert 'enter_gas_giant' in actor['legal_commands']
        return actor['command_options']['enter_gas_giant']['approach_quotes'][str(giant.id)]
    first = quote()
    before = (random.getstate(), Order.order_counter, unit.position, deepcopy(unit.owner.order_history),
              unit.commander_component.current_order, unit.antimatter_component.current_amount)
    assert quote() == first
    assert before == (random.getstate(), Order.order_counter, unit.position, unit.owner.order_history,
                      unit.commander_component.current_order, unit.antimatter_component.current_amount)
    assert first['estimated_antimatter'] > 22 and first['antimatter_shortfall'] > 0
    assert first['estimated_owner_turns'] > 1 and first['estimate_conditional']
    assert issue(game, unit.owner, Command('enter_gas_giant', (unit.id,), target_id=giant.id)).accepted
    journey = public_journey_progress(game, unit.owner, unit)
    assert first['estimated_owner_turns'] == journey['estimated_remaining_owner_turns']
    assert abs(first['estimated_antimatter'] - journey['estimated_remaining_antimatter']) < 1
