"""Information, typed targets and static route blockers from the September playtest."""
from concurrent.futures import Future
from copy import deepcopy
import json
import random

import pytest

from constants import HullSize, PlanetType
from domain.celestials import Planet, MetalAsteroid
from galaxy import StarSystem
from game_ai.adapters.base import PlanningRequest
from game_ai.contracts import Command
from game_ai.observation import build_observation
from game_ai.order_view import order_layers
from game_ai.prompt_context import planning_context
from game_control_protocol import ControlService, PROTOCOL_VERSION
from geometry import Position, distance
from player_controller import PlayerController
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from tests.support.combat import create_combat_ship
from tests.support.commands import world, issue
from unit_components.antimatter import AntimatterStorage
from unit_components.mining import MiningComponent
from unit_components.movement import Engines, Hyperdrive
from unit_components.enums import HyperdriveType
from unit_orders.gas_giant import EnterGasGiantOrder
from unit_orders.movement import MoveOrder


@pytest.mark.parametrize('fuel,damaged', [(0, False), (73.25, False), (10, True)])
def test_enemy_fuel_is_private_in_socket_and_provider_but_allied_fuel_remains(fuel, damaged):
    game, player, enemy, own = world()
    game.campaign_id, game.game_started, game.current_player = 'fuel-boundary', True, player
    game.view_mode = 'galaxy'
    player.controller = PlayerController.CODEX
    own.add_component(AntimatterStorage(own, max_capacity=400))
    target = create_combat_ship(game.galaxy, enemy, 'Contact', (0, 0), pos=(100, 0))
    target.add_component(AntimatterStorage(target, max_capacity=300))
    target.antimatter_component.current_amount = fuel
    if damaged:
        target.antimatter_component.current_hit_points = 0
    service = ControlService(game, port=0)
    response = service._dispatch_or_wait({'protocol_version': PROTOCOL_VERSION,
        'action': 'observe', 'request_id': 'fuel'}, Future())
    assert response['ok']
    socket = response['data']['observation']
    messages, _ = planning_context(PlanningRequest(game.campaign_id, player.agent_id, player.name, 1, socket, {}))
    provider = json.loads(messages[-1]['content'])['observation']
    for observed in (socket, provider):
        contact = next(unit for unit in observed['units'] if unit['id'] == target.id)
        assert 'antimatter' not in contact
        assert set(contact['capability_details']) <= {'weapons', 'defenses'}
        assert next(unit for unit in observed['units'] if unit['id'] == own.id)['antimatter']['maximum'] == 400
    enemy.team_id = player.team_id
    ally = next(unit for unit in build_observation(game, player)['units'] if unit['id'] == target.id)
    assert ally['antimatter'] == {'current': fuel, 'maximum': 300}


def test_disclosed_gas_giant_target_and_journey_survive_save_without_leaking_hidden_geometry():
    game = campaign()
    game.galaxy.game = game
    unit = ship(game)
    unit.add_component(Engines(unit, speed=100))
    unit.add_component(AntimatterStorage(unit, max_capacity=500))
    planet = Planet((0, 0), 'Sol', PlanetType.GAS_GIANT)
    planet.position = Position(2000, 0)
    game.galaxy.systems['Sol'].add_celestial_body(planet)
    root = EnterGasGiantOrder(unit, {'target_id': planet.id})
    unit.commander_component.add_order(root)
    before = (random.getstate(), deepcopy(unit.owner.order_history))
    def check(actor):
        visible = order_layers(actor, 'self', {actor.id}, {planet.id})['current_order']
        assert visible['target_id'] == planet.id and visible['target_visibility'] == 'visible'
        assert visible['progress']['journey']['estimated_remaining_owner_turns'] > 0
        assert visible['suborders'][0]['target_id'] == planet.id
        assert actor.commander_component.current_order.sub_orders[0].primary_target_reference() == ('celestial', planet.id)
        hidden = order_layers(actor, 'self', {actor.id}, set())['current_order']
        assert hidden['target_id'] is None and hidden['parameters'] == {}
        assert 'journey' not in hidden['progress']
        assert hidden['suborders'][0]['parameters'] == {}
    check(unit)
    assert before == (random.getstate(), unit.owner.order_history)
    saved = json.loads(json.dumps(serialize_game_state(game)))
    assert deserialize_game_state(game, saved)
    restored = game.galaxy.get_unit_by_id(unit.id)
    assert restored.commander_component.current_order.public_id == root.public_id
    check(restored)


@pytest.mark.parametrize('kind', ['mine', 'continuous_mine'])
@pytest.mark.parametrize('blocked', ['basic_drive', 'no_drive', 'diameter'])
def test_impossible_mining_targets_reject_atomically_and_preserve_work(kind, blocked):
    game, player, _, unit = world()
    unit.add_component(MiningComponent(unit))
    unit.add_component(AntimatterStorage(unit, max_capacity=400))
    other = StarSystem('Beta', Position(100, 0), radius=3)
    other.in_galaxy = game.galaxy
    game.galaxy.systems['Beta'] = other
    asteroid = MetalAsteroid((0, 0), 'Beta')
    other.add_celestial_body(asteroid)
    game.galaxy.system_graph = {'Sol': {'Beta': HullSize.TINY if blocked == 'diameter' else HullSize.TITAN},
                               'Beta': {'Sol': HullSize.TITAN}}
    if blocked == 'no_drive':
        unit.remove_component(Hyperdrive)
    elif blocked == 'diameter':
        unit.add_component(Hyperdrive(unit, HyperdriveType.ADVANCED, jump_range=3))
    root = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
                            'destination_position': Position(800, 0)})
    unit.commander_component.add_order(root)
    view = next(item for item in build_observation(game, player)['units'] if item['id'] == unit.id)
    assert asteroid.id not in view['command_options'][kind]['target_ids']
    original = (unit.name, deepcopy(player.order_history), random.getstate())
    verdict = issue(game, player, Command('rename_unit', (unit.id,), new_name='Replaced'), Command(kind, (unit.id,), target_id=asteroid.id))
    assert not verdict.accepted and verdict.failure_stage == 'preflight'
    assert verdict.errors[0].code == {'basic_drive': 'system_unreachable', 'no_drive': 'hyperdrive_unavailable', 'diameter': 'path_unavailable'}[blocked]
    assert unit.commander_component.current_order is root
    assert original == (unit.name, player.order_history, random.getstate())


def test_feasible_mining_uses_surface_approach_in_another_sector():
    game, player, _, unit = world()
    unit.add_component(MiningComponent(unit, mining_range=300))
    unit.add_component(AntimatterStorage(unit, max_capacity=400))
    asteroid = MetalAsteroid((0, 1), 'Sol')
    game.galaxy.systems['Sol'].add_celestial_body(asteroid)
    result = issue(game, player, Command('mine', (unit.id,), target_id=asteroid.id))
    assert result.accepted
    move = unit.commander_component.current_order.sub_orders[0]
    assert move.primary_target_reference() == ('celestial', asteroid.id)
    assert asteroid.collision_radius + 50 <= distance(move.parameters['destination_position'], asteroid.position) < 300
    from turn_processor import TurnProcessor
    for _ in range(180):
        TurnProcessor(game).process_player_turn(player)
        game.turn_number += 1
        if unit.mining_component.raw_metal_cargo > 0:
            break
    assert unit.in_hex == asteroid.in_hex
    assert unit.mining_component.raw_metal_cargo > 0
    assert not any(event.get('status') == 'failed' for event in player.order_history)


def test_titan_entry_matches_shared_rules_and_compact_sidebar():
    from celestial_descriptions import describe_body
    from gui.sidebar.celestial_formatting import body_summary
    game = campaign()
    unit = ship(game, hull=HullSize.TITAN)
    unit.add_component(Engines(unit, speed=100))
    planet = Planet((0, 0), 'Sol', PlanetType.GAS_GIANT)
    assert planet.can_hide_unit(unit)
    profile = describe_body(planet)
    assert any('Tiny through Titan' in text for text in profile.rules)
    assert any('Tiny–Titan' in row.text for row in body_summary(planet, profile))


def test_infiltration_utility_routes_also_reject_known_drive_limits():
    from unit_components.intelligence import IntelligenceComponent
    game, player, enemy, unit = world()
    unit.add_component(IntelligenceComponent(unit))
    other = StarSystem('Beta', Position(100, 0), radius=3)
    other.in_galaxy = game.galaxy
    game.galaxy.systems['Beta'] = other
    game.galaxy.system_graph = {'Sol': {'Beta': HullSize.TITAN}, 'Beta': {'Sol': HullSize.TITAN}}
    body = Planet((0, 0), 'Beta', PlanetType.TERRAN)
    body.owner = enemy
    body.population = 40
    other.add_celestial_body(body)
    player.planetary_intel[body.id] = {'owner_id': enemy.id, 'observed_turn': 1}
    root = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
                            'destination_position': Position(800, 0)})
    unit.commander_component.add_order(root)
    view = next(actor for actor in build_observation(game, player)['units'] if actor['id'] == unit.id)
    assert body.id not in view['command_options']['infiltrate_planet']['target_ids']
    result = issue(game, player, Command('infiltrate_planet', (unit.id,), target_id=body.id))
    assert not result.accepted and result.errors[0].code == 'system_unreachable'
    assert unit.commander_component.current_order is root and not player.order_history
