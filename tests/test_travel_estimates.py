"""Arrival estimates follow movement timing, without charging terminal recharge."""
from types import SimpleNamespace

import pytest

from antimatter_logistics import estimate_approach
from game_ai.contracts import Command
from game_ai.order_view import public_journey_progress
from geometry import Circle, Position
from tests.support.campaigns import campaign, ship
from tests.support.commands import issue
from turn_processor import TurnProcessor
from unit_components.antimatter import AntimatterStorage
from unit_components.movement import Engines, Hyperdrive
from unit_components.enums import HyperdriveType


@pytest.mark.parametrize('jumps, initial_recharge', [(1, 0), (1, 2), (2, 0)])
def test_jump_arrival_preview_matches_actual_owner_resolutions(jumps, initial_recharge):
    from galaxy import Hex
    game = campaign()
    unit = ship(game)
    unit.add_component(Engines(unit, speed=100))
    unit.add_component(Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED, jump_range=1))
    unit.add_component(AntimatterStorage(unit, max_capacity=500))
    if jumps == 2:
        game.galaxy.systems['Sol'].hexes[(2, 0)] = Hex(2, 0, 'Sol')
    if initial_recharge:
        unit.hyperdrive_component.start_recharge()
        unit.hyperdrive_component.recharge_time_remaining = initial_recharge
    command = Command('move', (unit.id,), system_name='Sol', hex_coord=(jumps, 0), position=(0, -3500))
    assert issue(game, unit.owner, command).accepted
    preview = public_journey_progress(game, unit.owner, unit)
    expected = initial_recharge + 1 + (jumps - 1) * unit.hyperdrive_component.RECHARGE_DURATION
    assert preview['estimated_remaining_owner_turns'] == expected
    for resolution in range(1, expected + 1):
        unit.commander_component.prepare_for_movement()
        TurnProcessor(game)._process_movement(unit.owner)
        unit.update()
        completed = [e for e in unit.owner.order_history if e['type'] == 'move' and e['outcome'] == 'completed']
        assert bool(completed) == (resolution == expected)
    assert unit.in_hex == (jumps, 0) and unit.position == Position(0, -3500)
    assert unit.hyperdrive_component.recharge_time_remaining > 0


def test_recharge_overlaps_sublight_and_does_not_delay_local_arrival():
    game = campaign()
    unit = ship(game)
    unit.add_component(Engines(unit, speed=100))
    unit.add_component(Hyperdrive(unit, jump_range=1))
    unit.add_component(AntimatterStorage(unit, max_capacity=500))
    drive = unit.hyperdrive_component
    drive.start_recharge()
    target = SimpleNamespace(in_system='Sol', in_hex=(0, 0), position=Position(300, 0))
    assert estimate_approach(unit, game.galaxy, target, approach_range=5).turns == 2
    sector = game.galaxy.systems['Sol'].hexes[(0, 0)]
    sector.static_inhibition_zones = [Circle(Position(0, 0), 1000)]
    target.in_hex = (1, 0)
    target.position = Position(0, -3500)
    ready_estimate = estimate_approach(unit, game.galaxy, target, approach_range=5)
    drive.recharge_time_remaining = 0
    assert estimate_approach(unit, game.galaxy, target, approach_range=5).turns == ready_estimate.turns


def test_service_budget_retains_post_arrival_readiness_upkeep():
    from antimatter_logistics import buffered_fuel, route_budget
    from unit_components.cloaking import CloakingDevice
    game = campaign()
    unit = ship(game)
    unit.add_component(Engines(unit, speed=100))
    unit.add_component(Hyperdrive(unit, drive_type=HyperdriveType.ADVANCED))
    unit.add_component(AntimatterStorage(unit, max_capacity=500))
    unit.add_component(CloakingDevice(unit))
    unit.cloaking_component.is_active = True
    source = ship(game)
    source.add_component(AntimatterStorage(source, max_capacity=500))
    target = ship(game, sector=(1, 0))
    target.position = Position(0, -3500)
    quote = estimate_approach(unit, game.galaxy, target)
    assert quote.turns == 1
    assert quote.readiness_fuel > quote.fuel
    assert route_budget(unit, source, target, game.galaxy) >= buffered_fuel(quote.readiness_fuel)
