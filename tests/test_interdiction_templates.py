"""Public interdiction specialists work through construction, turns and saves."""
import pytest

from constants import HullSize
from game_ai.contracts import Command
from game_ai.observation import build_observation
from geometry import Position
from player_controller import PlayerController
from save_manager import deserialize_game_state, serialize_game_state
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from turn_processor import TurnProcessor
from unit_components.constructor import Constructor, instantiate_unit_from_template
from unit_components.inhibitor import HyperspaceInhibitionFieldEmitter
from unit_components.enums import JumpStatus
from unit_orders.base import OrderStatus
from unit_orders.movement import ReachWaypointOrder


@pytest.mark.parametrize('controller', list(PlayerController))
@pytest.mark.parametrize('key,radius,capacity,burn,mobile', [
    ('INTERDICTION_FRIGATE', 600, 200, 6, True),
    ('INTERDICTION_STATION', 900, 300, 9, False),
])
def test_medium_specialists_build_and_operate_for_every_controller(
        controller, key, radius, capacity, burn, mobile):
    game = campaign()
    owner = game.players[0]
    owner.controller = controller
    builder = ship(game, 'Builder')
    builder.add_component(Constructor(builder))
    observation = build_observation(game, owner)
    entry = next(t for t in observation['action_catalogs']['construction_templates']
                 if t['template_name'] == key)
    assert entry['kind'] == ('ship' if mobile else 'station')
    assert entry['hull_size'] == 'MEDIUM'
    assert entry['resource_cost'] == {'credits': 2000, 'metal': 75, 'crystal': 25}
    assert entry['support']['inhibitor'] == {
        'inhibitor_radius': radius, 'antimatter_cost_per_turn': burn}
    assert builder.constructor_component.can_build(key) is not None
    balances = owner.credits, owner.metal, owner.crystal
    result = issue(game, owner, Command('construct', (builder.id,), template_name=key,
                   system_name='Sol', hex_coord=(0, 0), position=(200, 0)))
    assert result.accepted, result.errors
    paid_balances = balances[0] - 2000, balances[1] - 75, balances[2] - 25
    assert (owner.credits, owner.metal, owner.crystal) == paid_balances
    for _ in range(20):
        builder.constructor_component.update(game.galaxy)
    assert builder.constructor_component.current_construction_target is None
    unit = next(u for u in game.galaxy.systems['Sol'].hexes[(0, 0)].units
                if u.template_name == entry['name'])
    assert (owner.credits, owner.metal, owner.crystal) == paid_balances
    assert unit.hull_size == HullSize.MEDIUM
    assert unit.current_hull_usage == unit.hull_capacity == 50
    assert bool(unit.engines_component) == bool(unit.hyperdrive_component) == mobile
    assert len(unit.weapons_component.turrets) == 1
    assert unit.antimatter_component.current_amount == capacity
    assert not unit.inhibitor_component.is_active

    assert issue(game, owner, Command('toggle_inhibitor', (unit.id,))).accepted
    assert unit.antimatter_component.current_amount == capacity
    view = next(u for u in build_observation(game, owner)['units'] if u['id'] == unit.id)
    assert view['capability_details']['inhibitor']['antimatter_cost_per_turn'] == burn
    assert view['capability_details']['inhibitor']['is_active']
    assert unit.antimatter_component.current_amount == capacity
    processor = TurnProcessor(game)
    processor.process_player_turn(game.players[1])
    assert unit.antimatter_component.current_amount == capacity
    processor.process_player_turn(owner)
    assert unit.antimatter_component.current_amount == capacity - burn


def test_saved_installed_inhibitor_keeps_historical_equipment_and_gets_new_fuel_rate():
    game = campaign()
    unit = ship(game, 'Existing Interdictor', hull=HullSize.LARGE)
    emitter = HyperspaceInhibitionFieldEmitter(unit, radius=705.0, hull_cost=47.0)
    unit.add_component(emitter)
    emitter.current_hit_points = 400
    unit.antimatter_component.current_amount = 80
    assert emitter.set_active(True, game.galaxy).allowed
    hull_usage = unit.current_hull_usage

    restored = campaign()
    assert deserialize_game_state(restored, serialize_game_state(game))
    saved = restored.galaxy.get_unit_by_id(unit.id)
    emitter = saved.inhibitor_component
    assert saved.current_hull_usage == hull_usage
    assert emitter.radius == 705
    assert emitter.hull_cost == 47
    assert emitter.max_hit_points == 470
    assert emitter.current_hit_points == 400
    assert emitter.is_active
    assert saved.antimatter_component.current_amount == 80
    sector = restored.galaxy.systems['Sol'].hexes[(0, 0)]
    assert sector.dynamic_inhibition_zones[saved.id].radius == 705
    emitter.update()
    assert saved.antimatter_component.current_amount == pytest.approx(72.95)
    assert emitter.is_active


@pytest.mark.parametrize('relation', ['owner', 'ally', 'enemy'])
@pytest.mark.parametrize('field_at', ['origin', 'destination'])
def test_active_field_blocks_jumps_for_every_faction_until_deactivated(relation, field_at):
    game = campaign()
    owner = game.players[0]
    traveller_owner = owner if relation == 'owner' else game.players[1]
    if relation == 'ally':
        traveller_owner.team_id = owner.team_id
    field_sector = (0, 0) if field_at == 'origin' else (1, 0)
    station = instantiate_unit_from_template('INTERDICTION_STATION', owner, 'Sol',
        field_sector, Position(0, 0), game.galaxy, game)
    traveller = instantiate_unit_from_template('INTERDICTION_FRIGATE', traveller_owner,
        'Sol', (0, 0), Position(100, 0), game.galaxy, game)
    assert issue(game, owner, Command('toggle_inhibitor', (station.id,))).accepted
    destination = Position(100, 0)
    params = {'destination_system_name': 'Sol', 'destination_hex_coord': (1, 0),
              'destination_position': destination}
    order = ReachWaypointOrder(traveller, params)
    traveller.commander_component.add_order(order)
    fuel = traveller.antimatter_component.current_amount
    processor = TurnProcessor(game)
    processor._process_movement(traveller_owner)
    assert traveller.in_hex == (0, 0)
    assert traveller.antimatter_component.current_amount == fuel
    assert traveller.hyperdrive_component.jump_status == JumpStatus.ERROR
    order.check_completion_conditions()
    assert order.status == OrderStatus.FAILED

    assert issue(game, owner, Command('toggle_inhibitor', (station.id,))).accepted
    traveller.commander_component.clear_explicit_orders()
    traveller.commander_component.add_order(ReachWaypointOrder(traveller, params))
    processor._process_movement(traveller_owner)
    assert traveller.in_hex == (1, 0)
    assert traveller.position == destination
    assert traveller.antimatter_component.current_amount == fuel - 10
    assert traveller.hyperdrive_component.jump_status == JumpStatus.CHARGING
