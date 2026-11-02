"""Continuous logistics distinguish productive travel from actual waiting."""
import json

import pytest

from constants import StarType
from domain.celestials import Star
from game_ai.contracts import Command
from game_ai.order_view import public_journey_progress
from geometry import Position
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from turn_processor import TurnProcessor
from unit_components.antimatter import AntimatterStorage
from unit_components.constructor import instantiate_unit_from_template


@pytest.mark.parametrize('harvesting', [True, False])
def test_source_return_is_movement_then_wait_in_public_views_and_after_load(harvesting):
    game = campaign()
    game.galaxy.game = game
    actor = instantiate_unit_from_template('ANTIMATTER_HARVESTER' if harvesting else 'ANTIMATTER_TRANSPORTER',
        game.players[0], 'Sol', (0, 0), Position(2500 if harvesting else 100, 0), game.galaxy, game)
    if harvesting:
        source = Star('Sol', StarType.G_TYPE)
        game.galaxy.systems['Sol'].add_celestial_body(source)
    else:
        source = ship(game, 'Source')
        source.add_component(AntimatterStorage(source, max_capacity=1000))
    depot = ship(game, 'Depot')
    depot.position = Position(4500, 0)
    depot.add_component(AntimatterStorage(depot, max_capacity=50))
    depot.antimatter_component.current_amount = 0
    kind = 'continuous_resupply' if harvesting else 'continuous_antimatter_transport'
    assert issue(game, actor.owner, Command(kind, (actor.id,), source_id=source.id)).accepted
    root = actor.commander_component.current_order
    def tick():
        actor.commander_component.prepare_for_movement()
        TurnProcessor(game)._process_movement(actor.owner)
        actor.update()
    for _ in range(80):
        tick()
        if root.public_phase == 'returning_to_source' and root.public_return_reason == 'no_destination':
            break
    else:
        pytest.fail('Delivery did not start its source-return journey')
    assert root.public_waiting_reason is None
    assert root.get_state_data()['return_reason'] == 'no_destination'
    from game_ai.order_view import order_layers
    ids = {actor.id, depot.id, source.id}
    progress = order_layers(actor, 'self', ids, {source.id})['current_order']['progress']
    assert progress['phase'] == 'returning_to_source' and progress['waiting_reason'] is None
    tick()  # Resolve the newly pending source approach before comparing estimates.
    first = public_journey_progress(game, actor.owner, actor)['estimated_remaining_owner_turns']
    tick()
    assert public_journey_progress(game, actor.owner, actor)['estimated_remaining_owner_turns'] < first
    uid = actor.id
    assert deserialize_game_state(game, json.loads(json.dumps(serialize_game_state(game))))
    actor = game.galaxy.get_unit_by_id(uid)
    root = actor.commander_component.current_order
    assert root.public_phase == 'returning_to_source' and root.public_waiting_reason is None
    for _ in range(80):
        tick()
        if not root.sub_orders:
            break
    assert root.public_phase == ('harvesting' if harvesting else 'loading')
    assert root.public_waiting_reason == 'no_destination'
