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


@pytest.mark.parametrize('crystal', [False, True])
def test_continuous_mine_explains_cargo_refinery_and_delivery_after_load(crystal):
    from domain.celestials import MetalAsteroid, Comet
    from unit_components.mining import MiningComponent, MetalRefineryComponent, CrystalRefineryComponent
    from unit_components.movement import Engines
    from game_ai.observation import build_observation
    from gui.sidebar.order_formatting import format_order_state_data
    game = campaign()
    game.galaxy.game = game
    unit = ship(game)
    unit.position = Position(180, 0)
    unit.add_component(Engines(unit, speed=100))
    unit.add_component(AntimatterStorage(unit, max_capacity=500))
    unit.add_component(MiningComponent(unit, mining_rate=10, max_cargo=20))
    body = (Comet if crystal else MetalAsteroid)((0, 0), 'Sol')
    game.galaxy.systems['Sol'].add_celestial_body(body)
    assert issue(game, unit.owner, Command('continuous_mine', (unit.id,), target_id=body.id)).accepted
    root = unit.commander_component.current_order
    state = root.progress_view(game.galaxy)
    assert state['phase'] == 'mining' and not state['refinery_available']
    assert state['required_refinery_types'] == ['crystal' if crystal else 'metal']
    refinery = ship(game, 'Refinery')
    refinery.position = Position(1000, 0)
    refinery.add_component((CrystalRefineryComponent if crystal else MetalRefineryComponent)(refinery))
    def tick():
        unit.commander_component.prepare_for_movement()
        TurnProcessor(game)._process_movement(unit.owner)
        unit.update()
    resource = 'crystal' if crystal else 'metal'
    before = getattr(unit.owner, resource)
    for _ in range(4):
        tick()
        if root.progress_view(game.galaxy)['phase'] == 'delivering':
            break
    state = root.progress_view(game.galaxy)
    assert state['phase'] == 'delivering' and state['refinery_id'] == refinery.id
    assert state['raw_crystal' if crystal else 'raw_metal'] == 20
    assert getattr(unit.owner, resource) == before
    actor = next(u for u in build_observation(game, unit.owner)['units'] if u['id'] == unit.id)
    assert actor['current_order']['progress']['refinery_id'] == refinery.id
    assert any('Phase: Delivering' in line for line in format_order_state_data(root.get_state_data()))
    assert root.progress_view(game.galaxy, set())['refinery_id'] is None
    uid = unit.id
    assert deserialize_game_state(game, json.loads(json.dumps(serialize_game_state(game))))
    unit = game.galaxy.get_unit_by_id(uid)
    root = unit.commander_component.current_order
    assert root.progress_view(game.galaxy) == state
    for _ in range(15):
        tick()
        if getattr(unit.owner, resource) > before:
            break
    assert getattr(unit.owner, resource) == before + 20
    assert root.progress_view(game.galaxy)['phase'] == 'approaching_mine'


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
