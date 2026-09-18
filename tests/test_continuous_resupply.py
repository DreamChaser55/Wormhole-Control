"""End-to-end harvesting and continuous destination selection."""
import json

import pytest

from constants import StarType, NebulaType
from domain.celestials import Star, Nebula
from geometry import Position
from unit_components.antimatter import AntimatterHarvester
from unit_orders.antimatter import ContinuousResupplyOrder
from unit_orders.base import OrderStatus
from tests.support.campaigns import campaign
from tests.test_antimatter_logistics import vessel, issue, tick


def harvesting_scenario(nebula=False, manual=False, amount=0, position=(1000, 0)):
    game = campaign()
    source = (Nebula((0, 0), "Sol", NebulaType.HYDROGEN) if nebula
              else Star(in_system="Sol", star_type=StarType.G_TYPE))
    source.in_hex, source.position = (0, 0), Position(0, 0)
    source.name = "Harvest source"
    system = game.galaxy.systems['Sol']
    system.hexes[(0, 0)].celestial_bodies.append(source)
    system.celestial_bodies_by_id[source.id] = source
    system.hexes[(0, 0)].update_static_inhibition_zones()
    actor = vessel(game, 'harvester', amount=amount, capacity=150, moving=True, position=position)
    actor.add_component(AntimatterHarvester(actor))
    target = vessel(game, 'depot', amount=0, capacity=600, position=(3500, 0))
    command = dict(type='continuous_resupply', unit_ids=(actor.id,), source_id=source.id,
                   target_id=target.id if manual else None)
    return game, actor, source, target, command


@pytest.mark.parametrize('nebula', [False, True])
@pytest.mark.parametrize('manual', [False, True])
def test_harvest_deliver_return_and_repeat(nebula, manual):
    game, actor, source, target, command = harvesting_scenario(nebula, manual)
    result = issue(game, command)
    assert result.accepted, result.errors
    order = actor.commander_component.current_order
    seen_delivery = False
    seen_return = False
    for _ in range(400):
        tick(game, actor)
        assert order.status == OrderStatus.IN_PROGRESS, order.failure_reason
        seen_delivery |= order.phase == 'delivering'
        seen_return |= seen_delivery and order.phase == 'harvesting'
        if target.antimatter_component.current_amount > 200 and seen_return:
            break
    assert seen_return
    assert target.antimatter_component.current_amount > 200
    assert order.return_reserve == 60


def test_harvester_returns_inside_harvest_range_from_outside_source_sector():
    game, actor, source, target, command = harvesting_scenario(amount=100, position=(4500, 0))
    target.antimatter_component.current_amount = 600
    assert issue(game, command).accepted
    for _ in range(50):
        tick(game, actor)
    assert actor.harvester_component.find_nearby_harvest_source(game.galaxy) is source
    assert actor.antimatter_component.current_amount == 150
    assert actor.commander_component.current_order.waiting_reason == 'no_destination'


def test_manual_harvester_waits_at_source_when_depot_full_then_resumes():
    game, actor, source, target, command = harvesting_scenario(manual=True, amount=150)
    target.antimatter_component.current_amount = 600
    assert issue(game, command).accepted
    order = actor.commander_component.current_order
    tick(game, actor)
    assert order.phase == 'harvesting' and order.waiting_reason == 'destination_full'
    target.antimatter_component.current_amount = 0
    tick(game, actor)
    assert order.phase == 'delivering' and order.active_destination_unit_id == target.id
    target.antimatter_component.current_amount = 600
    tick(game, actor)
    assert order.phase == 'harvesting' and order.active_destination_unit_id is None


@pytest.mark.parametrize('parameters,reason', [({}, 'invalid_parameters'), ({'source_body_id': 99999}, 'target_unavailable')])
def test_missing_or_unknown_harvest_source(parameters, reason):
    game, actor, _, _, _ = harvesting_scenario()
    order = ContinuousResupplyOrder(actor, parameters)
    order.execute(game.galaxy)
    assert order.status == OrderStatus.FAILED and order.failure_reason == reason


def test_source_id_zero_and_human_event_use_gateway():
    from events import ContinuousResupplyEvent, EventBus
    from order_system import OrderSystem
    game, actor, source, target, command = harvesting_scenario()
    system = game.galaxy.systems['Sol']
    del system.celestial_bodies_by_id[source.id]
    source.id = 0
    system.celestial_bodies_by_id[0] = source
    bus = EventBus()
    OrderSystem(game, bus)
    bus.publish(ContinuousResupplyEvent([actor], source, False, target))
    order = actor.commander_component.current_order
    assert order.parameters == {'source_body_id': 0, 'target_unit_id': target.id}
    assert order.status == OrderStatus.IN_PROGRESS


@pytest.mark.parametrize('phase', ['harvesting', 'delivering'])
@pytest.mark.parametrize('manual', [False, True])
def test_harvester_save_restore_without_replay(phase, manual):
    from save_manager import serialize_game_state, deserialize_game_state
    game, actor, source, target, command = harvesting_scenario(manual=manual, amount=150 if phase == 'delivering' else 0)
    assert issue(game, command).accepted
    if phase == 'delivering':
        tick(game, actor)
    order = actor.commander_component.current_order
    assert order.phase == phase
    before = serialize_game_state(game)
    amount = actor.antimatter_component.current_amount
    runtime = order.get_persistence_state()
    assert deserialize_game_state(game, json.loads(json.dumps(before)))
    loaded = game.galaxy.get_unit_by_id(actor.id)
    assert loaded.antimatter_component.current_amount == amount
    assert loaded.commander_component.current_order.get_persistence_state() == runtime
    for _ in range(100):
        tick(game, loaded)
    assert game.galaxy.get_unit_by_id(target.id).antimatter_component.current_amount > 0
