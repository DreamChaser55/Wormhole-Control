"""Successful docking settles explicit roots before stored-unit order cleanup."""
import json

import pytest

from constants import HullSize
from geometry import Position
from order_history import history_view
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from turn_processor import TurnProcessor
from unit_components.hangar import HangarComponent
from unit_components.movement import Engines
from unit_components.strikecraft import StrikecraftBayComponent, StrikecraftWingComponent
from unit_orders.base import OrderStatus
from unit_orders.hangar import DockOrder


def docking_world(wing):
    game = campaign()
    game.galaxy.game = game
    carrier = ship(game, 'Carrier')
    bay = StrikecraftBayComponent(carrier, max_slots=2) if wing else HangarComponent(carrier, max_slots=2)
    carrier.add_component(bay)
    craft = ship(game, 'Returning craft', hull=HullSize.STRIKECRAFT_WING if wing else HullSize.TINY)
    if wing:
        craft.add_component(StrikecraftWingComponent(craft))
    craft.add_component(Engines(craft, speed=100))
    return game, carrier, craft, bay


@pytest.mark.parametrize('approaching', [False, True])
def test_docking_root_completes_once_and_survives_campaign_load(approaching):
    game, carrier, craft, bay = docking_world(True)
    craft.position = Position(900 if approaching else 150, 0)
    craft.strikecraft_wing_component.turns_outside = 20
    root = DockOrder(craft, {'target_carrier_id': carrier.id})
    craft.commander_component.add_order(root)
    if approaching:
        assert root.sub_orders
        carrier.position = Position(400, 100)
        for _ in range(20):
            TurnProcessor(game).process_player_turn(craft.owner)
            game.turn_number += 1
            if craft in bay.docked_units:
                break
    assert craft in bay.docked_units
    assert root.status == OrderStatus.COMPLETED
    events = [e for e in history_view(craft.owner)['events'] if e['order_id'] == root.public_id]
    assert len(events) == 1 and events[0]['outcome'] == 'completed'
    assert craft.strikecraft_wing_component.turns_outside == 0
    root.cancel()
    data = json.loads(json.dumps(serialize_game_state(game)))
    errors = []
    assert deserialize_game_state(game, data, on_error=errors.append), errors
    restored = game.galaxy.get_unit_by_id(carrier.id).strikecraft_bay_component.docked_units
    assert any(u.id == craft.id and u.strikecraft_wing_component.turns_outside == 0 for u in restored)
    assert [e for e in history_view(game.players[0])['events'] if e['order_id'] == root.public_id] == events


def test_general_hangar_docking_also_records_completion():
    game, carrier, craft, bay = docking_world(False)
    root = DockOrder(craft, {'target_carrier_id': carrier.id})
    craft.commander_component.add_order(root)
    assert craft in bay.docked_units
    assert craft.owner.order_history[-1]['outcome'] == 'completed'


def test_failed_dock_never_records_completion(monkeypatch):
    game, carrier, craft, bay = docking_world(True)
    monkeypatch.setattr(bay, 'dock', lambda *a, **kw: False)
    root = DockOrder(craft, {'target_carrier_id': carrier.id})
    craft.commander_component.add_order(root)
    assert craft not in bay.docked_units
    assert root.status == OrderStatus.FAILED
    assert [e['outcome'] for e in craft.owner.order_history] == ['failed']
