"""Dismantling invariants exercised through real orders, components and gateway."""
from copy import deepcopy
import pytest
from tests.support.campaigns import campaign, ship
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch, ContractError
from constants import HullSize
from geometry import Position
from unit_components.constructor import Constructor
from unit_components.strikecraft import StrikecraftBayComponent
from unit_components.hangar import HangarComponent
from unit_components.movement import Engines
from unit_orders.base import OrderStatus
from dismantling import evaluate, offline, process
from campaign_graph import find_unit


@pytest.fixture
def world():
    game = campaign()
    game.galaxy.game = game
    actor = ship(game, 'Constructor')
    actor.add_component(Constructor(actor))
    target = ship(game, 'Target', hull=HullSize.SMALL)
    return game, actor, target


def issue(game, *commands):
    return CommandGateway(game).apply_batch(game.players[0], CommandBatch(commands))


def start(game, actor, target):
    result = issue(game, Command('dismantle_unit', (actor.id,), target_id=target.id))
    assert result.accepted, result.errors
    return actor.commander_component.current_order


def finish(game, order):
    for _ in range(order.duration + 2):
        game.turn_number += 1
        process(game, order.unit.owner)


def bay_with_wing(game, carrier=None):
    carrier = carrier or ship(game, 'Carrier')
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=3, hull_cost=22.5))
    bay = carrier.strikecraft_bay_component
    assert bay.set_production(0, 'FIGHTER_WING')
    bay.construction_slot_index = 0
    bay.finish_auto_construction(game.galaxy)
    return carrier, bay, bay.docked_units[0]


def test_damage_at_completion_fractional_refund_and_once(world):
    game, actor, target = world
    cost = evaluate(actor, target, game.galaxy).members[0]['build_cost']
    credits = actor.owner.credits
    order = start(game, actor, target)
    assert offline(target) and order.progress == 0
    target.current_hit_points = 17
    finish(game, order)
    expected = 0.5 * cost * 17 / target.max_hit_points
    assert actor.owner.credits == pytest.approx(credits + expected)
    assert find_unit(game.galaxy, target.id) is None
    assert order.status == OrderStatus.COMPLETED
    order.advance(game.galaxy, game.turn_number + 1)
    order.cancel()
    assert actor.owner.credits == pytest.approx(credits + expected)
    assert len([e for e in actor.owner.order_history if e['order_id'] == order.public_id]) == 1


def test_cancel_restores_target_without_salvage(world):
    game, actor, target = world
    credits = actor.owner.credits
    order = start(game, actor, target)
    process(game, actor.owner)
    order.cancel()
    assert not offline(target)
    assert target.current_hit_points == target.max_hit_points
    assert actor.owner.credits == credits
    assert find_unit(game.galaxy, target.id) is target


@pytest.mark.parametrize('change', ['foreign', 'temporary', 'dead', 'self', 'hidden', 'component', 'range'])
def test_reject_illegal_targets(world, change):
    game, actor, target = world
    if change == 'foreign': target.owner = game.players[1]
    elif change == 'temporary': target.is_temporary = True
    elif change == 'dead': target.current_hit_points = 0
    elif change == 'self': target = actor
    elif change == 'hidden': target.is_hidden_in_gas_giant = True
    elif change == 'component': actor.constructor_component.current_hit_points = 0
    elif change == 'range': target.position = Position(1000, 0)
    assert not issue(game, Command('dismantle_unit', (actor.id,), target_id=target.id)).accepted
    assert actor.commander_component.current_order is None


def test_range_boundary_and_mobile_approach(world):
    game, actor, target = world
    target.position = Position(600, 0)
    assert evaluate(actor, target, game.galaxy).blocker is None
    target.position = Position(601, 0)
    actor.add_component(Engines(actor, speed=100))
    order = start(game, actor, target)
    assert order.phase == 'approach' and order.sub_orders and not offline(target)


@pytest.mark.parametrize('change', ['destroy_worker', 'destroy_target', 'capture', 'range', 'component'])
def test_interruptions_release_without_refund(world, change):
    game, actor, target = world
    credits = actor.owner.credits
    order = start(game, actor, target)
    if change == 'destroy_worker': actor.destroy()
    elif change == 'destroy_target': target.destroy()
    elif change == 'capture': target.owner = game.players[1]
    elif change == 'range': target.position = Position(1000, 0)
    else: actor.constructor_component.current_hit_points = 0
    process(game, actor.owner)
    assert order.status == OrderStatus.FAILED
    assert not offline(target)
    assert actor.owner.credits == credits


def test_disabled_worker_pauses_and_each_round_ticks_once(world):
    game, actor, target = world
    order = start(game, actor, target)
    actor.is_disabled = True
    process(game, actor.owner)
    assert order.progress == 0 and offline(target)
    actor.is_disabled = False
    process(game, actor.owner)
    process(game, actor.owner)
    assert order.progress == 1


def test_wing_waits_paid_replenishment_and_production_stays_paused(world):
    game, _, _ = world
    carrier, bay, wing = bay_with_wing(game)
    wing.current_hit_points = 5
    bay.replenishing_unit = wing
    order = start(game, carrier, wing)
    assert order.phase == 'waiting_for_paid_bay_work'
    assert not bay.production_enabled
    bay.update(game.galaxy)
    assert wing.current_hit_points == 15 and bay.replenishing_unit is None
    credits = carrier.owner.credits
    order.prepare(game.galaxy)
    assert offline(wing)
    bay.update(game.galaxy)
    assert wing.current_hit_points == 15
    finish(game, order)
    assert carrier.owner.credits == pytest.approx(credits + 65)
    assert not bay.docked_units and not bay.production_enabled
    bay.update(game.galaxy)
    assert not bay.constructing
    assert issue(game, Command('set_wing_production_enabled', (carrier.id,), enabled=True)).accepted
    bay.update(game.galaxy)
    assert bay.constructing


def test_deployed_or_wrong_bay_wings_rejected(world):
    game, actor, _ = world
    carrier, bay, wing = bay_with_wing(game)
    assert evaluate(actor, wing, game.galaxy).blocker
    assert bay.deploy(wing, game.galaxy)
    assert evaluate(carrier, wing, game.galaxy).blocker


def test_combined_job_includes_paid_new_wing_and_orphans_launched(world):
    game, actor, carrier = world
    _, bay, launched = bay_with_wing(game, carrier)
    assert bay.deploy(launched, game.galaxy)
    assert bay.set_production(1, 'FIGHTER_WING')
    bay.update(game.galaxy)
    order = start(game, actor, carrier)
    assert order.phase == 'waiting_for_paid_bay_work'
    for _ in range(bay.production_template(0)['build_time']): bay.update(game.galaxy)
    wing = bay.docked_units[0]
    order.prepare(game.galaxy)
    assert [m['unit_id'] for m in order.members] == [carrier.id, wing.id]
    assert order.duration == sum(m['turns'] for m in order.members)
    assert offline(carrier) and offline(wing)
    assert not bay.deploy(wing, game.galaxy)
    credits = actor.owner.credits
    expected = sum(m['estimated_refund'] for m in order.members)
    finish(game, order)
    assert actor.owner.credits == pytest.approx(credits + expected)
    assert find_unit(game.galaxy, carrier.id) is None and find_unit(game.galaxy, wing.id) is None
    assert find_unit(game.galaxy, launched.id) is launched
    assert launched.strikecraft_wing_component.mother_carrier is None


def test_recursive_hangar_and_foreign_contents(world):
    game, actor, target = world
    target.add_component(HangarComponent(target, max_slots=2))
    tiny = ship(game, hull=HullSize.TINY)
    assert target.hangar_component.dock(tiny, game.galaxy)
    assert evaluate(actor, tiny, game.galaxy).blocker
    preview = evaluate(actor, target, game.galaxy)
    assert len(preview.members) == 2
    tiny.owner = game.players[1]
    assert evaluate(actor, target, game.galaxy).blocker


def test_batch_overlap_and_offline_followup_are_atomic(world):
    game, actor, target = world
    second = ship(game, 'Second constructor')
    second.add_component(Constructor(second))
    commands = [Command('dismantle_unit', (u.id,), target_id=target.id) for u in (actor, second)]
    result = issue(game, *commands)
    assert not result.accepted and not offline(target)
    assert actor.commander_component.current_order is None
    result = issue(game, commands[0], Command('set_stance', (target.id,), stance='do_nothing'))
    assert not result.accepted and not offline(target)


def test_cancel_then_reassign_in_same_batch(world):
    game, actor, target = world
    first = start(game, actor, target)
    other = ship(game)
    other.add_component(Constructor(other))
    result = issue(game, Command('cancel_order', (actor.id,), order_id=first.public_id),
                   Command('dismantle_unit', (other.id,), target_id=target.id))
    assert result.accepted, result.errors
    assert offline(target) and first.status == OrderStatus.CANCELLED


@pytest.mark.parametrize('phase', ['working', 'approach', 'waiting', 'queued'])
def test_save_round_trip_no_replay(world, phase):
    from save_manager import serialize_game_state
    from campaign_persistence import prepare_campaign
    from unit_orders.base import Order, OrderType
    game, actor, target = world
    if phase == 'approach':
        actor.add_component(Engines(actor, speed=100))
        target.position = Position(1000, 0)
    if phase == 'waiting':
        _, bay, _ = bay_with_wing(game, target)
        assert bay.set_production(1, 'FIGHTER_WING')
        bay.update(game.galaxy)
    if phase == 'queued':
        actor.commander_component.add_order(Order(actor, OrderType.TOGGLE_INHIBITOR))
        result = issue(game, Command('dismantle_unit', (actor.id,), target_id=target.id, queue=True))
        assert result.accepted
        order = actor.commander_component.orders_queue[-1]
    else:
        order = start(game, actor, target)
    if phase == 'working': process(game, actor.owner)
    data = serialize_game_state(game)
    restored = prepare_campaign(deepcopy(data)).state
    # prepare_campaign returns the validated candidate game.
    new_actor = find_unit(restored.galaxy, actor.id)
    new_order = new_actor.commander_component.orders_queue[-1] if phase == 'queued' else new_actor.commander_component.current_order
    assert new_order.public_id == order.public_id
    assert new_order.progress == order.progress and new_order.phase == order.phase
    assert new_actor.owner.credits == actor.owner.credits
    assert offline(find_unit(restored.galaxy, target.id)) == (phase == 'working')


def test_boolean_contract_is_strict():
    for value in (None, 1, 'true'):
        with pytest.raises(ContractError):
            Command.from_dict(dict(type='set_wing_production_enabled', unit_ids=[0], enabled=value))


def test_current_equipment_prices_ignore_template_and_component_damage(world):
    from custom_unit_templates import CustomUnitTemplate
    from refit_validation import installed_configuration
    from math import ceil
    game, actor, target = world
    target.template_name = 'missing-original-design'
    target.add_component(Engines(target, speed=125))
    design = CustomUnitTemplate('current', target.hull_size, installed_configuration(target))
    target.engines_component.current_hit_points = 0
    preview = evaluate(actor, target, game.galaxy)
    assert preview.refund == design.build_cost / 2
    assert preview.duration == max(1, ceil(design.build_time / 2))
    assert preview.members[0]['cargo_lost']['current_amount'] == target.antimatter_component.current_amount


def test_cancel_then_operate_target_in_same_batch(world):
    from unit_components.weapons import Weapons, Turret
    from unit_components.enums import TurretType
    game, actor, target = world
    weapons = Weapons(target)
    weapons.add_turret(Turret(TurretType.MASS_DRIVER, 10, 100, 1, target))
    target.add_component(weapons)
    order = start(game, actor, target)
    result = issue(game, Command('cancel_order', (actor.id,), order_id=order.public_id),
                   Command('set_stance', (target.id,), stance='do_nothing'))
    assert result.accepted, result.errors
    assert not offline(target)


def test_deploy_then_dismantle_rejected_before_mutation(world):
    game, _, _ = world
    carrier, bay, wing = bay_with_wing(game)
    result = issue(game, Command('deploy_unit', (carrier.id,), target_id=wing.id),
                   Command('dismantle_unit', (carrier.id,), target_id=wing.id))
    assert not result.accepted and result.failure_stage == 'preflight'
    assert wing in bay.docked_units and bay.production_enabled


def test_offline_sensors_income_refuelling_and_upkeep(world):
    from environmental_effects import sensor_radius, long_range_sensor_hexes
    from antimatter_logistics import endpoint_ready
    from economy import calculate_unit_upkeep
    from unit_components.civilian_habitat import CivilianHabitatComponent
    game, actor, target = world
    target.add_component(CivilianHabitatComponent(target))
    upkeep = calculate_unit_upkeep(target.hull_size, target.current_hull_usage)
    order = start(game, actor, target)
    assert sensor_radius(target) == long_range_sensor_hexes(target) == 0
    assert not target.civilian_habitat_component.is_active(game.galaxy)
    assert not endpoint_ready(target, game.galaxy)
    assert calculate_unit_upkeep(target.hull_size, target.current_hull_usage) == upkeep
    order.cancel()
    assert sensor_radius(target) > 0 and endpoint_ready(target, game.galaxy)


def test_no_future_salvage_spending(world):
    from unit_templates import UNIT_TEMPLATES
    game, actor, target = world
    actor.owner.credits = 0
    template = next(name for name, value in UNIT_TEMPLATES.items()
                    if value['hull_size'] != HullSize.STRIKECRAFT_WING)
    result = issue(game, Command('dismantle_unit', (actor.id,), target_id=target.id),
                   Command('construct', (actor.id,), template_name=template, system_name='Sol',
                           hex_coord=(0, 0), position=(100, 0), queue=True))
    assert not result.accepted and result.failure_stage == 'preflight'
    assert not offline(target) and actor.owner.credits == 0
    assert result.errors[0].code == 'insufficient_resources'


def test_required_bay_loss_and_containment_change_abort(world):
    game, actor, carrier = world
    _, bay, wing = bay_with_wing(game, carrier)
    order = start(game, actor, carrier)
    bay.current_hit_points = 0
    process(game, actor.owner)
    assert order.status == OrderStatus.FAILED and not offline(wing)
    bay.current_hit_points = bay.max_hit_points
    actor.commander_component.clear_explicit_orders()
    order = start(game, actor, carrier)
    bay.docked_units.remove(wing)
    game.galaxy.systems[wing.in_system].hexes[wing.in_hex].units.append(wing)
    process(game, actor.owner)
    assert order.status == OrderStatus.FAILED and not offline(carrier)


def test_saved_inconsistent_membership_rejected(world):
    game, actor, target = world
    order = start(game, actor, target)
    order.members[0]['build_cost'] += 1
    with pytest.raises(ValueError, match='membership or valuation'):
        order.restore_bindings(game.galaxy)


@pytest.mark.filterwarnings('error:Finding font with id:UserWarning')
@pytest.mark.parametrize('themed', [False, True])
def test_preview_dialog_routes_to_shared_gateway(world, pygame_context, themed):
    from types import SimpleNamespace
    import pygame
    import pygame_gui
    from gui.dismantling_window import DismantlingWindow
    from gui.theme_loader import build_ui_manager
    from display_config import DisplayConfig
    game, actor, target = world
    game.display_config = DisplayConfig(1280, 720, False)
    manager = build_ui_manager(game.display_config) if themed else pygame_gui.UIManager((1280, 720))
    gui = SimpleNamespace(manager=manager, game_instance=game, display_config=game.display_config)
    dialog = DismantlingWindow(gui, actor, target)
    gui.dismantling_window = dialog
    assert dialog.submit.is_enabled and dialog.append.is_enabled
    dialog.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=dialog.submit))
    assert gui.dismantling_window is None and offline(target)
    manager.clear_and_reset()


def test_end_turn_ticks_cooldowns_upkeep_and_private_completion(world):
    from turn_processor import TurnProcessor
    from turn_briefing import initialize_campaign, begin_window
    from economy import calculate_player_upkeep
    from unit_components.weapons import Weapons, Turret
    from unit_components.enums import TurretType
    game, actor, target = world
    weapons = Weapons(target)
    weapons.add_turret(Turret(TurretType.MASS_DRIVER, 1, 100, 2, target, current_cooldown=2))
    target.add_component(weapons)
    initialize_campaign(game)
    begin_window(game, actor.owner)
    begin_window(game, game.players[1])
    order = start(game, actor, target)
    credits, upkeep = actor.owner.credits, calculate_player_upkeep(game.galaxy, actor.owner)
    refund = sum(m['estimated_refund'] for m in order.members)
    processor = TurnProcessor(game)
    for _ in range(order.duration):
        processor.process_player_turn(actor.owner)
        game.turn_number += 1
    assert weapons.turrets[0].current_cooldown == 0
    assert order.status == OrderStatus.COMPLETED
    assert actor.owner.credits == pytest.approx(credits - upkeep * order.duration + refund)
    assert any('Dismantling completed' in e.detail and e.amount == refund for e in actor.owner.briefing.pending)
    assert not any('Dismantling' in e.detail or e.category == 'loss' for e in game.players[1].briefing.pending)


def test_observation_disclosure_and_docked_rename(world):
    from game_ai.observation import build_observation
    game, actor, target = world
    ship(game, 'Enemy observer', owner=1)
    order = start(game, actor, target)
    own = next(u for u in build_observation(game, actor.owner)['units'] if u['id'] == target.id)
    assert own['capability_details']['dismantling']['members'] == order.members
    enemy = next(u for u in build_observation(game, game.players[1])['units'] if u['id'] == target.id)
    assert 'dismantling' not in enemy.get('capability_details', {})
    carrier, _, wing = bay_with_wing(game)
    start(game, carrier, wing)
    result = issue(game, Command('rename_unit', (wing.id,), new_name='Retiring wing'))
    assert result.accepted and wing.name == 'Retiring wing'


def test_batch_cancel_unblocks_component_validators_without_mutation(world):
    game, actor, carrier = world
    _, bay, _ = bay_with_wing(game, carrier)
    order = start(game, actor, carrier)
    result = issue(game, Command('cancel_order', (actor.id,), order_id=order.public_id),
                   Command('set_wing_production', (carrier.id,), slot_index=0, template_name='FIGHTER_WING'),
                   Command('set_wing_production_enabled', (carrier.id,), enabled=True))
    assert result.accepted, result.errors
    assert bay.production_enabled and not offline(carrier)


@pytest.mark.parametrize('terminal', ['completed', 'cancelled'])
def test_terminal_save_does_not_replay_settlement(world, terminal):
    from save_manager import serialize_game_state
    from campaign_persistence import prepare_campaign
    game, actor, target = world
    order = start(game, actor, target)
    if terminal == 'completed':
        finish(game, order)
    else:
        order.cancel()
    loaded = prepare_campaign(serialize_game_state(game)).state
    restored_actor = find_unit(loaded.galaxy, actor.id)
    process(loaded, restored_actor.owner)
    assert restored_actor.owner.credits == actor.owner.credits
    assert not getattr(restored_actor, '_dismantle_executor', None)


def test_cancelled_approach_releases_navigation_and_claim(world):
    game, actor, target = world
    actor.add_component(Engines(actor, speed=100))
    target.position = Position(1000, 0)
    order = start(game, actor, target)
    order.update(game.galaxy)
    order.cancel()
    assert not getattr(actor, '_dismantle_executor', None)
    assert not getattr(target, '_dismantle_job', None)
    assert evaluate(actor, target, game.galaxy).blocker is None
