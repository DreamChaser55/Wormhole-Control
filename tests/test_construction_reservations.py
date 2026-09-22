"""Construction budgets remain private while allied capacity remains shared."""
import pytest

from game_ai.contracts import Command
from geometry import Position
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from unit_components.constructor import Constructor
from unit_components.movement import Engines
from unit_orders.construction import ConstructOrder
from unit_orders.movement import MoveOrder


def builder(game, **kwargs):
    unit = ship(game, **kwargs)
    unit.add_component(Constructor(unit))
    unit.add_component(Engines(unit, speed=100))
    return unit


def build_command(unit):
    return Command('construct', (unit.id,), template_name='SHIPYARD_MK1',
                   system_name=unit.in_system, hex_coord=unit.in_hex,
                   position=(100, 0))


def queue_build(unit):
    unit.commander_component.add_order(MoveOrder(unit, {
        'destination_system_name': unit.in_system, 'destination_hex_coord': unit.in_hex,
        'destination_position': Position(1500, 0),
    }))
    pending = ConstructOrder(unit, {
        'unit_template_name': 'SHIPYARD_MK1', 'target_system_name': unit.in_system,
        'target_hex_coord': unit.in_hex, 'target_position': Position(1500, 0),
    })
    unit.commander_component.add_order(pending)
    assert unit.commander_component.current_order.status.name == 'IN_PROGRESS'
    return pending


@pytest.mark.parametrize('reservation_owner', [None, 'enemy', 'ally', 'self'])
def test_only_own_pending_builds_reduce_budget(reservation_owner):
    game = campaign()
    player, other = game.players
    player.credits = 1000
    actor = builder(game)
    if reservation_owner is not None:
        if reservation_owner == 'ally':
            other.team_id = player.team_id
        queued = builder(game, owner=0 if reservation_owner == 'self' else 1, system='Beta')
        pending = queue_build(queued)
        before_queue = list(queued.commander_component.orders_queue)
    before_other = other.credits
    result = issue(game, player, Command('rename_unit', (actor.id,), new_name='Accepted'),
                   build_command(actor))
    assert result.accepted == (reservation_owner != 'self')
    assert player.credits == (1000 if reservation_owner == 'self' else 0)
    assert actor.name == ('ship' if reservation_owner == 'self' else 'Accepted')
    assert bool(actor.constructor_component.current_construction_target) == result.accepted
    assert other.credits == before_other
    if reservation_owner is not None:
        assert pending.status.name == 'PENDING'
        assert list(queued.commander_component.orders_queue) == before_queue
    if not result.accepted:
        assert result.failure_stage == 'preflight'
        assert result.errors[0].code == 'insufficient_resources'


@pytest.mark.parametrize('edit', ['cancel_order', 'clear_explicit_orders', 'replace'])
def test_releasing_own_pending_build_does_not_create_a_refund(edit):
    game = campaign()
    player = game.players[0]
    player.credits = 1000
    actor = builder(game)
    pending = queue_build(actor)
    if edit == 'replace':
        commands = [build_command(actor)]
    else:
        edit_command = Command(edit, (actor.id,),
                               order_id=pending.public_id if edit == 'cancel_order' else None)
        commands = [edit_command, build_command(builder(game))]
    assert issue(game, player, *commands).accepted
    assert player.credits == 0


def test_paid_construction_is_not_reserved_again():
    game = campaign()
    player = game.players[0]
    player.credits = 2000
    first, second = builder(game), builder(game)
    assert issue(game, player, build_command(first)).accepted
    assert player.credits == 1000
    assert issue(game, player, build_command(second)).accepted
    assert player.credits == 0


def test_allied_pending_dock_still_reserves_shared_hangar():
    from constants import HullSize
    from unit_components.hangar import HangarComponent
    from unit_orders.hangar import DockOrder
    game = campaign()
    player, ally = game.players
    ally.team_id = player.team_id
    carrier = ship(game)
    carrier.position = Position(3000, 0)
    carrier.add_component(HangarComponent(carrier, max_slots=1))
    first = ship(game, owner=1, hull=HullSize.TINY)
    first.add_component(Engines(first, speed=100))
    first.commander_component.add_order(DockOrder(first, {'target_carrier_id': carrier.id}))
    second = ship(game, hull=HullSize.TINY)
    result = issue(game, player, Command('dock_in_hangar', (second.id,), target_id=carrier.id))
    assert not result.accepted
    assert not carrier.hangar_component.docked_units


def test_allied_pending_load_still_reserves_colony_population():
    from domain.celestials import Moon
    from unit_components.colony import ColonyComponent
    from unit_orders.colony import LoadColonistsOrder
    game = campaign()
    player, ally = game.players
    ally.team_id = player.team_id
    source = Moon((0, 0), 'Sol')
    source.owner, source.population = player, 50
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.celestial_bodies.append(source)
    game.galaxy.systems['Sol'].celestial_bodies_by_id[source.id] = source
    first = ship(game, owner=1)
    first.position = Position(2000, 0)
    first.add_component(ColonyComponent(first))
    first.add_component(Engines(first, speed=100))
    first.commander_component.add_order(LoadColonistsOrder(first, {'target_id': source.id, 'amount': 40}))
    second = ship(game)
    second.add_component(ColonyComponent(second))
    result = issue(game, player, Command('load_colonists', (second.id,), target_id=source.id, amount=20))
    assert not result.accepted
    assert result.errors[0].code == 'insufficient_population'
    assert source.population == 50
