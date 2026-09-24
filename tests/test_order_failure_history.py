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
