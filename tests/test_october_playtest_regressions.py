"""October playtest defects checked through commands and real owner resolutions."""
from copy import deepcopy

import pytest

from campaign_graph import is_deployed
from constants import HullSize, PlanetType, StarType
from domain.celestials import Planet, Star, MetalAsteroid
from events import IssueMoveOrderEvent
from game_ai.commands import resource_budget_view
from game_ai.contracts import Command
from game_ai.observation import build_observation
from game_ai.order_view import public_journey_progress
from geometry import Position, distance
from order_system import OrderSystem
from resource_costs import resource_balances
from strikecraft_service import process as process_service
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from turn_processor import TurnProcessor
from unit_components.antimatter import AntimatterHarvester, AntimatterStorage
from unit_components.constructor import Constructor
from unit_components.enums import HyperdriveType, TurretType, WingType
from unit_components.intelligence import Agent, IntelligenceComponent
from unit_components.movement import Engines, Hyperdrive
from unit_components.sensors import Sensors
from unit_components.strikecraft import StrikecraftBayComponent, StrikecraftWingComponent
from unit_components.weapons import Weapons, Turret
from unit_orders.base import OrderStatus
from unit_orders.movement import MoveOrder


def mobile(game, name, position, *, speed=100, fuel=600):
    unit = ship(game, name, hull=HullSize.MEDIUM)
    unit.position = Position(*position)
    unit.add_component(Engines(unit, speed=speed))
    unit.add_component(AntimatterStorage(unit, max_capacity=600))
    unit.antimatter_component.current_amount = fuel
    return unit


def resolve(game):
    TurnProcessor(game).process_player_turn(game.players[0])
    game.turn_number += 1


@pytest.mark.parametrize('harvesting,moving_endpoint', [(False, 'recipient'), (True, 'recipient'), (False, 'source')])
@pytest.mark.parametrize('manual', [False, True])
@pytest.mark.parametrize('remote', [False, True])
def test_continuous_deliveries_advance_while_endpoint_moves(harvesting, manual, moving_endpoint, remote):
    game = campaign()
    actor = mobile(game, 'Supplier', (1000, 0))
    target = mobile(game, 'Recipient', (3500, 0), speed=40, fuel=100)
    if harvesting:
        source = Star(in_system='Sol', star_type=StarType.G_TYPE)
        source.in_hex = (0, 0)
        game.galaxy.systems['Sol'].add_celestial_body(source)
        actor.add_component(AntimatterHarvester(actor))
    else:
        source = mobile(game, 'Source', (1050, 0), speed=40)
    kind = 'continuous_resupply' if harvesting else 'continuous_antimatter_transport'
    if moving_endpoint == 'source':
        actor.antimatter_component.current_amount = 100
        source.position = Position(3500, 0)
        target.position = Position(1000, 1000)
    moving = target if moving_endpoint == 'recipient' else source
    if remote:
        actor.add_component(Hyperdrive(actor, drive_type=HyperdriveType.ADVANCED, jump_range=5))
        game.galaxy.systems['Sol'].move_unit_between_hexes(moving, (1, 0))
    assert issue(game, actor.owner,
        Command('move', (moving.id,), system_name='Sol', hex_coord=moving.in_hex, position=(3500, 1800)),
        Command(kind, (actor.id,), source_id=source.id, target_id=target.id if manual else None)).accepted
    root = actor.commander_component.current_order
    positions = []
    for _ in range(12):
        resolve(game)
        positions.append(actor.position.to_tuple())
        assert root.status == OrderStatus.IN_PROGRESS
    assert len(set(positions[2:])) >= 4  # Inter-sector routes also wait for drive recharge.
    # A slower moving recipient remains on its own work throughout the pursuit.
    assert moving.position.y > 0 and moving.commander_component.current_order is not None
    for _ in range(100):
        resolve(game)
        if target.antimatter_component.current_amount > 100:
            break
    assert target.antimatter_component.current_amount > 100


@pytest.mark.parametrize('remote', [False, True])
@pytest.mark.parametrize('body_type', ['planet', 'star', 'asteroid'])
@pytest.mark.parametrize('destination', ['center', 'surface', 'clearance', 'boundary'])
@pytest.mark.parametrize('human', [False, True])
def test_impossible_move_preserves_paid_build_and_queued_reservation(remote, body_type, destination, human):
    game = campaign()
    game.gui = None
    actor = mobile(game, 'Builder', (1500, 0))
    actor.add_component(Constructor(actor))
    actor.add_component(Hyperdrive(actor, drive_type=HyperdriveType.ADVANCED, jump_range=5))
    actor.add_component(Sensors(actor, long_range_hexes=2))
    coord = (1, 0) if remote else (0, 0)
    body = (Planet(coord, 'Sol', PlanetType.TERRAN) if body_type == 'planet' else
            Star(in_system='Sol', star_type=StarType.G_TYPE) if body_type == 'star' else
            MetalAsteroid(coord, 'Sol'))
    body.in_hex = coord
    game.galaxy.systems['Sol'].add_celestial_body(body)
    build = Command('construct', (actor.id,), template_name='SHIPYARD_MK1',
                    system_name='Sol', hex_coord=(0, 0), position=(1600, 0))
    treasury_before_build = resource_balances(actor.owner)
    assert issue(game, actor.owner, build, Command(**{**vars(build), 'queue': True})).accepted
    root = actor.commander_component.current_order
    queued = tuple(actor.commander_component.orders_queue)
    before = resource_balances(actor.owner)
    budget = resource_budget_view(game, actor.owner)
    history = deepcopy(actor.owner.order_history)
    job = deepcopy(actor.constructor_component.current_construction_target)
    pos = {'center': (0, 0), 'surface': (body.collision_radius, 0),
           'clearance': (body.collision_radius + 25, 0), 'boundary': (5001, 0)}[destination]
    if human:
        from unittest.mock import Mock
        OrderSystem(game, Mock()).handle_issue_move_order(
            IssueMoveOrderEvent([actor], 'Sol', coord, Position(*pos), False))
    else:
        result = issue(game, actor.owner,
            Command('rename_unit', (actor.id,), new_name='Changed'),
            Command('move', (actor.id,), system_name='Sol', hex_coord=coord, position=pos))
        assert not result.accepted and result.applied_count == 0
        assert result.errors[0].code == 'invalid_destination'
    assert actor.name == 'Builder'
    assert actor.commander_component.current_order is root and root.status == OrderStatus.IN_PROGRESS
    assert tuple(actor.commander_component.orders_queue) == queued
    assert resource_balances(actor.owner) == before
    assert resource_budget_view(game, actor.owner) == budget
    assert actor.owner.order_history == history
    assert actor.constructor_component.current_construction_target == job
    actor.commander_component.clear_explicit_orders()
    actor.commander_component.clear_explicit_orders()
    assert resource_balances(actor.owner) == treasury_before_build


def test_direct_move_cannot_land_inside_solid_body():
    game = campaign()
    unit = mobile(game, 'Traveller', (1500, 0))
    planet = Planet((1, 0), 'Sol', PlanetType.TERRAN)
    game.galaxy.systems['Sol'].add_celestial_body(planet)
    unit.add_component(Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5))
    order = MoveOrder(unit, dict(destination_system_name='Sol', destination_hex_coord=(1, 0),
                           destination_position=Position(0, 0)))
    order.execute(game.galaxy)
    assert order.status == OrderStatus.FAILED and order.failure_reason == 'path_unavailable'
    assert not order.sub_orders and unit.hyperdrive_component.hex_jump_target is None


def wing_world():
    game = campaign()
    game.galaxy.game = game
    carrier = mobile(game, 'Carrier', (100, 0))
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=2))
    carrier.add_component(Sensors(carrier, short_range_radius=3000, long_range_hexes=2))
    wing = ship(game, 'Wing', hull=HullSize.STRIKECRAFT_WING)
    wing.position = Position(1500, 0)
    wing.remove_component(AntimatterStorage)
    wing.add_component(Engines(wing, speed=100))
    wing.add_component(StrikecraftWingComponent(wing, WingType.FIGHTER))
    weapons = Weapons(wing)
    weapons.add_turret(Turret(TurretType.MASS_DRIVER, 4, 200, 2, wing))
    wing.add_component(weapons)
    bay = carrier.strikecraft_bay_component
    bay.assign_wing(wing, 0)
    bay.launched_units.append(wing)
    wing.strikecraft_wing_component.mother_carrier = carrier
    return game, carrier, wing


@pytest.mark.parametrize('kind', ['move', 'patrol', 'dock', 'return_for_service'])
def test_tankless_wing_journey_matches_actual_flight(kind):
    game, carrier, wing = wing_world()
    if kind == 'return_for_service':
        wing.strikecraft_wing_component.turns_outside = 79
        process_service(game, wing.owner, advance=True)
    else:
        command = (Command('dock_in_strikecraft_bay', (wing.id,), target_id=carrier.id) if kind == 'dock' else
                   Command(kind, (wing.id,), system_name='Sol', hex_coord=(0, 0), position=(3000, 0)))
        assert issue(game, wing.owner, command).accepted
    for _ in range(3):
        journey = public_journey_progress(game, wing.owner, wing)
        assert journey['waiting_reason'] is None
        assert journey['next_step_antimatter'] == journey['estimated_remaining_antimatter'] == 0
        before = Position(*wing.position.to_tuple())
        resolve(game)
        assert distance(before, wing.position) > 0


@pytest.mark.parametrize('bulk', [False, True])
def test_live_and_projected_service_launch_errors_match(bulk):
    game, carrier, wing = wing_world()
    wing.position = Position(150, 0)
    dock = Command('dock_in_strikecraft_bay', (wing.id,), target_id=carrier.id)
    launch = (Command('deploy_all_wings', (carrier.id,)) if bulk else
              Command('deploy_unit', (carrier.id,), target_id=wing.id))
    projected = issue(game, wing.owner, dock, launch)
    assert projected.errors[0].code == 'wing_service_required'
    assert is_deployed(wing, game.galaxy)
    assert issue(game, wing.owner, dock).accepted
    live = issue(game, wing.owner, launch)
    assert not live.accepted and live.errors[0].code == projected.errors[0].code
    assert wing in carrier.strikecraft_bay_component.docked_units


def test_deployment_requires_fresh_observation_before_new_actor_commands():
    game, carrier, wing = wing_world()
    wing.position = Position(150, 0)
    assert issue(game, wing.owner, Command('dock_in_strikecraft_bay', (wing.id,), target_id=carrier.id)).accepted
    game.turn_number += 1
    launch = Command('deploy_unit', (carrier.id,), target_id=wing.id)
    stance = Command('set_stance', (wing.id,), stance='attack_weapon_range')
    result = issue(game, wing.owner, launch, stance)
    assert not result.accepted and result.errors[0].code == 'unit_unavailable'
    assert wing in carrier.strikecraft_bay_component.docked_units
    assert issue(game, wing.owner, launch).accepted
    observed = build_observation(game, wing.owner)
    view = next(u for u in observed['units'] if u['id'] == wing.id)
    assert 'set_stance' in view['legal_commands']
    assert issue(game, wing.owner, stance).accepted
    guidance = next(u for u in observed['units'] if u['id'] == carrier.id)['command_options']['deploy_unit']
    assert guidance['requires_observation_after']


def test_hull_enums_are_readable_in_units_and_connections():
    game, carrier, wing = wing_world()
    game.galaxy.system_graph = {'Sol': {'Beta': HullSize.LARGE}}
    observation = build_observation(game, wing.owner)
    views = {u['id']: u for u in observation['units']}
    assert views[carrier.id]['hull_size'] == 'MEDIUM'
    assert views[wing.id]['hull_size'] == 'STRIKECRAFT_WING'
    sol = next(s for s in observation['systems'] if s['name'] == 'Sol')
    assert sol['connections'][0]['maximum_hull'] == 'LARGE'


@pytest.mark.parametrize('seed', [42, 17, 123, 2026, 20261002])
def test_normal_builders_and_harvesters_start_near_home_inhibition_edge(seed):
    from game_settings import GameSettings, PlayerConfig
    from game_setup import prepare_new_campaign
    from campaign_graph import iter_units
    from constants import SECTOR_CIRCLE_RADIUS_LOGICAL
    game = prepare_new_campaign(GameSettings(seed=seed, num_systems=2,
        system_radius_min=3, system_radius_max=3, player_configs=[
            PlayerConfig('One', (0, 200, 0), team_id=1),
            PlayerConfig('Two', (200, 0, 0), team_id=2)])).state
    for unit, _ in iter_units(game.galaxy):
        world = game.galaxy.get_celestial_body_by_id(unit.owner.homeworld_id)
        radius = distance(unit.position, world.position)
        assert world.collision_radius + 50 <= radius <= SECTOR_CIRCLE_RADIUS_LOGICAL
        if unit.colony_component:
            assert radius <= world.collision_radius + 250  # Prompt first loading approach.
        else:
            assert 0 < world.inhibition_field_radius - radius <= 250


@pytest.mark.parametrize('kind', ['move', 'patrol', 'defend', 'append_patrol_waypoints'])
def test_navigation_commands_share_endpoint_rejection(kind):
    game, _carrier, wing = wing_world()
    assert issue(game, wing.owner, Command('patrol', (wing.id,), system_name='Sol',
        hex_coord=(0, 0), position=(2500, 0))).accepted
    original = wing.commander_component.current_order
    params = dict(system_name='Sol', hex_coord=(0, 0), position=(6000, 0))
    if kind == 'append_patrol_waypoints':
        command = Command(kind, (wing.id,), order_id=original.public_id, waypoints=[params])
    elif kind == 'patrol':
        command = Command(kind, (wing.id,), waypoints=[params])
    else:
        command = Command(kind, (wing.id,), **params)
    result = issue(game, wing.owner, command)
    assert not result.accepted and result.errors[0].code == 'invalid_destination'
    assert wing.commander_component.current_order is original


@pytest.mark.parametrize('position', [(5000, 0), (4000, 3000)])
def test_exact_sector_boundary_is_a_legal_move_destination(position):
    game = campaign()
    unit = mobile(game, 'Traveller', (1500, 0))
    assert issue(game, unit.owner, Command('move', (unit.id,), system_name='Sol',
                 hex_coord=(0, 0), position=position)).accepted
    assert unit.commander_component.current_order.status == OrderStatus.IN_PROGRESS


def test_defend_body_approaches_surface_and_holds_outside_it():
    game, _carrier, wing = wing_world()
    body = Planet((0, 0), 'Sol', PlanetType.TERRAN)
    game.galaxy.systems['Sol'].add_celestial_body(body)
    assert issue(game, wing.owner, Command('defend', (wing.id,), target_id=body.id)).accepted
    root = wing.commander_component.current_order
    view = next(u for u in build_observation(game, wing.owner)['units'] if u['id'] == wing.id)['current_order']
    assert view['target_id'] == body.id and view['target_visibility'] == 'visible'
    assert view['progress']['journey']['waiting_reason'] is None
    for _ in range(30):
        resolve(game)
    assert root.status == OrderStatus.IN_PROGRESS and not root.sub_orders
    assert body.collision_radius + 50 <= distance(wing.position, body.position) <= body.collision_radius + 150.01


@pytest.mark.parametrize('remote', [False, True])
def test_colony_intelligence_missions_complete_without_landing(remote):
    game = campaign()
    game.galaxy.game = game
    spy = mobile(game, 'Spy', (3000, 0))
    spy.add_component(IntelligenceComponent(spy, agents_count=2, agents_capacity=2, has_counter_intelligence=True))
    spy.add_component(Sensors(spy, long_range_hexes=2))
    spy.add_component(Hyperdrive(spy, drive_type=HyperdriveType.ADVANCED, jump_range=5))
    body = Planet((1, 0) if remote else (0, 0), 'Sol', PlanetType.TERRAN)
    body.owner, body.population = game.players[1], 40
    game.galaxy.systems['Sol'].add_celestial_body(body)

    def finish(command):
        assert issue(game, spy.owner, command).accepted
        root = spy.commander_component.current_order
        for _ in range(80):
            if root.status == OrderStatus.COMPLETED:
                break
            resolve(game)
            assert distance(spy.position, body.position) >= body.collision_radius + 50
        assert root.status == OrderStatus.COMPLETED

    finish(Command('infiltrate_planet', (spy.id,), target_id=body.id))
    agent = body.infiltrating_agents[0]
    spy.position = Position(3000, 0)
    finish(Command('extract_agent', (spy.id,), agent_id=agent.id))
    assert agent not in body.infiltrating_agents and spy.intelligence_component.available_agents == 2

    body.owner = spy.owner
    hostile = Agent(game.players[1], source_unit_id=0, target_type='CELESTIAL_BODY', target_id=body.id)
    hostile.attached_to = body
    body.infiltrating_agents.append(hostile)
    spy.position = Position(body.collision_radius + 450, 0)
    assert issue(game, spy.owner, Command('ci_sweep', (spy.id,))).accepted
    assert hostile.is_discovered
    spy.position = Position(3000, 0)
    finish(Command('eliminate_agent', (spy.id,), agent_id=hostile.id))
    assert hostile not in body.infiltrating_agents


def test_undisclosed_solid_does_not_leak_through_move_preflight():
    game = campaign()
    unit = mobile(game, 'Traveller', (1500, 0))
    unit.add_component(Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5))
    body = Planet((0, 0), 'Beta', PlanetType.TERRAN)
    game.galaxy.systems['Beta'].add_celestial_body(body)
    remote = next(system for system in build_observation(game, unit.owner)['systems'] if system['name'] == 'Beta')
    assert body.id not in {item['id'] for item in remote.get('celestial_bodies', [])}
    result = issue(game, unit.owner, Command('move', (unit.id,), system_name='Beta',
                                          hex_coord=(0, 0), position=(0, 0)))
    assert result.accepted  # Issuance cannot disclose an unknown obstacle.
    root = unit.commander_component.current_order
    assert root.status == OrderStatus.FAILED and root.failure_reason == 'path_unavailable'
    assert unit.owner.order_history[-1]['outcome'] == 'failed'


def test_wing_with_storage_retains_fuel_costs_and_waits_when_empty():
    game, _carrier, wing = wing_world()
    wing.add_component(AntimatterStorage(wing, max_capacity=100))
    wing.antimatter_component.current_amount = 0
    assert issue(game, wing.owner, Command('move', (wing.id,), system_name='Sol',
                                          hex_coord=(0, 0), position=(3000, 0))).accepted
    journey = public_journey_progress(game, wing.owner, wing)
    assert journey['next_step_antimatter'] > 0 and journey['estimated_remaining_antimatter'] > 0
    assert journey['waiting_reason'] == 'insufficient_antimatter'
    before = wing.position.to_tuple()
    resolve(game)
    assert wing.position.to_tuple() == before
