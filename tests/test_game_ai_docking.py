"""
tests/test_game_ai_docking.py

Comprehensive test suite for disambiguated AI docking commands:
- "dock_in_hangar" for Tiny ships
- "dock_in_strikecraft_bay" for Strikecraft wings
- Rules engine supported_commands and command_guidance
- Schema and CommandBatch validation
- CommandGateway preflight, slot reservation, and order execution
- Rejections for mismatched hull sizes, missing carrier bays, and capacity limits
"""

import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import HullSize
from entities import Player, Unit
from galaxy import Galaxy, StarSystem
from unit_components import (
    Commander,
    HangarComponent,
    StrikecraftBayComponent,
    StrikecraftWingComponent,
)
from unit_orders import DockOrder
from game_ai.contracts import Command, CommandBatch, SUPPORTED_COMMANDS
from game_ai.rules import supported_commands, command_guidance
from game_ai.observation import build_observation, COMMAND_HELP
from game_ai.commands import CommandGateway


@pytest.fixture
def ai_dock_setup():
    p1 = Player("Player 1", (0, 0, 255), is_human=False)
    galaxy = Galaxy()
    system = StarSystem(name="Sol", position=Position(0, 0), radius=3)
    galaxy.systems = {"Sol": system}

    game = MagicMock()
    game.galaxy = galaxy
    game.players = [p1]
    game.current_player_index = 0
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.event_bus = MagicMock()
    return p1, galaxy, system, game


def test_supported_commands_and_contracts():
    assert "dock_in_hangar" in SUPPORTED_COMMANDS
    assert "dock_in_strikecraft_bay" in SUPPORTED_COMMANDS
    assert "dock" not in SUPPORTED_COMMANDS

    assert "dock_in_hangar" in COMMAND_HELP
    assert "dock_in_strikecraft_bay" in COMMAND_HELP
    assert "dock" not in COMMAND_HELP


def test_rules_supported_commands_and_guidance(ai_dock_setup):
    p1, galaxy, system, game = ai_dock_setup

    tiny_ship = Unit(p1, Position(10, 10), (0, 0), "Sol", "Scout", HullSize.TINY, game)
    tiny_ship.id = 101
    tiny_ship.add_component(Commander(tiny_ship))
    system.hexes[(0, 0)].add_unit(tiny_ship)

    wing = Unit(p1, Position(15, 15), (0, 0), "Sol", "Fighter Wing", HullSize.STRIKECRAFT_WING, game)
    wing.id = 102
    wing.add_component(Commander(wing))
    wing.add_component(StrikecraftWingComponent(wing))
    system.hexes[(0, 0)].add_unit(wing)

    carrier = Unit(p1, Position(20, 20), (0, 0), "Sol", "Super Carrier", HullSize.HUGE, game)
    carrier.id = 200
    carrier.add_component(Commander(carrier))
    carrier.add_component(HangarComponent(carrier, max_slots=2))
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=2))
    system.hexes[(0, 0)].add_unit(carrier)

    # 1. Supported commands for Tiny ship
    tiny_supported = supported_commands(tiny_ship)
    assert "dock_in_hangar" in tiny_supported
    assert "dock_in_strikecraft_bay" not in tiny_supported

    # 2. Supported commands for Strikecraft Wing
    wing_supported = supported_commands(wing)
    assert "dock_in_strikecraft_bay" in wing_supported
    assert "dock_in_hangar" not in wing_supported

    # 3. Guidance / Legal Targets
    legal_tiny, options_tiny, _ = command_guidance(
        game, p1, tiny_ship, exact_bodies=[], visible_units=[carrier]
    )
    assert "dock_in_hangar" in legal_tiny
    assert carrier.id in options_tiny.get("dock_in_hangar", {}).get("target_ids", [])

    legal_wing, options_wing, _ = command_guidance(
        game, p1, wing, exact_bodies=[], visible_units=[carrier]
    )
    assert "dock_in_strikecraft_bay" in legal_wing
    assert carrier.id in options_wing.get("dock_in_strikecraft_bay", {}).get("target_ids", [])


def test_gateway_execute_dock_in_hangar(ai_dock_setup):
    p1, galaxy, system, game = ai_dock_setup

    tiny_ship = Unit(p1, Position(10, 10), (0, 0), "Sol", "Scout", HullSize.TINY, game)
    tiny_ship.id = 101
    tiny_ship.add_component(Commander(tiny_ship))
    system.hexes[(0, 0)].add_unit(tiny_ship)

    carrier = Unit(p1, Position(20, 20), (0, 0), "Sol", "Hangar Carrier", HullSize.LARGE, game)
    carrier.id = 200
    carrier.add_component(Commander(carrier))
    carrier.add_component(HangarComponent(carrier, max_slots=2))
    system.hexes[(0, 0)].add_unit(carrier)

    galaxy.get_unit_by_id = lambda uid: carrier if uid == carrier.id else (tiny_ship if uid == tiny_ship.id else None)

    gateway = CommandGateway(game)
    batch = CommandBatch(
        commands=(
            Command(type="dock_in_hangar", unit_ids=(tiny_ship.id,), target_id=carrier.id),
        )
    )

    result = gateway.apply_batch(p1, batch)
    assert result.accepted
    assert result.applied_count == 1
    assert tiny_ship in carrier.hangar_component.docked_units


def test_gateway_execute_dock_in_strikecraft_bay(ai_dock_setup):
    p1, galaxy, system, game = ai_dock_setup

    wing = Unit(p1, Position(15, 15), (0, 0), "Sol", "Fighter Wing", HullSize.STRIKECRAFT_WING, game)
    wing.id = 102
    wing.add_component(Commander(wing))
    wing.add_component(StrikecraftWingComponent(wing))
    system.hexes[(0, 0)].add_unit(wing)

    carrier = Unit(p1, Position(20, 20), (0, 0), "Sol", "Bay Carrier", HullSize.LARGE, game)
    carrier.id = 200
    carrier.add_component(Commander(carrier))
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=2))
    system.hexes[(0, 0)].add_unit(carrier)

    galaxy.get_unit_by_id = lambda uid: carrier if uid == carrier.id else (wing if uid == wing.id else None)

    gateway = CommandGateway(game)
    batch = CommandBatch(
        commands=(
            Command(type="dock_in_strikecraft_bay", unit_ids=(wing.id,), target_id=carrier.id),
        )
    )

    result = gateway.apply_batch(p1, batch)
    assert result.accepted
    assert result.applied_count == 1
    assert wing in carrier.strikecraft_bay_component.docked_units


def test_gateway_rejects_mismatched_docking_commands(ai_dock_setup):
    p1, galaxy, system, game = ai_dock_setup

    tiny_ship = Unit(p1, Position(10, 10), (0, 0), "Sol", "Scout", HullSize.TINY, game)
    tiny_ship.id = 101
    tiny_ship.add_component(Commander(tiny_ship))
    system.hexes[(0, 0)].add_unit(tiny_ship)

    wing = Unit(p1, Position(15, 15), (0, 0), "Sol", "Fighter Wing", HullSize.STRIKECRAFT_WING, game)
    wing.id = 102
    wing.add_component(Commander(wing))
    wing.add_component(StrikecraftWingComponent(wing))
    system.hexes[(0, 0)].add_unit(wing)

    carrier = Unit(p1, Position(20, 20), (0, 0), "Sol", "Carrier", HullSize.HUGE, game)
    carrier.id = 200
    carrier.add_component(Commander(carrier))
    carrier.add_component(HangarComponent(carrier, max_slots=2))
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=2))
    system.hexes[(0, 0)].add_unit(carrier)

    galaxy.get_unit_by_id = lambda uid: carrier if uid == carrier.id else (tiny_ship if uid == tiny_ship.id else (wing if uid == wing.id else None))

    gateway = CommandGateway(game)

    # 1. Strikecraft Wing attempting dock_in_hangar -> rejected
    batch_invalid_wing = CommandBatch(
        commands=(
            Command(type="dock_in_hangar", unit_ids=(wing.id,), target_id=carrier.id),
        )
    )
    result_wing = gateway.apply_batch(p1, batch_invalid_wing)
    assert not result_wing.accepted
    assert len(result_wing.errors) > 0
    assert result_wing.errors[0].code in {"capability_unavailable", "invalid_target"}

    # 2. Tiny ship attempting dock_in_strikecraft_bay -> rejected
    batch_invalid_tiny = CommandBatch(
        commands=(
            Command(type="dock_in_strikecraft_bay", unit_ids=(tiny_ship.id,), target_id=carrier.id),
        )
    )
    result_tiny = gateway.apply_batch(p1, batch_invalid_tiny)
    assert not result_tiny.accepted
    assert len(result_tiny.errors) > 0
    assert result_tiny.errors[0].code in {"capability_unavailable", "invalid_target"}


def test_gateway_rejects_capacity_overflow(ai_dock_setup):
    p1, galaxy, system, game = ai_dock_setup

    tiny1 = Unit(p1, Position(10, 10), (0, 0), "Sol", "Scout 1", HullSize.TINY, game)
    tiny1.id = 101
    tiny1.add_component(Commander(tiny1))
    system.hexes[(0, 0)].add_unit(tiny1)

    tiny2 = Unit(p1, Position(12, 12), (0, 0), "Sol", "Scout 2", HullSize.TINY, game)
    tiny2.id = 102
    tiny2.add_component(Commander(tiny2))
    system.hexes[(0, 0)].add_unit(tiny2)

    carrier = Unit(p1, Position(20, 20), (0, 0), "Sol", "Hangar Carrier", HullSize.LARGE, game)
    carrier.id = 200
    carrier.add_component(Commander(carrier))
    carrier.add_component(HangarComponent(carrier, max_slots=1))  # only 1 slot!
    system.hexes[(0, 0)].add_unit(carrier)

    galaxy.get_unit_by_id = lambda uid: carrier if uid == carrier.id else (tiny1 if uid == tiny1.id else (tiny2 if uid == tiny2.id else None))

    gateway = CommandGateway(game)
    batch = CommandBatch(
        commands=(
            Command(type="dock_in_hangar", unit_ids=(tiny1.id, tiny2.id), target_id=carrier.id),
        )
    )
    result = gateway.apply_batch(p1, batch)
    assert not result.accepted
    assert len(result.errors) > 0
    assert result.errors[0].code in {"insufficient_capacity", "invalid_target"}
