"""Fixed galaxy destinations survive UI dispatch, execution, queues and saves."""
from copy import deepcopy

import pytest

from campaign_graph import find_unit, iter_units
from events import ConstructEvent, EventBus
from game_ai.contracts import Command, ContractError
from game_ai.order_view import order_layers
from geometry import Position
from galaxy import StarSystem
from location_validation import location
from order_system import OrderSystem
from save_manager import serialize_game_state, deserialize_game_state
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from unit_components.constructor import Constructor
from unit_components.movement import Engines, Hyperdrive
from unit_components.enums import HyperdriveType
from unit_orders.base import Order, OrderStatus, OrderType
from unit_orders.construction import ConstructOrder
from unit_orders.movement import MoveOrder, ReachWaypointOrder
from unit_orders.patrol import PatrolOrder
from unit_orders.defend import DefendOrder
from unit_orders.abilities import UseAbilityOrder


def build_world():
    game = campaign()
    game.gui = None
    game.event_bus = EventBus()
    OrderSystem(game, game.event_bus)
    game.players[0].credits = 10000
    builder = ship(game, "Builder")
    builder.add_component(Constructor(builder))
    builder.add_component(Engines(builder, speed=1000))
    builder.add_component(Hyperdrive(builder, drive_type=HyperdriveType.ADVANCED, jump_range=30))
    builder.antimatter_component.max_capacity = 1000
    builder.antimatter_component.current_amount = 1000
    return game, builder


def build_command(builder, *, system="Sol", coord=(0, 0), pos=(200, 0), queue=False):
    return Command("construct", (builder.id,), template_name="CRYSTAL_REFINERY_STATION",
                   system_name=system, hex_coord=coord, position=pos, queue=queue)


@pytest.mark.parametrize("field,value", [
    ("system_name", None), ("system_name", ""), ("system_name", " "),
    ("hex_coord", None), ("hex_coord", [True, 0]), ("hex_coord", [0.5, 0]),
    ("hex_coord", [0]), ("position", None), ("position", [True, 0]),
    ("position", [float("nan"), 0]), ("position", [float("inf"), 0]),
])
def test_bad_construct_location_rejects_entire_batch_without_effects(field, value):
    game, builder = build_world()
    original = Order(builder, OrderType.TOGGLE_INHIBITOR)
    builder.commander_component.add_order(original)
    before = builder.owner.credits
    raw = build_command(builder).to_dict()
    raw[field] = value
    with pytest.raises(ContractError):
        Command.from_dict(raw)
    # Direct Python commands receive the same validation before an earlier cancellation.
    command = Command(**{**vars(build_command(builder)), field: value})
    result = issue(game, builder.owner, Command("cancel_orders", (builder.id,)), command)
    assert not result.accepted
    assert builder.commander_component.current_order is original
    assert builder.owner.credits == before
    assert not builder.constructor_component.current_construction_target


@pytest.mark.parametrize("field", ["system_name", "hex_coord", "position"])
@pytest.mark.parametrize("kind,ability", [("move", None), ("construct", None), ("patrol", None),
    ("defend", None), *[("use_ability", a) for a in
    ("microjump", "cluster_warhead", "ghost_fleet", "mine_clearing_sweep", "nebula_catalyst")]])
def test_every_positional_command_requires_each_location_field(field, kind, ability):
    raw = dict(type=kind, unit_ids=[1], system_name="Sol", hex_coord=[0, 0], position=[200, 0])
    if kind == "construct":
        raw["template_name"] = "CRYSTAL_REFINERY_STATION"
    if ability:
        raw["ability"] = ability
        if ability == "nebula_catalyst":
            raw["target_id"] = 2
    Command.from_dict(raw)
    del raw[field]
    with pytest.raises(ContractError):
        Command.from_dict(raw)


@pytest.mark.parametrize("cls,params", [(MoveOrder, {}), (ReachWaypointOrder, {}),
    (ConstructOrder, {"unit_template_name": "CRYSTAL_REFINERY_STATION"}), (DefendOrder, {}),
    (PatrolOrder, {"waypoints": [{"position": Position(0, 0)}]}),
    (UseAbilityOrder, {"ability_type": "microjump", "target_position": Position(0, 0)})])
def test_malformed_internal_orders_fail_cleanly(cls, params):
    game, builder = build_world()
    order = cls(builder, params)
    order.execute(game.galaxy)
    assert order.status == OrderStatus.FAILED
    assert order.failure_reason == "invalid_parameters"


@pytest.mark.parametrize("system,coord", [("missing", (0, 0)), ("Sol", (12, 12))])
def test_nonexistent_construction_site_preserves_existing_order(system, coord):
    game, builder = build_world()
    original = Order(builder, OrderType.TOGGLE_INHIBITOR)
    builder.commander_component.add_order(original)
    result = issue(game, builder.owner, build_command(builder, system=system, coord=coord))
    assert not result.accepted and result.errors[0].code == "invalid_destination"
    assert builder.commander_component.current_order is original


def test_logged_cross_sector_regression_routes_and_builds_at_clicked_site(caplog):
    game, builder = build_world()
    system = StarSystem("Epsilon Eridani", Position(0, 0), radius=12)
    system.in_galaxy = game.galaxy
    game.galaxy.systems[system.name] = system
    game.galaxy.move_unit_between_systems(builder, "Sol", system.name, (-4, -6))
    caplog.set_level("DEBUG")
    selected = Position(-431.75, -557.65)
    event = ConstructEvent([builder], "CRYSTAL_REFINERY_STATION", selected, False,
                           system_name=system.name, hex_coord=(10, -4))
    selected.x = 999  # The selection/event owns its copied coordinates.
    game.event_bus.publish(event)
    root = builder.commander_component.current_order
    assert root.parameters["target_hex_coord"] == (10, -4)
    assert root.parameters["target_position"] == Position(-431.75, -557.65)
    assert root.sub_orders[0].parameters["destination_hex_coord"] == (10, -4)
    before = {u.id for u, _ in iter_units(game.galaxy)}
    for _ in range(100):
        from turn_processor import TurnProcessor
        TurnProcessor(game)._process_movement(builder.owner)
        builder.update()
        if root.status in {OrderStatus.COMPLETED, OrderStatus.FAILED}:
            break
    assert root.status == OrderStatus.COMPLETED
    built = [u for u, _ in iter_units(game.galaxy) if u.id not in before]
    assert len(built) == 1
    assert (built[0].in_system, built[0].in_hex, built[0].position) == (system.name, (10, -4), Position(-431.75, -557.65))
    assert "Epsilon Eridani (10, -4) at (-431.75, -557.65)" in caplog.text


def test_queued_site_survives_view_change_and_previous_move():
    game, builder = build_world()
    move = Command("move", (builder.id,), system_name="Sol", hex_coord=(1, 0), position=(200, 0))
    assert issue(game, builder.owner, move, build_command(builder, queue=True)).accepted
    queued = builder.commander_component.orders_queue[0]
    game.current_system_name, game.current_sector_coord = "Beta", (1, 0)
    for _ in range(100):
        from turn_processor import TurnProcessor
        TurnProcessor(game)._process_movement(builder.owner)
        builder.update()
        if queued.status in {OrderStatus.COMPLETED, OrderStatus.FAILED}:
            break
    assert queued.status == OrderStatus.COMPLETED
    assert builder.in_hex == (0, 0)
    assert queued.parameters["target_system_name"] == "Sol"
    assert queued.parameters["target_position"] == Position(200, 0)


@pytest.mark.parametrize("via_ui", [False, True])
def test_stationary_builder_cannot_build_same_xy_in_other_sector(via_ui):
    game, builder = build_world()
    builder.remove_component(Engines)
    original = Order(builder, OrderType.TOGGLE_INHIBITOR)
    builder.commander_component.add_order(original)
    if via_ui:
        game.event_bus.publish(ConstructEvent([builder], "CRYSTAL_REFINERY_STATION", builder.position, False,
                                             system_name="Beta", hex_coord=(0, 0)))
    else:
        assert not issue(game, builder.owner, build_command(builder, system="Beta", pos=(100, 0))).accepted
    assert builder.commander_component.current_order is original
    assert builder.owner.credits == 10000


@pytest.mark.parametrize("displacement", ["sector", "range"])
def test_displacement_refunds_once_and_preserves_queued_sibling(displacement):
    game, builder = build_world()
    assert issue(game, builder.owner, build_command(builder)).accepted
    root = builder.commander_component.current_order
    pending = ConstructOrder(builder, dict(root.parameters))
    builder.commander_component.add_order(pending)
    assert builder.owner.credits == 8540
    if displacement == "sector":
        game.galaxy.systems["Sol"].move_unit_between_hexes(builder, (1, 0))
    else:
        builder.position = Position(2000, 0)
    builder.constructor_component.update(game.galaxy)
    assert root.status == OrderStatus.FAILED and root.failure_reason == "target_out_of_range"
    assert builder.owner.credits == 10000
    assert list(builder.commander_component.orders_queue) == [pending]
    builder.constructor_component.finish_construction(game.galaxy)
    root.cancel()
    builder.constructor_component.update(game.galaxy)
    assert builder.owner.credits == 10000
    assert len(builder.owner.order_history) == 1
    assert len(list(iter_units(game.galaxy))) == 1


@pytest.mark.parametrize("phase", ["pending", "approaching", "building"])
def test_complete_build_location_roundtrips_without_replaying_charges(phase):
    game, builder = build_world()
    if phase == "pending":
        builder.commander_component.add_order(Order(builder, OrderType.TOGGLE_INHIBITOR))
    command = build_command(builder, system="Beta" if phase == "pending" else "Sol",
                            coord=(1, 0) if phase == "approaching" else (0, 0), queue=phase == "pending")
    assert issue(game, builder.owner, command).accepted
    before = builder.owner.credits
    state = serialize_game_state(game)
    assert deserialize_game_state(game, state)
    builder = find_unit(game.galaxy, builder.id)
    root = builder.commander_component.orders_queue[0] if phase == "pending" else builder.commander_component.current_order
    assert root.parameters["target_system_name"] == command.system_name
    assert root.parameters["target_hex_coord"] == command.hex_coord
    assert builder.owner.credits == before
    exposed = order_layers(builder, "self", {builder.id}, set())
    shown = exposed["queued_orders"][0] if phase == "pending" else exposed["current_order"]
    assert shown["parameters"]["system_name"] == command.system_name
    assert shown["parameters"]["hex_coord"] == list(command.hex_coord)


@pytest.mark.parametrize("broken", ["missing_field", "job_mismatch", "owner_mismatch", "old_version"])
def test_bad_saved_destinations_are_rejected_transactionally(broken):
    game, builder = build_world()
    assert issue(game, builder.owner, build_command(builder)).accepted
    original = serialize_game_state(game)
    state = deepcopy(original)
    def visit(value):
        if isinstance(value, dict):
            if value.get("order_type") == "CONSTRUCT" and broken == "missing_field":
                value["parameters"].pop("target_system_name", None)
            for key, item in value.items():
                if key == "current_construction_target" and broken == "job_mismatch" and item:
                    item["system_name"] = "Beta"
                if key == "construction_order_id" and broken == "owner_mismatch":
                    value[key] = "0" * 32
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(state)
    if broken == "old_version":
        state["version"] = "4.9"
    assert not deserialize_game_state(game, state)
    assert game.galaxy.get_unit_by_id(builder.id) is builder
    after = serialize_game_state(game)
    after.pop("timestamp")
    original.pop("timestamp")
    assert after == original


def test_location_copies_coordinates_and_keeps_zero_and_negative_values():
    coord, pos = [0, -1], Position(0, -12.5)
    site = location("Sol", coord, pos)
    coord[0], pos.x = 8, 100
    assert site == ("Sol", (0, -1), Position(0, -12.5))


def test_construct_overlay_uses_selected_sector_before_execution():
    from types import SimpleNamespace
    from rendering.sector_renderer.sector_overlay_renderer import SectorOverlayRenderer
    game, builder = build_world()
    order = ConstructOrder(builder, dict(unit_template_name="CRYSTAL_REFINERY_STATION",
        target_system_name="Beta", target_hex_coord=(0, 0), target_position=Position(200, 0)))
    renderer = SectorOverlayRenderer(SimpleNamespace(game=game))
    assert renderer.order_targets_sector(order, "Beta", (0, 0))
    assert not renderer.order_targets_sector(order, "Sol", (0, 0))
    waypoints = []
    renderer.collect_waypoints_from_order(order, builder, waypoints)
    assert [(w["system"], w["hex"], w["position"]) for w in waypoints] == [
        ("Beta", (0, 0), Position(200, 0))]


def test_queued_internal_order_copies_location_before_execution():
    game, builder = build_world()
    point, coord = Position(200, 0), [1, 0]
    order = ConstructOrder(builder, dict(unit_template_name="CRYSTAL_REFINERY_STATION",
        target_system_name="Sol", target_hex_coord=coord, target_position=point))
    point.x, coord[0] = 999, 0
    assert order.parameters["target_position"] == Position(200, 0)
    assert order.parameters["target_hex_coord"] == (1, 0)


@pytest.mark.parametrize("ability", ["microjump", "ghost_fleet", "mine_clearing_sweep"])
def test_local_abilities_reject_remote_site_and_recheck_queued_sector(ability):
    from unit_components.abilities import AbilityComponent
    from unit_components.enums import AbilityType
    from unit_components.minelayer import MinelayerComponent
    from tactical_abilities import deployments
    game, builder = build_world()
    builder.add_component(AbilityComponent(builder, [AbilityType(ability)]))
    builder.add_component(MinelayerComponent(builder))
    if ability == "mine_clearing_sweep":
        from domain.minefields import Minefield
        field = Minefield(game.players[1], Position(200, 0), (0, 0), "Sol", mines_remaining=5)
        field.reveal_to(builder.owner)
        game.galaxy.systems["Sol"].hexes[(0, 0)].minefields.append(field)
    blocker = Order(builder, OrderType.TOGGLE_INHIBITOR)
    builder.commander_component.add_order(blocker)
    remote = Command("use_ability", (builder.id,), ability=ability,
                     system_name="Sol", hex_coord=(1, 0), position=(200, 0))
    assert not issue(game, builder.owner, remote).accepted
    assert builder.commander_component.current_order is blocker
    local = Command("use_ability", (builder.id,), ability=ability,
                    system_name="Sol", hex_coord=(0, 0), position=(200, 0), queue=True)
    assert issue(game, builder.owner, local).accepted
    queued = builder.commander_component.orders_queue[0]
    fuel = builder.antimatter_component.current_amount
    game.galaxy.systems["Sol"].move_unit_between_hexes(builder, (1, 0))
    builder.commander_component.cancel_order(blocker.local_order_id)
    assert queued.status == OrderStatus.FAILED
    assert builder.antimatter_component.current_amount == fuel
    assert not deployments(game.galaxy, builder.id, "ghost_fleet")


def test_entity_and_self_commands_retain_location_free_contract():
    for raw in [dict(type="attack", unit_ids=[1], target_id=2),
                dict(type="defend", unit_ids=[1], target_id=2),
                dict(type="use_ability", unit_ids=[1], ability="ion_bolt", target_id=2),
                dict(type="use_ability", unit_ids=[1], ability="multiply_antimatter")]:
        assert Command.from_dict(raw).position is None


def test_saved_patrol_waypoint_requires_complete_location():
    game, builder = build_world()
    assert issue(game, builder.owner, Command("patrol", (builder.id,), waypoints=(
        dict(system_name="Sol", hex_coord=(0, 0), position=(500, 0)),))).accepted
    state = serialize_game_state(game)
    def corrupt(value):
        if isinstance(value, dict):
            if value.get("order_type") == "PATROL":
                value["parameters"]["waypoints"][0].pop("system_name")
            for item in value.values():
                corrupt(item)
        elif isinstance(value, list):
            for item in value:
                corrupt(item)
    corrupt(state)
    assert not deserialize_game_state(game, state)
    assert game.galaxy.get_unit_by_id(builder.id) is builder


def test_displaced_nested_build_settles_before_root_reports_failure():
    game, builder = build_world()
    assert issue(game, builder.owner, build_command(builder, coord=(1, 0))).accepted
    root = builder.commander_component.current_order
    from turn_processor import TurnProcessor
    for _ in range(20):
        TurnProcessor(game)._process_movement(builder.owner)
        builder.update()
        if builder.constructor_component.current_construction_target:
            break
    constructor = builder.constructor_component
    owning = constructor._owning_construction_order()
    assert owning is not None and owning is not root
    # The saved approaching root must retain the active child's charge ownership.
    state = serialize_game_state(game)
    assert deserialize_game_state(game, state)
    builder = find_unit(game.galaxy, builder.id)
    root = builder.commander_component.current_order
    constructor = builder.constructor_component
    pending = ConstructOrder(builder, dict(root.parameters))
    builder.commander_component.add_order(pending)
    builder.position = Position(2000, 0)
    constructor.update(game.galaxy)
    root.update(game.galaxy)
    assert root.status == OrderStatus.FAILED and root.failure_reason == "target_out_of_range"
    assert builder.owner.credits == 10000
    assert list(builder.commander_component.orders_queue) == [pending]
    assert pending.status == OrderStatus.PENDING
    assert len(builder.owner.order_history) == 1
    constructor.finish_construction(game.galaxy)
    root.cancel()
    assert builder.owner.credits == 10000
    assert len(list(iter_units(game.galaxy))) == 1


@pytest.mark.parametrize("ability", ["microjump", "cluster_warhead", "ghost_fleet"])
def test_pending_positional_ability_and_patrol_roundtrip(ability):
    game, builder = build_world()
    blocker = Order(builder, OrderType.TOGGLE_INHIBITOR)
    builder.commander_component.add_order(blocker)
    ability_order = UseAbilityOrder(builder, dict(ability_type=ability,
        target_system_name="Sol", target_hex_coord=(1, 0), target_position=Position(222, -33)))
    builder.commander_component.add_order(ability_order)
    patrol = PatrolOrder(builder, dict(waypoints=[dict(system_name="Beta", hex_coord=(0, 0), position=Position(123, 45))]))
    builder.commander_component.add_order(patrol)
    state = serialize_game_state(game)
    assert deserialize_game_state(game, state)
    builder = find_unit(game.galaxy, builder.id)
    loaded_ability, loaded_patrol = builder.commander_component.orders_queue
    assert loaded_ability.parameters == ability_order.parameters
    assert loaded_patrol.parameters == patrol.parameters


def test_construct_routes_through_wormhole_to_another_system():
    from constants import HullSize
    from domain.celestials import Wormhole
    from turn_processor import TurnProcessor
    game, builder = build_world()
    entry, exit_ = Wormhole((0, 0), "Sol", "Beta"), Wormhole((0, 0), "Beta", "Sol")
    entry.exit_wormhole_id, exit_.exit_wormhole_id = exit_.id, entry.id
    for wormhole in (entry, exit_):
        wormhole.diameter = HullSize.HUGE
        game.galaxy.wormholes[wormhole.id] = wormhole
        game.galaxy.systems[wormhole.in_system].add_celestial_body(wormhole)
    game.galaxy._build_system_graph()
    assert issue(game, builder.owner, build_command(builder, system="Beta", pos=(2000, 0))).accepted
    root = builder.commander_component.current_order
    for _ in range(100):
        TurnProcessor(game)._process_movement(builder.owner)
        builder.update()
        if root.status in {OrderStatus.COMPLETED, OrderStatus.FAILED}:
            break
    assert root.status == OrderStatus.COMPLETED, root.failure_reason
    built = [u for u, _ in iter_units(game.galaxy) if u.id != builder.id]
    assert len(built) == 1
    assert (built[0].in_system, built[0].in_hex, built[0].position) == ("Beta", (0, 0), Position(2000, 0))
