"""Offline regressions for the shared Luna/Codex intelligence interface."""

from types import SimpleNamespace

from constants import CI_SWEEP_ANTIMATTER_COST, CI_SWEEP_CREDIT_COST, PlanetType
from entities import Planet, Player, Unit
from game_ai.adapters.base import PlanningResult
from game_ai.command_spec import CONTRACT_VERSION
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch, ContractError, TurnPlan
from game_ai.coordinator import AgentTurnCoordinator
from game_ai.observation import build_observation
from game_control_protocol import ControlService
from geometry import Position
from player_controller import PlayerController
from tests.test_stance_visibility import create_combat_ship, create_test_galaxy
from unit_components import Agent, IntelligenceComponent
from unit_orders import OrderStatus, OrderType


def intelligence_world():
    galaxy, player, enemy = create_test_galaxy()
    game = galaxy.game
    game.players = [player, enemy]
    game.current_player = player
    game.current_player_index = 0
    game.turn_number = 1
    game.sidebar_needs_update = False
    game.visibility_dirty = False

    spy = create_combat_ship(galaxy, player, "Spy", (0, 0), pos=(0, 0))
    spy.add_component(
        IntelligenceComponent(
            spy,
            agents_count=2,
            agents_capacity=2,
            has_counter_intelligence=True,
        )
    )
    enemy_a = create_combat_ship(galaxy, enemy, "Enemy A", (0, 0), pos=(100, 0))
    enemy_b = create_combat_ship(galaxy, enemy, "Enemy B", (0, 0), pos=(300, 0))
    enemy_a.add_component(IntelligenceComponent(enemy_a, agents_count=1, agents_capacity=1))
    return game, player, enemy, spy, enemy_a, enemy_b


def issue(game, player, *commands):
    return CommandGateway(game).apply_batch(player, CommandBatch(tuple(commands), end_turn=False))


def test_contract_v3_intelligence_shapes():
    assert CONTRACT_VERSION == 3
    sabotage = Command.from_dict(
        {
            "type": "sabotage",
            "unit_ids": [],
            "agent_id": 4,
            "sabotage_type": "engines",
        }
    )
    assert sabotage.agent_id == 4 and sabotage.sabotage_type == "engines"
    for raw in (
        {"type": "sabotage", "unit_ids": [1], "agent_id": 4, "sabotage_type": "engines"},
        {"type": "sabotage", "unit_ids": [], "agent_id": 4, "sabotage_type": "economics"},
        {"type": "relocate_agent", "unit_ids": [], "agent_id": 4, "target_id": 5, "queue": True},
        {"type": "extract_agent", "unit_ids": [1, 2], "agent_id": 4},
    ):
        try:
            Command.from_dict(raw)
        except ContractError:
            pass
        else:
            raise AssertionError(f"invalid command accepted: {raw}")


def test_observation_discloses_only_authorized_agent_state():
    game, player, enemy, spy, enemy_a, enemy_b = intelligence_world()
    own_agent = spy.intelligence_component.deploy_agent(enemy_a)
    own_agent.is_discovered = True
    hidden = Agent(enemy, enemy_a.id, "UNIT", spy.id, agent_id=700, is_discovered=False)
    discovered = Agent(enemy, enemy_a.id, "UNIT", spy.id, agent_id=701, is_discovered=True)
    spy.infiltrating_agents.extend([hidden, discovered])

    observation = build_observation(game, player)
    assert observation["schema_version"] == 5
    assert observation["command_catalog"]["version"] == 3
    assert observation["intelligence"]["owned_agents"] == [
        {
            "agent_id": own_agent.id,
            "source_unit_id": spy.id,
            "host_type": "unit",
            "target_id": enemy_a.id,
            "active_sabotage": None,
        }
    ]
    assert "is_discovered" not in observation["intelligence"]["owned_agents"][0]
    assert observation["intelligence"]["discovered_enemy_agents"] == [
        {
            "agent_id": discovered.id,
            "owner_id": enemy.id,
            "host_type": "unit",
            "target_id": spy.id,
        }
    ]
    assert hidden.id not in {item["agent_id"] for item in observation["intelligence"]["owned_agents"]}
    assert hidden.id not in {item["agent_id"] for item in observation["intelligence"]["discovered_enemy_agents"]}
    hostile = next(view for view in observation["units"] if view["id"] == enemy_a.id)
    assert "IntelligenceComponent" not in hostile["components"]
    assert "sabotage" in observation["player_commands"]["legal"]
    relocation = observation["player_commands"]["options"]["relocate_agent"]["agents"][0]
    assert relocation == {"agent_id": own_agent.id, "target_ids": [enemy_b.id]}


def test_allied_agents_share_intel_without_becoming_controllable():
    game, player, enemy, spy, enemy_a, enemy_b = intelligence_world()
    ally = Player(name="Ally", color=(0, 255, 0), team_id=player.team_id)
    game.players.append(ally)
    allied_ship = create_combat_ship(game.galaxy, ally, "Allied Ship", (0, 0), pos=(50, 0))
    allied_spy = create_combat_ship(game.galaxy, ally, "Allied Spy", (0, 0), pos=(75, 0))
    allied_spy.add_component(IntelligenceComponent(allied_spy, agents_count=1, agents_capacity=1))
    allied_agent = allied_spy.intelligence_component.deploy_agent(enemy_b)
    enemy_agent = enemy_a.intelligence_component.deploy_agent(allied_ship)
    enemy_agent.is_discovered = True

    observation = build_observation(game, player)
    assert allied_agent.id not in {
        item["agent_id"] for item in observation["intelligence"]["owned_agents"]
    }
    assert allied_agent.id not in {
        item["agent_id"]
        for item in observation["player_commands"]["options"]["sabotage"]["agents"]
    }
    assert observation["intelligence"]["discovered_enemy_agents"] == [
        {
            "agent_id": enemy_agent.id,
            "owner_id": enemy.id,
            "host_type": "unit",
            "target_id": allied_ship.id,
        }
    ]


def test_gateway_infiltrates_visible_unit_and_exact_enemy_colony():
    game, player, enemy, spy, enemy_a, _ = intelligence_world()
    planet = Planet((0, 0), "Sol", PlanetType.TERRAN)
    planet.owner = enemy
    planet.position = Position(200, 0)
    game.galaxy.systems["Sol"].add_celestial_body(planet)

    unit_result = issue(game, player, Command("infiltrate_unit", (spy.id,), target_id=enemy_a.id))
    assert unit_result.accepted
    assert any(agent.owner is player for agent in enemy_a.infiltrating_agents)

    colony_result = issue(game, player, Command("infiltrate_planet", (spy.id,), target_id=planet.id))
    assert colony_result.accepted
    assert any(agent.owner is player for agent in planet.infiltrating_agents)


def test_player_level_sabotage_and_relocation_preserve_ship_orders():
    game, player, _, spy, enemy_a, enemy_b = intelligence_world()
    agent = spy.intelligence_component.deploy_agent(enemy_a)
    existing = SimpleNamespace(public_id="existing", order_type=SimpleNamespace(name="MOVE"),
                               status=SimpleNamespace(name="IN_PROGRESS"), parameters={})
    spy.commander_component.current_order = existing

    result = issue(
        game,
        player,
        Command("sabotage", agent_id=agent.id, sabotage_type="engines"),
        Command("relocate_agent", agent_id=agent.id, target_id=enemy_b.id),
        Command("sabotage", agent_id=agent.id, sabotage_type="weapons"),
    )
    assert result.accepted and result.applied_count == 3
    assert spy.commander_component.current_order is existing
    assert agent not in enemy_a.infiltrating_agents and agent in enemy_b.infiltrating_agents
    assert agent.active_sabotage.value == "weapons"
    assert not agent.is_discovered


def test_agent_guessing_and_invalid_host_sabotage_are_atomic():
    game, player, _, spy, enemy_a, _ = intelligence_world()
    agent = spy.intelligence_component.deploy_agent(enemy_a)
    errors = [
        issue(game, player, Command("sabotage", agent_id=value, sabotage_type="engines")).errors
        for value in (agent.id + 100000, 999999)
    ]
    assert errors[0] == errors[1]
    result = issue(
        game,
        player,
        Command("sabotage", agent_id=agent.id, sabotage_type="engines"),
        Command("sabotage", agent_id=agent.id, sabotage_type="economy"),
    )
    assert not result.accepted and agent.active_sabotage is None


def test_ci_sweep_projection_discovery_and_elimination():
    game, player, enemy, spy, enemy_a, _ = intelligence_world()
    hostile_agent = enemy_a.intelligence_component.deploy_agent(spy)
    start_credits = float(player.credits)
    start_am = float(spy.antimatter_component.current_amount)

    rejected = issue(
        game,
        player,
        Command("ci_sweep", (spy.id,)),
        Command("ci_sweep", (spy.id,)),
    )
    assert not rejected.accepted
    assert player.credits == start_credits and spy.antimatter_component.current_amount == start_am
    assert not hostile_agent.is_discovered

    swept = issue(game, player, Command("ci_sweep", (spy.id,)))
    assert swept.accepted and hostile_agent.is_discovered
    assert player.credits == start_credits - CI_SWEEP_CREDIT_COST
    assert spy.antimatter_component.current_amount == start_am - CI_SWEEP_ANTIMATTER_COST

    eliminated = issue(game, player, Command("eliminate_agent", (spy.id,), agent_id=hostile_agent.id))
    assert eliminated.accepted
    order = spy.commander_component.current_order
    assert order.order_type == OrderType.ELIMINATE_AGENT
    if order.status != OrderStatus.COMPLETED:
        order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert hostile_agent not in spy.infiltrating_agents


def test_extract_to_another_ship_after_source_destruction():
    game, player, _, source, enemy_a, _ = intelligence_world()
    agent = source.intelligence_component.deploy_agent(enemy_a)
    extractor = create_combat_ship(game.galaxy, player, "Extractor", (0, 0), pos=(50, 0))
    extractor.add_component(IntelligenceComponent(extractor, agents_count=0, agents_capacity=1))
    source.destroy()

    result = issue(game, player, Command("extract_agent", (extractor.id,), agent_id=agent.id))
    assert result.accepted
    order = extractor.commander_component.current_order
    if order.status != OrderStatus.COMPLETED:
        order.execute(game.galaxy)
    assert order.status == OrderStatus.COMPLETED
    assert agent not in enemy_a.infiltrating_agents
    assert extractor.intelligence_component.available_agents == 1
    assert agent not in source.intelligence_component.deployed_agents


def test_luna_coordinator_and_codex_control_use_identical_gateway_effects():
    luna_game, luna_player, _, luna_spy, luna_target, _ = intelligence_world()
    codex_game, codex_player, _, codex_spy, codex_target, _ = intelligence_world()
    luna_agent = luna_spy.intelligence_component.deploy_agent(luna_target)
    codex_agent = codex_spy.intelligence_component.deploy_agent(codex_target)

    strict_command = Command(
        "sabotage", agent_id=luna_agent.id, sabotage_type="engines"
    ).to_dict()
    luna_plan = TurnPlan.from_dict(
        {
            "plan": ["Disrupt the hostile ship."],
            "commands": [strict_command],
            "memory_patch": {
                "strategy": None,
                "objectives": None,
                "commitments": None,
                "beliefs": None,
                "lessons": None,
                "misc": None,
            },
            "end_turn": True,
        },
        strict=True,
    )
    luna_player.controller = PlayerController.OPENAI
    luna_game.game_started = True
    luna_game.campaign_id = "luna-intelligence"
    luna_game.gui = None
    luna_game.end_turn = lambda: None
    coordinator = AgentTurnCoordinator(luna_game, provider=object())
    try:
        coordinator._write_memory = lambda *_args: None
        coordinator._record_telemetry = lambda *_args, **_kwargs: None
        coordinator._apply_result(
            PlanningResult(luna_plan, "fake", "gpt-5.6-luna", "medium")
        )
    finally:
        coordinator.shutdown()

    codex_player.controller = PlayerController.CODEX
    codex_game.game_started = True
    codex_game.campaign_id = "codex-intelligence"
    codex_game.view_mode = "galaxy"
    service = ControlService(codex_game, port=0)
    try:
        observed = service._dispatch("observe", "observe-intelligence", {})
        assert observed["ok"]
        observation = observed["data"]["observation"]
        assert observation["schema_version"] == 5
        assert observation["command_catalog"]["version"] == 3
        assert observation["intelligence"]["owned_agents"][0]["agent_id"] == codex_agent.id

        commanded = service._dispatch(
            "command",
            "command-intelligence",
            {
                "turn_token": observed["data"]["turn_token"],
                "commands": [
                    {
                        "type": "sabotage",
                        "unit_ids": [],
                        "agent_id": codex_agent.id,
                        "sabotage_type": "engines",
                    }
                ],
            },
        )
        assert commanded["ok"] and commanded["data"]["accepted"]
    finally:
        service.shutdown()

    assert luna_agent.active_sabotage.value == "engines"
    assert codex_agent.active_sabotage.value == luna_agent.active_sabotage.value
