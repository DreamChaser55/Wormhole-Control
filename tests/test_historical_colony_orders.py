"""Remembered ownership authorizes travel, but never authorizes unseen effects."""
from copy import deepcopy
import random
from types import SimpleNamespace

import pytest

from constants import PlanetType
from domain.celestials import Planet, Moon, ColonizableAsteroid
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch
from game_ai.observation import build_observation
from geometry import Position
from planetary_intel import ownership_view, order_phase, refresh, revalidate_colony_orders
from planetary_warfare import process_actions
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from unit_components.antimatter import AntimatterStorage
from unit_components.colony import ColonyComponent
from unit_components.intelligence import IntelligenceComponent
from unit_components.movement import Engines
from unit_components.planetary import TroopTransportComponent, SiegeBatteryComponent
from unit_orders.base import OrderStatus
from unit_orders.movement import MoveOrder


KINDS = ('colonize', 'load_colonists', 'recruit_troops', 'bombard_planet', 'invade_planet', 'infiltrate_planet')
COLONY_CASES = [(kind, False) for kind in KINDS] + [pytest.param('colonize', True, id='colonize_unknown')]


def scenario(kind, cls=Moon, *, approaching=False, unknown=False):
    game = campaign()
    game.galaxy.game = game
    body = cls((0, 0), 'Sol', PlanetType.TERRAN) if cls is Planet else cls((0, 0), 'Sol')
    body.owner = None if kind == 'colonize' else game.players[1]
    body.population = 40 if body.owner else 0
    game.galaxy.systems['Sol'].add_celestial_body(body)
    unit = ship(game)
    unit.in_galaxy = game.galaxy
    for component in (Engines(unit, speed=100), AntimatterStorage(unit, max_capacity=200),
                      ColonyComponent(unit), IntelligenceComponent(unit),
                      TroopTransportComponent(unit), SiegeBatteryComponent(unit)):
        unit.add_component(component)
    unit.colony_component.population_cargo = 20 if kind == 'colonize' else 0
    unit.troop_transport_component.troops = 40 if kind == 'invade_planet' else 0
    unit.sensors_component.short_range_radius = unit.sensors_component.long_range_hexes = 0
    unit.position = Position(3000 if approaching else body.collision_radius + 150, 0)
    if kind == 'bombard_planet' and not approaching:
        unit.position = Position(body.collision_radius + 1000, 0)
    remembered_owner = game.players[0] if kind in {'load_colonists', 'recruit_troops'} else body.owner
    if not unknown:
        unit.owner.planetary_intel[body.id] = {'owner_id': remembered_owner.id if remembered_owner else None, 'observed_turn': 3}
    game.invasion_rng = random.Random(1)
    game.selected_objects = [unit]
    game.is_unit_visible = lambda candidate: candidate.owner == unit.owner
    game.hex_has_presence = lambda *args: False
    return game, body, unit


def command(unit, body, kind, *, queue=False):
    return Command(type=kind, unit_ids=(unit.id,), target_id=body.id, queue=queue,
                   amount=10 if kind in {'load_colonists', 'recruit_troops', 'invade_planet'} else None)


def issue(game, *commands):
    return CommandGateway(game).apply_batch(game.players[0], CommandBatch(commands))


def effects(game, body, unit):
    return (body.owner, body.population, body.fortification_level, body.defense_readiness,
            unit.owner.credits, unit.antimatter_component.current_amount,
            unit.colony_component.population_cargo, unit.troop_transport_component.troops,
            unit.intelligence_component.available_agents, game.invasion_rng.getstate(),
            unit.last_planetary_action_round)


@pytest.mark.parametrize('cls', [Planet, Moon, ColonizableAsteroid])
@pytest.mark.parametrize('kind, unknown', COLONY_CASES)
def test_historical_targets_are_discovered_and_issuable_without_hidden_statistics(cls, kind, unknown):
    from input_processor.context_menu_builder import build_sector_context_menu_options
    game, body, unit = scenario(kind, cls, approaching=True, unknown=unknown)
    def exposed():
        observation = build_observation(game, unit.owner)
        menu = build_sector_context_menu_options(game, body, body.position)[0]
        return observation, menu
    observation, menu = before = exposed()
    actor = next(item for item in observation['units'] if item['id'] == unit.id)
    assert kind in actor['legal_commands']
    assert any(item[1] == kind for item in menu)
    if kind == 'invade_planet':
        assert actor['command_options'][kind]['targets'][0]['success_probability'] is None
    # Both worlds have identical disclosed history, despite different live truth.
    body.owner = game.players[1] if body.owner is None else None
    body.population = 0.5
    body.fortification_level = 3
    body.defense_readiness = .25
    assert exposed() == before
    result = issue(game, command(unit, body, kind))
    assert result.accepted, result.errors
    root = unit.commander_component.current_order
    assert root.status == OrderStatus.IN_PROGRESS
    assert root.sub_orders
    assert ownership_view(game, unit.owner, body).observed_turn == (None if unknown else 3)


@pytest.mark.parametrize('kind, unknown', COLONY_CASES)
def test_waiting_preserves_effects_queue_and_order_identity_then_revalidates(kind, unknown):
    game, body, unit = scenario(kind, unknown=unknown)
    before = effects(game, body, unit)
    assert issue(game, command(unit, body, kind)).accepted
    root = unit.commander_component.current_order
    public_id = root.public_id
    followup = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
                               'destination_position': Position(3000, 0)})
    unit.commander_component.add_order(followup)
    for _ in range(3):
        unit.commander_component.prepare_for_movement()
        unit.commander_component.update()
        process_actions(game, unit.owner)
        revalidate_colony_orders(game)
        assert root.status == OrderStatus.IN_PROGRESS
        assert root.public_id == public_id
        assert order_phase(root, game.galaxy) == 'waiting_for_contact'
        assert list(unit.commander_component.orders_queue) == [followup]
        assert not unit.owner.order_history
        assert effects(game, body, unit) == before
    observed = build_observation(game, unit.owner)
    actor = next(item for item in observed['units'] if item['id'] == unit.id)
    assert actor['current_order']['progress']['phase'] == 'waiting_for_contact'
    from gui.sidebar.order_formatting import format_order_state_data
    assert any('Waiting for sensor contact' in text for text in format_order_state_data(root.get_state_data()))
    # Formerly owned sources are discovered captured; other targets remain valid.
    unit.sensors_component.long_range_hexes = 1
    refresh(game)
    revalidate_colony_orders(game)
    if kind in {'load_colonists', 'recruit_troops'}:
        assert root.status == OrderStatus.FAILED
        assert effects(game, body, unit) == before
        assert list(unit.commander_component.orders_queue) == [followup]
    else:
        root.update(game.galaxy)
        process_actions(game, unit.owner)
        assert effects(game, body, unit) != before
        assert root.status != OrderStatus.FAILED or root.failure_reason == 'assault_repulsed'
    assert ownership_view(game, unit.owner, body).observed_turn == game.turn_number


@pytest.mark.parametrize('kind, unknown', COLONY_CASES)
def test_reacquired_incompatible_owner_fails_once_before_effects(kind, unknown):
    game, body, unit = scenario(kind, approaching=True, unknown=unknown)
    assert issue(game, command(unit, body, kind)).accepted
    root = unit.commander_component.current_order
    children = list(root.sub_orders)
    body.owner = game.players[1] if kind in {'colonize', 'load_colonists', 'recruit_troops'} else None
    before = effects(game, body, unit)
    for _ in range(2):
        revalidate_colony_orders(game)
        assert root.status == OrderStatus.IN_PROGRESS and list(root.sub_orders) == children
    unit.sensors_component.long_range_hexes = 1
    refresh(game)
    for _ in range(2):
        revalidate_colony_orders(game)
    assert root.status == OrderStatus.FAILED
    assert not root.sub_orders
    assert len(unit.owner.order_history) == 1
    assert effects(game, body, unit) == before


@pytest.mark.parametrize('approaching', [False, True])
@pytest.mark.parametrize('kind, unknown', COLONY_CASES)
def test_save_load_preserves_historical_orders_without_effects(kind, approaching, unknown):
    game, body, unit = scenario(kind, approaching=approaching, unknown=unknown)
    assert issue(game, command(unit, body, kind)).accepted
    root = unit.commander_component.current_order
    # A harmless movement follow-up avoids capacity reservations for a second job.
    followup = Command(type='move', unit_ids=(unit.id,), system_name='Sol', hex_coord=(0, 0),
                       position=(3000, 100), queue=True)
    assert issue(game, followup).accepted
    recorded = deepcopy(unit.owner.planetary_intel)
    state = serialize_game_state(game)
    restored = SimpleNamespace()
    assert deserialize_game_state(restored, state)
    actor = restored.galaxy.get_unit_by_id(unit.id)
    target = restored.galaxy.get_celestial_body_by_id(body.id)
    loaded = actor.commander_component.current_order
    assert actor.owner.planetary_intel == recorded
    assert loaded.public_id == root.public_id and loaded.status == OrderStatus.IN_PROGRESS
    assert len(actor.commander_component.orders_queue) == 1
    assert order_phase(loaded, restored.galaxy) == ('approach' if approaching else 'waiting_for_contact')
    assert effects(restored, target, actor)[1:] == effects(game, body, unit)[1:]
    assert not actor.owner.order_history


@pytest.mark.parametrize('unknown', [False, True])
def test_stale_in_range_load_is_conditional_and_cannot_finance_replacement(unknown):
    game, source, unit = scenario('load_colonists')
    destination = Moon((1, 0), 'Sol')
    game.galaxy.systems['Sol'].add_celestial_body(destination)
    if not unknown:
        unit.owner.planetary_intel[destination.id] = {'owner_id': None, 'observed_turn': 3}
    load = command(unit, source, 'load_colonists')
    replace = command(unit, destination, 'colonize')
    before = effects(game, source, unit)
    rejected = issue(game, load, replace)
    assert not rejected.accepted and rejected.failure_stage == 'preflight'
    assert unit.commander_component.current_order is None
    assert effects(game, source, unit) == before
    queued = command(unit, destination, 'colonize', queue=True)
    accepted = issue(game, load, queued)
    assert accepted.accepted, accepted.errors
    assert effects(game, source, unit) == before
    assert unit.commander_component.current_order.order_type.name == 'LOAD_COLONISTS'
    assert len(unit.commander_component.orders_queue) == 1


def test_stale_recruitment_reserves_credits_and_supports_only_queued_invasion():
    game, source, unit = scenario('recruit_troops')
    destination = Moon((1, 0), 'Sol')
    destination.owner = game.players[1]
    game.galaxy.systems['Sol'].add_celestial_body(destination)
    unit.owner.planetary_intel[destination.id] = {'owner_id': destination.owner.id, 'observed_turn': 3}
    before = effects(game, source, unit)
    recruit = command(unit, source, 'recruit_troops')
    assert not issue(game, recruit, command(unit, destination, 'invade_planet')).accepted
    result = issue(game, recruit, command(unit, destination, 'invade_planet', queue=True))
    assert result.accepted, result.errors
    observation = build_observation(game, unit.owner)
    budget = observation['active_player']['resources']['resource_budget']
    assert budget['reserved']['credits'] == 20
    assert effects(game, source, unit) == before


@pytest.mark.parametrize('kind, unknown', COLONY_CASES)
def test_turn_processing_keeps_moving_toward_historical_targets(kind, unknown):
    from turn_processor import TurnProcessor
    game, body, unit = scenario(kind, approaching=True, unknown=unknown)
    assert issue(game, command(unit, body, kind)).accepted
    root = unit.commander_component.current_order
    start = unit.position.x
    processor = TurnProcessor(game)
    processor.process_player_turn(game.players[1])
    assert root.status == OrderStatus.IN_PROGRESS
    # Planetary orders start their movement children during the first unit update.
    for _ in range(2):
        processor.process_player_turn(unit.owner)
        game.turn_number += 1
    assert root.status == OrderStatus.IN_PROGRESS and unit.position.x < start
    assert order_phase(root, game.galaxy) == 'approach'
    assert ownership_view(game, unit.owner, body).status == ('unknown' if unknown else 'last_known')
    assert not unit.owner.order_history


@pytest.mark.parametrize('sensor_loss', ['damage', 'dust'])
def test_suppressed_contact_waits_and_recovers_without_observation_effects(sensor_loss):
    from constants import NebulaType
    from domain.celestials import Nebula
    game, body, unit = scenario('colonize')
    sensors = unit.sensors_component
    sensors.short_range_radius = 200
    if sensor_loss == 'damage':
        sensors.current_hit_points = 0
    else:
        cloud = Nebula((0, 0), 'Sol', NebulaType.DUST)
        game.galaxy.systems['Sol'].add_celestial_body(cloud)
    assert issue(game, command(unit, body, 'colonize')).accepted
    root = unit.commander_component.current_order
    root.update(game.galaxy)
    assert order_phase(root, game.galaxy) == 'waiting_for_contact'
    if sensor_loss == 'damage':
        sensors.current_hit_points = sensors.max_hit_points
    else:
        # The allied scout restores shared coverage without changing our range.
        from domain.players import Player
        game.players.append(Player('Ally', (0, 0, 200), team_id=unit.owner.team_id))
        observer = ship(game, 'observer', owner=2)
        observer.position = Position(body.collision_radius + 60, 0)
        observer.sensors_component.short_range_radius = 200
        observer.sensors_component.long_range_hexes = 0
    before = effects(game, body, unit)
    build_observation(game, unit.owner)
    assert unit.owner.planetary_intel[body.id]['observed_turn'] == game.turn_number
    assert effects(game, body, unit) == before
    assert root.status == OrderStatus.IN_PROGRESS
    root.update(game.galaxy)
    assert root.status == OrderStatus.COMPLETED


def test_commit_rejects_newly_disclosed_incompatible_owner_before_replacement(monkeypatch):
    game, body, unit = scenario('colonize')
    existing = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
                                'destination_position': Position(3000, 0)})
    unit.commander_component.add_order(existing)
    gateway = CommandGateway(game)
    original = gateway._require_colony_target
    calls = 0
    def reveal(player, target, kind):
        nonlocal calls
        calls += 1
        if calls == 2:
            body.owner = game.players[1]
            unit.sensors_component.long_range_hexes = 1
        return original(player, target, kind)
    monkeypatch.setattr(gateway, '_require_colony_target', reveal)
    result = gateway.apply_batch(unit.owner, CommandBatch((command(unit, body, 'colonize'),)))
    assert not result.accepted
    assert unit.commander_component.current_order is existing
    assert unit.colony_component.population_cargo == 20


@pytest.mark.parametrize('kind', ['colonize', 'infiltrate_planet'])
def test_immediate_colony_action_retries_after_contact_loss_without_double_effect(kind):
    game, body, unit = scenario(kind)
    assert issue(game, command(unit, body, kind)).accepted
    root = unit.commander_component.current_order
    unit.sensors_component.short_range_radius = 200
    root.update(game.galaxy)
    assert root.status == OrderStatus.COMPLETED
    after = effects(game, body, unit)
    root.update(game.galaxy)
    root.execute(game.galaxy)
    assert effects(game, body, unit) == after


@pytest.mark.parametrize('unknown', [False, True])
def test_movement_reacquires_surface_contact_and_finishes_colonization(unknown):
    from turn_processor import TurnProcessor
    game, body, unit = scenario('colonize', approaching=True, unknown=unknown)
    unit.sensors_component.short_range_radius = 200
    unit.position = Position(body.collision_radius + 340, 0)
    assert issue(game, command(unit, body, 'colonize')).accepted
    root = unit.commander_component.current_order
    processor = TurnProcessor(game)
    for _ in range(4):
        processor.process_player_turn(unit.owner)
        if root.status == OrderStatus.COMPLETED:
            break
    assert root.status == OrderStatus.COMPLETED
    assert body.owner == unit.owner and body.population == 20
    assert unit.colony_component.population_cargo == 0
    assert unit.owner.planetary_intel[body.id]['observed_turn'] == game.turn_number


@pytest.mark.parametrize('kind, unknown', [(kind, False) for kind in
                                         ('colonize', 'load_colonists', 'infiltrate_planet')]
                         + [pytest.param('colonize', True, id='colonize_unknown')])
def test_human_events_accept_historical_targets_and_wait(kind, unknown):
    from events import EventBus
    from order_system import OrderSystem
    game, body, unit = scenario(kind, unknown=unknown)
    system = OrderSystem(game, EventBus())
    event = SimpleNamespace(units=[unit], target_body=body, amount=10, shift_pressed=False,
                            target_system=body.in_system, target_hex=body.in_hex)
    getattr(system, 'handle_' + kind)(event)
    root = unit.commander_component.current_order
    assert root.order_type.name.lower() == kind
    assert root.status == OrderStatus.IN_PROGRESS
    assert order_phase(root, game.galaxy) == 'waiting_for_contact'


@pytest.mark.parametrize('controller', ['codex', 'openai'])
@pytest.mark.parametrize('kind, unknown', COLONY_CASES)
def test_automated_controllers_accept_historical_orders(controller, kind, unknown):
    from player_controller import PlayerController
    game, body, unit = scenario(kind, unknown=unknown)
    game.current_player = unit.owner
    unit.owner.controller = PlayerController(controller)
    cmd = command(unit, body, kind)
    before = effects(game, body, unit)
    if controller == 'codex':
        from game_control_protocol import ControlService
        service = ControlService(game, port=0)
        try:
            observed = service._dispatch('observe', 'observe-history', {})
            assert observed['ok'], observed
            result = service._dispatch('command', 'command-history', {
                'turn_token': observed['data']['turn_token'], 'commands': [cmd.to_dict()]})
            assert result['ok'] and result['data']['accepted'], result
        finally:
            service.shutdown()
    else:
        from game_ai.adapters.base import PlanningResult
        from game_ai.adapters.fake import FakePlanningProvider
        from game_ai.contracts import TurnPlan
        from game_ai.coordinator import AgentTurnCoordinator
        game.gui = None
        game.end_turn = lambda: None
        plan = TurnPlan.from_dict(dict(plan=[], commands=[cmd.to_dict()],
            memory_patch={key: None for key in ('strategy', 'objectives', 'commitments', 'beliefs', 'lessons', 'misc')},
            end_turn=True), strict=True)
        coordinator = AgentTurnCoordinator(game, provider=FakePlanningProvider([]))
        try:
            coordinator._write_memory = lambda *_args: None
            coordinator._record_telemetry = lambda *_args, **_kwargs: None
            coordinator._apply_result(PlanningResult(plan, 'fake', 'gpt-6-luna', 'medium'))
        finally:
            coordinator.shutdown()
    assert unit.commander_component.current_order.status == OrderStatus.IN_PROGRESS
    assert effects(game, body, unit) == before


@pytest.mark.parametrize('known_owner', ['self', 'ally', 'enemy'])
@pytest.mark.parametrize('current', [False, True])
def test_known_occupied_colonization_rejected_without_replacing_orders(known_owner, current):
    from events import EventBus
    from input_processor.context_menu_builder import build_sector_context_menu_options
    from order_system import OrderSystem
    game, body, unit = scenario('colonize', approaching=True)
    owner = unit.owner if known_owner == 'self' else game.players[1]
    if known_owner == 'ally':
        owner.team_id = unit.owner.team_id
    unit.owner.planetary_intel[body.id] = {'owner_id': owner.id, 'observed_turn': 3}
    if current:
        body.owner = owner
        unit.sensors_component.long_range_hexes = 1
    existing = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
                                'destination_position': Position(3500, 0)})
    unit.commander_component.add_order(existing)
    actor = next(item for item in build_observation(game, unit.owner)['units'] if item['id'] == unit.id)
    assert body.id not in actor['command_options']['colonize']['target_ids']
    assert not any(item[1] == 'colonize' for item in build_sector_context_menu_options(game, body, body.position)[0])
    before = effects(game, body, unit)
    rejected = issue(game, command(unit, body, 'colonize'))
    assert not rejected.accepted and rejected.errors[0].code == 'invalid_target'
    OrderSystem(game, EventBus()).handle_colonize(SimpleNamespace(units=[unit], target_body=body, shift_pressed=False))
    assert unit.commander_component.current_order is existing
    assert effects(game, body, unit) == before


@pytest.mark.parametrize('target_kind', ['missing', 'gas_giant', 'metal_asteroid'])
def test_unknown_colonization_requires_an_existing_colonizable_body(target_kind):
    from domain.celestials import MetalAsteroid
    from planetary_intel import colony_target_blocker
    game, _, unit = scenario('colonize', unknown=True)
    body = None
    if target_kind == 'gas_giant':
        body = Planet((0, 0), 'Sol', PlanetType.GAS_GIANT)
    elif target_kind == 'metal_asteroid':
        body = MetalAsteroid((0, 0), 'Sol')
    if body is not None:
        game.galaxy.systems['Sol'].add_celestial_body(body)
    assert colony_target_blocker(game, unit.owner, body, 'colonize') == 'target_unavailable'
    target_id = body.id if body is not None else 999999
    actor = next(item for item in build_observation(game, unit.owner)['units'] if item['id'] == unit.id)
    assert target_id not in actor['command_options']['colonize']['target_ids']
    result = issue(game, Command(type='colonize', unit_ids=(unit.id,), target_id=target_id))
    assert not result.accepted
    assert unit.commander_component.current_order is None


def test_unknown_colonization_revalidates_new_contact_at_commit(monkeypatch):
    game, body, unit = scenario('colonize', approaching=True, unknown=True)
    body.owner = game.players[1]
    existing = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
                                'destination_position': Position(3500, 0)})
    unit.commander_component.add_order(existing)
    gateway = CommandGateway(game)
    original = gateway._require_colony_target
    calls = 0
    def acquire_contact(player, target, kind):
        nonlocal calls
        calls += 1
        if calls == 2:
            unit.sensors_component.long_range_hexes = 1
        return original(player, target, kind)
    monkeypatch.setattr(gateway, '_require_colony_target', acquire_contact)
    before = effects(game, body, unit)
    result = gateway.apply_batch(unit.owner, CommandBatch((command(unit, body, 'colonize'),)))
    assert not result.accepted and result.failure_stage == 'commit'
    assert unit.commander_component.current_order is existing
    assert effects(game, body, unit) == before
