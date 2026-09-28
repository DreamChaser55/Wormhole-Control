"""Ownership disclosure, historical knowledge and controller parity."""
from copy import deepcopy
from types import SimpleNamespace

import pygame
import pytest

from constants import PlanetType
from domain.celestials import Planet, Moon, ColonizableAsteroid
from domain.players import Player
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch
from game_ai.observation import build_observation
from geometry import Position
from planetary_intel import ownership_view, presentation_view, refresh, decode_records
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from visibility import VisibilityService


def world(game, cls=Planet, owner=1, *, sector=(0, 0), system='Sol'):
    body = cls(sector, system, PlanetType.TERRAN) if cls is Planet else cls(sector, system)
    body.owner = game.players[owner] if owner is not None else None
    body.population = 40 if owner is not None else 0
    game.galaxy.systems[system].add_celestial_body(body)
    return body


def scout(game, body):
    unit = ship(game)
    unit.sensors_component.short_range_radius = 200
    unit.sensors_component.long_range_hexes = 0
    unit.position = Position(body.collision_radius + 200, 0)
    return unit


def view(game, body, *, record=True):
    viewer = game.players[0]
    snapshot = VisibilityService.compute(game.galaxy, viewer, game.turn_number, record_intel=record)
    return ownership_view(game, viewer, body, snapshot)


@pytest.mark.parametrize('cls', [Planet, Moon, ColonizableAsteroid])
@pytest.mark.parametrize('owner', [None, 1])
def test_surface_boundary_memory_and_unseen_changes(cls, owner):
    game = campaign()
    body = world(game, cls, owner)
    assert view(game, body).status == 'unknown'
    unit = scout(game, body)
    assert view(game, body, record=False).status == 'current'
    assert game.players[0].planetary_intel == {}
    assert view(game, body).owner_id == (None if owner is None else game.players[1].id)
    remembered = deepcopy(game.players[0].planetary_intel)
    unit.position.x += .01
    stale = view(game, body)
    assert stale.status == 'last_known' and stale.observed_turn == game.turn_number
    game.players.append(Player('Third', (0, 0, 200)))
    body.owner = game.players[2]
    body.population = 80
    body.fortification_level = 3
    game.turn_number += 1
    assert view(game, body) == stale
    assert game.players[0].planetary_intel == remembered
    unit.position.x -= .01
    assert view(game, body).owner_id == game.players[2].id
    assert view(game, body).observed_turn == game.turn_number


def test_long_range_and_friendly_knowledge_are_separate_from_sensed_ids():
    game = campaign()
    body = world(game, sector=(1, 0))
    unit = ship(game)
    assert view(game, body).status == 'unknown'
    unit.sensors_component.long_range_hexes = 1
    assert view(game, body).status == 'current'
    unit.sensors_component.long_range_hexes = 0
    assert view(game, body).status == 'last_known'
    body.owner = game.players[0]
    snapshot = VisibilityService.compute(game.galaxy, game.players[0], record_intel=False)
    assert body.id not in snapshot.sensed_colony_ids
    assert ownership_view(game, game.players[0], body, snapshot).status == 'current'


@pytest.mark.parametrize('unavailable', ['destroyed', 'dead', 'submerged', 'docked', 'dismantling'])
def test_unavailable_sensor_platforms_do_not_reveal(unavailable, monkeypatch):
    game = campaign()
    body = world(game)
    unit = scout(game, body)
    if unavailable == 'destroyed':
        unit.sensors_component.current_hit_points = 0
    elif unavailable == 'dead':
        unit.current_hit_points = 0
    elif unavailable == 'submerged':
        unit.is_hidden_in_gas_giant = True
    elif unavailable == 'docked':
        game.galaxy.systems['Sol'].hexes[(0, 0)].units.remove(unit)
    else:
        monkeypatch.setattr('dismantling.offline', lambda candidate: candidate is unit)
    assert view(game, body).status == 'unknown'


def test_shared_allied_sensors_agents_and_scan(monkeypatch):
    game = campaign()
    game.players.append(Player('Ally', (50, 100, 100), team_id=game.players[0].team_id))
    body = world(game)
    unit = scout(game, body)
    unit.owner = game.players[2]
    assert view(game, body).status == 'current'
    unit.owner = game.players[1]
    assert view(game, body).status == 'last_known'
    from unit_components.intelligence import Agent
    agent = Agent(game.players[0], unit.id, 'UNIT', unit.id)
    unit.infiltrating_agents.append(agent)
    assert view(game, body).status == 'current'
    unit.infiltrating_agents.clear()
    body.infiltrating_agents.append(Agent(game.players[2], unit.id, 'PLANET', body.id))
    assert view(game, body).status == 'current'
    body.infiltrating_agents.clear()
    monkeypatch.setattr('titan_abilities.coverage', lambda galaxy, viewer: {('Sol', (0, 0))})
    assert view(game, body).status == 'current'
    monkeypatch.setattr('titan_abilities.coverage', lambda galaxy, viewer: set())
    assert view(game, body).status == 'last_known'


def test_effective_ranges_respect_dust_sabotage_and_magnetic_suppression():
    from constants import NebulaType, StormType
    from domain.celestials import Nebula, Storm
    from unit_components.intelligence import Agent
    from unit_components.enums import SabotageType
    game = campaign()
    body = world(game)
    unit = scout(game, body)
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    dust = Nebula((0, 0), 'Sol', NebulaType.DUST)
    sector.add_celestial_body(dust)
    assert view(game, body).status == 'unknown'
    sector.celestial_bodies.remove(dust)
    agent = Agent(game.players[1], unit.id, 'UNIT', unit.id, active_sabotage=SabotageType.SENSORS)
    unit.infiltrating_agents.append(agent)
    unit.sensors_component.long_range_hexes = 1
    assert view(game, body).status == 'unknown'
    unit.infiltrating_agents.clear()
    unit.position.x = 3000
    assert view(game, body).status == 'current'
    sector.add_celestial_body(Storm((0, 0), 'Sol', StormType.MAGNETIC))
    assert view(game, body).status == 'last_known'


@pytest.mark.parametrize('remembered', [False, True])
@pytest.mark.parametrize('remote', [False, True])
def test_hidden_owner_statistics_do_not_change_observation_or_ui(remembered, remote):
    from gui.sidebar.panels_world import build_celestial_body_panel, build_hex_panel
    from input_processor.context_menu_builder import build_sector_context_menu_options
    from unit_components.colony import ColonyComponent
    from unit_components.intelligence import IntelligenceComponent
    from rendering.planetary_intel import draw_ownership_ring
    from rendering.drawing_utils import selection_color_for
    game = campaign()
    body = world(game, owner=None, system='Beta' if remote else 'Sol')
    unit = scout(game, body)
    unit.position.x = 4000
    unit.add_component(ColonyComponent(unit))
    unit.colony_component.population_cargo = 20
    unit.add_component(IntelligenceComponent(unit))
    game.selected_objects = [unit]
    game.is_unit_visible = lambda candidate: candidate.owner == game.players[0]
    game.hex_has_presence = lambda *args: False
    if remembered:
        game.players[0].planetary_intel[body.id] = {'owner_id': None, 'observed_turn': 2}
    def visible_output():
        surface = pygame.Surface((60, 60))
        draw_ownership_ring(surface, game, body, (30, 30), 10)
        return (build_observation(game, game.players[0]), build_celestial_body_panel(game, body),
                build_hex_panel(game, game.galaxy.systems[body.in_system].hexes[body.in_hex]),
                build_sector_context_menu_options(game, body, body.position)[0],
                selection_color_for(body, game), pygame.image.tobytes(surface, 'RGB'))
    before = visible_output()
    body.owner = game.players[1]
    body.population = 90
    body.fortification_level = 3
    body.defense_readiness = .25
    assert visible_output() == before


def test_snapshot_viewer_and_dirty_snapshot_cannot_leak():
    game = campaign()
    body = world(game)
    unit = scout(game, body)
    game.visibility = VisibilityService.compute(game.galaxy, game.players[0], record_intel=False)
    unit.position.x += 1
    game.visibility_dirty = True
    assert presentation_view(game, body).status == 'unknown'
    game.visibility_dirty = False
    game.players.append(Player('Third', (1, 2, 3)))
    game.current_player_index = 2
    assert presentation_view(game, body).status == 'unknown'


def test_stale_colony_save_round_trip_and_pure_load():
    game = campaign()
    body = world(game)
    unit = scout(game, body)
    refresh(game)
    unit.position.x += 1
    body.owner = None
    remembered = deepcopy(game.players[0].planetary_intel)
    restored = SimpleNamespace()
    deserialize_game_state(restored, serialize_game_state(game))
    assert restored.players[0].planetary_intel == remembered
    loaded_body = restored.galaxy.get_celestial_body_by_id(body.id)
    assert view(restored, loaded_body, record=False).owner_id == game.players[1].id
    assert restored.players[0].planetary_intel == remembered


@pytest.mark.parametrize('invalid', [None, {}, [dict(body_id=True, owner_id=None, observed_turn=1)],
    [dict(body_id=1, owner_id=False, observed_turn=1)],
    [dict(body_id=1, owner_id=None, observed_turn=0)],
    [dict(body_id=1, owner_id=None, observed_turn=8)],
    [dict(body_id=1, owner_id=99, observed_turn=1)],
    [dict(body_id=1, owner_id=None, observed_turn=1)] * 2])
def test_invalid_intelligence_records_reject(invalid):
    with pytest.raises(ValueError, match='planetary_intel'):
        decode_records(invalid, turn=7, player_ids={0, 1})


@pytest.mark.parametrize('kind', ['load_colonists', 'infiltrate_planet',
                                 'invade_planet', 'bombard_planet', 'recruit_troops',
                                 'upgrade_planetary_defenses'])
def test_guessed_and_missing_colony_targets_reject_identically(kind):
    from unit_components.colony import ColonyComponent
    from unit_components.intelligence import IntelligenceComponent
    from unit_components.planetary import TroopTransportComponent, SiegeBatteryComponent
    game = campaign()
    body = world(game, owner=None)
    unit = scout(game, body)
    unit.add_component(ColonyComponent(unit))
    unit.colony_component.population_cargo = 20
    unit.add_component(IntelligenceComponent(unit))
    unit.add_component(TroopTransportComponent(unit))
    unit.add_component(SiegeBatteryComponent(unit))
    unit.troop_transport_component.troops = 20
    unit.position.x += 1
    def result(target_id):
        command = Command(type=kind, unit_ids=() if kind == 'upgrade_planetary_defenses' else (unit.id,),
                          target_id=target_id,
                          amount=10 if kind in {'invade_planet', 'load_colonists', 'recruit_troops'} else None)
        return CommandGateway(game).apply_batch(game.players[0], CommandBatch((command,)))
    stale = result(body.id)
    body.owner = game.players[1]
    owned = result(body.id)
    missing = result(999999)
    assert not stale.accepted
    assert stale.errors == owned.errors == missing.errors
    assert stale.errors[0].code == 'target_unavailable'
    assert unit.commander_component.current_order is None


def test_enemy_home_markers_require_current_coverage():
    from galaxy_utils import get_home_systems_mapping
    game = campaign()
    body = world(game)
    game.players[1].homeworld_id = body.id
    unit = scout(game, body)
    view(game, body)
    assert game.players[1] in get_home_systems_mapping(game, player_scoped=True)['Sol']
    unit.position.x += 1
    assert not get_home_systems_mapping(game, player_scoped=True)
    assert game.players[1] in get_home_systems_mapping(game)['Sol']


@pytest.mark.parametrize('kind', ['COLONIZE', 'INFILTRATE_PLANET', 'INVADE_PLANET', 'BOMBARD_PLANET'])
def test_lost_contact_preserves_approach_and_queue(kind):
    from planetary_intel import revalidate_colony_orders
    from unit_orders.base import Order, OrderType, OrderStatus
    from unit_orders.colony import ColonizeOrder
    from unit_orders.intelligence import InfiltratePlanetOrder
    from unit_orders.planetary import InvadePlanetOrder, BombardPlanetOrder
    from unit_components.colony import ColonyComponent
    from unit_components.intelligence import IntelligenceComponent
    from unit_components.planetary import TroopTransportComponent, SiegeBatteryComponent
    from unit_components.antimatter import AntimatterStorage
    from unit_components.movement import Engines
    game = campaign()
    body = world(game, Moon, owner=None if kind == 'COLONIZE' else 1)
    unit = scout(game, body)
    unit.add_component(ColonyComponent(unit))
    unit.add_component(IntelligenceComponent(unit))
    unit.add_component(TroopTransportComponent(unit))
    unit.add_component(SiegeBatteryComponent(unit))
    unit.add_component(AntimatterStorage(unit, max_capacity=200))
    unit.add_component(Engines(unit, speed=100))
    unit.colony_component.population_cargo = 10
    unit.troop_transport_component.troops = 20
    unit.sensors_component.long_range_hexes = 1
    unit.position.x = 2500  # Outside every action's operational range.
    classes = {'COLONIZE': ColonizeOrder, 'INFILTRATE_PLANET': InfiltratePlanetOrder,
               'INVADE_PLANET': InvadePlanetOrder, 'BOMBARD_PLANET': BombardPlanetOrder}
    field = 'target_body_id' if kind == 'INFILTRATE_PLANET' else 'target_id'
    order = classes[kind](unit, {field: body.id, 'amount': 10})
    unit.commander_component.add_order(order)
    followup = Order(unit, OrderType.TOGGLE_INHIBITOR)
    unit.commander_component.add_order(followup)
    assert order.status == OrderStatus.IN_PROGRESS and order.sub_orders
    fuel = unit.antimatter_component.current_amount
    unit.sensors_component.long_range_hexes = 0
    revalidate_colony_orders(game)
    assert order.status == OrderStatus.IN_PROGRESS
    assert order.sub_orders
    assert list(unit.commander_component.orders_queue) == [followup]
    assert unit.antimatter_component.current_amount == fuel
    assert unit.colony_component.population_cargo == 10
    assert unit.troop_transport_component.troops == 20
    assert not game.players[0].order_history
    unit.sensors_component.long_range_hexes = 1
    revalidate_colony_orders(game)
    assert order.status == OrderStatus.IN_PROGRESS


def test_last_known_sidebar_and_ring_use_observed_owner():
    from gui.sidebar.panels_world import build_celestial_body_panel
    from rendering.planetary_intel import draw_ownership_ring
    game = campaign()
    body = world(game)
    unit = scout(game, body)
    view(game, body)
    unit.position.x += 1
    body.owner = None
    rows = build_celestial_body_panel(game, body)
    texts = [r.get('text', '') for r in rows]
    assert 'Owner: Two' in texts
    assert 'Last observed: turn 7' in texts
    assert not any(t.startswith(('Population:', 'Readiness:', 'Planetary defense:')) for t in texts)
    surface = pygame.Surface((80, 80))
    draw_ownership_ring(surface, game, body, (40, 40), 20)
    muted = tuple(round(c * .55) for c in game.players[1].color)
    colors = {tuple(surface.get_at((x, y)))[:3] for x in range(80) for y in range(80)}
    assert muted in colors and game.players[1].color not in colors


@pytest.mark.parametrize('bad_reference', ['body', 'noncolonizable', 'owner'])
def test_invalid_saved_references_leave_live_campaign_unchanged(bad_reference):
    from constants import StarType
    from domain.celestials import Star
    game = campaign()
    body = world(game)
    scout(game, body)
    refresh(game)
    data = serialize_game_state(game)
    record = data['players'][0]['planetary_intel'][0]
    if bad_reference == 'body':
        record['body_id'] = 999999
    elif bad_reference == 'owner':
        record['owner_id'] = 999999
    else:
        star = Star('Sol', StarType.G_TYPE)
        game.galaxy.systems['Sol'].add_celestial_body(star)
        data = serialize_game_state(game)
        data['players'][0]['planetary_intel'][0]['body_id'] = star.id
    before_galaxy, before_players = game.galaxy, game.players
    assert not deserialize_game_state(game, data)
    assert game.galaxy is before_galaxy and game.players is before_players


def test_real_deep_scan_expiration_keeps_ownership_history():
    from tests.test_titans import titan, command, advance
    from titan_abilities import process
    game = campaign()
    body = world(game, sector=(1, 0))
    unit = titan(game)
    unit.sensors_component.long_range_hexes = 0
    assert view(game, body).status == 'unknown'
    assert command(game, unit, 'deep_scan', system_name='Sol', hex_coord=(1, 0)).accepted
    process(game, unit.owner)
    assert view(game, body).status == 'current'
    advance(game, unit, 5)
    assert view(game, body).status == 'last_known'
    assert view(game, body).observed_turn == 7


def test_queued_invasion_checks_contact_before_resources_and_rng():
    import random
    from tests.test_planetary_warfare import vessel
    from unit_orders.planetary import InvadePlanetOrder
    from unit_orders.base import OrderStatus
    from planetary_warfare import process_actions
    game = campaign()
    body = world(game)
    unit = vessel(game, body, troops=40)
    unit.sensors_component.long_range_hexes = 1
    view(game, body)
    order = InvadePlanetOrder(unit, {'target_id': body.id, 'amount': 40})
    unit.commander_component.orders_queue.append(order)
    unit.sensors_component.short_range_radius = unit.sensors_component.long_range_hexes = 0
    game.invasion_rng = random.Random(1)
    before = (unit.owner.credits, unit.antimatter_component.current_amount, game.invasion_rng.getstate())
    unit.commander_component.start_next_order()
    process_actions(game, unit.owner)
    assert order.status == OrderStatus.IN_PROGRESS
    from planetary_intel import order_phase
    assert order_phase(order, game.galaxy) == 'waiting_for_contact'
    assert unit.troop_transport_component.troops == 40
    assert before == (unit.owner.credits, unit.antimatter_component.current_amount, game.invasion_rng.getstate())


def test_commit_accepts_contact_loss_with_recorded_intel(monkeypatch):
    from tests.test_planetary_warfare import vessel
    from unit_orders.base import Order, OrderType, OrderStatus
    game = campaign()
    body = world(game)
    unit = vessel(game, body, troops=40)
    unit.sensors_component.long_range_hexes = 1
    existing = Order(unit, OrderType.MOVE)
    existing.status = OrderStatus.IN_PROGRESS
    unit.commander_component.current_order = existing
    gateway = CommandGateway(game)
    view(game, body)
    original = gateway._require_colony_target
    calls = 0
    def lose_contact(player, target, kind):
        nonlocal calls
        calls += 1
        if calls == 2:
            unit.sensors_component.short_range_radius = unit.sensors_component.long_range_hexes = 0
        return original(player, target, kind)
    monkeypatch.setattr(gateway, '_require_colony_target', lose_contact)
    result = gateway.apply_batch(unit.owner, CommandBatch((
        Command(type='invade_planet', unit_ids=(unit.id,), target_id=body.id, amount=40),)))
    assert result.accepted
    assert unit.commander_component.current_order is not existing
    assert unit.commander_component.current_order.status == OrderStatus.IN_PROGRESS
    assert unit.troop_transport_component.troops == 40
