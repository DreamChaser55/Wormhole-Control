import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from game_ai.adapters.base import (
    PlanningOutputError,
    PlanningRequest,
    PlanningResult,
    RepairContext,
    RepairIssue,
)
from game_ai.adapters.fake import FakePlanningProvider
from game_ai.adapters.openai_responses import OpenAIResponsesProvider
from game_ai.commands import CommandError, CommandGateway, CommandResult
from game_ai.coordinator import AgentTurnCoordinator
from game_ai.contracts import Command, CommandBatch, ContractError, TurnPlan
from game_ai.evaluation import (
    EvaluationCase,
    colony_opening_case,
    colony_opening_gateway_case,
    compare_gateway_reasoning_efforts,
    compare_reasoning_efforts,
    inhibitor_overlap_case,
    run_evaluation,
    score_plan,
)
from game_ai.memory import AgentMemory, write_memory_sidecar
from game_ai.observation import build_observation
from game_ai.runtime import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_REPAIR_RETRIES,
    LUNA_MODEL,
    MAX_REPAIR_RETRIES,
    MIN_REPAIR_RETRIES,
    SUPPORTED_REASONING_EFFORTS,
    get_runtime_config,
    normalize_repair_retries,
)


EMPTY_PATCH = {
    "strategy": None,
    "objectives": None,
    "commitments": None,
    "beliefs": None,
    "lessons": None,
    "misc": None,
}


class TestRuntimeConfiguration(unittest.TestCase):
    def test_supported_efforts_share_the_luna_runtime_envelope(self):
        for effort in SUPPORTED_REASONING_EFFORTS:
            runtime_config = get_runtime_config(effort)
            self.assertEqual(runtime_config.model, LUNA_MODEL)
            self.assertEqual(runtime_config.reasoning_effort, effort)
            self.assertEqual(runtime_config.max_output_tokens, 7000)
            self.assertEqual(runtime_config.timeout_seconds, 120.0)
            self.assertEqual(runtime_config.max_commands, 40)

    def test_missing_and_invalid_efforts_default_to_medium(self):
        for effort in (None, "", "unsupported"):
            self.assertEqual(
                get_runtime_config(effort).reasoning_effort,
                DEFAULT_REASONING_EFFORT,
            )

    def test_repair_retries_are_normalized_and_bounded(self):
        self.assertEqual(normalize_repair_retries(None), DEFAULT_REPAIR_RETRIES)
        self.assertEqual(normalize_repair_retries("invalid"), DEFAULT_REPAIR_RETRIES)
        self.assertEqual(normalize_repair_retries(True), DEFAULT_REPAIR_RETRIES)
        self.assertEqual(normalize_repair_retries(-10), MIN_REPAIR_RETRIES)
        self.assertEqual(normalize_repair_retries(99), MAX_REPAIR_RETRIES)
        self.assertEqual(normalize_repair_retries("4"), 4)


class TestContracts(unittest.TestCase):
    def test_turn_plan_round_trip_and_command_limit(self):
        raw = {
            "plan": ["Move the scout."],
            "commands": [
                {
                    "type": "move",
                    "unit_ids": [3],
                    "system_name": "Sol",
                    "hex_coord": [0, 1],
                    "position": [10, 20],
                }
            ],
            "memory_patch": EMPTY_PATCH,
            "end_turn": True,
        }
        plan = TurnPlan.from_dict(raw)
        self.assertEqual(plan.batch.commands[0].hex_coord, (0, 1))
        self.assertTrue(plan.batch.end_turn)
        with self.assertRaises(ContractError):
            TurnPlan.from_dict({**raw, "commands": raw["commands"] * 2}, max_commands=1)

    def test_unknown_command_is_rejected(self):
        with self.assertRaises(ContractError):
            Command.from_dict({"type": "teleport", "unit_ids": [1]})

    def test_defend_and_precision_attack_contracts_roundtrip(self):
        raw = {
            "plan": ["Defend post and snipe engines."],
            "commands": [
                {
                    "type": "attack",
                    "unit_ids": [1],
                    "target_id": 2,
                    "target_component": "Engines",
                },
                {
                    "type": "defend",
                    "unit_ids": [1],
                    "system_name": "Sol",
                    "hex_coord": [0, 0],
                    "position": [100.0, 200.0],
                },
            ],
            "memory_patch": EMPTY_PATCH,
            "end_turn": True,
        }
        plan = TurnPlan.from_dict(raw)
        self.assertEqual(plan.batch.commands[0].target_component, "Engines")
        self.assertEqual(plan.batch.commands[1].type, "defend")
        self.assertEqual(plan.batch.commands[1].position, (100.0, 200.0))
        serialized = plan.to_dict()
        self.assertEqual(serialized["commands"][0]["target_component"], "Engines")
        self.assertEqual(serialized["commands"][1]["type"], "defend")

    def test_planning_request_serializes_repair_context_separately(self):
        plan = TurnPlan((), CommandBatch((), True), EMPTY_PATCH)
        request = PlanningRequest(
            "campaign",
            "agent",
            "AI",
            1,
            {"schema_version": 2},
            {},
            RepairContext(plan, (RepairIssue(0, "invalid", "Fix command 0."),)),
        )
        payload = request.to_dict()
        self.assertEqual(payload["observation"], {"schema_version": 2})
        self.assertEqual(payload["repair_context"]["rejected_plan"], plan.to_dict())
        self.assertEqual(
            payload["repair_context"]["validation_errors"][0]["command_index"],
            0,
        )


class TestMemory(unittest.TestCase):
    def test_memory_is_bounded_and_sidecar_is_derived(self):
        memory = AgentMemory()
        memory.apply_patch(
            {
                "strategy": "Expand",
                "objectives": [f"Objective {index}" for index in range(20)],
                "misc": [f"Misc Note {index}" for index in range(20)],
            },
            turn=4,
        )
        memory.add_receipt("Scout moved.", turn=4)
        self.assertEqual(len(memory.objectives), 12)
        self.assertEqual(len(memory.misc), 16)
        with tempfile.TemporaryDirectory() as directory:
            path = write_memory_sidecar(
                Path(directory),
                campaign_id="campaign",
                agent_id="agent",
                player_name="AI",
                memory=memory,
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("# AI — Agent Memory", text)
            self.assertIn("## Misc\n\n- Misc Note 0", text)
            self.assertIn("- Turn 4:\n  - Scout moved.", text)

    def test_memory_misc_field_roundtrip_and_defaults(self):
        memory = AgentMemory()
        self.assertEqual(memory.misc, [])
        markdown = memory.to_markdown(
            player_name="AI", campaign_id="camp", agent_id="ag"
        )
        self.assertIn("## Misc\n\n- None recorded.", markdown)

        memory.apply_patch({"misc": ["Important reminder.", "Enemy spotted."]}, turn=2)
        self.assertEqual(memory.misc, ["Important reminder.", "Enemy spotted."])
        serialized = memory.to_dict()
        self.assertEqual(serialized["misc"], ["Important reminder.", "Enemy spotted."])

        restored = AgentMemory.from_dict(serialized)
        self.assertEqual(restored.misc, ["Important reminder.", "Enemy spotted."])

    def test_receipts_markdown_formatting_multiline(self):
        memory = AgentMemory()
        memory.add_receipt("Move Scout.; Colonize Planet 1.; Build Ship.", turn=1)
        memory.add_receipt("No commands issued.", turn=2)
        memory.add_receipt("Attack Enemy A.; Defend Base.", turn=3)

        markdown = memory.to_markdown(
            player_name="Player 2",
            campaign_id="test-campaign",
            agent_id="test-agent",
        )

        expected_receipts_block = (
            "## Recent receipts\n\n"
            "- Turn 1:\n"
            "  - Move Scout.\n"
            "  - Colonize Planet 1.\n"
            "  - Build Ship.\n"
            "- Turn 2:\n"
            "  - No commands issued.\n"
            "- Turn 3:\n"
            "  - Attack Enemy A.\n"
            "  - Defend Base."
        )
        self.assertIn(expected_receipts_block, markdown)

    def test_receipts_markdown_empty_and_fallback(self):
        memory = AgentMemory()
        markdown = memory.to_markdown(
            player_name="Player 2",
            campaign_id="test-campaign",
            agent_id="test-agent",
        )
        self.assertIn("## Recent receipts\n\n- None recorded.", markdown)

        memory.receipts = ["Direct Action 1; Direct Action 2"]
        markdown_custom = memory.to_markdown(
            player_name="Player 2",
            campaign_id="test-campaign",
            agent_id="test-agent",
        )
        self.assertIn("## Recent receipts\n\n- Direct Action 1\n- Direct Action 2", markdown_custom)

    def test_player_identity_reasoning_and_memory_survive_save_round_trip(self):
        import builtins
        import typing

        builtins.typing = typing
        from entities import Player
        from save_manager import deserialize_player, serialize_player

        player = Player(
            "Luna High",
            (12, 34, 56),
            is_human=False,
            persistent_id="player-stable",
            agent_id="agent-stable",
            ai_reasoning_effort="high",
            ai_repair_retries=4,
            ai_memory={"strategy": "Hold Sol."},
        )
        restored = deserialize_player(serialize_player(player))
        self.assertEqual(restored.persistent_id, "player-stable")
        self.assertEqual(restored.agent_id, "agent-stable")
        self.assertEqual(restored.ai_reasoning_effort, "high")
        self.assertEqual(restored.ai_repair_retries, 4)
        self.assertEqual(restored.ai_memory["strategy"], "Hold Sol.")
        serialized = serialize_player(player)
        self.assertEqual(serialized["ai_reasoning_effort"], "high")
        self.assertEqual(serialized["ai_repair_retries"], 4)
        self.assertNotIn("ai_profile", serialized)

    def test_player_deserialization_reasoning_effort_normalization(self):
        import builtins
        import typing

        builtins.typing = typing
        from save_manager import deserialize_player

        for raw_effort, expected_effort in (
            ("low", "low"),
            ("LOW", "low"),
            ("medium", "medium"),
            ("high", "high"),
            ("HIGH", "high"),
            ("fast", "medium"),
            ("balanced", "medium"),
            ("strategic", "medium"),
            ("unknown", "medium"),
            ("max", "medium"),
            (None, "medium"),
        ):
            data = {"name": "AI Player", "is_human": False}
            if raw_effort is not None:
                data["ai_reasoning_effort"] = raw_effort
            restored = deserialize_player(data)
            self.assertEqual(
                restored.ai_reasoning_effort,
                expected_effort,
            )

    def test_legacy_and_invalid_repair_retry_values_are_normalized(self):
        import builtins
        import typing

        builtins.typing = typing
        from save_manager import deserialize_player

        self.assertEqual(
            deserialize_player({"name": "Legacy AI"}).ai_repair_retries,
            DEFAULT_REPAIR_RETRIES,
        )
        self.assertEqual(
            deserialize_player({"ai_repair_retries": 0}).ai_repair_retries,
            MIN_REPAIR_RETRIES,
        )
        self.assertEqual(
            deserialize_player({"ai_repair_retries": 100}).ai_repair_retries,
            MAX_REPAIR_RETRIES,
        )
        self.assertEqual(
            deserialize_player({"ai_repair_retries": "bad"}).ai_repair_retries,
            DEFAULT_REPAIR_RETRIES,
        )

    def test_game_state_uses_save_version_2_2(self):
        import builtins
        import typing

        builtins.typing = typing
        from save_manager import serialize_game_state

        game = SimpleNamespace(
            players=[],
            galaxy=None,
            turn_number=1,
            current_player_index=0,
            view_mode="galaxy",
            current_system_name=None,
            current_sector_coord=None,
            campaign_id="campaign",
        )
        self.assertEqual(serialize_game_state(game)["version"], "2.2")


class _FakeResponses:
    def __init__(self, output):
        self.output = output
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            id="response-1",
            output_text=json.dumps(self.output),
            usage=SimpleNamespace(input_tokens=12, output_tokens=8, total_tokens=20),
        )


class TestOpenAIAdapter(unittest.TestCase):
    def test_responses_adapter_uses_strict_stateless_output(self):
        output = {
            "plan": [],
            "commands": [],
            "memory_patch": EMPTY_PATCH,
            "end_turn": True,
        }
        responses = _FakeResponses(output)
        client = SimpleNamespace(responses=responses)
        provider = OpenAIResponsesProvider(client=client)
        request = PlanningRequest("campaign", "agent", "AI", 1, {}, {})
        result = provider.plan_turn(request, get_runtime_config("high"))
        self.assertEqual(result.response_id, "response-1")
        self.assertFalse(responses.kwargs["store"])
        self.assertTrue(responses.kwargs["text"]["format"]["strict"])
        self.assertEqual(responses.kwargs["model"], "gpt-5.6-luna")
        self.assertEqual(responses.kwargs["reasoning"], {"effort": "high"})
        self.assertEqual(result.reasoning_effort, "high")
        self.assertNotIn("tools", responses.kwargs)
        self.assertEqual(responses.kwargs["prompt_cache_key"], "wormhole-control-turn-v2")
        self.assertNotIn("previous_response_id", responses.kwargs)

    def test_responses_adapter_classifies_invalid_output_as_repairable(self):
        responses = _FakeResponses(None)
        provider = OpenAIResponsesProvider(
            client=SimpleNamespace(responses=responses)
        )
        with self.assertRaises(PlanningOutputError) as caught:
            provider.plan_turn(
                PlanningRequest("campaign", "agent", "AI", 1, {}, {}),
                get_runtime_config("low"),
            )
        self.assertEqual(caught.exception.code, "invalid_contract")
        self.assertEqual(caught.exception.reasoning_effort, "low")


class _Player:
    def __init__(self, player_id, team_id):
        self.id = player_id
        self.name = f"P{player_id}"
        self.team_id = team_id
        self.credits = self.metal = self.crystal = 10

    def is_allied_with(self, other):
        return other is not None and self.team_id == other.team_id


class _Commander:
    def __init__(self):
        self.current_order = None
        self.orders_queue = []
        self.stance = SimpleNamespace(value="do_nothing")
        self.clear_count = 0

    def clear_orders(self):
        self.clear_count += 1
        self.current_order = None
        self.orders_queue.clear()

    def add_order(self, order):
        self.orders_queue.append(order)

    def get_allowed_stances(self):
        return []


def _unit(unit_id, owner):
    return SimpleNamespace(
        id=unit_id,
        name=f"U{unit_id}",
        owner=owner,
        in_system="Sol",
        in_hex=(0, 0),
        position=SimpleNamespace(x=0, y=0),
        hull_size=SimpleNamespace(value="small"),
        current_hit_points=10,
        max_hit_points=10,
        is_disabled=False,
        components={},
        antimatter_component=None,
        commander_component=_Commander(),
        engines_component=None,
        weapons_component=None,
        colony_component=None,
        constructor_component=None,
        repair_component=None,
        mining_component=None,
        harvester_component=None,
        hangar_component=None,
        strikecraft_bay_component=None,
        trade_component=None,
        inhibitor_component=None,
        cloaking_component=None,
        ability_component=None,
    )


class TestInformationBoundaryAndGateway(unittest.TestCase):
    @staticmethod
    def _colony_fixture(*, population=50, unit_count=1):
        from entities import Moon, Planet, PlanetType

        player = _Player(1, 1)
        units = [_unit(10 + index, player) for index in range(unit_count)]
        for unit in units:
            unit.colony_component = SimpleNamespace(
                population_cargo=0,
                max_cargo=100,
            )
        source = Planet((0, 0), "Sol", next(iter(PlanetType)))
        source.owner = player
        source.population = population
        target = Moon((1, 0), "Sol")
        bodies = {source.id: source, target.id: target}

        class Galaxy:
            systems = {}

            def __init__(self):
                self.bodies = bodies

            def get_unit_by_id(self, unit_id):
                return next((unit for unit in units if unit.id == unit_id), None)

            def get_celestial_body_by_id(self, body_id):
                return self.bodies.get(body_id)

        game = SimpleNamespace(
            galaxy=Galaxy(),
            sidebar_needs_update=False,
            visibility_dirty=False,
        )
        return player, units, source, target, game

    @staticmethod
    def _inhibitor_fixture(
        *, positions=((0, 0),), active_ids=(), static_zones=()
    ):
        from geometry import Circle, Position
        from unit_components import HyperspaceInhibitionFieldEmitter

        player = _Player(1, 1)
        units = [_unit(10 + index, player) for index in range(len(positions))]
        for unit, position in zip(units, positions):
            unit.position = Position(*position)
            component = HyperspaceInhibitionFieldEmitter(unit, radius=100.0)
            unit.inhibitor_component = component
            unit.components = {HyperspaceInhibitionFieldEmitter: component}

        hex_obj = SimpleNamespace(
            boundary_circle=Circle(Position(0, 0), 500.0),
            static_inhibition_zones=list(static_zones),
            dynamic_inhibition_zones={},
            celestial_bodies=[],
            units=units,
            minefields=[],
        )
        hex_obj.get_all_inhibition_zones = lambda: (
            hex_obj.static_inhibition_zones
            + list(hex_obj.dynamic_inhibition_zones.values())
        )
        for unit in units:
            if unit.id in active_ids:
                unit.inhibitor_component.turn_on()
                hex_obj.dynamic_inhibition_zones[unit.id] = Circle(
                    unit.position, unit.inhibitor_component.radius
                )

        system = SimpleNamespace(
            position=Position(0, 0),
            radius=1,
            hexes={(0, 0): hex_obj},
        )

        class Galaxy:
            systems = {"Sol": system}
            system_graph = {"Sol": {}}

            @staticmethod
            def get_unit_by_id(unit_id):
                return next((unit for unit in units if unit.id == unit_id), None)

            @staticmethod
            def get_celestial_body_by_id(_body_id):
                return None

        game = SimpleNamespace(
            galaxy=Galaxy(),
            players=[player],
            turn_number=3,
            sidebar_needs_update=False,
            visibility_dirty=False,
        )
        return player, units, hex_obj, game

    def test_hidden_enemy_is_omitted_but_presence_is_retained(self):
        viewer = _Player(1, 1)
        enemy = _Player(2, 2)
        own_unit = _unit(10, viewer)
        hidden_unit = _unit(20, enemy)
        hex_obj = SimpleNamespace(
            celestial_bodies=[], units=[own_unit, hidden_unit], minefields=[]
        )
        system = SimpleNamespace(
            position=SimpleNamespace(x=1, y=2),
            radius=2,
            hexes={(0, 0): hex_obj},
        )
        galaxy = SimpleNamespace(systems={"Sol": system}, system_graph={"Sol": {}})
        game = SimpleNamespace(
            galaxy=galaxy,
            players=[viewer, enemy],
            turn_number=1,
        )
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(),
            presence_hexes={("Sol", (0, 0))},
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, viewer)
        self.assertEqual([unit["id"] for unit in observation["units"]], [10])
        self.assertEqual(
            observation["undetailed_enemy_presence"],
            [{"system_name": "Sol", "hex_coord": [0, 0]}],
        )

    def test_batch_preflight_is_all_or_nothing(self):
        player = _Player(1, 1)
        unit = _unit(10, player)

        class Galaxy:
            def get_unit_by_id(self, unit_id):
                return unit if unit_id == 10 else None

        game = SimpleNamespace(galaxy=Galaxy(), sidebar_needs_update=False)
        batch = CommandBatch(
            commands=(
                Command(type="cancel_orders", unit_ids=(10,)),
                Command(type="cancel_orders", unit_ids=(999,)),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch)
        self.assertFalse(result.accepted)
        self.assertEqual(unit.commander_component.clear_count, 0)

    def test_blocked_inhibitor_is_not_advertised_as_legal(self):
        from geometry import Circle, Position

        player, units, _hex_obj, game = self._inhibitor_fixture(
            static_zones=(Circle(Position(0, 0), 50.0),)
        )
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(),
            presence_hexes=set(),
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, player)

        unit_view = observation["units"][0]
        inhibitor = unit_view["capability_details"]["inhibitor"]
        self.assertEqual(observation["schema_version"], 3)
        self.assertIn("toggle_inhibitor", unit_view["supported_commands"])
        self.assertNotIn("toggle_inhibitor", unit_view["legal_commands"])
        self.assertFalse(inhibitor["can_activate"])
        self.assertEqual(inhibitor["activation_blocker"], "inhibitor_overlap")
        self.assertEqual(
            unit_view["command_options"]["toggle_inhibitor"],
            {
                "current_state": "inactive",
                "resulting_state": "active",
                "available": False,
                "unavailable_reason": "inhibitor_overlap",
            },
        )

    def test_active_inhibitor_advertises_legal_deactivation(self):
        player, units, _hex_obj, game = self._inhibitor_fixture(active_ids=(10,))
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(),
            presence_hexes=set(),
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, player)

        unit_view = observation["units"][0]
        inhibitor = unit_view["capability_details"]["inhibitor"]
        self.assertIn("toggle_inhibitor", unit_view["legal_commands"])
        self.assertTrue(inhibitor["is_active"])
        self.assertFalse(inhibitor["can_activate"])
        self.assertIsNone(inhibitor["activation_blocker"])
        self.assertEqual(
            unit_view["command_options"]["toggle_inhibitor"]["resulting_state"],
            "inactive",
        )

    def test_inhibitor_overlap_is_retryable_preflight_rejection(self):
        from geometry import Circle, Position

        player, units, _hex_obj, game = self._inhibitor_fixture(
            static_zones=(Circle(Position(0, 0), 50.0),)
        )
        result = CommandGateway(game).apply_batch(
            player,
            CommandBatch(
                commands=(
                    Command(type="cancel_orders", unit_ids=(units[0].id,)),
                    Command(type="toggle_inhibitor", unit_ids=(units[0].id,)),
                )
            ),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.failure_stage, "preflight")
        self.assertTrue(result.retryable)
        self.assertEqual(result.errors[0].command_index, 1)
        self.assertEqual(result.errors[0].code, "inhibitor_overlap")
        self.assertEqual(units[0].commander_component.clear_count, 0)
        self.assertFalse(units[0].inhibitor_component.is_active)

    def test_projected_inhibitor_activations_cannot_overlap(self):
        player, units, _hex_obj, game = self._inhibitor_fixture(
            positions=((0, 0), (150, 0))
        )
        result = CommandGateway(game).apply_batch(
            player,
            CommandBatch(
                commands=(
                    Command(type="toggle_inhibitor", unit_ids=(units[0].id,)),
                    Command(type="toggle_inhibitor", unit_ids=(units[1].id,)),
                )
            ),
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.errors[0].command_index, 1)
        self.assertEqual(result.errors[0].code, "inhibitor_overlap")
        self.assertTrue(all(not unit.inhibitor_component.is_active for unit in units))

    def test_projected_deactivation_can_enable_later_activation(self):
        player, units, hex_obj, game = self._inhibitor_fixture(
            positions=((0, 0), (0, 0)), active_ids=(10,)
        )
        result = CommandGateway(game).apply_batch(
            player,
            CommandBatch(
                commands=(
                    Command(type="toggle_inhibitor", unit_ids=(units[0].id,)),
                    Command(type="toggle_inhibitor", unit_ids=(units[1].id,)),
                )
            ),
        )

        self.assertTrue(result.accepted)
        self.assertFalse(units[0].inhibitor_component.is_active)
        self.assertTrue(units[1].inhibitor_component.is_active)
        self.assertNotIn(units[0].id, hex_obj.dynamic_inhibition_zones)
        self.assertIn(units[1].id, hex_obj.dynamic_inhibition_zones)
        self.assertEqual(
            result.receipts,
            (
                "Deactivated inhibitor on U10.",
                "Activated inhibitor on U11.",
            ),
        )

    def test_colonist_load_can_feed_a_queued_colonize_command(self):
        player, units, source, target, game = self._colony_fixture()
        batch = CommandBatch(
            commands=(
                Command(
                    type="load_colonists",
                    unit_ids=(units[0].id,),
                    target_id=source.id,
                    amount=50,
                    queue=False,
                ),
                Command(
                    type="colonize",
                    unit_ids=(units[0].id,),
                    target_id=target.id,
                    queue=True,
                ),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch)
        self.assertTrue(result.accepted)
        self.assertEqual(result.applied_count, 2)
        self.assertEqual(len(units[0].commander_component.orders_queue), 2)

    def test_existing_queued_load_can_feed_colonization(self):
        player, units, source, target, game = self._colony_fixture()
        units[0].commander_component.current_order = SimpleNamespace(
            order_type=SimpleNamespace(name="LOAD_COLONISTS"),
            status=SimpleNamespace(name="IN_PROGRESS"),
            parameters={"target_id": source.id, "amount": 40},
        )
        result = CommandGateway(game).apply_batch(
            player,
            CommandBatch(
                commands=(
                    Command(
                        type="colonize",
                        unit_ids=(units[0].id,),
                        target_id=target.id,
                        queue=True,
                    ),
                )
            ),
        )
        self.assertTrue(result.accepted)

    def test_cancellation_releases_projected_population_reservation(self):
        player, units, source, _target, game = self._colony_fixture(unit_count=2)
        batch = CommandBatch(
            commands=(
                Command(
                    type="load_colonists",
                    unit_ids=(units[0].id,),
                    target_id=source.id,
                    amount=50,
                    queue=False,
                ),
                Command(type="cancel_orders", unit_ids=(units[0].id,)),
                Command(
                    type="load_colonists",
                    unit_ids=(units[1].id,),
                    target_id=source.id,
                    amount=50,
                    queue=True,
                ),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch)
        self.assertTrue(result.accepted)
        self.assertEqual(result.applied_count, 3)

    def test_colonize_without_cargo_or_preserved_load_is_rejected_atomically(self):
        player, units, source, target, game = self._colony_fixture()
        batch = CommandBatch(
            commands=(
                Command(
                    type="load_colonists",
                    unit_ids=(units[0].id,),
                    target_id=source.id,
                    amount=50,
                    queue=False,
                ),
                Command(
                    type="colonize",
                    unit_ids=(units[0].id,),
                    target_id=target.id,
                    queue=False,
                ),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch)
        self.assertFalse(result.accepted)
        self.assertEqual(units[0].commander_component.clear_count, 0)
        self.assertIn("queue=true", result.errors[0].message)

    def test_colonist_population_is_reserved_across_multi_unit_command(self):
        player, units, source, _target, game = self._colony_fixture(
            population=50, unit_count=2
        )
        batch = CommandBatch(
            commands=(
                Command(
                    type="load_colonists",
                    unit_ids=tuple(unit.id for unit in units),
                    target_id=source.id,
                    amount=30,
                ),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch)
        self.assertFalse(result.accepted)
        self.assertEqual(result.errors[0].code, "insufficient_population")
        self.assertTrue(all(unit.commander_component.clear_count == 0 for unit in units))

    def test_construction_credits_are_reserved_across_a_batch(self):
        player = _Player(1, 1)
        unit = _unit(10, player)
        buildable = SimpleNamespace(
            unit_template_name="SCOUT",
            cost_credits=6,
            time_to_build=1,
        )
        unit.constructor_component = SimpleNamespace(
            can_build=lambda name: buildable if name == "SCOUT" else None,
            buildable_units=[buildable],
        )

        class Galaxy:
            def get_unit_by_id(self, unit_id):
                return unit if unit_id == unit.id else None

        game = SimpleNamespace(galaxy=Galaxy(), sidebar_needs_update=False)
        command = Command(
            type="construct",
            unit_ids=(unit.id,),
            position=(0, 0),
            template_name="SCOUT",
            queue=True,
        )
        result = CommandGateway(game).apply_batch(
            player, CommandBatch(commands=(command, command))
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.errors[0].code, "insufficient_resources")
        self.assertEqual(unit.commander_component.clear_count, 0)

    def test_colony_sources_targets_and_capacity_are_validated_before_commit(self):
        from entities import Star, StarType

        def assert_rejected(configure, make_command, expected_code):
            player, units, source, target, game = self._colony_fixture()
            configure(player, units[0], source, target, game)
            command = make_command(units[0], source, target, game)
            result = CommandGateway(game).apply_batch(
                player, CommandBatch(commands=(command,))
            )
            self.assertFalse(result.accepted)
            self.assertEqual(result.errors[0].code, expected_code)
            self.assertEqual(units[0].commander_component.clear_count, 0)

        assert_rejected(
            lambda _player, _unit, source, _target, _game: setattr(
                source, "owner", _Player(2, 1)
            ),
            lambda unit, source, _target, _game: Command(
                type="load_colonists",
                unit_ids=(unit.id,),
                target_id=source.id,
                amount=10,
            ),
            "invalid_relation",
        )
        assert_rejected(
            lambda _player, unit, _source, _target, _game: setattr(
                unit.colony_component, "max_cargo", 5
            ),
            lambda unit, source, _target, _game: Command(
                type="load_colonists",
                unit_ids=(unit.id,),
                target_id=source.id,
                amount=10,
            ),
            "insufficient_capacity",
        )

        def add_star(_player, _unit, _source, _target, game):
            star = Star("Sol", next(iter(StarType)))
            game.galaxy.bodies[star.id] = star
            game.invalid_star = star

        assert_rejected(
            add_star,
            lambda unit, _source, _target, game: Command(
                type="load_colonists",
                unit_ids=(unit.id,),
                target_id=game.invalid_star.id,
                amount=10,
            ),
            "invalid_target",
        )
        assert_rejected(
            add_star,
            lambda unit, _source, _target, game: Command(
                type="colonize",
                unit_ids=(unit.id,),
                target_id=game.invalid_star.id,
            ),
            "invalid_target",
        )

    def test_observation_reports_colony_legality_and_capacity(self):
        player, units, source, target, game = self._colony_fixture()
        hex_obj = SimpleNamespace(
            celestial_bodies=[source, target], units=units, minefields=[]
        )
        system = SimpleNamespace(
            position=SimpleNamespace(x=1, y=2),
            radius=2,
            hexes={(0, 0): hex_obj},
        )
        game.galaxy.systems = {"Sol": system}
        game.galaxy.system_graph = {"Sol": {}}
        game.players = [player]
        game.turn_number = 1
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(),
            presence_hexes=set(),
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, player)
        unit_view = observation["units"][0]
        self.assertEqual(observation["schema_version"], 3)
        self.assertNotIn("celestial_bodies", observation)
        self.assertIn("colonize", unit_view["supported_commands"])
        self.assertNotIn("colonize", unit_view["legal_commands"])
        self.assertIn("load_colonists", unit_view["legal_commands"])
        self.assertEqual(
            unit_view["capability_details"]["colony"]["maximum_cargo"],
            100.0,
        )
        self.assertEqual(unit_view["command_options"]["colonize"]["target_ids"], [target.id])
        self.assertEqual(unit_view["conditional_commands"][0]["type"], "colonize")

    def test_hybrid_observation_summarizes_remote_neutral_bodies(self):
        from entities import Moon, Planet, PlanetType, Star, StarType

        player = _Player(1, 1)
        unit = _unit(10, player)
        planet_type = next(iter(PlanetType))
        star_type = next(iter(StarType))

        def make_system(name, bodies, units=()):
            return SimpleNamespace(
                position=SimpleNamespace(x=0, y=0),
                radius=4,
                hexes={
                    (0, 0): SimpleNamespace(
                        celestial_bodies=bodies,
                        units=list(units),
                        minefields=[],
                    )
                },
            )

        sol_star = Star("Sol", star_type)
        sol_target = Moon((0, 0), "Sol")
        vega_star = Star("Vega", star_type)
        vega_target = Planet((0, 0), "Vega", planet_type)
        sirius_star = Star("Sirius", star_type)
        remote_neutral = Planet((0, 0), "Sirius", planet_type)
        remote_colony = Planet((0, 0), "Sirius", planet_type)
        remote_colony.owner = player
        remote_colony.population = 20
        galaxy = SimpleNamespace(
            systems={
                "Sol": make_system("Sol", [sol_star, sol_target], [unit]),
                "Vega": make_system("Vega", [vega_star, vega_target]),
                "Sirius": make_system(
                    "Sirius", [sirius_star, remote_neutral, remote_colony]
                ),
            },
            system_graph={
                "Sol": {"Vega": SimpleNamespace(value="huge")},
                "Vega": {"Sol": SimpleNamespace(value="huge")},
                "Sirius": {},
            },
        )
        game = SimpleNamespace(galaxy=galaxy, players=[player], turn_number=1)
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(), presence_hexes=set()
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, player)

        systems = {system["name"]: system for system in observation["systems"]}
        self.assertEqual(systems["Sol"]["detail_level"], "full")
        self.assertEqual(systems["Vega"]["detail_level"], "full")
        self.assertEqual(systems["Sirius"]["detail_level"], "summary")
        notable_ids = {body["id"] for body in systems["Sirius"]["notable_bodies"]}
        self.assertIn(sirius_star.id, notable_ids)
        self.assertIn(remote_colony.id, notable_ids)
        self.assertNotIn(remote_neutral.id, notable_ids)
        self.assertEqual(
            systems["Sirius"]["body_summary"]["neutral_colonizable_count"], 1
        )
        self.assertNotIn(
            remote_neutral.id,
            observation["action_catalogs"]["colonization_target_ids"],
        )

    def test_large_hybrid_observation_stays_below_character_budget(self):
        from entities import Planet, PlanetType, Star, StarType

        player = _Player(1, 1)
        unit = _unit(10, player)
        planet_type = next(iter(PlanetType))
        star_type = next(iter(StarType))
        systems = {}
        graph = {}
        remaining_planets = 785
        for index in range(15):
            name = f"System {index}"
            count = remaining_planets // (15 - index)
            remaining_planets -= count
            bodies = [Star(name, star_type)] + [
                Planet((0, 0), name, planet_type) for _ in range(count)
            ]
            systems[name] = SimpleNamespace(
                position=SimpleNamespace(x=index, y=0),
                radius=4,
                hexes={
                    (0, 0): SimpleNamespace(
                        celestial_bodies=bodies,
                        units=[unit] if index == 0 else [],
                        minefields=[],
                    )
                },
            )
            graph[name] = {}
        graph["System 0"]["System 1"] = SimpleNamespace(value="huge")
        graph["System 1"]["System 0"] = SimpleNamespace(value="huge")
        galaxy = SimpleNamespace(systems=systems, system_graph=graph)
        game = SimpleNamespace(galaxy=galaxy, players=[player], turn_number=1)
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids=set(), presence_hexes=set()
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            observation = build_observation(game, player)
        payload = json.dumps(
            PlanningRequest("campaign", "agent", "AI", 1, observation, {}).to_dict(),
            separators=(",", ":"),
        )
        self.assertLess(len(payload), 75_000)

    @staticmethod
    def _combat_fixture():
        from geometry import Position
        from unit_components import Engines, Weapons, Hyperdrive, HyperdriveType

        player = _Player(1, 1)
        enemy_player = _Player(2, 2)

        my_unit = _unit(10, player)
        my_unit.engines_component = Engines(my_unit, speed=50.0)
        my_unit.weapons_component = Weapons(my_unit)
        my_unit.components = {
            Engines: my_unit.engines_component,
            Weapons: my_unit.weapons_component,
        }

        enemy_unit = _unit(20, enemy_player)
        enemy_unit.engines_component = Engines(enemy_unit, speed=50.0)
        enemy_unit.weapons_component = Weapons(enemy_unit)
        enemy_unit.hyperdrive_component = Hyperdrive(
            enemy_unit, drive_type=HyperdriveType.BASIC, jump_range=5
        )
        enemy_unit.components = {
            Engines: enemy_unit.engines_component,
            Weapons: enemy_unit.weapons_component,
            Hyperdrive: enemy_unit.hyperdrive_component,
        }

        units = [my_unit, enemy_unit]
        units_by_id = {u.id: u for u in units}

        class Galaxy:
            systems = {
                "Sol": SimpleNamespace(
                    position=Position(0, 0),
                    radius=1,
                    hexes={(0, 0): SimpleNamespace(units=units, celestial_bodies=[])},
                )
            }
            system_graph = {"Sol": {}}

            @staticmethod
            def get_unit_by_id(unit_id):
                return units_by_id.get(unit_id)

            @staticmethod
            def get_celestial_body_by_id(_body_id):
                return None

        game = SimpleNamespace(
            galaxy=Galaxy(),
            players=[player, enemy_player],
            sidebar_needs_update=False,
            visibility_dirty=False,
            turn_number=1,
        )
        return player, enemy_player, my_unit, enemy_unit, game

    def test_attack_with_subsystem_targeting(self):
        player, enemy_player, my_unit, enemy_unit, game = self._combat_fixture()
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids={enemy_unit.id}, presence_hexes=set()
        )
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            batch = CommandBatch(
                commands=(
                    Command(
                        type="attack",
                        unit_ids=(my_unit.id,),
                        target_id=enemy_unit.id,
                        target_component="Engines",
                    ),
                )
            )
            result = CommandGateway(game).apply_batch(player, batch)
            self.assertTrue(result.accepted)
            self.assertEqual(result.receipts, ("Attack U20 (Engines) for U10.",))
            self.assertEqual(len(my_unit.commander_component.orders_queue), 1)
            order = my_unit.commander_component.orders_queue[0]
            self.assertEqual(order.parameters["target_component_type"], "Engines")

        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            batch_alias = CommandBatch(
                commands=(
                    Command(
                        type="attack",
                        unit_ids=(my_unit.id,),
                        target_id=enemy_unit.id,
                        target_component="hyperdrive",
                    ),
                )
            )
            result_alias = CommandGateway(game).apply_batch(player, batch_alias)
            self.assertTrue(result_alias.accepted)
            self.assertEqual(result_alias.receipts, ("Attack U20 (Hyperdrive) for U10.",))

    def test_attack_subsystem_targeting_rejections(self):
        player, enemy_player, my_unit, enemy_unit, game = self._combat_fixture()
        snapshot = SimpleNamespace(
            visible_enemy_unit_ids={enemy_unit.id}, presence_hexes=set()
        )
        # 1. Non-existent component on enemy unit
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            batch_invalid_target = CommandBatch(
                commands=(
                    Command(
                        type="attack",
                        unit_ids=(my_unit.id,),
                        target_id=enemy_unit.id,
                        target_component="ColonyComponent",
                    ),
                )
            )
            result = CommandGateway(game).apply_batch(player, batch_invalid_target)
            self.assertFalse(result.accepted)
            self.assertEqual(result.errors[0].code, "invalid_target")

        # 2. Bogus / unresolvable component name
        with patch("visibility.VisibilityService.compute", return_value=snapshot):
            batch_bogus = CommandBatch(
                commands=(
                    Command(
                        type="attack",
                        unit_ids=(my_unit.id,),
                        target_id=enemy_unit.id,
                        target_component="laser_cannon_mk2",
                    ),
                )
            )
            result = CommandGateway(game).apply_batch(player, batch_bogus)
            self.assertFalse(result.accepted)
            self.assertEqual(result.errors[0].code, "invalid_value")

    def test_defend_command_execution(self):
        player, enemy_player, my_unit, enemy_unit, game = self._combat_fixture()
        # 1. Valid defend command with coordinates
        batch_valid = CommandBatch(
            commands=(
                Command(
                    type="defend",
                    unit_ids=(my_unit.id,),
                    system_name="Sol",
                    hex_coord=(0, 0),
                    position=(50.0, 50.0),
                ),
            )
        )
        result = CommandGateway(game).apply_batch(player, batch_valid)
        self.assertTrue(result.accepted)
        self.assertEqual(result.receipts, ("Defend Sol (0, 0) for U10.",))
        self.assertEqual(len(my_unit.commander_component.orders_queue), 1)

        # 2. Missing coordinate fields
        batch_missing = CommandBatch(
            commands=(
                Command(
                    type="defend",
                    unit_ids=(my_unit.id,),
                    system_name="Sol",
                ),
            )
        )
        result_missing = CommandGateway(game).apply_batch(player, batch_missing)
        self.assertFalse(result_missing.accepted)
        self.assertEqual(result_missing.errors[0].code, "missing_field")

        # 3. Unit without weapons cannot perform defend
        my_unit.weapons_component = None
        result_no_weapons = CommandGateway(game).apply_batch(player, batch_valid)
        self.assertFalse(result_no_weapons.accepted)
        self.assertEqual(result_no_weapons.errors[0].code, "capability_unavailable")


class TestCoordinator(unittest.TestCase):
    @staticmethod
    def _coordinator_fixture(repair_retries, plans):
        player = _Player(1, 1)
        player.is_human = False
        player.agent_id = "agent-1"
        player.ai_reasoning_effort = "medium"
        player.ai_repair_retries = repair_retries
        player.ai_memory = {}
        player.last_ai_report = {}
        ended = []
        game = SimpleNamespace(
            game_started=True,
            campaign_id="campaign-1",
            current_player=player,
            turn_number=3,
            galaxy=SimpleNamespace(),
            gui=None,
            end_turn=lambda: ended.append(True),
        )
        provider = FakePlanningProvider(plans)
        return player, game, ended, provider, AgentTurnCoordinator(
            game, provider=provider
        )

    @staticmethod
    def _finish_pending_request(coordinator):
        coordinator._future.result(timeout=2)
        coordinator.update()

    def test_fake_provider_completes_turn_and_persists_receipt(self):
        player = _Player(1, 1)
        player.is_human = False
        player.agent_id = "agent-1"
        player.ai_reasoning_effort = "low"
        player.ai_memory = {}
        player.last_ai_report = {}
        ended = []
        game = SimpleNamespace(
            game_started=True,
            campaign_id="campaign-1",
            current_player=player,
            turn_number=3,
            galaxy=SimpleNamespace(),
            gui=None,
            end_turn=lambda: ended.append(True),
        )
        plan = TurnPlan(("Consolidate.",), CommandBatch((), True), EMPTY_PATCH)
        provider = FakePlanningProvider([plan])
        coordinator = AgentTurnCoordinator(game, provider=provider)
        try:
            with patch("game_ai.coordinator.build_observation", return_value={}), patch.object(
                coordinator, "_write_memory"
            ), patch.object(coordinator, "_record_telemetry"):
                self.assertTrue(coordinator.start_current_turn())
                coordinator._future.result(timeout=2)
                coordinator.update()
            self.assertEqual(ended, [True])
            self.assertIn("No commands issued.", player.ai_memory["receipts"][-1])
            self.assertEqual(player.last_ai_report["plan"], ["Consolidate."])
            self.assertEqual(player.last_ai_report["reasoning_effort"], "low")
            self.assertEqual(provider.runtime_configs[0].reasoning_effort, "low")
        finally:
            coordinator.shutdown()

    def test_configured_repairs_forward_latest_errors_and_can_recover(self):
        first_plan = TurnPlan(("First.",), CommandBatch((), True), EMPTY_PATCH)
        second_plan = TurnPlan(("Second.",), CommandBatch((), True), EMPTY_PATCH)
        accepted_plan = TurnPlan(("Recovered.",), CommandBatch((), True), EMPTY_PATCH)
        player, _game, ended, provider, coordinator = self._coordinator_fixture(
            2, [first_plan, second_plan, accepted_plan]
        )
        rejected_first = CommandResult(
            accepted=False,
            errors=(CommandError(0, "first_error", "First rejection"),),
        )
        rejected_second = CommandResult(
            accepted=False,
            errors=(CommandError(1, "second_error", "Second rejection"),),
        )
        accepted = CommandResult(accepted=True)
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch("game_ai.coordinator.CommandGateway") as gateway_class, patch.object(
                coordinator, "_write_memory"
            ), patch.object(coordinator, "_record_telemetry"):
                gateway_class.return_value.apply_batch.side_effect = [
                    rejected_first,
                    rejected_second,
                    accepted,
                ]
                self.assertTrue(coordinator.start_current_turn())
                self.assertEqual(coordinator.status_message, "thinking…")
                self._finish_pending_request(coordinator)
                self.assertEqual(coordinator.status_message, "revising... retry 1/2")
                self._finish_pending_request(coordinator)
                self.assertEqual(coordinator.status_message, "revising... retry 2/2")
                self._finish_pending_request(coordinator)

            self.assertEqual(len(provider.requests), 3)
            self.assertEqual(
                provider.requests[1].repair_context.to_dict()["validation_errors"],
                [{
                    "command_index": 0,
                    "code": "first_error",
                    "message": "First rejection",
                }],
            )
            self.assertEqual(
                provider.requests[1].repair_context.rejected_plan,
                first_plan,
            )
            self.assertEqual(provider.requests[1].observation, {})
            self.assertEqual(
                provider.requests[2].repair_context.to_dict()["validation_errors"],
                [{
                    "command_index": 1,
                    "code": "second_error",
                    "message": "Second rejection",
                }],
            )
            self.assertEqual(
                provider.requests[2].repair_context.rejected_plan,
                second_plan,
            )
            self.assertEqual(ended, [True])
            self.assertEqual(player.last_ai_report["plan"], ["Recovered."])
        finally:
            coordinator.shutdown()

    def test_retry_limit_is_snapshotted_and_exhaustion_returns_manual_control(self):
        plan = TurnPlan(("Invalid.",), CommandBatch((), True), EMPTY_PATCH)
        player, game, ended, provider, coordinator = self._coordinator_fixture(
            1, [plan, plan]
        )

        class Button:
            def __init__(self):
                self.enabled = False

            def enable(self):
                self.enabled = True

            def disable(self):
                self.enabled = False

        dialogs = []
        button = Button()
        game.gui = SimpleNamespace(
            end_turn_button=button,
            show_error_dialog=lambda message, title: dialogs.append((message, title)),
        )
        rejected = CommandResult(
            accepted=False,
            errors=(CommandError(0, "invalid", "Still invalid"),),
        )
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch("game_ai.coordinator.CommandGateway") as gateway_class, patch.object(
                coordinator, "_record_telemetry"
            ):
                gateway_class.return_value.apply_batch.side_effect = [
                    rejected,
                    rejected,
                ]
                self.assertTrue(coordinator.start_current_turn())
                player.ai_repair_retries = 5
                self._finish_pending_request(coordinator)
                self._finish_pending_request(coordinator)

            self.assertEqual(len(provider.requests), 2)
            self.assertEqual(coordinator.state, "error")
            self.assertTrue(button.enabled)
            self.assertEqual(ended, [])
            self.assertEqual(dialogs[0][1], "AI Turn Error")
            self.assertIn("end the turn manually", dialogs[0][0])

            provider._plans.extend([plan])
            with patch("game_ai.coordinator.build_observation", return_value={}):
                self.assertTrue(coordinator.start_current_turn())
            self.assertEqual(coordinator._max_repair_retries, 5)
        finally:
            coordinator.shutdown()

    def test_invalid_model_output_uses_repair_context_and_same_reasoning(self):
        plan = TurnPlan(("Recovered.",), CommandBatch((), True), EMPTY_PATCH)
        player, _game, ended, _provider, coordinator = self._coordinator_fixture(
            1, []
        )

        class Provider:
            def __init__(self):
                self.requests = []
                self.runtime_configs = []

            def plan_turn(self, request, runtime_config):
                self.requests.append(request)
                self.runtime_configs.append(runtime_config)
                if len(self.requests) == 1:
                    raise PlanningOutputError(
                        "invalid_json",
                        "Invalid JSON.",
                        provider="fake",
                        model=runtime_config.model,
                        reasoning_effort=runtime_config.reasoning_effort,
                    )
                return PlanningResult(
                    plan=plan,
                    provider="fake",
                    model=runtime_config.model,
                    reasoning_effort=runtime_config.reasoning_effort,
                )

        provider = Provider()
        coordinator.provider = provider
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={"schema_version": 2}
            ), patch("game_ai.coordinator.CommandGateway") as gateway_class, patch.object(
                coordinator, "_write_memory"
            ), patch.object(coordinator, "_record_output_error"), patch.object(
                coordinator, "_record_telemetry"
            ):
                gateway_class.return_value.apply_batch.return_value = CommandResult(
                    accepted=True
                )
                self.assertTrue(coordinator.start_current_turn())
                coordinator._future.exception(timeout=2)
                coordinator.update()
                self._finish_pending_request(coordinator)

            self.assertEqual(ended, [True])
            self.assertEqual(len(provider.requests), 2)
            repair = provider.requests[1].repair_context
            self.assertIsNone(repair.rejected_plan)
            self.assertEqual(repair.errors[0].code, "invalid_json")
            self.assertEqual(provider.requests[1].observation, {"schema_version": 2})
            self.assertEqual(
                [config.reasoning_effort for config in provider.runtime_configs],
                ["medium", "medium"],
            )
        finally:
            coordinator.shutdown()

    def test_malformed_output_exhausts_exact_semantic_retry_budget(self):
        _player, _game, ended, _provider, coordinator = self._coordinator_fixture(
            1, []
        )

        class InvalidProvider:
            def __init__(self):
                self.requests = []

            def plan_turn(self, request, runtime_config):
                self.requests.append(request)
                raise PlanningOutputError(
                    "invalid_contract",
                    "The turn output violated its contract.",
                    provider="fake",
                    model=runtime_config.model,
                    reasoning_effort=runtime_config.reasoning_effort,
                )

        provider = InvalidProvider()
        coordinator.provider = provider
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch.object(coordinator, "_record_output_error"):
                self.assertTrue(coordinator.start_current_turn())
                coordinator._future.exception(timeout=2)
                coordinator.update()
                coordinator._future.exception(timeout=2)
                coordinator.update()
            self.assertEqual(len(provider.requests), 2)
            self.assertIsNotNone(provider.requests[1].repair_context)
            self.assertEqual(coordinator.state, "error")
            self.assertEqual(ended, [])
        finally:
            coordinator.shutdown()

    def test_transport_failure_does_not_use_semantic_retry(self):
        _player, _game, ended, _provider, coordinator = self._coordinator_fixture(
            3, []
        )

        class TransportProvider:
            def __init__(self):
                self.calls = 0

            def plan_turn(self, request, runtime_config):
                self.calls += 1
                raise TimeoutError("provider timeout")

        provider = TransportProvider()
        coordinator.provider = provider
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch.object(coordinator, "_record_transport_error"):
                self.assertTrue(coordinator.start_current_turn())
                coordinator._future.exception(timeout=2)
                coordinator.update()
            self.assertEqual(provider.calls, 1)
            self.assertEqual(coordinator.state, "error")
            self.assertNotIn("provider timeout", coordinator.last_error)
            self.assertEqual(ended, [])
        finally:
            coordinator.shutdown()

    def test_commit_failure_is_not_retried(self):
        plan = TurnPlan(("Commit.",), CommandBatch((), True), EMPTY_PATCH)
        _player, _game, ended, provider, coordinator = self._coordinator_fixture(
            3, [plan]
        )
        commit_failure = CommandResult(
            accepted=False,
            errors=(CommandError(-1, "commit_failed", "Commit failed"),),
            failure_stage="commit",
            retryable=False,
        )
        try:
            with patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch("game_ai.coordinator.CommandGateway") as gateway_class, patch.object(
                coordinator, "_record_telemetry"
            ):
                gateway_class.return_value.apply_batch.return_value = commit_failure
                self.assertTrue(coordinator.start_current_turn())
                self._finish_pending_request(coordinator)
            self.assertEqual(len(provider.requests), 1)
            self.assertEqual(ended, [])
            self.assertEqual(coordinator.state, "error")
        finally:
            coordinator.shutdown()

    def test_telemetry_records_reasoning_effort(self):
        import save_manager

        player = SimpleNamespace(agent_id="agent-1")
        game = SimpleNamespace(
            campaign_id="campaign-1",
            current_player=player,
            turn_number=4,
        )
        plan = TurnPlan(("Wait.",), CommandBatch((), True), EMPTY_PATCH)
        result = PlanningResult(
            plan=plan,
            provider="fake",
            model="gpt-5.6-luna",
            reasoning_effort="high",
        )
        coordinator = AgentTurnCoordinator(
            game,
            provider=FakePlanningProvider([]),
        )
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(
                save_manager, "SAVES_DIR", directory
            ):
                coordinator._record_telemetry(
                    result,
                    CommandResult(accepted=True),
                    status="accepted",
                )
                record = json.loads(
                    (Path(directory) / "ai_telemetry.jsonl").read_text(
                        encoding="utf-8"
                    )
                )
            self.assertEqual(record["model"], "gpt-5.6-luna")
            self.assertEqual(record["reasoning_effort"], "high")
            self.assertEqual(record["attempt_index"], 0)
            self.assertFalse(record["is_repair"])
            self.assertEqual(record["command_summaries"], [])
            self.assertFalse(record["will_retry"])
        finally:
            coordinator.shutdown()

    def test_telemetry_records_every_rejected_and_accepted_attempt(self):
        import save_manager

        command = Command(type="cancel_orders", unit_ids=(1,))
        plan = TurnPlan(
            (), CommandBatch((command,), True), EMPTY_PATCH
        )
        _player, _game, ended, _provider, coordinator = self._coordinator_fixture(
            2, [plan, plan, plan]
        )
        rejected = CommandResult(
            accepted=False,
            errors=(CommandError(0, "invalid", "Try again."),),
        )
        accepted = CommandResult(accepted=True, applied_count=1)
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(
                save_manager, "SAVES_DIR", directory
            ), patch(
                "game_ai.coordinator.build_observation", return_value={}
            ), patch("game_ai.coordinator.CommandGateway") as gateway_class, patch.object(
                coordinator, "_write_memory"
            ):
                gateway_class.return_value.apply_batch.side_effect = [
                    rejected,
                    rejected,
                    accepted,
                ]
                self.assertTrue(coordinator.start_current_turn())
                self._finish_pending_request(coordinator)
                self._finish_pending_request(coordinator)
                self._finish_pending_request(coordinator)
                records = [
                    json.loads(line)
                    for line in (
                        Path(directory) / "ai_telemetry.jsonl"
                    ).read_text(encoding="utf-8").splitlines()
                ]
            self.assertEqual(ended, [True])
            self.assertEqual([record["attempt_index"] for record in records], [0, 1, 2])
            self.assertEqual([record["will_retry"] for record in records], [True, True, False])
            self.assertEqual([record["status"] for record in records], ["rejected", "rejected", "accepted"])
            self.assertEqual(records[0]["command_summaries"][0]["type"], "cancel_orders")
            self.assertEqual(records[0]["error_details"][0]["command_index"], 0)
            self.assertNotIn("plan", records[0])
            self.assertNotIn("observation", records[0])
        finally:
            coordinator.shutdown()


class TestLogging(unittest.TestCase):
    def test_third_party_http_clients_cannot_emit_debug_request_bodies(self):
        import logging

        from game_logging import THIRD_PARTY_LOGGERS, setup_logging

        setup_logging(log_to_file=False)
        for logger_name in THIRD_PARTY_LOGGERS:
            self.assertGreaterEqual(
                logging.getLogger(logger_name).getEffectiveLevel(), logging.WARNING
            )
        record = logging.LogRecord(
            "openai._base_client.responses",
            logging.DEBUG,
            __file__,
            1,
            "request body: secret",
            (),
            None,
        )
        self.assertTrue(
            all(not handler.filter(record) for handler in logging.getLogger().handlers)
        )


class TestEvaluation(unittest.TestCase):
    def test_colony_opening_fixture_and_reasoning_comparison_are_opt_in(self):
        case = colony_opening_case()
        command = Command(
            type="load_colonists",
            unit_ids=(101,),
            target_id=201,
            amount=50,
        )
        plan = TurnPlan(
            ("Load first.",), CommandBatch((command,), True), EMPTY_PATCH
        )
        provider = FakePlanningProvider([plan, plan, plan])
        reports = compare_reasoning_efforts(provider, [case])
        self.assertEqual(set(reports), {"low", "medium", "high"})
        self.assertTrue(all(report.pass_rate == 1.0 for report in reports.values()))
        self.assertEqual(
            [config.reasoning_effort for config in provider.runtime_configs],
            ["low", "medium", "high"],
        )

    def test_inhibitor_overlap_fixture_forbids_invalid_busywork(self):
        case = inhibitor_overlap_case()
        wait_plan = TurnPlan(("Hold position.",), CommandBatch((), True), EMPTY_PATCH)
        invalid_plan = TurnPlan(
            ("Activate defenses.",),
            CommandBatch(
                (Command(type="toggle_inhibitor", unit_ids=(625,)),), True
            ),
            EMPTY_PATCH,
        )

        self.assertTrue(score_plan(case, wait_plan).passed)
        invalid_score = score_plan(case, invalid_plan)
        self.assertFalse(invalid_score.passed)
        self.assertEqual(invalid_score.forbidden_count, 1)

    def test_gateway_reasoning_comparison_tracks_repairs_and_acceptance(self):
        invalid = TurnPlan(
            ("Colonize immediately.",),
            CommandBatch(
                (
                    Command(
                        type="colonize", unit_ids=(101,), target_id=202, queue=True
                    ),
                ),
                True,
            ),
            EMPTY_PATCH,
        )
        repaired = TurnPlan(
            ("Load before colonizing.",),
            CommandBatch(
                (
                    Command(
                        type="load_colonists",
                        unit_ids=(101,),
                        target_id=201,
                        amount=50,
                    ),
                    Command(
                        type="colonize", unit_ids=(101,), target_id=202, queue=True
                    ),
                ),
                True,
            ),
            EMPTY_PATCH,
        )

        class RepairAwareProvider:
            def __init__(self):
                self.requests = []

            def plan_turn(self, request, runtime_config):
                self.requests.append(request)
                plan = repaired if request.repair_context else invalid
                return PlanningResult(
                    plan=plan,
                    provider="fake",
                    model=runtime_config.model,
                    reasoning_effort=runtime_config.reasoning_effort,
                    usage={"input_tokens": 10, "output_tokens": 5},
                    latency_seconds=0.25,
                )

        provider = RepairAwareProvider()
        reports = compare_gateway_reasoning_efforts(
            provider, [colony_opening_gateway_case()]
        )
        for report in reports.values():
            self.assertEqual(report.acceptance_rate, 1.0)
            self.assertEqual(report.scores[0].attempts, 2)
            self.assertEqual(report.scores[0].retries_used, 1)
            self.assertEqual(report.scores[0].input_tokens, 20)
            self.assertEqual(report.scores[0].output_tokens, 10)
            self.assertEqual(report.scores[0].latency_seconds, 0.5)
        self.assertTrue(all(request.repair_context for request in provider.requests[1::2]))

    def test_fixture_score_tracks_required_and_forbidden_commands(self):
        request = PlanningRequest("c", "a", "AI", 1, {}, {})
        case = EvaluationCase(
            "opening",
            request,
            required_command_types=frozenset({"move"}),
            forbidden_command_types=frozenset({"attack"}),
        )
        plan = TurnPlan(
            ("Scout",),
            CommandBatch((Command(type="move", unit_ids=(1,)),), True),
            {},
        )
        score = score_plan(case, plan)
        self.assertTrue(score.passed)
        self.assertEqual(score.required_coverage, 1.0)

    def test_evaluation_reports_effective_reasoning_effort(self):
        request = PlanningRequest("c", "a", "AI", 1, {}, {})
        case = EvaluationCase("wait", request)
        plan = TurnPlan(("Wait",), CommandBatch((), True), EMPTY_PATCH)
        provider = FakePlanningProvider([plan])

        report = run_evaluation(
            provider,
            [case],
            reasoning_effort="invalid",
        )

        self.assertEqual(report.reasoning_effort, "medium")
        self.assertEqual(report.to_dict()["reasoning_effort"], "medium")
        self.assertEqual(provider.runtime_configs[0].model, "gpt-5.6-luna")


if __name__ == "__main__":
    unittest.main()
