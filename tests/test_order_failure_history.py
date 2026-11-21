"""Terminal failures cross execution, disclosure, briefing and persistence boundaries."""
import json

from constants import FieldDensity, HullSize
from domain.celestials import IceField
from game_ai.observation import build_observation
from game_ai.order_view import order_layers
from geometry import Position
from order_history import history_view
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from turn_briefing import initialize_campaign, begin_window, finish_window, summary_view
from unit_components.movement import Engines
from unit_orders.base import OrderStatus
from unit_orders.movement import MoveOrder, ReachWaypointOrder


def test_hazard_child_failure_survives_public_views_and_campaign_load():
    game = campaign()
    unit = ship(game, hull=HullSize.LARGE)
    unit.add_component(Engines(unit, speed=100))
    owner, enemy = game.players
    initialize_campaign(game)
    begin_window(game, owner)
    order = MoveOrder(unit, {
        'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
        'destination_position': Position(4000, 0),
    })
    child = ReachWaypointOrder(unit, dict(order.parameters))
    order.add_sub_order(child)
    order.register_explicit_root()
    order.status = OrderStatus.IN_PROGRESS
    unit.commander_component.current_order = order
    field = IceField((0, 0), 'Sol', density=FieldDensity.MEDIUM)
    field.position = Position(4000, 0)
    game.galaxy.systems['Sol'].add_celestial_body(field)
    order.update(game.galaxy)
    assert child.failure_reason == order.failure_reason == 'hazard_blocked'
    assert order.status == OrderStatus.FAILED
    assert order_layers(unit, 'self', {unit.id}, set())['current_order']['failure_reason'] == 'hazard_blocked'
    assert order_layers(unit, 'enemy', {unit.id}, {field.id}) == {}
    event = history_view(owner)['events'][0]
    assert event['reason'] == 'hazard_blocked'
    assert set(event) == {'event_id', 'turn', 'player_id', 'unit_id', 'order_id', 'type', 'outcome', 'reason'}
    assert build_observation(game, owner)['order_history']['events'] == [event]
    assert build_observation(game, enemy)['order_history']['events'] == []
    order.cancel()
    order.update(game.galaxy)
    assert history_view(owner)['events'] == [event]
    finish_window(game, owner)
    assert any('hazard blocked' in entry['detail'] for entry in summary_view(owner)['entries'])
    assert not summary_view(enemy)['entries']

    saved_history = history_view(owner)
    saved_summary = summary_view(owner)
    data = json.loads(json.dumps(serialize_game_state(game)))
    errors = []
    assert deserialize_game_state(game, data, on_error=errors.append), errors
    restored_owner = game.players[0]
    assert history_view(restored_owner) == saved_history
    assert summary_view(restored_owner) == saved_summary
    restored_unit = game.galaxy.get_unit_by_id(unit.id)
    if restored_unit.commander_component.current_order is not None:
        restored_unit.commander_component.current_order.cancel()
    assert history_view(restored_owner) == saved_history


def test_unknown_failure_details_are_sanitized_everywhere():
    game = campaign()
    unit = ship(game)
    initialize_campaign(game)
    begin_window(game, unit.owner)
    order = MoveOrder(unit, {
        'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
        'destination_position': unit.position,
    })
    order.register_explicit_root()
    unit.commander_component.current_order = order
    private_reason = 'secret target 98765 at (1234, 4321): internal exception'
    order.fail(private_reason)
    finish_window(game, unit.owner)
    view = order_layers(unit, 'self', {unit.id}, set())
    assert view['current_order']['failure_reason'] == 'execution_failed'
    history = history_view(unit.owner)
    assert history['events'][0]['reason'] == 'execution_failed'
    public = json.dumps([view, history, summary_view(unit.owner)])
    for secret in ('secret target 98765', '(1234, 4321)', 'internal exception'):
        assert secret not in public
    assert 'execution failed' in public


def test_synchronously_failed_promoted_order_is_released_immediately():
    from constants import StarType
    from domain.celestials import Star
    from unit_components.antimatter import AntimatterStorage, AntimatterHarvester
    from unit_orders.fuel_transport import TransferAntimatterOrder
    from unit_orders.antimatter import ContinuousResupplyOrder
    game = campaign()
    star = Star(in_system='Sol', star_type=StarType.G_TYPE)
    star.in_hex = (0, 0)
    star.position = Position(0, 0)
    game.galaxy.systems['Sol'].add_celestial_body(star)
    harvester = ship(game, 'Harvester', hull=HullSize.MEDIUM)
    harvester.position = Position(4500, 0)
    harvester.add_component(Engines(harvester, speed=175))
    harvester.add_component(AntimatterStorage(harvester, max_capacity=300))
    harvester.antimatter_component.current_amount = 10.0
    harvester.add_component(AntimatterHarvester(harvester))
    recipient = ship(game, 'Depot', hull=HullSize.SMALL)
    recipient.position = Position(4550, 0)
    recipient.add_component(AntimatterStorage(recipient, max_capacity=100))
    recipient.antimatter_component.current_amount = 0.0
    give = TransferAntimatterOrder(harvester, {'target_unit_id': recipient.id})
    resupply = ContinuousResupplyOrder(harvester, {'source_body_id': star.id})
    harvester.commander_component.add_order(give)
    harvester.commander_component.add_order(resupply)
    harvester.commander_component.update()
    assert give.status == OrderStatus.COMPLETED
    assert resupply.status == OrderStatus.FAILED
    assert harvester.commander_component.current_order is None
    assert not harvester.commander_component.orders_queue
    view = order_layers(harvester, 'self', {harvester.id, recipient.id}, {star.id})
    assert view['current_order'] is None
    assert not view['standing_order']['suspended']


def test_approached_gas_giant_entry_promotes_leave_and_following_move_same_turn():
    from constants import PlanetType
    from domain.celestials import Planet
    from unit_orders.gas_giant import EnterGasGiantOrder, LeaveGasGiantOrder
    game = campaign()
    giant = Planet((0, 0), 'Sol', planet_type=PlanetType.GAS_GIANT)
    giant.position = Position(0, 0)
    giant.collision_radius = 400.0
    game.galaxy.systems['Sol'].add_celestial_body(giant)
    unit = ship(game, 'Frigate', hull=HullSize.MEDIUM)
    unit.position = Position(800, 0)
    unit.add_component(Engines(unit, speed=200))
    entry = EnterGasGiantOrder(unit, {'target_id': giant.id})
    leave = LeaveGasGiantOrder(unit)
    onward = MoveOrder(unit, {
        'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
        'destination_position': Position(1600, 0),
    })
    unit.commander_component.add_order(entry)
    unit.commander_component.add_order(leave)
    unit.commander_component.add_order(onward)
    # Force arrival at entry distance so the enter sub-order completes during update().
    unit.position = Position(420, 0)
    entry.sub_orders.popleft()
    unit.commander_component.update()
    assert entry.status == OrderStatus.COMPLETED
    assert leave.status == OrderStatus.COMPLETED
    assert not unit.is_hidden_in_gas_giant
    assert unit.commander_component.current_order is onward
    assert onward.status == OrderStatus.IN_PROGRESS


def test_post_update_planetary_order_settles_current_order_same_turn():
    from constants import PlanetType
    from domain.celestials import Planet
    from turn_processor import TurnProcessor
    from unit_components.antimatter import AntimatterStorage
    from unit_components.planetary import TroopTransportComponent
    from unit_orders.planetary import RecruitTroopsOrder
    game = campaign()
    home = Planet((0, 0), 'Sol', planet_type=PlanetType.TERRAN)
    home.in_hex = (0, 0)
    home.position = Position(0, 0)
    home.collision_radius = 100.0
    home.owner = game.players[0]
    home.population = 50.0
    home.population_capacity = 100
    game.galaxy.systems['Sol'].add_celestial_body(home)
    game.players[0].credits = 5000
    transport = ship(game, 'Transport', hull=HullSize.MEDIUM)
    transport.position = Position(150, 0)
    transport.add_component(Engines(transport, speed=150))
    transport.add_component(AntimatterStorage(transport, max_capacity=200))
    transport.add_component(TroopTransportComponent(transport, capacity=40))
    initialize_campaign(game)
    order = RecruitTroopsOrder(transport, {'target_id': home.id, 'amount': 10})
    transport.commander_component.add_order(order)
    begin_window(game, game.players[0])
    TurnProcessor(game).process_player_turn(game.players[0])
    finish_window(game, game.players[0])
    assert order.status == OrderStatus.COMPLETED
    assert transport.commander_component.current_order is None
    assert any(e['detail'] == 'Idle after finishing orders' for e in summary_view(game.players[0])['entries'])
