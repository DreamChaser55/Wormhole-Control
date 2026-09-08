"""Regressions at gameplay boundaries: geometry, storage, setup and turn cadence."""
import random
from unittest.mock import Mock

import pytest

from constants import HullSize, PlanetType, SECTOR_CIRCLE_RADIUS_LOGICAL
from entities import Planet, Player, GameObject, Minefield
from geometry import Position, Circle, distance, segment_intersects_circle, compute_avoidance_waypoints, NoSafePathError
from game_settings import GameSettings, PlayerConfig, SpawnProfile
from game_setup import prepare_new_campaign, start_new_game
from turn_processor import TurnProcessor
from unit_components import Engines, AntimatterStorage, Defenses, Agent
from unit_components.enums import TurretType, UnitStance
from unit_orders import Order, OrderStatus, MoveOrder, ReachWaypointOrder
from unit_orders.gas_giant import EnterGasGiantOrder, LeaveGasGiantOrder
from tests.test_persistence_integrity import campaign, ship


@pytest.fixture(autouse=True)
def preserve_process_state():
    owners = ((GameObject, 'object_counter'), (Player, 'player_counter'),
              (Agent, 'agent_counter'), (Order, 'order_counter'))
    counters = [(owner, field, getattr(owner, field)) for owner, field in owners]
    state = random.getstate()
    random.seed(12)
    yield
    for owner, field, value in counters:
        setattr(owner, field, value)
    random.setstate(state)


@pytest.fixture
def atmosphere():
    game = campaign()
    giant = Planet((0, 0), 'Sol', PlanetType.GAS_GIANT)
    game.galaxy.systems['Sol'].add_celestial_body(giant)
    unit = ship(game, hull=HullSize.MEDIUM)
    unit.in_galaxy = game.galaxy
    unit.position = Position(800, 0)
    unit.add_component(Engines(unit, speed=200))
    unit.add_component(AntimatterStorage(unit, max_capacity=1000))
    unit.antimatter_component.current_amount = 1000
    return game, giant, unit


@pytest.mark.parametrize('amount,reduction,damage', [
    (0, .5, 0), (-10, .5, 0), (1, .75, 0), (10, .5, 5),
    (10, 1, 0), (10, 2, 0), (10, -1, 10), (10, 0, 10),
])
def test_damage_floor(atmosphere, amount, reduction, damage):
    _, _, unit = atmosphere
    unit.damage_reduction = reduction
    hp = unit.current_hit_points
    unit.take_damage(amount)
    assert unit.current_hit_points == hp - damage


@pytest.mark.parametrize('mitigation', ['cover', 'defenses'])
def test_fully_mitigated_damage_stays_zero(atmosphere, monkeypatch, mitigation):
    _, _, unit = atmosphere
    unit.damage_reduction = .5
    if mitigation == 'cover':
        monkeypatch.setattr(unit, 'get_environmental_cover_bonus', lambda kind: 1)
    else:
        defenses = Defenses(unit, shields=100)
        unit.add_component(defenses)
        monkeypatch.setattr(defenses, 'calculate_mitigation', lambda amount, kind: amount)
    hp = unit.current_hit_points
    unit.take_damage(25, TurretType.BEAM)
    assert unit.current_hit_points == hp


def test_reduced_lethal_damage_still_destroys(atmosphere):
    game, _, unit = atmosphere
    unit.damage_reduction = .5
    unit.take_damage(unit.current_hit_points * 2)
    assert unit.current_hit_points == 0
    assert unit not in game.galaxy.systems['Sol'].hexes[(0, 0)].units


def assert_clear(points, obstacles, margin=50):
    # Independent intersection routine checks complete segments, not just vertices.
    for a, b in zip(points, points[1:]):
        for obstacle in obstacles:
            assert not segment_intersects_circle(a, b, Circle(obstacle.center, obstacle.radius + margin - 1e-5))


@pytest.mark.parametrize('height,detour', [(0, True), (149, True), (150, False), (151, False)])
def test_expanded_collision_clearance(height, detour):
    start, end = Position(-300, height), Position(300, height)
    obstacles = [Circle(Position(0, 0), 100)]
    waypoints = compute_avoidance_waypoints(start, end, obstacles)
    assert bool(waypoints) is detour
    assert_clear([start, *waypoints, end], obstacles)


def test_multiple_obstacles_and_boundary():
    start, end = Position(-450, 0), Position(450, 0)
    obstacles = [Circle(Position(-140, 0), 65), Circle(Position(140, -40), 70)]
    waypoints = compute_avoidance_waypoints(start, end, obstacles, boundary=Circle(Position(0, 0), 500))
    assert_clear([start, *waypoints, end], obstacles)
    assert all(p.magnitude() <= 500 for p in waypoints)


def test_boundary_chooses_other_bypass_and_impossible_route_fails():
    start, end = Position(-400, 100), Position(400, 100)
    obstacles = [Circle(Position(0, 190), 230)]
    route = compute_avoidance_waypoints(start, end, obstacles, boundary=Circle(Position(0, 0), 450))
    assert route and all(p.magnitude() <= 450 for p in route)
    assert_clear([start, *route, end], obstacles)
    wall = [Circle(Position(0, y), 200) for y in (-400, 0, 400)]
    with pytest.raises(NoSafePathError):
        compute_avoidance_waypoints(Position(-450, 0), Position(450, 0), wall, boundary=Circle(Position(0, 0), 500))


def test_clearance_band_escape_and_destination_rejection():
    obstacle = Circle(Position(0, 0), 100)
    start, end = Position(120, 0), Position(400, 0)
    route = compute_avoidance_waypoints(start, end, [obstacle])
    assert route[0].x >= 150
    assert_clear([*route, end], [obstacle])
    with pytest.raises(NoSafePathError):
        compute_avoidance_waypoints(end, start, [obstacle])
    assert compute_avoidance_waypoints(Position(0, 0), end, [obstacle]) == []
    assert compute_avoidance_waypoints(end, Position(0, 0), [obstacle]) == []


@pytest.mark.parametrize('order_class', [MoveOrder, ReachWaypointOrder])
def test_unavailable_route_fails_order_without_engine_target(atmosphere, order_class):
    game, giant, unit = atmosphere
    order = order_class(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
                               'destination_position': Position(giant.collision_radius + 10, 0)})
    unit.commander_component.add_order(order)
    assert order.status == OrderStatus.FAILED
    assert order.failure_reason == 'path_unavailable'
    assert unit.engines_component.move_target is None


def test_failed_later_route_leg_cannot_start_earlier_jump(atmosphere):
    from unit_components import Hyperdrive
    game, _, unit = atmosphere
    unit.add_component(Hyperdrive(unit))
    world = Planet((1, 0), 'Sol')
    system = game.galaxy.systems['Sol']
    system.add_celestial_body(world)
    system.hexes[(1, 0)].update_static_inhibition_zones()
    order = MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (1, 0),
                            'destination_position': Position(world.collision_radius + 10, 0)})
    unit.commander_component.add_order(order)
    assert order.status == OrderStatus.FAILED and order.failure_reason == 'path_unavailable'
    assert not order.sub_orders
    unit.commander_component.update()
    assert unit.engines_component.move_target is None
    assert unit.hyperdrive_component.hex_jump_target is None


def move(unit):
    return MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
                            'destination_position': Position(1600, 0)})


def test_entry_exit_journal_and_fifo_resume(atmosphere):
    game, giant, unit = atmosphere
    commander = unit.commander_component
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    entry = EnterGasGiantOrder(unit, {'target_id': giant.id})
    leave, onward = LeaveGasGiantOrder(unit), move(unit)
    commander.add_order(entry)
    commander.add_order(leave)
    commander.add_order(onward)
    assert unit.is_hidden_in_gas_giant
    assert commander.stance == UnitStance.ATTACK_SAME_SECTOR
    TurnProcessor(game)._process_unit_updates(unit.owner)
    assert not unit.is_hidden_in_gas_giant
    assert commander.stance == UnitStance.ATTACK_SAME_SECTOR
    assert commander.current_order is onward
    assert [(event['type'], event['outcome']) for event in unit.owner.order_history] == [
        ('enter_gas_giant', 'completed'), ('leave_gas_giant', 'completed')]
    entry.cancel()
    leave.cancel()
    assert entry.status == leave.status == OrderStatus.COMPLETED
    assert len(unit.owner.order_history) == 2


def test_approached_entry_completes_root_once(atmosphere):
    game, giant, unit = atmosphere
    unit.position = Position(1400, 0)
    entry = EnterGasGiantOrder(unit, {'target_id': giant.id})
    unit.commander_component.add_order(entry)
    processor = TurnProcessor(game)
    for _ in range(12):
        processor._process_movement(unit.owner)
        processor._process_unit_updates(unit.owner)
        if entry.status == OrderStatus.COMPLETED:
            break
    assert entry.status == OrderStatus.COMPLETED
    assert unit.is_hidden_in_gas_giant
    assert [e['outcome'] for e in unit.owner.order_history] == ['completed']


def test_paused_fifo_survives_save_and_can_be_edited(atmosphere):
    from save_manager import serialize_game_state, deserialize_game_state
    from game_ai.observation import build_observation
    from game_ai.commands import CommandGateway, CommandBatch
    from game_ai.contracts import Command
    game, giant, unit = atmosphere
    commander = unit.commander_component
    commander.add_order(EnterGasGiantOrder(unit, {'target_id': giant.id}))
    paused, leave = move(unit), LeaveGasGiantOrder(unit)
    commander.add_order(paused)
    commander.add_order(leave)
    commander.update()
    assert commander.current_order is None
    assert list(commander.orders_queue) == [paused, leave]
    payload = serialize_game_state(game)
    assert deserialize_game_state(game, payload)
    restored = game.galaxy.get_unit_by_id(unit.id)
    restored.commander_component.update()
    assert restored.is_hidden_in_gas_giant
    observed = next(u for u in build_observation(game, game.players[0])['units'] if u['id'] == unit.id)
    assert observed['queued_orders'][1]['blocked_by_order_id'] == paused.public_id
    assert 'cancel_order' in observed['legal_commands']
    assert paused.public_id in observed['command_options']['cancel_order']['order_ids']
    assert observed['command_options']['set_stance']['values']
    result = CommandGateway(game).apply_batch(game.players[0], CommandBatch((Command('cancel_order', (unit.id,), order_id=paused.public_id),)))
    assert result.accepted, result.errors
    assert not restored.is_hidden_in_gas_giant
    events = game.players[0].order_history
    assert [(e['type'], e['outcome']) for e in events] == [
        ('enter_gas_giant', 'completed'), ('move', 'cancelled'), ('leave_gas_giant', 'completed')]


def test_gas_exit_repeated_random_bearings_are_deconflicted(atmosphere, monkeypatch):
    game, giant, unit = atmosphere
    other = ship(game, name='second', hull=HullSize.MEDIUM)
    other.in_galaxy = game.galaxy
    other.add_component(Engines(other, speed=100))
    giant.hide_unit(unit, game.galaxy)
    giant.hide_unit(other, game.galaxy)
    monkeypatch.setattr(random, 'uniform', lambda *args: 0)
    p1 = giant.release_unit(unit, game.galaxy)
    p2 = giant.release_unit(other, game.galaxy)
    assert p1 is not None and p2 is not None
    assert distance(p1, p2) >= 50
    assert distance(p1, giant.position) == pytest.approx(725)


def test_gas_exit_boundary_and_blocked_failure(atmosphere, monkeypatch):
    game, giant, unit = atmosphere
    giant.position = Position(4999, 0)
    giant.hide_unit(unit, game.galaxy)
    monkeypatch.setattr(random, 'uniform', lambda *args: 0)
    pos = giant.release_unit(unit, game.galaxy)
    assert pos is not None and pos.magnitude() <= SECTOR_CIRCLE_RADIUS_LOGICAL - 20
    giant.hide_unit(unit, game.galaxy)
    blocker = Planet((0, 0), 'Sol')
    blocker.position, blocker.collision_radius = giant.position, 2000
    game.galaxy.systems['Sol'].add_celestial_body(blocker)
    original = unit.position
    leave = LeaveGasGiantOrder(unit)
    unit.commander_component.add_order(leave)
    assert leave.status == OrderStatus.FAILED and leave.failure_reason == 'path_unavailable'
    assert unit.is_hidden_in_gas_giant and unit in giant.hidden_units
    assert unit.position == original
    assert unit not in game.galaxy.systems['Sol'].hexes[(0, 0)].units


def test_ai_preflight_gas_queue_dependencies(atmosphere):
    from game_ai.commands import CommandGateway, CommandBatch
    from game_ai.contracts import Command
    game, giant, unit = atmosphere
    result = CommandGateway(game).apply_batch(unit.owner, CommandBatch((
        Command('enter_gas_giant', (unit.id,), target_id=giant.id),
        Command('leave_gas_giant', (unit.id,), queue=True),
        Command('move', (unit.id,), system_name='Sol', hex_coord=(0, 0), position=(1600, 0), queue=True),
    )))
    assert result.accepted, result.errors
    unit.commander_component.update()
    assert not unit.is_hidden_in_gas_giant
    assert unit.commander_component.current_order.order_type.name == 'MOVE'


@pytest.mark.parametrize('players', [2, 3, 6])
@pytest.mark.parametrize('moving', [False, True])
def test_mine_damage_once_per_owner_turn(players, moving):
    game = campaign()
    game.players = [Player(str(i), (10, 20, 30), team_id=i+1) for i in range(players)]
    victim = ship(game, owner=0)
    victim.position = Position(0, 0)
    field = Minefield(game.players[1], Position(0, 0), (0, 0), 'Sol', mines_remaining=20, mine_damage=20)
    game.galaxy.systems['Sol'].hexes[(0, 0)].minefields.append(field)
    processor = TurnProcessor(game)
    if moving:
        victim.position = Position(1000, 0)
        processor._process_movement = lambda player: setattr(victim, 'position', Position(0, 0)) if player is victim.owner else None
    else:
        processor._process_movement = lambda player: None
    hp = victim.current_hit_points
    for _ in range(2):
        for player in game.players:
            processor.process_player_turn(player)
    assert hp - victim.current_hit_points == 40
    assert field.mines_remaining == 18


def settings_for(galaxy, profile=SpawnProfile.NORMAL):
    from galaxy import StarSystem
    # Campaign setup uses real product bounds; smaller worlds remain engine fixtures.
    for index in range(len(galaxy.systems), 5):
        name = f'Extra{index}'
        galaxy.systems[name] = StarSystem(name, Position(index * 300, 0), radius=3)
        for sector in galaxy.systems[name].hexes.values():
            sector.celestial_bodies.clear()
            sector.update_static_inhibition_zones()
    return GameSettings(num_systems=len(galaxy.systems), pregenerated_galaxy=galaxy,
                        spawn_profile=profile, player_configs=[
        PlayerConfig('One', (0, 200, 0), team_id=1, home_system_name='Sol'),
        PlayerConfig('Two', (200, 0, 0), team_id=2, home_system_name='Beta')])


@pytest.mark.parametrize('kind', list(PlanetType))
def test_homeworld_selection_and_caps(kind):
    game = campaign()
    for name, system in game.galaxy.systems.items():
        system.add_celestial_body(Planet((0, 0), name, kind))
    settings = settings_for(game.galaxy)
    settings.starting_population = 1000
    prepared = prepare_new_campaign(settings)
    for player in prepared.state.players:
        world = prepared.state.galaxy.get_celestial_body_by_id(player.homeworld_id)
        assert world.is_colonizable and world.planet_type != PlanetType.GAS_GIANT
        assert world.population == world.max_population
        assert world.planet_type == (PlanetType.TERRAN if kind == PlanetType.GAS_GIANT else kind)
    assert all(body.owner is None for system in game.galaxy.systems.values() for _, body in system.get_all_celestial_bodies())


def test_population_clamp_precedes_sabotage(atmosphere, monkeypatch):
    game, _, _ = atmosphere
    world = Planet((1, 0), 'Sol', PlanetType.GREENHOUSE)
    world.owner, world.population = game.players[0], 50
    monkeypatch.setattr(world, 'is_sabotaged', lambda kind: True)
    world.update_population()
    assert world.population == 35


def test_start_validation_rechecks_mutable_settings_and_preserves_campaign(monkeypatch):
    game = campaign()
    game.gui, game.ai_coordinator = Mock(), Mock()
    settings = settings_for(game.galaxy)
    snapshot = dict(vars(game))
    counters = GameObject.object_counter, Player.player_counter, Order.order_counter
    settings.player_configs[1].home_system_name = 'Sol'
    assert not start_new_game(game, settings)
    assert 'distinct' in game.last_setup_error
    assert {key: value for key, value in vars(game).items() if key != 'last_setup_error'} == snapshot
    assert (GameObject.object_counter, Player.player_counter, Order.order_counter) == counters
    game.ai_coordinator.reset.assert_not_called()
    game.gui.show_game_ui.assert_not_called()
    settings.player_configs[1].home_system_name = 'Beta'
    monkeypatch.setattr('game_setup.spawn_units', lambda *args, **kwargs: None)
    assert not start_new_game(game, settings)
    assert (GameObject.object_counter, Player.player_counter, Order.order_counter) == counters
    assert not any(body.owner for system in game.galaxy.systems.values() for _, body in system.get_all_celestial_bodies())


def test_normal_count_and_negative_population_rejected():
    configs = [PlayerConfig(str(i), (10, 20, 30), team_id=i+1) for i in range(6)]
    with pytest.raises(ValueError, match='distinct'):
        GameSettings(num_systems=5, player_configs=configs)
    with pytest.raises(ValueError, match='non-negative'):
        GameSettings(starting_population=-1)


def test_testing_allows_shared_systems_and_normal_mixed_starts():
    from galaxy import Hex
    game = campaign()
    game.galaxy.systems['Sol'].hexes[(0, 1)] = Hex(0, 1, 'Sol')
    settings = settings_for(game.galaxy, SpawnProfile.TESTING)
    settings.player_configs[1].home_system_name = 'Sol'
    prepared = prepare_new_campaign(settings)
    assert {home[0] for home in prepared.state.player_homeworlds.values()} == {'Sol'}
    settings = settings_for(game.galaxy)
    settings.player_configs[1].home_system_name = None
    prepared = prepare_new_campaign(settings)
    assert len({home[0] for home in prepared.state.player_homeworlds.values()}) == 2


def test_setup_rejects_shortfall_missing_system_and_no_homeworld_space(monkeypatch):
    game = campaign()
    settings = settings_for(game.galaxy)
    settings.num_systems = 6
    with pytest.raises(ValueError, match='contains 5'):
        prepare_new_campaign(settings)
    settings.num_systems = 5
    settings.player_configs[1].home_system_name = 'Missing'
    with pytest.raises(ValueError, match='does not exist'):
        prepare_new_campaign(settings)
    settings.player_configs[1].home_system_name = 'Beta'
    for name, system in game.galaxy.systems.items():
        for coord in system.hexes:
            system.add_celestial_body(Planet(coord, name, PlanetType.GAS_GIANT))
    with pytest.raises(ValueError, match='No valid homeworld'):
        prepare_new_campaign(settings)


def test_generation_shortfall_is_an_error(monkeypatch):
    from galaxy import Galaxy
    monkeypatch.setattr(random, 'randint', lambda a, b: a)
    with pytest.raises(ValueError, match='Could place only 1 of 2'):
        Galaxy(num_systems=2)


def test_blocked_gas_exit_preserves_queue_and_respects_hull_fields(atmosphere):
    from constants import FieldDensity
    from entities import IceField
    game, giant, unit = atmosphere
    commander = unit.commander_component
    commander.add_order(EnterGasGiantOrder(unit, {'target_id': giant.id}))
    leave, onward = LeaveGasGiantOrder(unit), move(unit)
    commander.add_order(leave)
    commander.add_order(onward)
    field = IceField((0, 0), 'Sol', density=FieldDensity.HIGH)
    game.galaxy.systems['Sol'].add_celestial_body(field)
    commander.update()
    assert leave.status == OrderStatus.FAILED
    assert leave.failure_reason == 'path_unavailable'
    assert list(commander.orders_queue) == [onward]
    assert unit.is_hidden_in_gas_giant and unit in giant.hidden_units
    assert onward.status == OrderStatus.PENDING


def test_mines_overlap_alliances_and_stored_units(atmosphere):
    from unit_components import HangarComponent
    game, giant, hidden = atmosphere
    victim = ship(game, hull=HullSize.HUGE)
    carrier = ship(game, name='carrier')
    carrier.position = Position(1500, 0)
    docked = ship(game, name='docked', hull=HullSize.TINY)
    carrier.add_component(HangarComponent(carrier, max_slots=1))
    assert carrier.hangar_component.dock(docked, game.galaxy)
    assert giant.hide_unit(hidden, game.galaxy)
    hidden_hp, docked_hp, victim_hp = hidden.current_hit_points, docked.current_hit_points, victim.current_hit_points
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    hostile = [Minefield(game.players[1], Position(0, 0), (0, 0), 'Sol', mines_remaining=5, mine_damage=20) for _ in range(2)]
    ally = Player('Ally', (20, 30, 40), team_id=victim.owner.team_id)
    friendly = Minefield(ally, Position(0, 0), (0, 0), 'Sol', mines_remaining=5)
    sector.minefields.extend([*hostile, friendly])
    TurnProcessor(game)._process_minefield_detonations(victim.owner)
    assert victim.current_hit_points == victim_hp - 40
    assert [field.mines_remaining for field in sector.minefields] == [4, 4, 5]
    assert hidden.current_hit_points == hidden_hp and docked.current_hit_points == docked_hp


def test_mine_crossing_without_final_contact_and_lethal_overlap():
    game = campaign()
    victim = ship(game, hull=HullSize.TINY)
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    fields = [Minefield(game.players[1], Position(0, 0), (0, 0), 'Sol', mines_remaining=2, mine_damage=10000) for _ in range(2)]
    sector.minefields.extend(fields)
    victim.position = Position(-1000, 0)
    victim.add_component(Engines(victim, speed=2000))
    victim.add_component(AntimatterStorage(victim, max_capacity=1000))
    victim.antimatter_component.current_amount = 1000
    victim.commander_component.add_order(MoveOrder(victim, {
        'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
        'destination_position': Position(1000, 0)}))
    processor = TurnProcessor(game)
    # The complete engine movement crosses the field but ends outside it.
    processor._process_movement(victim.owner)
    assert victim.position == Position(1000, 0)
    processor._process_minefield_detonations(victim.owner)
    assert [field.mines_remaining for field in fields] == [2, 2]
    victim.position = Position(0, 0)
    processor._process_minefield_detonations(victim.owner)
    assert victim.current_hit_points == 0 and victim not in sector.units
    assert [field.mines_remaining for field in fields] == [1, 2]


def test_setup_presentation_failure_does_not_reject_commit():
    game = campaign()
    settings = settings_for(game.galaxy)
    preview = game.galaxy
    game.gui, game.ai_coordinator = Mock(), Mock()
    game.gui.show_game_ui.side_effect = RuntimeError('broken presentation')
    game.check_and_schedule_ai_turn = Mock()
    assert start_new_game(game, settings)
    assert game.galaxy is not preview and game.last_setup_error is None
    game.ai_coordinator.reset.assert_called_once()
    game.check_and_schedule_ai_turn.assert_called_once()
    settings.player_configs[0].home_system_name = 'Changed later'
    assert game.settings.player_configs[0].home_system_name == 'Sol'


def test_wizard_stays_open_when_preparation_fails():
    from game_actions.app_actions import handle_start_new_game_with_settings
    game = campaign()
    game.gui = Mock()
    game.start_new_game = lambda settings: start_new_game(game, settings)
    settings = settings_for(game.galaxy)
    settings.starting_population = -1
    handle_start_new_game_with_settings(game, {'settings': settings})
    game.gui.close_new_game_wizard.assert_not_called()
    game.gui.show_warning_dialog.assert_called_once()


def test_control_protocol_uses_normal_topology_validation():
    from game_control_protocol import _parse_new_game_settings, ProtocolError
    players = [{'name': str(i), 'controller': 'codex' if i == 0 else 'human', 'team_id': i+1} for i in range(6)]
    with pytest.raises(ProtocolError, match='distinct'):
        _parse_new_game_settings({'num_systems': 5, 'players': players})
    players = players[:2]
    for player in players:
        player['home_system_name'] = 'Sol'
    with pytest.raises(ProtocolError, match='distinct'):
        _parse_new_game_settings({'num_systems': 5, 'players': players})


def test_reference_planet_table_matches_numeric_authority():
    from pathlib import Path
    from constants import PLANET_TRAITS
    reference = (Path(__file__).resolve().parents[1] / 'docs' / 'REFERENCE.md').read_text(encoding='utf-8')
    table = reference.split('### 12.1 Planetary Classification & Traits')[1].split('### 12.2')[0]
    rows = [line.split('|')[1:-1] for line in table.splitlines() if line.startswith('| **')]
    assert len(rows) == len(PLANET_TRAITS)
    for row in rows:
        name, colonizable, population, growth, metal, crystal, antimatter = [cell.strip().replace('**', '') for cell in row]
        traits = PLANET_TRAITS[PlanetType[name.upper().replace(' ', '_')]]
        assert (colonizable == 'Yes') == traits['is_colonizable']
        assert float(population) == traits['max_population']
        assert float(growth.split('%')[0]) / 100 == pytest.approx(traits['growth_rate'])
        assert float(metal.split()[0]) == traits['passive_metal']
        assert float(crystal.split()[0]) == traits['passive_crystal']
        assert float(antimatter.rstrip('x')) == traits['am_harvest_multiplier']
