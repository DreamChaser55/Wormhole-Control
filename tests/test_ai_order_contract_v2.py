"""Real-engine regressions for the shared AI order contract (no API calls)."""
import json
from collections import deque
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch, ContractError, TurnPlan
from game_ai.observation import build_observation
from game_ai.order_view import order_layers
from geometry import Position
from unit_components import CloakingDevice, UnitStance
from unit_orders import AttackOrder, MoveOrder, Order, OrderStatus, OrderType, PatrolOrder
from tests.test_stance_visibility import create_combat_ship, create_test_galaxy


def world():
    galaxy, player, enemy = create_test_galaxy()
    game = SimpleNamespace(galaxy=galaxy, players=[player, enemy], turn_number=1,
                           sidebar_needs_update=False, visibility_dirty=False, gui=None)
    galaxy.game = game
    unit = create_combat_ship(galaxy, player, "Scout", (0, 0))
    return game, player, enemy, unit


def issue(game, player, *commands):
    return CommandGateway(game).apply_batch(player, CommandBatch(tuple(commands)))


def waypoint(x=500):
    return {"system_name": "Sol", "hex_coord": [0, 0], "position": [x, 0]}


@pytest.mark.parametrize("fields", [
    {"queue": "false"}, {"queue": 0}, {"quue": True}, {"unit_ids": [True]},
    {"unit_ids": [1.0]}, {"unit_ids": [-1]}, {"unit_ids": [1, 1]},
    {"unit_ids": list(range(13))}, {"unit_ids": "1"}, {"position": [float("nan"), 0]},
    {"position": [float("inf"), 0]}, {"position": [True, 0]}, {"hex_coord": [0.5, 0]},
    {"amount": 2}, {"target_id": False}, {"system_name": 7},
])
def test_strict_socket_shape_rejects_ambiguous_input(fields):
    raw = {"type": "move", "unit_ids": [1], **waypoint(), **fields}
    with pytest.raises(ContractError):
        Command.from_dict(raw)


def test_direct_command_validation_and_batch_limit_are_atomic():
    game, player, _, unit = world()
    original = Order(unit, OrderType.TOGGLE_INHIBITOR)
    unit.commander_component.add_order(original)
    bad = Command(type="move", unit_ids=(unit.id,), queue="false", **waypoint())
    result = issue(game, player, Command("cancel_orders", (unit.id,)), bad)
    assert not result.accepted and result.failure_stage == "preflight"
    assert unit.commander_component.current_order is original
    assert not player.order_history
    assert not issue(game, player, *[Command("cancel_orders", (unit.id,))] * 41).accepted


def test_sparse_and_strict_commands_normalize_identically():
    sparse = Command.from_dict({"type": "patrol", "unit_ids": [1], "waypoints": [waypoint()]})
    assert sparse == Command.from_dict(sparse.to_dict())
    for extra in ({"position": [0, 0]}, {"queue": True}):
        with pytest.raises(ContractError):
            Command.from_dict({"type": "clear_explicit_orders", "unit_ids": [1], **extra})
    with pytest.raises(ContractError):
        TurnPlan.from_dict({"plan": [], "commands": [], "memory_patch": {}, "end_turn": False})


def test_destroyed_cloak_rejects_before_preceding_cancellation():
    game, player, _, unit = world()
    unit.add_component(CloakingDevice(unit))
    unit.cloaking_component.current_hit_points = 0
    original = Order(unit, OrderType.TOGGLE_INHIBITOR)
    unit.commander_component.add_order(original)
    result = issue(game, player, Command("cancel_orders", (unit.id,)), Command("toggle_cloaking", (unit.id,)))
    assert not result.accepted and result.applied_count == 0
    assert unit.commander_component.current_order is original
    view = build_observation(game, player)["units"][0]
    assert "toggle_cloaking" in view["supported_commands"]
    assert "toggle_cloaking" not in view["legal_commands"]
    assert not view["capability_details"]["cloaking"]["can_activate"]


def test_patrol_routes_append_queue_blocking_and_precise_cancellation():
    game, player, _, unit = world()
    commander = unit.commander_component
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    result = issue(game, player, Command("patrol", (unit.id,), waypoints=(waypoint(), waypoint(700))))
    assert result.accepted
    current = commander.current_order
    assert current.public_id == result.operation_results[0]["order_id"]
    assert len(current.parameters["waypoints"]) == 2
    child = current.sub_orders[0]
    assert issue(game, player, Command("append_patrol_waypoints", (unit.id,), order_id=current.public_id, waypoints=(waypoint(900),))).accepted
    assert current.sub_orders[0] is child
    assert issue(game, player, Command("patrol", (unit.id,), queue=True, waypoints=(waypoint(300),))).accepted
    queued = commander.orders_queue[0]
    assert queued is not current and len(current.parameters["waypoints"]) == 3
    view = build_observation(game, player)["units"][0]
    assert view["standing_order"]["suspended"]
    assert view["current_order"]["type"] == "patrol"
    assert view["queued_orders"][0]["blocked_by_order_id"] == current.public_id
    assert issue(game, player, Command("cancel_order", (unit.id,), order_id=current.public_id)).accepted
    assert commander.current_order is queued
    assert issue(game, player, Command("clear_explicit_orders", (unit.id,))).accepted
    assert commander.stance == UnitStance.ATTACK_SAME_SECTOR
    assert issue(game, player, Command("cancel_orders", (unit.id,))).accepted
    assert commander.stance == UnitStance.DO_NOTHING
    assert [e["outcome"] for e in player.order_history] == ["cancelled", "cancelled"]


def test_invalid_route_and_removed_id_reject_atomically():
    game, player, _, unit = world()
    issue(game, player, Command("patrol", (unit.id,), waypoints=(waypoint(),)))
    original = unit.commander_component.current_order
    bad = {**waypoint(), "system_name": "nonexistent"}
    assert not issue(game, player, Command("cancel_orders", (unit.id,)), Command("patrol", (unit.id,), waypoints=(waypoint(), bad))).accepted
    assert unit.commander_component.current_order is original
    result = issue(game, player, Command("cancel_order", (unit.id,), order_id=original.public_id),
                   Command("append_patrol_waypoints", (unit.id,), order_id=original.public_id, waypoints=(waypoint(),)))
    assert not result.accepted and result.errors[0].code == "order_unavailable"
    assert unit.commander_component.current_order is original
    assert not issue(game, player, Command("append_patrol_waypoints", (unit.id,), order_id=original.public_id,
                                         waypoints=tuple(waypoint() for _ in range(16)))).accepted


def test_commit_failure_reports_completed_uncertain_and_unattempted_operations():
    game, player, _, unit = world()
    original = unit.commander_component.set_stance
    def fail_after_mutation(stance):
        original(stance)
        raise RuntimeError("secret detail must not escape")
    with patch.object(unit.commander_component, "set_stance", side_effect=fail_after_mutation):
        result = issue(game, player, Command("clear_explicit_orders", (unit.id,)),
                       Command("set_stance", (unit.id,), stance="attack_same_sector"),
                       Command("clear_explicit_orders", (unit.id,)))
    assert not result.accepted and not result.retryable
    assert result.applied_count == 1 and len(result.receipts) == 1
    assert result.failure_stage == "commit" and result.errors[0].command_index == 1
    assert result.requires_observation and result.may_have_partial_effects
    assert [op["status"] for op in result.operation_results] == ["applied", "failed", "unattempted"]
    assert unit.commander_component.stance == UnitStance.ATTACK_SAME_SECTOR
    assert game.sidebar_needs_update and game.visibility_dirty
    assert "secret" not in str(result)


def test_secrecy_stance_layers_and_target_derived_geometry():
    from unit_components.intelligence import IntelligenceComponent
    game, player, enemy, unit = world()
    target = create_combat_ship(game.galaxy, enemy, "SECRET NAME", (0, 0), pos=(1000, 0))
    target.add_component(IntelligenceComponent(target))
    commander = unit.commander_component
    commander.set_stance(UnitStance.ATTACK_SAME_SECTOR)
    commander.update()
    view = build_observation(game, player)
    own = next(v for v in view["units"] if v["id"] == unit.id)
    hostile = next(v for v in view["units"] if v["id"] == target.id)
    assert own["current_order"] is None and own["standing_order"]["engagement"]["origin"] == "stance"
    assert "IntelligenceComponent" not in hostile["components"]
    assert "IntelligenceComponent" not in own["command_options"]["attack"]["target_components"][str(target.id)]
    errors = [issue(game, player, Command("attack", (unit.id,), target_id=target.id, target_component=name)).errors
              for name in ("IntelligenceComponent", "DoesNotExist")]
    assert errors[0] == errors[1]
    assert issue(game, player, Command("attack", (unit.id,), target_id=target.id)).accepted
    assert commander.current_order.order_type == OrderType.ATTACK
    hidden = order_layers(unit, "self", {unit.id}, set())["current_order"]
    assert hidden["target_id"] is None and hidden["parameters"] == {}
    def check(node):
        assert node["parameters"] == {}
        for child in node["suborders"]:
            check(child)
    check(hidden)
    fixed = MoveOrder(unit, {"destination_system_name": "Sol", "destination_hex_coord": (0, 0), "destination_position": Position(42, 0)})
    commander.clear_explicit_orders()
    commander.add_order(fixed)
    assert order_layers(unit, "self", set(), set())["current_order"]["parameters"]["position"] == [42, 0]


def test_history_identity_roundtrip_and_bounded_exactly_once_outcomes():
    from order_history import history_view
    from save_manager import serialize_order, deserialize_order, serialize_player, deserialize_player
    game, player, _, unit = world()
    root = Order(unit, OrderType.MOVE)
    child = Order(unit, OrderType.REACH_WAYPOINT)
    root.add_sub_order(child)
    root.register_explicit_root()
    root.status = OrderStatus.IN_PROGRESS
    child.fail("path_unavailable")
    root.update(game.galaxy)
    assert player.order_history[-1]["reason"] == "path_unavailable"
    root.cancel()
    assert len(player.order_history) == 1
    data = serialize_order(root)
    restored = deserialize_order(data, unit, None)
    assert restored.public_id == root.public_id
    restored.register_explicit_root(restored=True)
    restored.cancel()
    assert len(player.order_history) == 1
    legacy = dict(data)
    legacy.pop("public_id")
    assert deserialize_order(legacy, unit, None).public_id != root.public_id
    for _ in range(150):
        order = Order(unit, OrderType.MOVE)
        order.register_explicit_root()
        order.status = OrderStatus.COMPLETED
    history = history_view(player)
    assert len(history["events"]) <= 128
    assert len(json.dumps(history["events"], ensure_ascii=False)) <= 32000
    assert history["omitted_count"] > 0
    restored_player = deserialize_player(serialize_player(player))
    assert history_view(restored_player) == history


@pytest.mark.parametrize("kind", ["construct", "refit"])
def test_pending_job_cancellation_does_not_refund_or_stop_active_job(kind):
    from unit_components.constructor import Constructor, BuildableUnit
    from unit_orders import ConstructOrder, RefitOrder
    game, player, _, unit = world()
    unit.add_component(Constructor(unit))
    component = unit.constructor_component
    player.credits = 500
    if kind == "construct":
        order = ConstructOrder(unit, {"unit_template_name": "test", "target_position": Position(500, 0)})
        pending = ConstructOrder(unit, dict(order.parameters))
        component.can_build = lambda name: SimpleNamespace(cost_credits=100, time_to_build=5)
        unit.commander_component.add_order(order)
        target_attr = "current_construction_target"
    else:
        # Start a real component job and bind its charge just as RefitOrder.execute does.
        order = RefitOrder(unit, {"target_unit_id": unit.id})
        pending = RefitOrder(unit, dict(order.parameters))
        order.register_explicit_root()
        order.status = OrderStatus.IN_PROGRESS
        unit.commander_component.current_order = order
        assert component.start_refit(unit, "ADD", "Sensors", cost_credits=100, time_to_build=5)
        component.refit_order_id = order.public_id
        order._charged_credits = 100
        order._charged_player_id = player.id
        target_attr = "current_refit_target"
    unit.commander_component.add_order(pending)
    target = getattr(component, target_attr)
    assert player.credits == 400
    assert issue(game, player, Command("cancel_order", (unit.id,), order_id=pending.public_id)).accepted
    assert getattr(component, target_attr) is target and player.credits == 400
    assert issue(game, player, Command("cancel_order", (unit.id,), order_id=order.public_id)).accepted
    assert getattr(component, target_attr) is None and player.credits == 500
    order.cancel()
    assert player.credits == 500


def test_socket_partial_response_cached_and_observation_required():
    from game_control_protocol import ControlService, PROTOCOL_VERSION
    from player_controller import PlayerController
    game, player, _, unit = world()
    game.game_started = True
    game.campaign_id = "test"
    game.current_player = player
    game.view_mode = "galaxy"
    player.controller = PlayerController.CODEX
    service = ControlService(game, port=0)
    request = {"protocol_version": PROTOCOL_VERSION, "action": "command", "request_id": "failure",
               "turn_token": service._turn_token(player),
               "commands": [{"type": "clear_explicit_orders", "unit_ids": [unit.id]}]}
    with patch.object(unit.commander_component, "clear_explicit_orders", side_effect=RuntimeError("failure")) as mutation:
        first = service._dispatch_or_wait(request, Future())
        second = service._dispatch_or_wait(request, Future())
    assert first == second and mutation.call_count == 1
    assert first["data"]["requires_observation"] and first["data"]["turn_token"] is None
    blocked = service._dispatch_or_wait({**request, "action": "end_turn", "request_id": "end"}, Future())
    assert blocked["error"]["code"] == "observation_required"
    observed = service._dispatch_or_wait({"protocol_version": 2, "action": "observe"}, Future())
    assert observed["ok"] and observed["data"]["turn_token"] != request["turn_token"]
    assert service._dispatch_or_wait({**request, "request_id": "fresh", "turn_token": observed["data"]["turn_token"]}, Future())["ok"]


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("kind", ["construct", "refit"])
def test_restored_component_job_refunds_only_its_owner_once(legacy, kind):
    from save_manager import deserialize_order, serialize_order
    from unit_components.constructor import Constructor
    from unit_orders import ConstructOrder, RefitOrder
    game, player, _, unit = world()
    unit.add_component(Constructor(unit))
    constructor = unit.constructor_component
    constructor.can_build = lambda name: SimpleNamespace(cost_credits=100, time_to_build=5)
    player.credits = 500
    if kind == "construct":
        root = ConstructOrder(unit, {"unit_template_name": "test", "target_position": Position(500, 0)})
        unit.commander_component.add_order(root)
    else:
        root = RefitOrder(unit, {"target_unit_id": unit.id})
        root.register_explicit_root()
        root.status = OrderStatus.IN_PROGRESS
        unit.commander_component.current_order = root
        constructor.start_refit(unit, "ADD", "Sensors", cost_credits=100, time_to_build=5)
        constructor.refit_order_id = root.public_id
        root._charged_credits = 100
        root._charged_player_id = player.id
    data = serialize_order(root)
    if legacy:
        data.pop("public_id")
        data["runtime_state"] = {}
    restored = deserialize_order(data, unit, None)
    constructor.construction_order_id = constructor.refit_order_id = None
    unit.commander_component.restore_explicit_orders(restored, [], game.galaxy)
    assert player.credits == 400 and not player.order_history
    assert issue(game, player, Command("cancel_order", (unit.id,), order_id=restored.public_id)).accepted
    assert player.credits == 500
    restored.cancel()
    assert player.credits == 500 and len(player.order_history) == 1


def test_tactical_values_use_engine_helpers_and_ally_detail():
    from unit_components.enums import SabotageType
    game, player, _, unit = world()
    ally = type(player)("Ally", (1, 2, 3), team_id=player.team_id)
    game.players.append(ally)
    friend = create_combat_ship(game.galaxy, ally, "Ally", (0, 0))
    friend.commander_component.add_order(Order(friend, OrderType.REPAIR))
    unit.experience_points = 1000
    with patch.object(unit, "is_sabotaged", side_effect=lambda kind: kind == SabotageType.SENSORS):
        views = build_observation(game, player)["units"]
        own = next(v for v in views if v["id"] == unit.id)
        details = own["capability_details"]
        assert details["hyperdrive"]["effective_jump_range"] == unit.hyperdrive_component.effective_jump_range
        assert details["sensors"]["effective_short_range_radius"] == unit.sensors_component.effective_short_range_radius
        assert details["weapons"]["turrets"][0]["range"] == unit.weapons_component.turrets[0].range
    friendly = next(v for v in views if v["id"] == friend.id)
    assert friendly["current_order"]["order_id"] == friend.commander_component.current_order.public_id
    assert not friendly["current_order"]["cancellable"]
    assert "order_history" not in friendly


def test_expansion_caps_preserve_all_explicit_roots():
    game, player, _, unit = world()
    root = Order(unit, OrderType.MOVE)
    for _ in range(50):
        root.add_sub_order(Order(unit, OrderType.REACH_WAYPOINT))
    root.register_explicit_root()
    unit.commander_component.current_order = root
    queued = [PatrolOrder(unit, {"waypoints": [waypoint()] * 20}) for _ in range(45)]
    unit.commander_component.orders_queue = deque(queued)
    view = order_layers(unit, "self", {unit.id}, set())
    assert len(view["current_order"]["suborders"]) == 32
    assert view["current_order"]["omitted_suborders"] == 18
    assert [v["order_id"] for v in view["queued_orders"]] == [o.public_id for o in queued]
    assert view["queued_orders"][0]["parameters"]["omitted_waypoints"] == 4


def test_destruction_and_ownership_interruption_do_not_refund_or_duplicate():
    from order_history import interrupt_unit_orders
    game, player, enemy, unit = world()
    root = Order(unit, OrderType.CONSTRUCT)
    unit.commander_component.add_order(root)
    before = player.credits
    with patch.object(root, "cancel", side_effect=AssertionError("must not refund")):
        interrupt_unit_orders(unit, "ownership_lost")
        unit.owner = enemy
        interrupt_unit_orders(unit, "unit_destroyed")
    assert player.credits == before and not enemy.order_history
    assert [event["reason"] for event in player.order_history] == ["ownership_lost"]


def test_luna_rejects_incomplete_turn_before_mutation_and_preserves_memory_on_commit_failure():
    from game_ai.adapters.base import PlanningResult
    from game_ai.coordinator import AgentTurnCoordinator
    from player_controller import PlayerController
    game, player, _, unit = world()
    game.current_player = player
    game.campaign_id = "test"
    player.controller = PlayerController.OPENAI
    player.ai_memory = {"strategy": "original"}
    coordinator = AgentTurnCoordinator(game, provider=object())
    try:
        plan = TurnPlan((), CommandBatch((Command("clear_explicit_orders", (unit.id,)),), end_turn=False), {})
        result = PlanningResult(plan, "fake", "gpt-5.6-luna", "medium")
        with patch("game_ai.coordinator.CommandGateway") as gateway, patch.object(coordinator, "_handle_output_error") as output_error:
            coordinator._apply_result(result)
            gateway.assert_not_called()
            output_error.assert_called_once()
        valid = TurnPlan((), CommandBatch((Command("clear_explicit_orders", (unit.id,)),)), {"strategy": "rejected"})
        with patch.object(unit.commander_component, "clear_explicit_orders", side_effect=RuntimeError("failure")), patch.object(coordinator, "_append_telemetry"):
            coordinator._apply_result(PlanningResult(valid, "fake", "gpt-5.6-luna", "medium"))
        assert player.ai_memory == {"strategy": "original"}
        assert player.last_ai_report["failure_stage"] == "commit"
        assert coordinator.state == "error" and coordinator._repair_attempts_used == 0
    finally:
        coordinator.shutdown()


def test_append_while_returning_preserves_current_return_leg():
    game, player, _, unit = world()
    issue(game, player, Command("patrol", (unit.id,), waypoints=(waypoint(),)))
    root = unit.commander_component.current_order
    root.current_waypoint_index = 1
    root.patrol_phase = "TO_START"
    root._spawn_move_to_current_waypoint()
    child = root.sub_orders[0]
    assert issue(game, player, Command("append_patrol_waypoints", (unit.id,), order_id=root.public_id, waypoints=(waypoint(800),))).accepted
    assert root.current_waypoint_index == 2 and root.sub_orders[0] is child


def test_completed_colonist_load_is_not_refunded_by_stop():
    from entities import Planet
    from constants import PlanetType
    from unit_components import ColonyComponent
    game, player, _, unit = world()
    other = create_combat_ship(game.galaxy, player, "Other", (0, 0))
    for ship in (unit, other):
        ship.add_component(ColonyComponent(ship))
    body = Planet((0, 0), "Sol", next(iter(PlanetType)))
    body.position = Position(0, 0)
    body.owner, body.population = player, 50
    game.galaxy.systems["Sol"].add_celestial_body(body)
    batch = (Command("load_colonists", (unit.id,), target_id=body.id, amount=50),
             Command("cancel_orders", (unit.id,)),
             Command("load_colonists", (other.id,), target_id=body.id, amount=50))
    result = issue(game, player, *batch)
    assert not result.accepted and result.errors[-1].code == "insufficient_population"
    assert body.population == 50 and unit.colony_component.population_cargo == 0
    assert not player.order_history
    assert issue(game, player, *batch[:2]).accepted
    assert body.population == 0 and unit.colony_component.population_cargo == 50
    assert player.order_history[-1]["outcome"] == "completed"


def test_cancelling_queued_colonist_prerequisite_rejects_later_colonization():
    from entities import Moon, Planet
    from constants import PlanetType
    from unit_components import ColonyComponent
    from unit_orders import LoadColonistsOrder
    game, player, _, unit = world()
    unit.add_component(ColonyComponent(unit))
    source = Planet((0, 0), "Sol", next(iter(PlanetType)))
    source.owner, source.population = player, 50
    target = Moon((0, 0), "Sol")
    game.galaxy.systems["Sol"].add_celestial_body(source)
    game.galaxy.systems["Sol"].add_celestial_body(target)
    unit.commander_component.add_order(Order(unit, OrderType.TOGGLE_INHIBITOR))
    load = LoadColonistsOrder(unit, {"target_id": source.id, "amount": 50})
    unit.commander_component.add_order(load)
    result = issue(game, player, Command("cancel_order", (unit.id,), order_id=load.public_id),
                   Command("colonize", (unit.id,), target_id=target.id, queue=True))
    assert not result.accepted and unit.commander_component.orders_queue[0] is load
    assert issue(game, player, Command("colonize", (unit.id,), target_id=target.id, queue=True)).accepted


def test_offline_order_evaluations_and_rejected_plan_recovery():
    from game_ai.adapters.fake import FakePlanningProvider
    from game_ai.evaluation import (order_control_cases, run_evaluation,
                                    colony_opening_gateway_case, compare_gateway_reasoning_efforts)
    plans = [TurnPlan((), CommandBatch(), {}),
             TurnPlan((), CommandBatch((Command("set_stance", (101,), stance="attack_same_sector"),)), {}),
             TurnPlan((), CommandBatch((Command("patrol", (101,), waypoints=(waypoint(), waypoint(700))),)), {})]
    report = run_evaluation(FakePlanningProvider(plans), order_control_cases())
    assert report.pass_rate == 1.0
    rejected = TurnPlan((), CommandBatch((Command("colonize", (101,), target_id=202),)), {})
    repaired = TurnPlan((), CommandBatch((Command("load_colonists", (101,), target_id=201, amount=50),
                                         Command("colonize", (101,), target_id=202, queue=True))), {})
    provider = FakePlanningProvider([rejected, repaired])
    report = compare_gateway_reasoning_efforts(provider, [colony_opening_gateway_case()], efforts=("medium",))["medium"]
    assert report.acceptance_rate == 1.0 and report.scores[0].retries_used == 1
    assert provider.requests[-1].repair_context is not None


def test_luna_and_socket_patrols_have_identical_engine_effects():
    from game_ai.adapters.base import PlanningRequest
    from game_ai.adapters.openai_responses import OpenAIResponsesProvider
    from game_ai.runtime import get_runtime_config
    from game_control_protocol import ControlService
    from player_controller import PlayerController
    game, player, _, unit = world()
    raw = {"type": "patrol", "unit_ids": [unit.id], "waypoints": [waypoint(), waypoint(700)]}
    command = Command.from_dict(raw)
    patch_fields = {name: None for name in ("strategy", "objectives", "commitments", "beliefs", "lessons", "misc")}
    output = TurnPlan((), CommandBatch((command,)), patch_fields).to_dict()
    response = SimpleNamespace(output_text=json.dumps(output), id="fake", usage=None)
    provider = OpenAIResponsesProvider(client=SimpleNamespace(responses=SimpleNamespace(create=lambda **_: response)))
    result = provider.plan_turn(PlanningRequest("campaign", "agent", "AI", 1, {}, {}), get_runtime_config("medium"))
    assert issue(game, player, *result.plan.batch.commands).accepted
    expected = dict(unit.commander_component.current_order.parameters)
    game.game_started, game.current_player, game.campaign_id, game.view_mode = True, player, "campaign", "galaxy"
    player.controller = PlayerController.CODEX
    service = ControlService(game, port=0)
    reply = service._dispatch_or_wait({"protocol_version": 2, "action": "command", "request_id": "socket",
        "turn_token": service._turn_token(player), "commands": [raw]}, Future())
    assert reply["ok"] and unit.commander_component.current_order.parameters == expected
    # A sparse object is valid over the socket but is not strict model output.
    output["commands"] = [raw]
    response.output_text = json.dumps(output)
    from game_ai.adapters.base import PlanningOutputError
    with pytest.raises(PlanningOutputError):
        provider.plan_turn(PlanningRequest("campaign", "agent", "AI", 1, {}, {}), get_runtime_config("medium"))


def test_queued_docking_cancellation_releases_only_its_slot_reservation():
    from constants import HullSize
    from unit_components import HangarComponent
    from unit_orders import DockOrder
    game, player, _, first = world()
    first.hull_size = HullSize.TINY
    second = create_combat_ship(game.galaxy, player, "Second", (0, 0))
    second.hull_size = HullSize.TINY
    carrier = create_combat_ship(game.galaxy, player, "Carrier", (0, 0), pos=(2000, 0))
    carrier.add_component(HangarComponent(carrier, max_slots=1))
    first.commander_component.add_order(Order(first, OrderType.TOGGLE_INHIBITOR))
    dock = DockOrder(first, {"target_carrier_id": carrier.id})
    first.commander_component.add_order(dock)
    command = Command("dock_in_hangar", (second.id,), target_id=carrier.id)
    assert not issue(game, player, command).accepted
    assert issue(game, player, Command("cancel_order", (first.id,), order_id=dock.public_id), command).accepted
    assert first.commander_component.current_order.order_type == OrderType.TOGGLE_INHIBITOR
    assert not carrier.hangar_component.docked_units


def test_queued_construction_cancellation_releases_reservation_without_refund():
    from unit_components.constructor import Constructor
    from unit_orders import ConstructOrder
    game, player, _, unit = world()
    other = create_combat_ship(game.galaxy, player, "Other", (0, 0))
    for ship in (unit, other):
        ship.add_component(Constructor(ship))
        ship.constructor_component.can_build = lambda name: SimpleNamespace(cost_credits=100, time_to_build=5)
    player.credits = 100
    unit.commander_component.add_order(Order(unit, OrderType.TOGGLE_INHIBITOR))
    pending = ConstructOrder(unit, {"unit_template_name": "test", "target_position": Position(500, 0)})
    unit.commander_component.add_order(pending)
    build = Command("construct", (other.id,), template_name="test", position=(500, 0))
    assert not issue(game, player, build).accepted
    assert issue(game, player, Command("cancel_order", (unit.id,), order_id=pending.public_id), build).accepted
    assert player.credits == 0 and other.constructor_component.current_construction_target


def test_unobserved_body_cannot_be_targeted_by_guessed_id():
    from entities import Moon
    from galaxy import StarSystem, Hex
    from unit_components import ColonyComponent
    game, player, _, unit = world()
    remote = StarSystem("Unseen", Position(9000, 9000), radius=3)
    remote.hexes[(0, 0)] = Hex(q=0, r=0, in_system="Unseen")
    game.galaxy.systems["Unseen"] = remote
    body = Moon((0, 0), "Unseen")
    remote.add_celestial_body(body)
    unit.add_component(ColonyComponent(unit))
    unit.colony_component.population_cargo = 10
    assert body.id not in build_observation(game, player)["action_catalogs"]["colonization_target_ids"]
    first = issue(game, player, Command("colonize", (unit.id,), target_id=body.id))
    second = issue(game, player, Command("colonize", (unit.id,), target_id=999999999))
    assert first.errors == second.errors and first.errors[0].code == "target_unavailable"


def test_loading_pending_order_does_not_start_or_record_until_update():
    from unit_components.constructor import Constructor
    from unit_orders import ConstructOrder
    game, player, _, unit = world()
    unit.add_component(Constructor(unit))
    unit.constructor_component.can_build = lambda _: SimpleNamespace(cost_credits=100, time_to_build=5)
    player.credits = 500
    pending = ConstructOrder(unit, {"unit_template_name": "test", "target_position": Position(500, 0)})
    unit.commander_component.restore_explicit_orders(pending, [], game.galaxy)
    assert player.credits == 500 and not player.order_history
    unit.commander_component.update()
    assert player.credits == 400 and unit.constructor_component.current_construction_target
