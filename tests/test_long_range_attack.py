"""Real-engine coverage of attack approach policy and its public interfaces."""
from unittest.mock import MagicMock, patch
from types import SimpleNamespace

import pytest

from constants import HullSize
from domain.deployables import Deployable
from events import AttackUnitEvent
from game_ai.contracts import Command, ContractError
from game_ai.observation import build_observation
from game_ai.order_view import order_layers
from geometry import Position
from gui.sidebar.order_formatting import format_order_state_data
from input_processor.context_actions import handle_context_menu_action
from input_processor.context_menu_builder import build_sector_context_menu_options
from order_system import OrderSystem
from save_manager import serialize_unit, deserialize_unit, _restore_saved_commander
from tests.support.combat import create_combat_ship
from tests.support.commands import world, issue, waypoint
from unit_components.enums import TurretType, TurretVariant, UnitStance
from unit_components.weapons import Turret, Weapons
from unit_components.movement import Engines
from unit_orders.base import OrderStatus
from unit_orders.combat import AttackOrder, AttackLongRangeOrder
from unit_orders.movement import MoveOrder
from turn_processor import TurnProcessor


@pytest.fixture
def battle():
    game, player, enemy, unit = world()
    game.current_player_index = 0
    game.current_system_name = 'Sol'
    game.current_sector_coord = (0, 0)
    game.selected_objects = [unit]
    game.event_bus = MagicMock()
    game.is_unit_visible = lambda target: True
    target = create_combat_ship(game.galaxy, enemy, 'Target', (0, 0), pos=(1000, 0))
    target.current_hit_points = target.max_hit_points = 1000
    for base_range in (200, 300):
        unit.weapons_component.add_turret(Turret(
            TurretType.BEAM, damage=3, range=base_range, cooldown=1,
            parent_unit=unit, variant=TurretVariant.LONG_RANGE))
    return game, player, unit, target


@pytest.mark.parametrize('order_class,limit', [(AttackOrder, 300), (AttackLongRangeOrder, 600)])
@pytest.mark.parametrize('component', [None, 'Engines'])
@pytest.mark.parametrize('target_distance', [149, 150, 151, 200, 299, 300, 301, 400, 600, 750, 1000])
def test_approach_uses_shortest_relevant_effective_range(battle, order_class, limit, component, target_distance):
    game, _, unit, target = battle
    if component:
        limit *= 0.5
    target.position = Position(target_distance, 0)
    order = order_class(unit, {'target_unit_id': target.id, 'target_component_type': component})
    unit.commander_component.add_order(order)
    assert order.status == OrderStatus.IN_PROGRESS
    assert bool(order.sub_orders) == (target_distance >= limit)
    if order.sub_orders:
        assert order.sub_orders[0].parameters['standoff_distance'] == limit - 5
    # Repeated updates must not stop merely because a longer turret is in range.
    order.update(game.galaxy)
    assert bool(order.sub_orders) == (target_distance >= limit)


@pytest.mark.parametrize('order_class,limit', [(AttackOrder, 300), (AttackLongRangeOrder, 600)])
@pytest.mark.parametrize('component', [None, 'Engines'])
def test_pursuit_stops_and_restarts_without_retreat(battle, order_class, limit, component):
    game, _, unit, target = battle
    if component:
        limit *= 0.5
    order = order_class(unit, {'target_unit_id': target.id, 'target_component_type': component})
    unit.commander_component.add_order(order)
    approach = order.sub_orders[0]
    target.position = Position(limit - 10, 0)
    order.update(game.galaxy)
    assert approach.status == OrderStatus.CANCELLED
    assert not order.sub_orders
    assert unit.engines_component.move_target is None
    assert unit.position == Position(0, 0)
    target.position = Position(limit + 100, 0)
    order.update(game.galaxy)
    assert order.sub_orders[0].parameters['destination_position'] == Position(105, 0)
    # Pursuit across sectors requires continuing shared detailed coverage.
    game.galaxy.systems['Sol'].hexes[(0, 0)].units.remove(target)
    target.in_hex = (0, 1)
    game.galaxy.systems['Sol'].hexes[(0, 1)].units.append(target)
    create_combat_ship(game.galaxy, unit.owner, 'Forward scout', (0, 1))
    order.update(game.galaxy)
    assert order.sub_orders[0].parameters['destination_hex_coord'] == (0, 1)


@pytest.mark.parametrize('component,standoff', [(None, 595), ('Engines', 295)])
def test_range_policy_uses_variant_and_ignores_cooldowns(battle, component, standoff):
    game, _, unit, target = battle
    unit.weapons_component.turrets[0].range = 2000
    for turret in unit.weapons_component.turrets:
        turret.current_cooldown = 20
    target.position = Position(750, 0)
    order = AttackLongRangeOrder(unit, {'target_unit_id': target.id, 'target_component_type': component})
    unit.commander_component.add_order(order)
    assert order.sub_orders[0].parameters['standoff_distance'] == standoff


@pytest.mark.parametrize('turret_type', list(TurretType))
@pytest.mark.parametrize('variant', list(TurretVariant))
@pytest.mark.parametrize('component', [None, 'Engines'])
@pytest.mark.parametrize('offset', [-0.01, 0, 0.01])
def test_firing_range_boundary(battle, turret_type, variant, component, offset):
    game, _, unit, target = battle
    turret = Turret(turret_type, damage=8, range=301, cooldown=2,
                    parent_unit=unit, variant=variant)
    unit.weapons_component.turrets = [turret]
    hull_range = 903 if variant == TurretVariant.LONG_RANGE else 301
    limit = hull_range * 0.5 if component else hull_range
    target.position = Position(limit + offset, 0)
    target.engines_component.current_hit_points = target.engines_component.max_hit_points = 100
    unit.commander_component.add_order(AttackOrder(unit, {
        'target_unit_id': target.id, 'target_component_type': component}))
    hull_hp = target.current_hit_points
    engine_hp = target.engines_component.current_hit_points
    unit.weapons_component.update(game.galaxy)
    fired = offset < 0
    assert (turret.current_cooldown > 0) == fired
    assert (target.current_hit_points < hull_hp) == (fired and component is None)
    assert (target.engines_component.current_hit_points < engine_hp) == (fired and component is not None)
    assert turret.range == hull_range
    assert turret.target is target
    assert turret.target_component_type is (Engines if component else None)


@pytest.mark.parametrize('order_class', [AttackOrder, AttackLongRangeOrder])
def test_component_attack_holds_fire_and_fires_turrets_independently(battle, order_class):
    game, _, unit, target = battle
    weapons = unit.weapons_component
    target.engines_component.current_hit_points = target.engines_component.max_hit_points = 100
    target.position = Position(500, 0)
    order = order_class(unit, {'target_unit_id': target.id, 'target_component_type': 'Engines'})
    unit.commander_component.add_order(order)
    for turret in weapons.turrets:
        turret.current_cooldown = 2
    hull_hp = target.current_hit_points
    for remaining in (1, 0, 0):
        weapons.update(game.galaxy)
        assert [t.current_cooldown for t in weapons.turrets] == [remaining] * 3
        assert target.current_hit_points == hull_hp
        assert target.engines_component.current_hit_points == 100
        assert all(t.target is target and t.target_component_type is Engines for t in weapons.turrets)

    target.position = Position(375, 0)
    order.update(game.galaxy)
    weapons.update(game.galaxy)
    assert order.sub_orders  # The longest turret can fire while the ship still approaches.
    assert [t.current_cooldown > 0 for t in weapons.turrets] == [False, False, True]
    assert target.engines_component.current_hit_points == 97
    assert target.current_hit_points == hull_hp

    target.position = Position(100, 0)
    order.update(game.galaxy)
    for turret in weapons.turrets:
        turret.current_cooldown = 0
    weapons.update(game.galaxy)
    assert not order.sub_orders
    assert all(t.current_cooldown > 0 for t in weapons.turrets)
    assert target.engines_component.current_hit_points == 71
    assert target.current_hit_points == hull_hp


@pytest.mark.parametrize('order_class', [AttackOrder, AttackLongRangeOrder])
@pytest.mark.parametrize('phase', ['queued', 'cancelled'])
def test_inactive_component_attack_cannot_fire(battle, order_class, phase):
    game, _, unit, target = battle
    target.position = Position(100, 0)
    commander = unit.commander_component
    if phase == 'queued':
        commander.add_order(MoveOrder(unit, {'destination_system_name': 'Sol',
            'destination_hex_coord': (0, 0), 'destination_position': Position(500, 0)}))
    commander.add_order(order_class(unit, {'target_unit_id': target.id, 'target_component_type': 'Engines'}))
    if phase == 'cancelled':
        commander.clear_explicit_orders()
    unit.weapons_component.set_target(target, Engines)  # Simulate a stale cached lock.
    hull_hp, engine_hp = target.current_hit_points, target.engines_component.current_hit_points
    unit.weapons_component.update(game.galaxy)
    assert (target.current_hit_points, target.engines_component.current_hit_points) == (hull_hp, engine_hp)
    assert all(t.target is None for t in unit.weapons_component.turrets)


@pytest.mark.parametrize('kind,action,label,limit', [
    ('attack', 'attack_unit_Engines', 'Attack Engines (50% range)', 150),
    ('attack_long_range', 'attack_long_range_Engines', 'Engines (50% range)', 300),
])
def test_human_and_automated_component_attacks_share_range(battle, kind, action, label, limit):
    game, player, unit, target = battle
    options, _ = build_sector_context_menu_options(game, target, target.position)
    attack_options = dict(options)['Attack (long-range only)'] if kind == 'attack_long_range' else options
    assert (label, action) in attack_options
    with patch('input_processor.context_actions._get_shift_pressed', return_value=False):
        handle_context_menu_action(game, action, target)
    OrderSystem(game, game.event_bus).handle_attack_unit(game.event_bus.publish.call_args.args[0])
    human = unit.commander_component.current_order
    assert human.approach_range(target) == limit
    assert human.sub_orders[0].parameters['standoff_distance'] == limit - 5
    assert issue(game, player, Command(kind, (unit.id,), target_id=target.id, target_component='Engines')).accepted
    automated = unit.commander_component.current_order
    assert automated.parameters == human.parameters
    assert automated.approach_range(target) == limit
    assert automated.sub_orders[0].parameters['standoff_distance'] == limit - 5
    view = next(u for u in build_observation(game, player)['units'] if u['id'] == unit.id)
    assert [t['range'] for t in view['capability_details']['weapons']['turrets']] == [300, 600, 900]
    target.engines_component.current_hit_points = 0
    target.position = Position(100, 0)
    automated.update(game.galaxy)
    assert automated.status == OrderStatus.COMPLETED
    assert all(t.target is None for t in unit.weapons_component.turrets)


@pytest.mark.parametrize('order_class,arrival', [(AttackOrder, 705), (AttackLongRangeOrder, 405)])
@pytest.mark.parametrize('component', [None, 'Engines'])
def test_owner_turn_movement_stops_at_the_relevant_range(battle, order_class, arrival, component):
    game, player, unit, target = battle
    if component:
        arrival = 855 if order_class is AttackOrder else 705
    unit.commander_component.add_order(order_class(unit, {'target_unit_id': target.id, 'target_component_type': component}))
    processor = TurnProcessor(game)
    for _ in range(12):
        processor._process_movement(player)
        unit.commander_component.update()
    assert unit.position.x == pytest.approx(arrival)
    assert unit.engines_component.move_target is None
    assert unit.commander_component.current_order.status == OrderStatus.IN_PROGRESS


@pytest.mark.parametrize('broken', ['missing', 'destroyed', 'no_long_range', 'wing_target'])
def test_unavailable_long_range_order_fails_without_fallback(battle, broken):
    game, _, unit, target = battle
    if broken == 'missing':
        unit.remove_component(Weapons)
    elif broken == 'destroyed':
        unit.weapons_component.current_hit_points = 0
    elif broken == 'no_long_range':
        unit.weapons_component.turrets = unit.weapons_component.turrets[:1]
    else:
        target.hull_size = HullSize.STRIKECRAFT_WING
    order = AttackLongRangeOrder(unit, {'target_unit_id': target.id})
    unit.commander_component.add_order(order)
    assert order.status == OrderStatus.FAILED
    assert order.failure_reason == 'capability_unavailable'
    assert not order.sub_orders


def test_normal_attack_ignores_turrets_that_cannot_hit_target(battle):
    game, _, unit, target = battle
    target.hull_size = HullSize.STRIKECRAFT_WING
    unit.weapons_component.turrets[0].variant = TurretVariant.ANTI_STRIKECRAFT
    unit.weapons_component.turrets[1].range = 50
    target.position = Position(200, 0)
    order = AttackOrder(unit, {'target_unit_id': target.id})
    unit.commander_component.add_order(order)
    assert order.status == OrderStatus.IN_PROGRESS
    assert not order.sub_orders


@pytest.mark.parametrize('pre_movement', [False, True])
def test_losing_long_range_capability_releases_navigation_and_fire(battle, pre_movement):
    game, player, unit, target = battle
    commander = unit.commander_component
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    order = AttackLongRangeOrder(unit, {'target_unit_id': target.id})
    commander.add_order(order)
    assert unit.engines_component.move_target is not None
    unit.weapons_component.turrets = unit.weapons_component.turrets[:1]
    if pre_movement:
        commander.prepare_for_movement()
    else:
        order.update(game.galaxy)
    assert order.status == OrderStatus.FAILED
    assert order.failure_reason == 'capability_unavailable'
    assert unit.engines_component.move_target is None
    assert all(t.target is None for t in unit.weapons_component.turrets)
    commander.update()
    assert len([e for e in player.order_history if e['order_id'] == order.public_id]) == 1


def test_all_turrets_can_fire_and_queue_cancellation_preserves_active_attack(battle):
    game, _, unit, target = battle
    target.position = Position(750, 0)
    commander = unit.commander_component
    order = AttackLongRangeOrder(unit, {'target_unit_id': target.id})
    commander.add_order(order)
    weapons = unit.weapons_component
    weapons.update(game.galaxy)
    assert [t.current_cooldown > 0 for t in weapons.turrets] == [False, False, True]
    assert order.sub_orders
    queued = AttackLongRangeOrder(unit, {'target_unit_id': target.id})
    commander.add_order(queued)
    commander.cancel_order(queued.local_order_id)
    assert commander.get_active_attack_order() is order
    assert all(t.target is target for t in weapons.turrets)
    target.position = Position(200, 0)
    order.update(game.galaxy)
    for turret in weapons.turrets:
        turret.current_cooldown = 0
    weapons.update(game.galaxy)
    assert all(t.current_cooldown > 0 for t in weapons.turrets)
    commander.clear_explicit_orders()
    commander.add_order(MoveOrder(unit, {'destination_system_name': 'Sol',
        'destination_hex_coord': (0, 0), 'destination_position': Position(500, 0)}))
    commander.add_order(AttackLongRangeOrder(unit, {'target_unit_id': target.id}))
    weapons.set_target(target)  # A cached target must not grant authority to a queued attack.
    hp = target.current_hit_points
    weapons.update(game.galaxy)
    assert target.current_hit_points == hp
    assert all(t.target is None for t in weapons.turrets)


@pytest.mark.parametrize('queue', [False, True])
def test_human_menu_and_dispatch_preserve_ineligible_units(battle, queue):
    game, player, unit, target = battle
    other = create_combat_ship(game.galaxy, player, 'Short range', (0, 0))
    game.selected_objects = [unit, other]
    assert issue(game, player, Command.from_dict({'type': 'move', 'unit_ids': [unit.id, other.id], **waypoint()})).accepted
    previous = [u.commander_component.current_order for u in (unit, other)]
    options, _ = build_sector_context_menu_options(game, target, target.position)
    submenu = dict(options)['Attack (long-range only)']
    assert ('Hull', 'attack_long_range') in submenu
    assert ('Weapons (50% range)', 'attack_long_range_Weapons') in submenu
    with patch('input_processor.context_actions._get_shift_pressed', return_value=queue):
        handle_context_menu_action(game, 'attack_long_range_Weapons', target)
    event = game.event_bus.publish.call_args.args[0]
    assert isinstance(event, AttackUnitEvent) and event.long_range_only
    OrderSystem(game, game.event_bus).handle_attack_unit(event)
    assert other.commander_component.current_order is previous[1]
    assert not other.commander_component.orders_queue
    if queue:
        assert unit.commander_component.current_order is previous[0]
        attack = unit.commander_component.orders_queue[0]
    else:
        attack = unit.commander_component.current_order
        assert previous[0].status == OrderStatus.CANCELLED
    assert isinstance(attack, AttackLongRangeOrder)
    assert attack.parameters['target_component_type'] == 'Weapons'
    game.selected_objects = [other]
    assert 'Attack (long-range only)' not in dict(build_sector_context_menu_options(game, target, target.position)[0])


@pytest.mark.parametrize('invalid', ['no_long_range', 'destroyed', 'disabled', 'hidden_target', 'wing_target'])
def test_menu_and_gateway_reject_ineligible_attacks_without_replacing_work(battle, invalid):
    game, player, unit, target = battle
    assert issue(game, player, Command.from_dict({'type': 'move', 'unit_ids': [unit.id], **waypoint()})).accepted
    original = unit.commander_component.current_order
    if invalid == 'no_long_range':
        unit.weapons_component.turrets = unit.weapons_component.turrets[:1]
    elif invalid == 'destroyed':
        unit.weapons_component.current_hit_points = 0
    elif invalid == 'disabled':
        unit.is_disabled = True
    elif invalid == 'wing_target':
        target.hull_size = HullSize.STRIKECRAFT_WING
    else:
        target.position = Position(4000, 0)
        game.is_unit_visible = lambda _: False
    result = issue(game, player, Command('cancel_orders', (unit.id,)),
                   Command('attack_long_range', (unit.id,), target_id=target.id))
    assert not result.accepted and result.failure_stage == 'preflight'
    assert unit.commander_component.current_order is original
    assert 'Attack (long-range only)' not in dict(build_sector_context_menu_options(game, target, target.position)[0])


def test_discovery_gateway_and_hidden_target_redaction(battle):
    game, player, unit, target = battle
    view = next(u for u in build_observation(game, player)['units'] if u['id'] == unit.id)
    assert 'attack_long_range' in view['supported_commands']
    assert 'attack_long_range' in view['legal_commands']
    assert target.id in view['command_options']['attack_long_range']['target_ids']
    assert 'Weapons' in view['command_options']['attack_long_range']['target_components'][str(target.id)]
    command = Command('attack_long_range', (unit.id,), target_id=target.id, target_component='Weapons')
    assert Command.from_dict(command.to_dict()) == command
    with pytest.raises(ContractError):
        Command.from_dict({**command.to_dict(), 'position': [0, 0]})
    assert issue(game, player, command).accepted
    current = unit.commander_component.current_order
    assert isinstance(current, AttackLongRangeOrder)
    visible = order_layers(unit, 'self', {unit.id, target.id}, set())['current_order']
    assert visible['type'] == 'attack_long_range'
    assert visible['parameters']['target_component'] == 'Weapons'
    hidden = order_layers(unit, 'self', {unit.id}, set())['current_order']
    def check_redacted(order):
        assert order['target_id'] is None and order['parameters'] == {}
        for child in order['suborders']:
            check_redacted(child)
    check_redacted(hidden)
    assert order_layers(unit, 'enemy', {unit.id, target.id}, set()) == {}
    target.position = Position(4000, 0)
    hidden_result = issue(game, player, command)
    missing_result = issue(game, player, Command('attack_long_range', (unit.id,), target_id=999999))
    assert hidden_result.errors[0].code == missing_result.errors[0].code == 'target_unavailable'
    assert unit.commander_component.current_order is current


def test_invalid_member_rejects_the_whole_automated_group(battle):
    game, player, unit, target = battle
    other = create_combat_ship(game.galaxy, player, 'Short range', (0, 0))
    assert issue(game, player, Command('attack', (unit.id, other.id), target_id=target.id)).accepted
    previous = [u.commander_component.current_order for u in (unit, other)]
    result = issue(game, player, Command('attack_long_range', (unit.id, other.id), target_id=target.id))
    assert not result.accepted and result.applied_count == 0
    assert [u.commander_component.current_order for u in (unit, other)] == previous


def test_save_load_preserves_active_approach_queue_identity_and_subsystem(battle):
    game, player, unit, target = battle
    first = Command('attack_long_range', (unit.id,), target_id=target.id, target_component='Weapons')
    assert issue(game, player, first, Command('attack_long_range', (unit.id,), target_id=target.id, queue=True)).accepted
    order = unit.commander_component.current_order
    queued = unit.commander_component.orders_queue[0]
    history = list(player.order_history)
    restored = deserialize_unit(serialize_unit(unit), {p.id: p for p in game.players}, game)
    _restore_saved_commander(restored, game)
    active = restored.commander_component.current_order
    assert isinstance(active, AttackLongRangeOrder)
    assert active.public_id == order.public_id
    assert active.sub_orders[0].public_id == order.sub_orders[0].public_id
    assert active.parameters['target_component_type'] == 'Weapons'
    assert active.approach_range(target) == 300
    assert active.sub_orders[0].parameters['standoff_distance'] == 295
    assert [t.range for t in restored.weapons_component.turrets] == [300, 600, 900]
    assert all(t.target_component_type is Weapons for t in restored.weapons_component.turrets)
    assert restored.commander_component.orders_queue[0].public_id == queued.public_id
    assert restored.commander_component.orders_queue[0].status == OrderStatus.PENDING
    assert all(t.target is target for t in restored.weapons_component.turrets)
    assert restored.engines_component.move_target == unit.engines_component.move_target
    assert player.order_history == history
    assert 'Attack (long-range only)' in format_order_state_data(active.get_state_data())[0]
    # Loading keeps the component lock and cannot grant hull-range fire.
    target.position = Position(500, 0)
    hull_hp = target.current_hit_points
    component_hp = target.weapons_component.current_hit_points
    restored.weapons_component.update(game.galaxy)
    assert target.current_hit_points == hull_hp
    assert target.weapons_component.current_hit_points == component_hp
    assert all(t.current_cooldown == 0 for t in restored.weapons_component.turrets)
    target.weapons_component.current_hit_points = 0
    target.position = Position(200, 0)
    active.update(game.galaxy)
    assert active.status == OrderStatus.COMPLETED


def test_deployable_target_supports_human_and_automated_long_range_attack(battle):
    game, player, unit, target = battle
    deployable = Deployable(target.owner, Position(1000, 0), (0, 0), 'Sol', 'ghost_fleet', target.id, game.galaxy)
    deployable.identified_player_ids.add(player.id)
    game.galaxy.systems['Sol'].hexes[(0, 0)].deployables.append(deployable)
    options, _ = build_sector_context_menu_options(game, deployable, deployable.position)
    assert ('Attack (long-range only)', 'attack_long_range') in options
    view = next(u for u in build_observation(game, player)['units'] if u['id'] == unit.id)
    assert 'attack_long_range' in view['legal_commands']
    assert deployable.id in view['command_options']['attack_long_range']['target_ids']
    assert issue(game, player, Command('attack_long_range', (unit.id,), target_id=deployable.id)).accepted
    order = unit.commander_component.current_order
    assert order.sub_orders[0].parameters['standoff_distance'] == 595
    unit.commander_component.prepare_for_movement()
    assert order.status == OrderStatus.IN_PROGRESS


@pytest.mark.parametrize('deployable_target', [False, True])
def test_attack_overlays_keep_target_and_attack_style(battle, deployable_target):
    from constants import RED
    from rendering.sector_renderer.sector_overlay_renderer import SectorOverlayRenderer
    from rendering.system_renderer import SystemViewRenderer
    game, _, unit, target = battle
    if deployable_target:
        target = Deployable(target.owner, Position(1000, 0), (0, 1), 'Sol', 'ghost_fleet', target.id, game.galaxy)
        game.galaxy.systems['Sol'].hexes[(0, 1)].deployables.append(target)
    else:
        target.in_hex = (0, 1)
    order = AttackLongRangeOrder(unit, {'target_unit_id': target.id})
    unit.commander_component.restore_explicit_orders(None, [order])
    overlay = SectorOverlayRenderer(SimpleNamespace(game=game))
    assert overlay.order_targets_sector(order, 'Sol', (0, 1))
    waypoints = []
    overlay.collect_waypoints_from_order(order, unit, waypoints)
    assert waypoints[-1]['position'] == target.position
    assert overlay.get_waypoint_style(waypoints[-1]) == (RED, 2)
    game.screen = MagicMock()
    game.overlay_surface = MagicMock()
    game.system_view_mouse_hover_hex = None
    renderer = SystemViewRenderer(game)
    with patch.object(renderer, '_hex_to_pixel', side_effect=lambda q, r: Position(q * 10, r * 10)), \
            patch('rendering.system_renderer.pygame.draw.line') as line, \
            patch('rendering.system_renderer.pygame.draw.circle'):
        renderer._draw_system_view_order_lines(game.galaxy.systems['Sol'])
    assert any(call.args[1] == RED and call.args[3] == (0, 10) for call in line.call_args_list)
