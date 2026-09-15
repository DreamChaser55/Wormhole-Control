"""Storage logistics, conservative travel and multiplication integration."""

import json
import random

import pytest

from tests.support.campaigns import campaign, ship
from constants import HullSize
from geometry import Position
from unit_components.antimatter import AntimatterStorage, AntimatterHarvester
from unit_components.movement import Engines, Hyperdrive
from unit_components.abilities import AbilityComponent
from unit_components.enums import AbilityType, HyperdriveType
from unit_orders.base import Order, OrderStatus
from unit_orders.fuel_transport import (
    TransferAntimatterOrder,
    TakeAntimatterOrder,
    ContinuousAntimatterTransportOrder,
)
from antimatter_logistics import (
    estimate_approach,
    route_budget,
    in_transfer_range,
    buffered_fuel,
)
from tactical_abilities import activate, availability, start_owner_turn
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch
from save_manager import serialize_game_state, deserialize_game_state


def vessel(
    game,
    name="ship",
    amount=100,
    capacity=600,
    position=(100, 0),
    moving=False,
    owner=0,
    sector=(0, 0),
):
    unit = ship(game, name, owner=owner, hull=HullSize.MEDIUM, sector=sector)
    unit.add_component(AntimatterStorage(unit, max_capacity=capacity))
    unit.antimatter_component.current_amount = amount
    unit.position = Position(*position)
    if moving:
        unit.add_component(Engines(unit, speed=100))
        unit.add_component(
            Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=5)
        )
    return unit


def caster(game, **kwargs):
    unit = vessel(game, **kwargs)
    unit.add_component(
        AbilityComponent(
            unit, [AbilityType.MULTIPLY_ANTIMATTER, AbilityType.GHOST_FLEET]
        )
    )
    return unit


def issue(game, *commands):
    return CommandGateway(game).apply_batch(
        game.players[0], CommandBatch(tuple(Command(**c) for c in commands))
    )


def cast(unit, **extra):
    return dict(
        type="use_ability", unit_ids=(unit.id,), ability="multiply_antimatter", **extra
    )


@pytest.mark.parametrize("taking", [False, True])
def test_storage_only_exchange_conserves_rate_and_finishes(taking):
    game = campaign()
    actor = vessel(game, amount=0 if taking else 37)
    target = vessel(game, amount=37 if taking else 0)
    cls = TakeAntimatterOrder if taking else TransferAntimatterOrder
    order = cls(actor, {"target_unit_id": target.id})
    donor, recipient = (target, actor) if taking else (actor, target)
    previous = target.commander_component.current_order
    order.execute(game.galaxy)
    order.update(game.galaxy)
    assert (
        donor.antimatter_component.current_amount,
        recipient.antimatter_component.current_amount,
    ) == (12, 25)
    order.update(game.galaxy)
    assert (
        donor.antimatter_component.current_amount,
        recipient.antimatter_component.current_amount,
    ) == (0, 37)
    assert order.status == OrderStatus.COMPLETED
    assert target.commander_component.current_order is previous


def test_manual_harvester_donation_can_empty_tank():
    game = campaign()
    donor, target = vessel(game, amount=12), vessel(game, amount=0)
    donor.add_component(AntimatterHarvester(donor))
    order = TransferAntimatterOrder(donor, {"target_unit_id": target.id})
    order.execute(game.galaxy)
    order.update(game.galaxy)
    assert donor.antimatter_component.current_amount == 0


@pytest.mark.parametrize(
    "invalid", ["enemy", "self", "destroyed_storage", "hidden", "removed", "dead"]
)
def test_exchange_rejects_unavailable_endpoints_without_mutation(invalid):
    game = campaign()
    actor, target = vessel(game), vessel(game, amount=0)
    if invalid == "enemy":
        target.owner = game.players[1]
    elif invalid == "self":
        target = actor
    elif invalid == "destroyed_storage":
        target.antimatter_component.current_hit_points = 0
    elif invalid == "hidden":
        target.is_hidden_in_gas_giant = True
    elif invalid == "removed":
        game.galaxy.systems["Sol"].hexes[(0, 0)].units.remove(target)
    elif invalid == "dead":
        target.current_hit_points = 0
    order = TransferAntimatterOrder(actor, {"target_unit_id": target.id})
    order.execute(game.galaxy)
    assert order.status == OrderStatus.FAILED
    assert actor.antimatter_component.current_amount == 100


def test_take_approaches_using_only_recipient_engines():
    game = campaign()
    actor = vessel(game, amount=50, moving=True)
    depot = vessel(game, amount=100, position=(1500, 0))
    result = issue(
        game, dict(type="take_antimatter", unit_ids=(actor.id,), target_id=depot.id)
    )
    assert result.accepted, result.errors
    original = depot.position
    for _ in range(65):
        tick(game, actor)
    assert depot.position == original
    assert in_transfer_range(actor, depot)
    assert depot.antimatter_component.current_amount == 0
    assert actor.antimatter_component.current_amount > 50


def tick(game, actor):
    from turn_processor import TurnProcessor

    TurnProcessor(game)._process_movement(actor.owner)
    actor.update()


def route_scenario(*, distant_hex=False):
    game = campaign()
    actor = vessel(game, "transporter", amount=100, moving=True)
    source = vessel(game, "source", amount=1600, capacity=1600)
    target = vessel(
        game,
        "destination",
        amount=0,
        capacity=1600,
        position=(1900, 0),
        sector=(1, 0) if distant_hex else (0, 0),
    )
    command = dict(
        type="continuous_antimatter_transport",
        unit_ids=(actor.id,),
        source_id=source.id,
        target_id=target.id,
    )
    return game, actor, source, target, command


@pytest.mark.parametrize("distant_hex", [False, True])
def test_repeating_route_delivers_two_loads_and_keeps_return_fuel(distant_hex):
    game, actor, source, target, command = route_scenario(distant_hex=distant_hex)
    result = issue(game, command)
    assert result.accepted, result.errors
    order = actor.commander_component.current_order
    seen_return = False
    for _ in range(260):
        tick(game, actor)
        assert order.status == OrderStatus.IN_PROGRESS, order.failure_reason
        if target.antimatter_component.current_amount > 0 and order.phase == "loading":
            seen_return = True
        if target.antimatter_component.current_amount > 700:
            break
    assert seen_return
    assert target.antimatter_component.current_amount > 700
    assert source.position == Position(100, 0)
    assert actor.antimatter_component.current_amount >= 0
    assert (
        source.antimatter_component.current_amount
        + target.antimatter_component.current_amount
        + actor.antimatter_component.current_amount
        <= 1700
    )


def test_route_waits_for_supply_and_space_and_accepts_partial_load():
    game, actor, source, target, command = route_scenario()
    actor.antimatter_component.current_amount = 1
    source.antimatter_component.current_amount = 0
    assert issue(game, command).accepted
    tick(game, actor)
    order = actor.commander_component.current_order
    assert order.phase == "loading" and order.waiting_reason == "insufficient_load"
    source.antimatter_component.current_amount = 80
    target.antimatter_component.current_amount = 1600
    for _ in range(5):
        tick(game, actor)
    assert order.waiting_reason == "destination_full"
    target.antimatter_component.current_amount = 0
    tick(game, actor)
    assert order.phase == "delivering"


def test_route_waits_at_full_destination_then_resumes():
    game, actor, source, target, command = route_scenario()
    actor.antimatter_component.current_amount = 600
    assert issue(game, command).accepted
    order = actor.commander_component.current_order
    tick(game, actor)
    target.antimatter_component.current_amount = (
        target.antimatter_component.max_capacity
    )
    for _ in range(60):
        tick(game, actor)
    assert in_transfer_range(actor, target)
    assert order.phase == "delivering" and order.waiting_reason == "destination_full"
    target.antimatter_component.current_amount = 0
    tick(game, actor)
    assert target.antimatter_component.current_amount == 25


def test_estimates_are_pure_and_distinguish_impossible_from_zero():
    game, actor, source, target, _ = route_scenario()
    before = json.dumps(serialize_game_state(game)["galaxy"], sort_keys=True)
    counter, rng = Order.order_counter, random.getstate()
    assert estimate_approach(actor, game.galaxy, source).fuel == 0
    assert route_budget(actor, source, target, game.galaxy) > 0
    assert json.dumps(serialize_game_state(game)["galaxy"], sort_keys=True) == before
    assert (Order.order_counter, random.getstate()) == (counter, rng)
    actor.remove_component(Engines)
    assert estimate_approach(actor, game.galaxy, target) is None
    assert buffered_fuel(0) == 0 and buffered_fuel(10) == 23


def test_route_rejects_tank_too_small_and_lost_endpoint():
    game, actor, source, target, command = route_scenario()
    actor.antimatter_component.max_capacity = 1
    assert not issue(game, command).accepted
    actor.antimatter_component.max_capacity = 600
    assert issue(game, command).accepted
    order = actor.commander_component.current_order
    target.owner = game.players[1]
    tick(game, actor)
    assert order.status == OrderStatus.FAILED


def test_pulse_cost_snapshot_radius_clamp_and_recipient_exclusions():
    game = campaign()
    actor = caster(game, amount=100)
    edge = vessel(game, amount=90, capacity=100, position=(600, 0))
    empty = vessel(game, amount=0)
    outside = vessel(game, amount=50, position=(600.01, 0))
    enemy = vessel(game, amount=50, owner=1)
    hidden = vessel(game, amount=50)
    hidden.is_hidden_in_gas_giant = True
    assert activate(actor, "multiply_antimatter", game.galaxy)
    assert actor.antimatter_component.current_amount == 160
    assert edge.antimatter_component.current_amount == 100
    assert empty.antimatter_component.current_amount == 0
    assert all(
        u.antimatter_component.current_amount == 50 for u in (outside, enemy, hidden)
    )
    assert (
        actor.multiply_cast_ready_round
        == edge.multiply_receive_ready_round
        == game.turn_number + 30
    )
    assert (
        empty.multiply_receive_ready_round == outside.multiply_receive_ready_round == 0
    )


def test_shared_recipient_lock_and_caster_lock_survive_reinstall():
    game = campaign()
    first, second = caster(game), caster(game, name="second")
    assert activate(first, "multiply_antimatter", game.galaxy)
    amounts = (
        first.antimatter_component.current_amount,
        second.antimatter_component.current_amount,
    )
    assert not activate(second, "multiply_antimatter", game.galaxy)
    assert amounts == (
        first.antimatter_component.current_amount,
        second.antimatter_component.current_amount,
    )
    newcomer = vessel(game, amount=50)
    assert activate(second, "multiply_antimatter", game.galaxy)
    assert newcomer.antimatter_component.current_amount == 100
    assert first.antimatter_component.current_amount == amounts[0]
    first.remove_component(AbilityComponent)
    first.add_component(AbilityComponent(first, [AbilityType.MULTIPLY_ANTIMATTER]))
    assert (
        availability(first, "multiply_antimatter", game.galaxy)
        == "capability_unavailable"
    )
    game.turn_number += 29
    start_owner_turn(game.galaxy, first.owner, game.turn_number)
    assert not activate(first, "multiply_antimatter", game.galaxy)
    game.turn_number += 1
    start_owner_turn(game.galaxy, first.owner, game.turn_number)
    assert activate(first, "multiply_antimatter", game.galaxy)


@pytest.mark.parametrize("amount", [0, 19, 20, 40, 600])
def test_nonpositive_net_pulse_is_rejected_without_cost_or_cooldown(amount):
    game = campaign()
    actor = caster(game, amount=amount)
    assert not activate(actor, "multiply_antimatter", game.galaxy)
    assert actor.antimatter_component.current_amount == amount
    assert actor.multiply_cast_ready_round == actor.multiply_receive_ready_round == 0


def test_immediate_pulse_can_fund_later_cast_and_duplicate_rejection_is_atomic():
    game = campaign()
    actor, recipient = caster(game), caster(game, name="recipient", amount=15)
    later = dict(
        type="use_ability",
        unit_ids=(recipient.id,),
        ability="ghost_fleet",
        position=(350, 0),
    )
    result = issue(game, cast(actor), later)
    assert result.accepted, result.errors
    assert recipient.antimatter_component.current_amount == 5
    game = campaign()
    actor = caster(game)
    result = issue(game, cast(actor), cast(actor))
    assert not result.accepted
    assert actor.antimatter_component.current_amount == 100
    assert actor.multiply_cast_ready_round == 0


def test_queued_pickup_cannot_finance_immediate_cast():
    game = campaign()
    actor = caster(game, amount=19)
    source = vessel(game, amount=100)
    result = issue(
        game,
        dict(type="take_antimatter", unit_ids=(actor.id,), target_id=source.id),
        cast(actor),
    )
    assert not result.accepted
    assert source.antimatter_component.current_amount == 100


def test_transport_and_pulse_roundtrip_without_replaying_effects():
    game, actor, source, target, command = route_scenario()
    pulse = caster(game, name="pulse")
    assert activate(pulse, "multiply_antimatter", game.galaxy)
    assert issue(game, command).accepted
    for _ in range(35):
        tick(game, actor)
    before = serialize_game_state(game)
    assert deserialize_game_state(game, json.loads(json.dumps(before)))
    loaded = game.galaxy.get_unit_by_id(actor.id)
    loaded_pulse = game.galaxy.get_unit_by_id(pulse.id)
    assert (
        loaded.antimatter_component.current_amount
        == actor.antimatter_component.current_amount
    )
    assert (
        loaded.commander_component.current_order.phase
        == actor.commander_component.current_order.phase
    )
    assert loaded_pulse.multiply_cast_ready_round == pulse.multiply_cast_ready_round
    assert (
        loaded_pulse.multiply_receive_ready_round == pulse.multiply_receive_ready_round
    )
    assert (
        loaded_pulse.antimatter_component.current_amount
        == pulse.antimatter_component.current_amount
    )
    destination = game.galaxy.get_unit_by_id(target.id)
    prior = destination.antimatter_component.current_amount
    for _ in range(90):
        tick(game, loaded)
    assert destination.antimatter_component.current_amount > prior


def test_route_public_view_redacts_both_endpoints_and_children():
    from game_ai.order_view import order_layers

    game, actor, source, target, command = route_scenario()
    assert issue(game, command).accepted
    public = order_layers(actor, "self", {actor.id, source.id, target.id}, set())[
        "current_order"
    ]
    assert public["parameters"]["source_id"] == source.id
    assert public["parameters"]["target_id"] == target.id
    hidden = order_layers(actor, "self", {actor.id, source.id}, set())["current_order"]
    assert hidden["parameters"] == {}
    assert hidden["target_id"] is None
    assert str(target.id) not in json.dumps(hidden["parameters"])


def test_wormhole_route_estimate_and_actual_delivery():
    from domain.celestials import Wormhole

    game, actor, source, target, command = route_scenario()
    game.galaxy.systems["Sol"].hexes[(0, 0)].units.remove(target)
    target.in_system = "Beta"
    game.galaxy.systems["Beta"].hexes[(0, 0)].units.append(target)
    entry = Wormhole((0, 0), "Sol", "Beta")
    exit_ = Wormhole((0, 0), "Beta", "Sol")
    entry.exit_wormhole_id, exit_.exit_wormhole_id = exit_.id, entry.id
    for wormhole in (entry, exit_):
        game.galaxy.wormholes[wormhole.id] = wormhole
        game.galaxy.systems[wormhole.in_system].add_celestial_body(wormhole)
    game.galaxy.system_graph = {
        "Sol": {"Beta": HullSize.HUGE},
        "Beta": {"Sol": HullSize.HUGE},
    }
    assert estimate_approach(actor, game.galaxy, target) is not None
    result = issue(game, command)
    assert result.accepted, result.errors
    order = actor.commander_component.current_order
    for _ in range(260):
        tick(game, actor)
        assert order.status == OrderStatus.IN_PROGRESS, order.failure_reason
        if target.antimatter_component.current_amount > 650:
            break
    assert target.antimatter_component.current_amount > 650
    actor.hyperdrive_component.drive_type = HyperdriveType.BASIC
    assert route_budget(actor, source, target, game.galaxy) is None


def test_estimate_accounts_for_collision_detours_and_active_equipment():
    from domain.celestials import Star
    from constants import StarType
    from unit_components.cloaking import CloakingDevice

    game = campaign()
    actor = vessel(game, moving=True, position=(-2500, 0))
    target = vessel(game, position=(2500, 0))
    direct = estimate_approach(actor, game.galaxy, target)
    star = Star("Sol", StarType.G_TYPE)
    game.galaxy.systems["Sol"].add_celestial_body(star)
    detour = estimate_approach(actor, game.galaxy, target)
    assert detour.fuel > direct.fuel
    cloak = CloakingDevice(actor)
    actor.add_component(cloak)
    cloak.is_active = True
    active = estimate_approach(actor, game.galaxy, target)
    assert (
        active.fuel >= detour.fuel + detour.turns * cloak.get_antimatter_cost_per_turn()
    )


def test_allied_disabled_recipient_can_receive_pulse_and_take():
    game = campaign()
    game.players[1].team_id = game.players[0].team_id
    actor = caster(game)
    ally = vessel(game, owner=1, amount=50)
    ally.is_disabled = True
    assert activate(actor, "multiply_antimatter", game.galaxy)
    assert ally.antimatter_component.current_amount == 100
    assert issue(
        game, dict(type="take_antimatter", unit_ids=(actor.id,), target_id=ally.id)
    ).accepted
    actor.update()
    assert ally.antimatter_component.current_amount == 75


def test_multiple_casters_in_one_command_cannot_bypass_recipient_lock():
    game = campaign()
    first, second = caster(game), caster(game)
    result = issue(
        game,
        dict(
            type="use_ability",
            unit_ids=(first.id, second.id),
            ability="multiply_antimatter",
        ),
    )
    assert not result.accepted
    assert (
        first.antimatter_component.current_amount
        == second.antimatter_component.current_amount
        == 100
    )
    assert first.multiply_cast_ready_round == second.multiply_cast_ready_round == 0


def test_queued_pulse_has_no_speculative_gains_and_releases_reservation():
    game = campaign()
    actor, poor = caster(game, moving=True), caster(game, amount=15)
    move = dict(
        type="move",
        unit_ids=(actor.id,),
        system_name="Sol",
        hex_coord=(0, 0),
        position=(900, 0),
    )
    later = dict(
        type="use_ability",
        unit_ids=(poor.id,),
        ability="ghost_fleet",
        position=(350, 0),
    )
    result = issue(game, move, cast(actor, queue=True), later)
    assert not result.accepted
    assert actor.antimatter_component.current_amount == 100
    assert issue(game, move, cast(actor, queue=True)).accepted
    assert actor.multiply_cast_ready_round == 0
    assert issue(game, cast(actor)).accepted
    assert actor.multiply_cast_ready_round == game.turn_number + 30


def test_immediate_pulse_funds_legacy_ability():
    game = campaign()
    actor, recipient = caster(game), caster(game, amount=15)
    recipient.add_component(
        AbilityComponent(recipient, [AbilityType.ADAPTIVE_FORCEFIELD])
    )
    later = dict(
        type="use_ability", unit_ids=(recipient.id,), ability="adaptive_forcefield"
    )
    result = issue(game, cast(actor), later)
    assert result.accepted, result.errors
    assert recipient.antimatter_component.current_amount == 10


@pytest.mark.parametrize(
    "key,hull,capacity,cost,turns",
    [
        ("ANTIMATTER_TRANSPORTER", HullSize.MEDIUM, 600, 1970, 20),
        ("ANTIMATTER_STORAGE_STATION", HullSize.LARGE, 1600, 3700, 29),
        ("ANTIMATTER_CACHE_STATION", HullSize.SMALL, 460, 1000, 12),
    ],
)
def test_dedicated_designs_assemble_as_quoted(key, hull, capacity, cost, turns):
    from tests.test_builtin_catalog import create
    from unit_catalog import describe_template
    from unit_templates import UNIT_TEMPLATES

    game = campaign()
    unit = create(game, key)
    description = describe_template(key, UNIT_TEMPLATES[key])
    assert unit.hull_size == hull
    assert (
        unit.antimatter_component.current_amount
        == unit.antimatter_component.max_capacity
        == capacity
    )
    assert description["credit_cost"] == cost and description["turns"] == turns
    assert unit.harvester_component is None and unit.ability_component is None


def test_route_dialog_emits_start_and_queue_commands(monkeypatch, pygame_context):
    import pygame
    import pygame_gui
    from types import SimpleNamespace
    from gui.antimatter_transport_window import AntimatterTransportWindow

    game, actor, source, target, command = route_scenario()
    gui = SimpleNamespace(
        game_instance=game,
        manager=pygame_gui.UIManager((1000, 700)),
        antimatter_transport_window=None,
    )
    emitted = []
    monkeypatch.setattr(
        "tactical_ui.issue", lambda game, payload: emitted.append(payload) or True
    )
    for queued in (False, True):
        window = AntimatterTransportWindow(gui, actor, source)
        gui.antimatter_transport_window = window
        window.destination.selected_option = (
            next(label for label, uid in window.targets.items() if uid == target.id),
            "",
        )
        window.process_event(
            pygame.event.Event(
                pygame_gui.UI_BUTTON_PRESSED,
                ui_element=window.queue if queued else window.start,
            )
        )
        assert emitted[-1] == dict(command, unit_ids=[actor.id], queue=queued)
        assert gui.antimatter_transport_window is None


def test_issuance_and_replacement_never_exchange_extra_fuel():
    game = campaign()
    actor, source = vessel(game, amount=0), vessel(game, amount=100)
    pickup = dict(type="take_antimatter", unit_ids=(actor.id,), target_id=source.id)
    for _ in range(4):
        assert issue(game, pickup).accepted
    assert source.antimatter_component.current_amount == 100
    actor.update()
    assert source.antimatter_component.current_amount == 75
    assert issue(game, pickup).accepted
    assert source.antimatter_component.current_amount == 75


def test_batch_pulse_excludes_a_recipient_that_just_submerged():
    from domain.celestials import Planet
    from constants import PlanetType

    game = campaign()
    actor = caster(game, amount=40)
    recipient = vessel(game, amount=100, moving=True)
    body = Planet((0, 0), "Sol", PlanetType.GAS_GIANT)
    body.position = actor.position
    game.galaxy.systems["Sol"].add_celestial_body(body)
    result = issue(
        game,
        dict(type="enter_gas_giant", unit_ids=(recipient.id,), target_id=body.id),
        cast(actor),
    )
    assert not result.accepted
    assert not recipient.is_hidden_in_gas_giant
    assert actor.antimatter_component.current_amount == 40


@pytest.mark.parametrize(
    "field", ["multiply_cast_ready_round", "multiply_receive_ready_round"]
)
@pytest.mark.parametrize("value", [-1, True, 1.5])
def test_invalid_multiplication_deadlines_reject_transactionally(field, value):
    game = campaign()
    actor = caster(game)
    state = serialize_game_state(game)
    state["galaxy"]["systems"][0]["hexes"][0]["units"][0][field] = value
    assert not deserialize_game_state(game, state)
    assert game.galaxy.get_unit_by_id(actor.id) is actor


def test_capture_and_component_removal_do_not_reset_pulse_deadlines():
    game = campaign()
    actor = caster(game)
    assert activate(actor, "multiply_antimatter", game.galaxy)
    ready = game.turn_number + 30
    actor.owner = game.players[1]
    actor.remove_component(AbilityComponent)
    actor.remove_component(AntimatterStorage)
    state = serialize_game_state(game)
    assert deserialize_game_state(game, state)
    actor = game.galaxy.get_unit_by_id(actor.id)
    actor.add_component(AntimatterStorage(actor, max_capacity=600))
    actor.add_component(AbilityComponent(actor, [AbilityType.MULTIPLY_ANTIMATTER]))
    actor.antimatter_component.current_amount = 100
    assert (
        actor.multiply_cast_ready_round == actor.multiply_receive_ready_round == ready
    )
    assert not activate(actor, "multiply_antimatter", game.galaxy)


@pytest.mark.parametrize('amount,kind,prior', [
    (0, 'transfer_antimatter', 'take_antimatter'),
    (600, 'take_antimatter', 'transfer_antimatter'),
])
def test_ai_advertises_queued_pickup_delivery_dependencies(amount, kind, prior):
    from game_ai.rules import command_guidance
    game = campaign()
    actor, target = vessel(game, amount=amount), vessel(game)
    legal, options, conditional = command_guidance(
        game, actor.owner, actor, exact_bodies=[], visible_units=[actor, target])
    assert prior in legal and kind not in legal
    assert target.id in options[kind]['queued_target_ids']
    assert {'type': kind, 'requires_prior_command': prior, 'same_unit': True, 'queue': True} in conditional
