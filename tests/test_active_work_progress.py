"""Root work summaries track real execution without traversing queued work."""
import json

from constants import HullSize, StarType
from domain.celestials import Star
from game_ai.order_view import order_layers
from geometry import Position
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from turn_processor import TurnProcessor
from unit_components.antimatter import AntimatterStorage, AntimatterHarvester
from unit_components.constructor import instantiate_unit_from_template
from unit_components.movement import Engines
from unit_orders.antimatter import ContinuousResupplyOrder
from unit_orders.construction import ConstructOrder


def view(unit, ids=(), bodies=()):
    return order_layers(unit, 'self', {unit.id, *ids}, set(bodies))['current_order']


def test_approach_wrapped_construction_reports_real_active_job_and_loads_unchanged():
    game = campaign()
    game.galaxy.game, game.gui = game, None
    player = game.players[0]
    player.credits, player.metal, player.crystal = 100000, 10000, 10000
    unit = instantiate_unit_from_template('CONSTRUCTOR_MK1', player, 'Sol', (0, 0), Position(0, 0), game.galaxy, game)
    root = ConstructOrder(unit, {'unit_template_name': 'MISSILE_PLATFORM', 'target_system_name': 'Sol',
                                'target_hex_coord': (0, 0), 'target_position': Position(2000, 0)})
    unit.commander_component.add_order(root)
    assert view(unit)['active_phase'] == 'approaching'
    for _ in range(30):
        TurnProcessor(game).process_player_turn(player)
        if unit.constructor_component.current_construction_target:
            break
    assert unit.constructor_component.construction_order_id != root.public_id
    progress = view(unit)['progress']
    assert view(unit)['active_phase'] == progress['phase'] == 'building'
    assert progress['turns_completed'] == unit.constructor_component.construction_progress
    assert progress['turns_required'] == unit.constructor_component.time_to_build
    queued = ConstructOrder(unit, dict(root.parameters))
    unit.commander_component.add_order(queued)
    queued_view = order_layers(unit, 'self', {unit.id}, set())['queued_orders'][0]
    assert queued_view['active_phase'] == 'queued'
    assert 'turns_completed' not in queued_view['progress']
    before = serialize_game_state(game)
    assert view(unit)['progress'] == progress
    after = serialize_game_state(game)
    assert {k: v for k, v in after.items() if k != 'timestamp'} == {k: v for k, v in before.items() if k != 'timestamp'}
    errors = []
    assert deserialize_game_state(game, json.loads(json.dumps(before)), on_error=errors.append), errors
    restored = game.galaxy.get_unit_by_id(unit.id)
    assert view(restored)['progress'] == progress
    restored.is_disabled = True
    assert view(restored)['active_phase'] == 'stalled'


def test_harvester_distinguishes_building_delivery_reserve_from_absent_demand():
    game = campaign()
    source = Star(in_system='Sol', star_type=StarType.G_TYPE)
    source.in_hex, source.position = (0, 0), Position(0, 0)
    game.galaxy.systems['Sol'].add_celestial_body(source)
    actor = ship(game, 'Harvester', hull=HullSize.MEDIUM)
    actor.position = Position(1000, 0)
    for component in (AntimatterStorage(actor, max_capacity=150), Engines(actor, speed=100),
                      AntimatterHarvester(actor)):
        actor.add_component(component)
    target = ship(game, 'Recipient')
    target.position = Position(1500, 0)
    target.add_component(AntimatterStorage(target, max_capacity=200))
    target.antimatter_component.current_amount = 0
    actor.antimatter_component.current_amount = 40
    order = ContinuousResupplyOrder(actor, {'source_body_id': source.id, 'target_unit_id': None})
    actor.commander_component.add_order(order)
    order.update(game.galaxy)
    assert view(actor, [target.id], [source.id])['progress']['waiting_reason'] == 'building_delivery_reserve'
    assert order.get_state_data()['waiting_reason'] == 'building_delivery_reserve'
    assert actor.antimatter_component.current_amount == 40
    target.antimatter_component.current_amount = 200
    order.update(game.galaxy)
    assert view(actor, [target.id], [source.id])['progress']['waiting_reason'] == 'no_destination'
