"""Lost sensor contact cancels pursuit, across owners and execution boundaries."""
import json
import logging
from unittest.mock import Mock

import pytest

from geometry import Position
from order_history import history_view
from tests.support.campaigns import campaign
from tests.support.combat import create_combat_ship
from turn_processor import TurnProcessor
from unit_components.enums import TurretType, TurretVariant, UnitStance
from unit_components.intelligence import Agent
from unit_components.sensors import Sensors
from unit_components.weapons import Turret
from unit_orders.base import OrderStatus
from unit_orders.combat import AttackOrder, AttackLongRangeOrder, ProtectOrder
from unit_orders.defend import DefendOrder
from unit_orders.movement import MoveOrder
from unit_orders.patrol import PatrolOrder
from visibility import VisibilityService, is_unit_visible, hex_has_presence


@pytest.fixture
def battle():
    game = campaign()
    game.galaxy.game = game
    attacker = create_combat_ship(game.galaxy, game.players[0], 'System Enforcer 1', (0, 0), short_range=800)
    target = create_combat_ship(game.galaxy, game.players[1], 'Colonizer', (0, 0), pos=(600, 0))
    return game, attacker, target


def attack_ship(attacker, target, order_class=AttackOrder, component=None):
    variant = TurretVariant.LONG_RANGE if order_class is AttackLongRangeOrder else TurretVariant.STANDARD
    attacker.weapons_component.turrets = [Turret(
        TurretType.MASS_DRIVER, damage=6, range=100 if variant == TurretVariant.LONG_RANGE else 300,
        cooldown=2, parent_unit=attacker, variant=variant)]
    order = order_class(attacker, {'target_unit_id': target.id, 'target_component_type': component})
    attacker.commander_component.add_order(order)
    assert order.status == OrderStatus.IN_PROGRESS
    return order


def move_order(unit, position, sector=(0, 0)):
    return MoveOrder(unit, {'destination_system_name': 'Sol', 'destination_hex_coord': sector,
                            'destination_position': Position(*position)})


def assert_released(unit, order):
    assert order.status == OrderStatus.CANCELLED
    assert order.failure_reason == 'target_not_visible'
    assert not order.sub_orders
    assert unit.engines_component.move_target is None
    assert unit.hyperdrive_component.hex_jump_target is None
    assert unit.hyperdrive_component.wormhole_jump_target is None
    assert all(t.target is None and t.target_component_type is None for t in unit.weapons_component.turrets)


@pytest.mark.parametrize('order_class', [AttackOrder, AttackLongRangeOrder])
@pytest.mark.parametrize('component', [None, 'Hyperdrive'])
@pytest.mark.parametrize('checkpoint', ['movement', 'weapons', 'order', 'turn_end'])
@pytest.mark.parametrize('missing_binding', [False, True])
def test_contact_loss_cancels_once_without_pursuit_or_revival(
        battle, order_class, component, checkpoint, missing_binding, caplog):
    game, attacker, target = battle
    order = attack_ship(attacker, target, order_class, component)
    approach = order.sub_orders[0]
    waypoint = approach.sub_orders[0]
    attacker.sensors_component.short_range_radius = 0
    if missing_binding:
        attacker.weapons_component.clear_target()  # The original stalled-turret state.
    before = (attacker.position, attacker.antimatter_component.current_amount, target.current_hit_points,
              target.hyperdrive_component.current_hit_points)
    caplog.set_level(logging.DEBUG, logger='unit_orders.combat')
    processor = TurnProcessor(game)
    if checkpoint == 'movement':
        processor._process_movement(attacker.owner)
    elif checkpoint == 'weapons':
        attacker.weapons_component.update(game.galaxy)
    elif checkpoint == 'order':
        order.update(game.galaxy)
    else:
        processor._cancel_hidden_attacks()
    assert_released(attacker, order)
    assert approach.status == waypoint.status == OrderStatus.CANCELLED
    assert before == (attacker.position, attacker.antimatter_component.current_amount, target.current_hit_points,
                      target.hyperdrive_component.current_hit_points)
    attacker.sensors_component.short_range_radius = 800
    for _ in range(2):
        order.execute(game.galaxy)
        order.update(game.galaxy)
        order.resume(game.galaxy)
        processor._cancel_hidden_attacks()
        attacker.update()
    assert_released(attacker, order)
    assert attacker.commander_component.current_order is None
    events = history_view(attacker.owner)['events']
    assert len(events) == 1 and events[0]['outcome'] == 'cancelled'
    assert events[0]['reason'] == 'target_not_visible'
    assert [r.message for r in caplog.records if 'Attack cancelled:' in r.message] == [
        f'Attack cancelled: attacker={attacker.id} target={target.id} '
        f'order={order.public_id} reason=target_not_visible']


def test_enemy_turn_jump_cancels_before_next_players_briefing(battle):
    from turn_briefing import initialize_campaign, begin_window, summary_view
    game, attacker, target = battle
    initialize_campaign(game)
    begin_window(game, attacker.owner)
    target.position = Position(145, 0)
    order = attack_ship(attacker, target, component='Hyperdrive')
    attacker.update()
    hp = target.hyperdrive_component.current_hit_points
    assert hp < target.hyperdrive_component.max_hit_points
    before = (attacker.position, attacker.antimatter_component.current_amount,
              attacker.weapons_component.turrets[0].current_cooldown)
    target.commander_component.add_order(move_order(target, (1000, 0), (1, 0)))
    game.current_player_index = 1
    TurnProcessor(game).end_turn()
    assert target.in_hex == (1, 0)
    assert game.current_player_index == 0
    assert attacker.commander_component.current_order is None
    assert_released(attacker, order)
    assert before == (attacker.position, attacker.antimatter_component.current_amount,
                      attacker.weapons_component.turrets[0].current_cooldown)
    assert any('target not visible' in e['detail'] for e in summary_view(attacker.owner)['entries'])
    TurnProcessor(game)._process_movement(attacker.owner)
    assert attacker.position == before[0]
    assert target.hyperdrive_component.current_hit_points == hp


@pytest.mark.parametrize('coverage', ['allied_scout', 'agent'])
def test_shared_owner_coverage_survives_beyond_attackers_sensors(battle, coverage):
    from domain.players import Player
    game, attacker, target = battle
    order = attack_ship(attacker, target)
    attacker.sensors_component.short_range_radius = 0
    if coverage == 'allied_scout':
        ally = Player('Ally', (0, 0, 200), team_id=attacker.owner.team_id)
        game.players.append(ally)
        create_combat_ship(game.galaxy, ally, 'Scout', target.in_hex, pos=(600, 0))
    else:
        target.infiltrating_agents.append(Agent(attacker.owner, attacker.id, 'UNIT', target.id))
    # The active UI viewer is deliberately unrelated to the attacking owner.
    game.current_player_index = 1
    before = dict(attacker.owner.sector_intel)
    TurnProcessor(game)._cancel_hidden_attacks()
    assert order.status == OrderStatus.IN_PROGRESS
    assert attacker.owner.sector_intel == before


def test_radar_presence_does_not_preserve_attack(battle):
    game, attacker, target = battle
    order = attack_ship(attacker, target)
    attacker.sensors_component.short_range_radius = 200
    attacker.sensors_component.long_range_hexes = 2
    snapshot = VisibilityService.compute(game.galaxy, attacker.owner, record_intel=False)
    assert hex_has_presence(snapshot, 'Sol', target.in_hex)
    assert not is_unit_visible(snapshot, target)
    game.current_player_index = 1  # The UI viewer can see its own ship; the attacker cannot.
    TurnProcessor(game)._cancel_hidden_attacks()
    assert_released(attacker, order)


@pytest.mark.parametrize('concealment', ['atmosphere', 'docked'])
def test_target_leaving_deployed_space_is_a_lost_contact(battle, concealment):
    from constants import HullSize, PlanetType
    from domain.celestials import Planet
    from unit_components.hangar import HangarComponent
    game, attacker, target = battle
    order = attack_ship(attacker, target)
    if concealment == 'atmosphere':
        giant = Planet((0, 0), 'Sol', PlanetType.GAS_GIANT)
        giant.position = target.position
        game.galaxy.systems['Sol'].add_celestial_body(giant)
        assert giant.hide_unit(target, game.galaxy)
    else:
        carrier = create_combat_ship(game.galaxy, target.owner, 'Carrier', (0, 0), pos=(600, 0))
        hangar = HangarComponent(carrier, max_slots=1)
        carrier.add_component(hangar)
        target.hull_size = HullSize.TINY
        assert hangar.dock(target, game.galaxy)
    assert target not in game.galaxy.systems['Sol'].hexes[(0, 0)].units
    TurnProcessor(game)._cancel_hidden_attacks()
    assert_released(attacker, order)


@pytest.mark.parametrize('cause', ['sensor_destroyed', 'sensor_sabotage', 'cloak', 'nebula'])
def test_sensor_and_concealment_rules_drive_cancellation(battle, cause):
    from constants import NebulaType
    from domain.celestials import Nebula
    from unit_components.cloaking import CloakingDevice
    from unit_components.enums import CloakingType, SabotageType
    game, attacker, target = battle
    order = attack_ship(attacker, target)
    if cause == 'sensor_destroyed':
        attacker.take_component_damage(Sensors, attacker.sensors_component.max_hit_points)
    elif cause == 'sensor_sabotage':
        agent = Agent(target.owner, target.id, 'UNIT', attacker.id)
        agent.active_sabotage = SabotageType.SENSORS
        attacker.infiltrating_agents.append(agent)
    else:
        if cause == 'cloak':
            cloak = CloakingDevice(target, device_type=CloakingType.BASIC)
            target.add_component(cloak)
            cloak.is_active = True
        else:
            body = Nebula((0, 0), 'Sol', NebulaType.NITROGEN)
            game.galaxy.systems['Sol'].add_celestial_body(body)
        TurnProcessor(game)._cancel_hidden_attacks()
        assert order.status == OrderStatus.IN_PROGRESS  # Visual coverage beats concealment.
        attacker.sensors_component.short_range_radius = 200
    TurnProcessor(game)._cancel_hidden_attacks()
    assert_released(attacker, order)


def test_queued_work_is_deferred_and_hidden_queued_attacks_revalidate(battle):
    game, attacker, target = battle
    first = attack_ship(attacker, target)
    queued = AttackOrder(attacker, {'target_unit_id': target.id})
    followup = move_order(attacker, (-500, 0))
    commander = attacker.commander_component
    commander.add_order(queued)
    commander.add_order(followup)
    attacker.sensors_component.short_range_radius = 0
    TurnProcessor(game)._cancel_hidden_attacks()
    assert commander.current_order is None
    assert queued.status == followup.status == OrderStatus.PENDING
    assert list(commander.orders_queue) == [queued, followup]
    assert commander.stance == UnitStance.DO_NOTHING
    TurnProcessor(game)._process_movement(attacker.owner)
    assert first.status == queued.status == OrderStatus.CANCELLED
    assert commander.current_order is followup
    assert attacker.position == Position(-100, 0)


@pytest.mark.parametrize('mission', ['stance', 'patrol', 'protect', 'defend'])
def test_parent_mission_survives_and_can_acquire_a_fresh_engagement(battle, mission):
    game, attacker, target = battle
    commander = attacker.commander_component
    if mission == 'stance':
        commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
        commander.update()
        root = commander.standing_order
    else:
        if mission == 'patrol':
            target.position = Position(200, 0)  # Patrol engages within weapon range.
            root = PatrolOrder(attacker, {'waypoints': [
                {'system_name': 'Sol', 'hex_coord': (0, 0), 'position': Position(1500, 0)}]})
        elif mission == 'protect':
            vip = create_combat_ship(game.galaxy, attacker.owner, 'VIP', (0, 0), short_range=0)
            root = ProtectOrder(attacker, {'target_unit_id': vip.id})
        else:
            root = DefendOrder(attacker, {'destination_system_name': 'Sol', 'destination_hex_coord': (0, 0),
                                         'destination_position': Position(0, 0), 'guard_radius': 1000})
        commander.add_order(root)
    attack = root.sub_orders[0]
    assert isinstance(attack, AttackOrder)
    attacker.sensors_component.short_range_radius = 0
    TurnProcessor(game)._cancel_hidden_attacks()
    assert_released(attacker, attack)
    assert root.status == OrderStatus.IN_PROGRESS
    commander.prepare_for_movement()
    commander.update()
    assert root.status == OrderStatus.IN_PROGRESS
    assert commander.get_active_attack_order() is None
    if mission == 'patrol':
        assert root.current_waypoint_index == 0
        assert root.sub_orders[0].parameters['destination_position'] == Position(1500, 0)
    attacker.sensors_component.short_range_radius = 800
    commander.update()
    fresh = commander.get_active_attack_order()
    assert fresh is not None and fresh is not attack
    assert fresh.parameters['target_unit_id'] == target.id


@pytest.mark.parametrize('mode', ['hex_jump', 'system_jump'])
@pytest.mark.parametrize('order_class', [AttackOrder, AttackLongRangeOrder])
@pytest.mark.parametrize('component', [None, 'Hyperdrive'])
def test_deferred_jump_rechecks_contact_before_payment(mode, order_class, component, monkeypatch):
    from tests.test_movement_payment import moving_campaign
    from tests.support.campaigns import ship
    game, attacker, leg, _ = moving_campaign(mode)
    game.galaxy.game = game
    destination_system = 'Beta' if mode == 'system_jump' else 'Sol'
    destination_hex = (0, 0) if mode == 'system_jump' else (1, 0)
    target = ship(game, 'Target', owner=1, system=destination_system, sector=destination_hex)
    scout = ship(game, 'Scout', system=destination_system, sector=destination_hex)
    from unit_components.weapons import Weapons
    weapons = Weapons(attacker)
    variant = TurretVariant.LONG_RANGE if order_class is AttackLongRangeOrder else TurretVariant.STANDARD
    weapons.add_turret(Turret(TurretType.MASS_DRIVER, 6, 300, 2, attacker, variant))
    attacker.add_component(weapons)
    attack = order_class(attacker, {'target_unit_id': target.id, 'target_component_type': component})
    attack.register_explicit_root()
    attack.status = OrderStatus.IN_PROGRESS
    attack.add_sub_order(leg)  # Retain the already prepared real jump actuator.
    attacker.commander_component.current_order = attack
    prepare = attacker.commander_component.prepare_for_movement

    def prepare_then_lose_scout():
        prepare()
        assert attack.status == OrderStatus.IN_PROGRESS
        scout.take_component_damage(Sensors, scout.sensors_component.max_hit_points)

    monkeypatch.setattr(attacker.commander_component, 'prepare_for_movement', prepare_then_lose_scout)
    before = (attacker.in_system, attacker.in_hex, attacker.position, attacker.antimatter_component.current_amount)
    TurnProcessor(game)._process_movement(attacker.owner)
    assert_released(attacker, attack)
    assert before == (attacker.in_system, attacker.in_hex, attacker.position, attacker.antimatter_component.current_amount)
    assert attacker.hyperdrive_component.recharge_time_remaining == 0


def test_cancelled_patrol_engagement_roundtrip_preserves_interrupted_waypoint(battle):
    from save_manager import serialize_game_state, deserialize_game_state
    game, attacker, target = battle
    target.position = Position(200, 0)
    patrol = PatrolOrder(attacker, {'waypoints': [
        {'system_name': 'Sol', 'hex_coord': (0, 0), 'position': Position(1500, 0)}]})
    attacker.commander_component.add_order(patrol)
    attacker.sensors_component.short_range_radius = 0
    TurnProcessor(game)._cancel_hidden_attacks()
    assert patrol.sub_orders[0].status == OrderStatus.CANCELLED
    before = history_view(attacker.owner)
    data = json.loads(json.dumps(serialize_game_state(game)))
    errors = []
    assert deserialize_game_state(game, data, on_error=errors.append), errors
    loaded = game.galaxy.get_unit_by_id(attacker.id)
    restored = loaded.commander_component.current_order
    assert restored.public_id == patrol.public_id
    assert restored.sub_orders[0].failure_reason == 'target_not_visible'
    assert loaded.engines_component.move_target is None
    assert history_view(loaded.owner) == before
    TurnProcessor(game)._process_movement(loaded.owner)
    assert restored.status == OrderStatus.IN_PROGRESS
    assert restored.current_waypoint_index == 0
    assert restored.sub_orders[0].parameters['destination_position'] == Position(1500, 0)
    assert loaded.position == Position(100, 0)
    assert history_view(loaded.owner) == before


def test_observation_preflight_and_loading_do_not_cancel_or_restore_hidden_pursuit(battle):
    from game_ai.observation import build_observation
    from game_ai.contracts import Command, CommandBatch
    from game_ai.commands import CommandGateway
    from save_manager import serialize_game_state, deserialize_game_state
    game, attacker, target = battle
    order = attack_ship(attacker, target)
    attacker.sensors_component.short_range_radius = 0
    before = history_view(attacker.owner)
    build_observation(game, attacker.owner)
    result = CommandGateway(game).apply_batch(attacker.owner, CommandBatch((
        Command(type='attack', unit_ids=(attacker.id,), target_id=target.id),)))
    assert not result.accepted
    assert order.status == OrderStatus.IN_PROGRESS
    assert history_view(attacker.owner) == before
    data = json.loads(json.dumps(serialize_game_state(game)))
    errors = []
    assert deserialize_game_state(game, data, on_error=errors.append), errors
    loaded = game.galaxy.get_unit_by_id(attacker.id)
    restored = loaded.commander_component.current_order
    assert restored.status == OrderStatus.IN_PROGRESS
    assert history_view(loaded.owner) == before
    assert loaded.engines_component.move_target is None
    assert loaded.hyperdrive_component.hex_jump_target is None
    assert loaded.weapons_component.turrets[0].target is None
    TurnProcessor(game)._cancel_hidden_attacks()
    assert_released(loaded, restored)
    recorded = history_view(loaded.owner)
    assert len(recorded['events']) == 1
    data = json.loads(json.dumps(serialize_game_state(game)))
    assert deserialize_game_state(game, data, on_error=errors.append), errors
    TurnProcessor(game)._cancel_hidden_attacks()
    assert history_view(game.players[0]) == recorded


def test_turn_end_reuses_read_only_owner_snapshot(battle, monkeypatch):
    game, attacker, target = battle
    attack_ship(attacker, target)
    second = create_combat_ship(game.galaxy, attacker.owner, 'Second attacker', (0, 0))
    attack_ship(second, target)
    attacker.sensors_component.short_range_radius = second.sensors_component.short_range_radius = 0
    compute = Mock(wraps=VisibilityService.compute)
    monkeypatch.setattr(VisibilityService, 'compute', compute)
    TurnProcessor(game)._cancel_hidden_attacks()
    compute.assert_called_once_with(game.galaxy, attacker.owner, record_intel=False)
