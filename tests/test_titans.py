"""Titan rules exercised through real commands, turns, combat and save loading."""
import copy
import json

import pytest

from constants import HullSize
from geometry import Position
from tests.support.campaigns import campaign, ship
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch
from unit_components.constructor import instantiate_unit_from_template, Constructor
from unit_components.movement import Engines, Hyperdrive
from unit_components.enums import AbilityType, HyperdriveType, JumpStatus, TurretType
from unit_components.titan import TitanComponent
from unit_components.abilities import AbilityComponent
from unit_components.sensors import Sensors
from tactical_abilities import start_owner_turn, combat_hit
from titan_abilities import process, instance, protected, coverage, availability
from titan_acquisition import capacity


def titan(game, owner=0, template='TITAN_FLAGSHIP'):
    return instantiate_unit_from_template(template, game.players[owner], 'Sol', (0, 0), Position(0, 0), game.galaxy, game)


def command(game, unit, kind, **kwargs):
    return CommandGateway(game).apply_batch(unit.owner, CommandBatch((Command(type='use_ability', unit_ids=(unit.id,), ability=kind, **kwargs),)))


def advance(game, unit, turns=1):
    game.turn_number += turns
    start_owner_turn(game.galaxy, unit.owner, game.turn_number)


def builder(game, x=200):
    result = ship(game)
    result.position = Position(x, 0)
    result.add_component(Constructor(result))
    result.add_component(Engines(result, speed=100))
    result.owner.credits = result.owner.metal = result.owner.crystal = 1000000
    return result


def build(unit, **kwargs):
    return Command(type='construct', unit_ids=(unit.id,), template_name='TITAN_FLAGSHIP',
                   system_name='Sol', hex_coord=(0, 0), position=(200, 200), **kwargs)


def test_public_designs_costs_and_core_rules():
    from unit_templates import UNIT_TEMPLATES
    from custom_unit_templates import template_from_dict
    from economy import calculate_unit_upkeep
    from refit_validation import evaluate_refit
    from resource_costs import construction_cost
    for key, hull in [('TITAN_FLAGSHIP', 744.8021156), ('TITAN_CITADEL', 685.8006164)]:
        design = template_from_dict(key, UNIT_TEMPLATES[key])
        assert design.validate() == []
        assert design.total_hull_cost == pytest.approx(hull)
    game = campaign()
    unit = titan(game)
    assert unit.max_hit_points == 1600 and unit.hull_capacity == 800
    assert unit.titan_component.hull_cost == 100
    assert calculate_unit_upkeep(HullSize.TITAN, 800) == 130
    cost = construction_cost(HullSize.TITAN, 800, 44000)
    assert (cost.credits, cost.metal, cost.crystal) == (44000, 1200, 400)
    assert AbilityComponent.calc_hull_cost(['microjump', 'deep_scan']) == 40
    assert evaluate_refit(unit, 'REMOVE', 'TitanComponent').errors
    ordinary = ship(game)
    assert evaluate_refit(ordinary, 'ADD', 'TitanComponent').errors
    assert all(slot['production_template_name'] is None for slot in unit.strikecraft_bay_component.slots)


def test_deferred_activation_reserves_and_replacement_releases():
    game = campaign()
    unit = titan(game)
    fuel = unit.antimatter_component.current_amount
    assert command(game, unit, 'aegis_field').accepted
    assert unit.antimatter_component.current_amount == fuel
    assert not instance(unit, 'aegis_field').is_active
    assert command(game, unit, 'carrier_supremacy').accepted
    process(game, unit.owner)
    assert unit.antimatter_component.current_amount == fuel - 200
    assert instance(unit, 'carrier_supremacy').is_active
    assert not instance(unit, 'aegis_field').is_active
    process(game, unit.owner)
    assert unit.antimatter_component.current_amount == fuel - 200


@pytest.mark.parametrize('drive', [HyperdriveType.BASIC, HyperdriveType.ADVANCED])
def test_unlimited_fleet_jump_and_formation(drive):
    game = campaign()
    unit = titan(game)
    unit.hyperdrive_component.drive_type = drive
    unit.hyperdrive_component.jump_range = 1
    from galaxy import Hex
    system = game.galaxy.systems['Sol']
    system.hexes[(90, 0)] = Hex(90, 0, 'Sol')
    unit.owner.record_sector_intel('Sol', (90, 0), 1)
    escort = ship(game, hull=HullSize.HUGE)
    escort.add_component(Engines(escort, speed=100))
    escort.position = Position(150, 0)
    fuel = unit.antimatter_component.current_amount
    assert command(game, unit, 'fleet_jump', system_name='Sol', hex_coord=(90, 0), position=(100, 400)).accepted
    assert unit.in_hex == (0, 0)
    process(game, unit.owner)
    assert unit.in_hex == escort.in_hex == (90, 0)
    assert unit.position == Position(100, 400)
    assert escort.position == Position(250, 400)
    assert unit.hyperdrive_component.jump_status == JumpStatus.CHARGING
    assert unit.antimatter_component.current_amount == fuel - 200


@pytest.mark.parametrize('failure', ['other_system', 'unready', 'destroyed', 'missing', 'over_capacity', 'blocked'])
def test_jump_rejection_preserves_resources_and_orders(failure):
    game = campaign()
    unit = titan(game)
    unit.owner.record_sector_intel('Sol', (1, 0), 1)
    system_name = 'Sol'
    if failure == 'other_system':
        system_name = 'Beta'
        unit.owner.record_sector_intel('Beta', (1, 0), 1)
    elif failure == 'unready':
        unit.hyperdrive_component.start_recharge()
    elif failure == 'destroyed':
        unit.hyperdrive_component.current_hit_points = 0
    elif failure == 'missing':
        unit.remove_component(Hyperdrive)
    elif failure == 'over_capacity':
        for i in range(5):
            escort = ship(game)
            escort.position = Position((i+1)*100, 0)
            escort.add_component(Engines(escort, speed=100))
    elif failure == 'blocked':
        enemy = ship(game, owner=1, sector=(1, 0))
        enemy.position = Position(400, 400)
    fuel = unit.antimatter_component.current_amount
    old = unit.commander_component.current_order
    assert not command(game, unit, 'fleet_jump', system_name=system_name, hex_coord=(1, 0), position=(400, 400)).accepted
    assert unit.commander_component.current_order is old
    assert unit.antimatter_component.current_amount == fuel
    assert unit.in_hex == (0, 0)


def test_aegis_exact_duration_weapon_only_and_subsystem():
    game = campaign()
    unit = titan(game)
    target = ship(game)
    target.position = Position(300, 0)
    assert command(game, unit, 'aegis_field').accepted
    process(game, unit.owner)
    before = target.current_hit_points
    combat_hit(target, 100, TurretType.BEAM)
    assert target.current_hit_points == before - 50
    target.take_damage(20)
    assert target.current_hit_points == before - 70
    sensors_before = target.sensors_component.current_hit_points
    combat_hit(target, 10, TurretType.BEAM, component_type=Sensors)
    assert target.sensors_component.current_hit_points == sensors_before - 5
    advance(game, unit, 9)
    assert protected(target, 'aegis_field')
    advance(game, unit)
    assert not protected(target, 'aegis_field')
    assert availability(unit, 'aegis_field', game.galaxy) == 'capability_unavailable'


def test_lance_charge_cost_and_one_round_interruption_window():
    game = campaign()
    unit = titan(game)
    unit.sensors_component.short_range_radius = 4000
    target = ship(game, owner=1)
    target.position = Position(2900, 0)
    target.current_hit_points = target.max_hit_points = 1000
    fuel = unit.antimatter_component.current_amount
    assert command(game, unit, 'siege_lance', target_id=target.id).accepted
    process(game, unit.owner)
    assert target.current_hit_points == 1000
    assert unit.antimatter_component.current_amount == fuel-200
    process(game, unit.owner)
    assert target.current_hit_points == 1000
    advance(game, unit)
    process(game, unit.owner)
    assert target.current_hit_points == 500
    assert not instance(unit, 'siege_lance').is_active


@pytest.mark.parametrize('interruption', ['move', 'disable', 'capture', 'core', 'visibility', 'cancel'])
def test_lance_aborts_without_refund(interruption):
    game = campaign()
    unit = titan(game)
    target = ship(game, owner=1)
    target.current_hit_points = target.max_hit_points = 1000
    assert command(game, unit, 'siege_lance', target_id=target.id).accepted
    process(game, unit.owner)
    paid = unit.antimatter_component.current_amount
    if interruption == 'move':
        unit.position = Position(1, 1)
    elif interruption == 'disable':
        unit.is_disabled = True
    elif interruption == 'capture':
        unit.owner = game.players[1]
    elif interruption == 'core':
        unit.titan_component.current_hit_points = 0
    elif interruption == 'visibility':
        target.position = Position(2900, 0)
    else:
        result = CommandGateway(game).apply_batch(unit.owner, CommandBatch((Command(type='cancel_ability', unit_ids=(unit.id,), ability='siege_lance'),)))
        assert result.accepted
    advance(game, unit)
    process(game, unit.owner)
    assert target.current_hit_points == 1000
    assert unit.antimatter_component.current_amount == paid
    assert unit.titan_cooldowns['siege_lance'] > game.turn_number
    assert not instance(unit, 'siege_lance').is_active


def test_deep_scan_continuous_read_only_coverage_and_expiry():
    from visibility import VisibilityService, is_unit_visible
    game = campaign()
    unit = titan(game)
    target = ship(game, owner=1, sector=(1, 0))
    assert not is_unit_visible(VisibilityService.compute(game.galaxy, unit.owner, record_intel=False), target)
    assert command(game, unit, 'deep_scan', system_name='Sol', hex_coord=(1, 0)).accepted
    process(game, unit.owner)
    before = copy.deepcopy(instance(unit, 'deep_scan').to_state())
    assert is_unit_visible(VisibilityService.compute(game.galaxy, unit.owner, record_intel=False), target)
    newcomer = ship(game, owner=1, sector=(1, 0))
    assert is_unit_visible(VisibilityService.compute(game.galaxy, unit.owner, record_intel=False), newcomer)
    game.galaxy.systems['Sol'].move_unit_between_hexes(target, (0, 0))
    target.position = Position(3000, 0)
    assert not is_unit_visible(VisibilityService.compute(game.galaxy, unit.owner, record_intel=False), target)
    assert instance(unit, 'deep_scan').to_state() == before
    advance(game, unit, 5)
    assert not is_unit_visible(VisibilityService.compute(game.galaxy, unit.owner, record_intel=False), newcomer)
    assert ('Sol', (1, 0)) in unit.owner.sector_intel


def test_reservations_grouped_build_cancel_and_completion():
    game = campaign()
    a, b = builder(game), builder(game, 400)
    gateway = CommandGateway(game)
    credits = a.owner.credits
    assert not gateway.apply_batch(a.owner, CommandBatch((build(a), build(b)))).accepted
    assert a.owner.credits == credits
    assert capacity(game.galaxy, a.owner)['available'] == 1
    assert gateway.apply_batch(a.owner, CommandBatch((build(a),))).accepted
    assert len(capacity(game.galaxy, a.owner)['reservations']) == 1
    assert not gateway.apply_batch(a.owner, CommandBatch((build(b),))).accepted
    assert gateway.apply_batch(a.owner, CommandBatch((Command(type='cancel_orders', unit_ids=(a.id,)), build(b)))).accepted
    b.constructor_component.finish_construction(game.galaxy)
    state = capacity(game.galaxy, b.owner)
    assert len(state['owned_unit_ids']) == 1
    # Settle the completed root through ordinary commander work.
    b.commander_component.update()
    assert capacity(game.galaxy, b.owner)['reservations'] == []


@pytest.mark.parametrize('kind', ['aegis_field', 'deep_scan', 'carrier_supremacy', 'siege_lance'])
def test_active_round_trip_and_cooldowns_survive_refit(kind):
    from save_manager import serialize_game_state, deserialize_game_state
    game = campaign()
    unit = titan(game)
    kwargs = {}
    if kind == 'deep_scan':
        kwargs = {'system_name': 'Sol', 'hex_coord': (1, 0)}
    if kind == 'siege_lance':
        kwargs = {'target_id': ship(game, owner=1).id}
    assert command(game, unit, kind, **kwargs).accepted
    process(game, unit.owner)
    deadline = unit.titan_cooldowns[kind]
    fuel = unit.antimatter_component.current_amount
    saved = json.loads(json.dumps(serialize_game_state(game)))
    assert deserialize_game_state(game, saved)
    restored = game.galaxy.get_unit_by_id(unit.id)
    assert restored.titan_cooldowns[kind] == deadline
    assert restored.antimatter_component.current_amount == fuel
    assert instance(restored, kind).is_active
    process(game, restored.owner)
    assert restored.antimatter_component.current_amount == fuel
    restored.remove_component(AbilityComponent)
    restored.add_component(AbilityComponent(restored, [AbilityType(kind)], hull_cost=35))
    assert availability(restored, kind, game.galaxy) == 'capability_unavailable'


def test_capacity_counts_disabled_and_coreless_and_direct_creation():
    game = campaign()
    unit = titan(game)
    unit.remove_component(AbilityComponent)
    unit.remove_component(TitanComponent)
    unit.is_disabled = True
    assert capacity(game.galaxy, unit.owner)['available'] == 0
    assert titan(game) is None
    unit.current_hit_points = 0
    assert capacity(game.galaxy, unit.owner)['available'] == 1


def test_scan_source_loss_does_not_restart_after_repair():
    game = campaign()
    unit = titan(game)
    assert command(game, unit, 'deep_scan', system_name='Sol', hex_coord=(1, 0)).accepted
    process(game, unit.owner)
    unit.remove_component(Sensors)
    unit.add_component(Sensors(unit, short_range_radius=2000))
    assert list(coverage(game.galaxy, unit.owner)) == []


def test_supremacy_allied_other_carriers_nonstacking_and_base_stats():
    from tests.test_carrier_abilities import make_wing
    from strikecraft_abilities import outgoing_multiplier, incoming_multiplier
    from unit_components.strikecraft import StrikecraftBayComponent
    game = campaign()
    game.players[1].team_id = game.players[0].team_id
    first, second = titan(game), titan(game, owner=1)
    second.position = Position(400, 0)
    other_carrier = ship(game)
    other_carrier.add_component(StrikecraftBayComponent(other_carrier, max_slots=2))
    owned = make_wing(game, other_carrier)
    allied = make_wing(game, second, owner=1)
    allied.position = Position(3000, 0)  # Entire sector, not a gathering radius.
    enemy = ship(game)
    for caster in (first, second):
        assert command(game, caster, 'carrier_supremacy').accepted
        process(game, caster.owner)
    assert protected(owned, 'carrier_supremacy') and protected(allied, 'carrier_supremacy')
    for wing in (owned, allied):
        turret = wing.weapons_component.turrets[0]
        assert wing.engines_component.speed == 40
        assert wing.engines_component.effective_speed == 60
        assert turret.damage == 4
        assert outgoing_multiplier(wing, enemy, turret) == 2
        assert incoming_multiplier(wing) == 0.5
    advance(game, first)
    assert command(game, first, 'aegis_field').accepted
    process(game, first.owner)
    assert incoming_multiplier(owned) == 0.25
    assert incoming_multiplier(allied) == 0.5
    game.galaxy.systems['Sol'].move_unit_between_hexes(first, (1, 0))
    game.galaxy.systems['Sol'].move_unit_between_hexes(second, (1, 0))
    assert incoming_multiplier(owned) == 1
    assert owned.engines_component.effective_speed == 40


def test_supremacy_multiplies_attack_run_and_preserves_service_suppression():
    from tests.test_carrier_abilities import scenario
    from tactical_abilities import activate
    from strikecraft_abilities import outgoing_multiplier
    game, carrier, bomber, _, enemy, _ = scenario()
    hero = titan(game)
    assert command(game, hero, 'carrier_supremacy').accepted
    process(game, hero.owner)
    assert activate(carrier, 'attack_run', game.galaxy, enemy.id)
    advance(game, hero)
    root = bomber.commander_component.current_order
    bomber.position = Position(250, 0)
    root.update(game.galaxy)
    assert root.phase == 'release'
    assert outgoing_multiplier(bomber, enemy, bomber.weapons_component.turrets[0]) == 4
    # Mandatory recovery retains its authority even under Supremacy.
    bomber.strikecraft_wing_component.turns_outside = 80
    assert outgoing_multiplier(bomber, enemy, bomber.weapons_component.turrets[0]) == 0


def test_scan_allies_cloaks_mines_and_private_information():
    from visibility import VisibilityService, is_unit_visible, is_minefield_visible
    from domain.players import Player
    from domain.minefields import Minefield
    from unit_components.cloaking import CloakingDevice
    from unit_components.enums import CloakingType
    from game_ai.observation import build_observation
    game = campaign()
    ally = Player('Ally', (50, 50, 200))
    ally.team_id = game.players[0].team_id
    game.players.append(ally)
    hero = titan(game)
    target = ship(game, owner=1, sector=(1, 0))
    target.add_component(CloakingDevice(target, device_type=CloakingType.BASIC))
    target.cloaking_component.is_active = True
    mine = Minefield(target.owner, Position(400, 0), (1, 0), 'Sol', mines_remaining=5)
    game.galaxy.systems['Sol'].hexes[(1, 0)].minefields.append(mine)
    assert command(game, hero, 'deep_scan', system_name='Sol', hex_coord=(1, 0)).accepted
    process(game, hero.owner)
    for viewer in (hero.owner, ally):
        snapshot = VisibilityService.compute(game.galaxy, viewer, record_intel=False)
        assert is_unit_visible(snapshot, target)
        assert not is_minefield_visible(snapshot, mine)
        observed = build_observation(game, viewer)
        public = next(u for u in observed['units'] if u['id'] == target.id)
        assert 'troop_cargo' not in public and 'titan' not in public
        assert not public.get('orders')
    target.is_hidden_in_gas_giant = True
    assert not is_unit_visible(VisibilityService.compute(game.galaxy, hero.owner, record_intel=False), target)


def test_pending_capture_reserves_without_predicting_success():
    from unit_components.marines import MarinesComponent
    game = campaign()
    target = titan(game, owner=1)
    target.is_disabled = True
    target.weapons_component.current_hit_points = 0
    from unit_components.defenses import Defenses
    target.get_component(Defenses).current_hit_points = 0
    captor = builder(game, 1000)
    captor.sensors_component.short_range_radius = 2000
    captor.add_component(MarinesComponent(captor, marines_count=1000))
    captor.add_component(AbilityComponent(captor, [AbilityType.CAPTURE_UNIT]))
    result = command(game, captor, 'capture_unit', target_id=target.id, queue=True)
    assert result.accepted
    assert target.owner == game.players[1]
    assert capacity(game.galaxy, captor.owner)['available'] == 0
    other = builder(game, 500)
    assert not CommandGateway(game).apply_batch(captor.owner, CommandBatch((build(other),))).accepted
    captor.commander_component.clear_explicit_orders()
    assert capacity(game.galaxy, captor.owner)['available'] == 1


def test_queued_construction_freezes_hull_and_reserves_across_save():
    from unit_templates import UNIT_TEMPLATES
    from save_manager import serialize_game_state, deserialize_game_state
    game = campaign()
    constructor = builder(game)
    assert CommandGateway(game).apply_batch(constructor.owner, CommandBatch((build(constructor, queue=True),))).accepted
    assert deserialize_game_state(game, json.loads(json.dumps(serialize_game_state(game))))
    assert capacity(game.galaxy, game.players[0])['available'] == 0
    constructor = game.galaxy.get_unit_by_id(constructor.id)
    # Even edits after payment cannot turn a reservation into a different hull.
    original = UNIT_TEMPLATES['TITAN_FLAGSHIP']['hull_size']
    try:
        UNIT_TEMPLATES['TITAN_FLAGSHIP']['hull_size'] = HullSize.HUGE
        constructor.constructor_component.finish_construction(game.galaxy)
        assert capacity(game.galaxy, constructor.owner)['available'] == 1
        assert not capacity(game.galaxy, constructor.owner)['owned_unit_ids']
    finally:
        UNIT_TEMPLATES['TITAN_FLAGSHIP']['hull_size'] = original


def test_duplicate_titan_save_rejected_transactionally():
    from save_manager import serialize_game_state, deserialize_game_state
    game = campaign()
    first, second = titan(game), titan(game, owner=1)
    second.owner = first.owner
    bad = serialize_game_state(game)
    second.owner = game.players[1]
    before = serialize_game_state(game)
    assert not deserialize_game_state(game, bad)
    after = serialize_game_state(game)
    before.pop("timestamp"); after.pop("timestamp")
    assert after == before


@pytest.mark.parametrize('kind', ['fleet_jump', 'aegis_field', 'siege_lance', 'deep_scan', 'carrier_supremacy'])
def test_fake_controller_issues_each_power_through_shared_gateway(kind):
    import asyncio
    from game_ai.adapters.fake import FakePlanningProvider
    from game_ai.adapters.base import PlanningRequest
    from game_ai.contracts import TurnPlan
    from game_ai.observation import build_observation
    from game_ai.runtime import get_runtime_config
    from tests.support.ai import EMPTY_PATCH
    game = campaign()
    hero = titan(game)
    target = ship(game, owner=1)
    kwargs = {}
    if kind in ('deep_scan', 'fleet_jump'):
        kwargs.update(system_name='Sol', hex_coord=(1, 0))
    if kind == 'fleet_jump':
        hero.owner.record_sector_intel('Sol', (1, 0), 1)
        kwargs['position'] = (400, 400)
    if kind == 'siege_lance':
        kwargs['target_id'] = target.id
    cmd = Command(type='use_ability', unit_ids=(hero.id,), ability=kind, **kwargs)
    plan = TurnPlan.from_dict({'plan': [], 'commands': [cmd.to_dict()], 'memory_patch': EMPTY_PATCH, 'end_turn': True})
    request = PlanningRequest('test', 'agent', 'One', 7, build_observation(game, hero.owner), {})
    output = asyncio.run(FakePlanningProvider([plan]).plan_turn(request, get_runtime_config('low')))
    result = CommandGateway(game).apply_batch(hero.owner, output.plan.batch)
    assert result.accepted, result.errors
    assert not hero.titan_cooldowns
    process(game, hero.owner)
    assert hero.titan_cooldowns[kind] > game.turn_number


def test_human_hex_targeting_and_scan_expiry(pygame_context):
    from events import EventBus
    from order_system import OrderSystem
    from input_processor.mouse_handler import handle_mouse_click
    game = campaign()
    hero = titan(game)
    game.event_bus = EventBus()
    OrderSystem(game, game.event_bus)
    game.selected_objects = [hero]
    game.view_mode = 'system'
    game.system_view_mouse_hover_hex = (1, 0)
    game.pending_ability = ('deep_scan', False, True)
    handle_mouse_click(game, None, 3, Position(500, 300))
    assert game.pending_ability is None
    assert hero.commander_component.current_order.parameters['target_hex_coord'] == (1, 0)
    assert hero.antimatter_component.current_amount == 2000
    process(game, hero.owner)
    assert list(coverage(game.galaxy, hero.owner)) == [('Sol', (1, 0))]
    advance(game, hero, 5)
    assert not list(coverage(game.galaxy, hero.owner))


def test_jump_live_revalidation_is_atomic_and_preserves_passenger_orders():
    game = campaign()
    hero = titan(game)
    hero.owner.record_sector_intel('Sol', (1, 0), 1)
    escort = builder(game, 150)
    gateway = CommandGateway(game)
    assert gateway.apply_batch(hero.owner, CommandBatch((Command(type='move', unit_ids=(escort.id,),
        system_name='Sol', hex_coord=(0, 0), position=(500, 500)),))).accepted
    previous = escort.commander_component.current_order
    assert command(game, hero, 'fleet_jump', system_name='Sol', hex_coord=(1, 0), position=(400, 400)).accepted
    intruder = ship(game, owner=1, sector=(1, 0))
    intruder.position = Position(550, 400)
    process(game, hero.owner)
    assert hero.in_hex == escort.in_hex == (0, 0)
    assert hero.antimatter_component.current_amount == 2000
    assert not hero.titan_cooldowns
    assert escort.commander_component.current_order is previous


def test_capture_transfers_slot_and_preserves_enduring_cooldown():
    from unit_components.marines import MarinesComponent
    from unit_components.defenses import Defenses
    game = campaign()
    hero = titan(game, owner=1)
    hero.titan_cooldowns['deep_scan'] = 25
    hero.is_disabled = True
    hero.weapons_component.current_hit_points = hero.get_component(Defenses).current_hit_points = 0
    captor = builder(game, 50)
    captor.add_component(MarinesComponent(captor, marines_count=1000))
    captor.add_component(AbilityComponent(captor, [AbilityType.CAPTURE_UNIT]))
    assert command(game, captor, 'capture_unit', target_id=hero.id).accepted
    assert hero.owner == captor.owner
    assert capacity(game.galaxy, game.players[1])['available'] == 1
    assert capacity(game.galaxy, captor.owner)['owned_unit_ids'] == [hero.id]
    assert not capacity(game.galaxy, captor.owner)['reservations']
    assert hero.titan_cooldowns['deep_scan'] == 25


def test_builder_loss_and_dismantling_slot_lifecycle():
    from tests.test_dismantling import start, finish
    game = campaign()
    constructor = builder(game)
    assert CommandGateway(game).apply_batch(constructor.owner, CommandBatch((build(constructor, queue=True),))).accepted
    constructor.destroy()
    assert capacity(game.galaxy, game.players[0])['available'] == 1
    hero = titan(game)
    recycler = builder(game)
    order = start(game, recycler, hero)
    assert capacity(game.galaxy, hero.owner)['available'] == 0
    finish(game, order)
    assert capacity(game.galaxy, hero.owner)['available'] == 1


@pytest.mark.parametrize('transition', ['hide', 'other_system'])
def test_scan_cannot_restart_after_source_leaves_and_returns(transition):
    from domain.celestials import Planet
    from constants import PlanetType
    game = campaign()
    hero = titan(game)
    assert command(game, hero, 'deep_scan', system_name='Sol', hex_coord=(1, 0)).accepted
    process(game, hero.owner)
    if transition == 'hide':
        giant = Planet((0, 0), 'Sol', PlanetType.GAS_GIANT)
        giant.position = Position(400, 0)
        game.galaxy.systems['Sol'].add_celestial_body(giant)
        assert giant.hide_unit(hero, game.galaxy)
        assert capacity(game.galaxy, hero.owner)['available'] == 0
        assert giant.release_unit(hero, game.galaxy) is not None
    else:
        assert game.galaxy.move_unit_between_systems(hero, 'Sol', 'Beta', (0, 0))
        assert game.galaxy.move_unit_between_systems(hero, 'Beta', 'Sol', (0, 0))
    assert not instance(hero, 'deep_scan').is_active
    assert list(coverage(game.galaxy, hero.owner)) == []
    assert hero.titan_cooldowns['deep_scan'] > game.turn_number


def test_charge_holds_position_blocks_queue_and_suppresses_normal_weapons():
    from turn_processor import TurnProcessor
    game = campaign()
    hero = titan(game)
    target = ship(game, owner=1)
    target.current_hit_points = target.max_hit_points = 10000
    hero.weapons_component.set_target(target)
    assert command(game, hero, 'siege_lance', target_id=target.id).accepted
    assert CommandGateway(game).apply_batch(hero.owner, CommandBatch((Command(type='move', unit_ids=(hero.id,),
        system_name='Sol', hex_coord=(0, 0), position=(1000, 1000), queue=True),))).accepted
    TurnProcessor(game).process_player_turn(hero.owner)
    assert instance(hero, 'siege_lance').is_active
    assert target.current_hit_points == 10000
    assert hero.position == Position(0, 0)
    assert len(hero.commander_component.orders_queue) == 1


def test_lance_warns_target_and_allies_without_revealing_unseen_source():
    from turn_briefing import begin_window
    from domain.players import Player
    game = campaign()
    ally = Player('Ally', (20, 50, 200))
    ally.team_id = game.players[1].team_id
    game.players.append(ally)
    hero = titan(game)
    hero.name = 'SECRET SOURCE'
    hero.sensors_component.short_range_radius = 4000
    target = ship(game, owner=1)
    target.position = Position(2900, 0)
    for viewer in (target.owner, ally):
        begin_window(game, viewer)
    assert command(game, hero, 'siege_lance', target_id=target.id).accepted
    process(game, hero.owner)
    for viewer in (target.owner, ally):
        warnings = [e.detail for e in viewer.briefing.pending if 'Siege Lance charging' in e.detail]
        assert len(warnings) == 1 and 'unknown attacker' in warnings[0]
        assert 'SECRET SOURCE' not in warnings[0]
