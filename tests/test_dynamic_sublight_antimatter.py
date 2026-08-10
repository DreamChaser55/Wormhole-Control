import pytest
from unittest.mock import MagicMock
from constants import HullSize, ENGINE_ANTIMATTER_COST_PER_TURN, BASELINE_ENGINE_SPEED
from custom_unit_templates import get_sublight_antimatter_cost_per_turn
from entities import Unit
from geometry import Position
from unit_components import Engines, AntimatterStorage
from unit_orders import calculate_required_antimatter
from turn_processor import TurnProcessor


def test_get_sublight_antimatter_cost_per_turn_baseline():
    # Medium hull (1.0), baseline speed 100.0 (1.0) -> base cost 2.0
    cost = get_sublight_antimatter_cost_per_turn(HullSize.MEDIUM, 100.0)
    assert cost == pytest.approx(2.0)


def test_get_sublight_antimatter_cost_per_turn_speed_scaling():
    # Medium hull (1.0), speed 200.0 -> 2.0 * 1.0 * 2.0 = 4.0
    cost_fast = get_sublight_antimatter_cost_per_turn(HullSize.MEDIUM, 200.0)
    assert cost_fast == pytest.approx(4.0)

    # Medium hull (1.0), speed 50.0 -> 2.0 * 1.0 * 0.5 = 1.0
    cost_slow = get_sublight_antimatter_cost_per_turn(HullSize.MEDIUM, 50.0)
    assert cost_slow == pytest.approx(1.0)


def test_get_sublight_antimatter_cost_per_turn_hull_scaling():
    # Tiny hull (0.6), speed 100.0 -> 2.0 * 0.6 * 1.0 = 1.2
    cost_tiny = get_sublight_antimatter_cost_per_turn(HullSize.TINY, 100.0)
    assert cost_tiny == pytest.approx(1.2)

    # Small hull (0.8), speed 100.0 -> 2.0 * 0.8 * 1.0 = 1.6
    cost_small = get_sublight_antimatter_cost_per_turn(HullSize.SMALL, 100.0)
    assert cost_small == pytest.approx(1.6)

    # Large hull (1.5), speed 100.0 -> 2.0 * 1.5 * 1.0 = 3.0
    cost_large = get_sublight_antimatter_cost_per_turn(HullSize.LARGE, 100.0)
    assert cost_large == pytest.approx(3.0)

    # Huge hull (2.0), speed 100.0 -> 2.0 * 2.0 * 1.0 = 4.0
    cost_huge = get_sublight_antimatter_cost_per_turn(HullSize.HUGE, 100.0)
    assert cost_huge == pytest.approx(4.0)


def test_get_sublight_antimatter_cost_per_turn_combined_scaling():
    # Huge hull (2.0), speed 150.0 (1.5) -> 2.0 * 2.0 * 1.5 = 6.0
    cost = get_sublight_antimatter_cost_per_turn(HullSize.HUGE, 150.0)
    assert cost == pytest.approx(6.0)


def test_get_sublight_antimatter_cost_per_turn_zero_speed():
    assert get_sublight_antimatter_cost_per_turn(HullSize.MEDIUM, 0.0) == 0.0
    assert get_sublight_antimatter_cost_per_turn(HullSize.MEDIUM, -10.0) == 0.0


from tests.test_unit_components import MockUnit, MockPlayer

def test_turn_processor_sublight_antimatter_consumption():
    game = MagicMock()
    player = MockPlayer()
    system = MagicMock()
    
    unit = MockUnit()
    unit.name = "TestHugeCruiser"
    unit.hull_size = HullSize.HUGE
    unit.owner = player
    unit.position = Position(0.0, 0.0)
    unit.in_system = "Sol"

    engines = Engines(unit, speed=150.0)
    engines.move_target = Position(300.0, 0.0)

    am_storage = AntimatterStorage(unit)
    am_storage.max_capacity = 100.0
    am_storage.current_amount = 100.0

    unit.components = {
        AntimatterStorage: am_storage,
        Engines: engines
    }

    system.get_all_units.return_value = [(unit, (0, 0))]
    system.hexes = {(0, 0): MagicMock()}
    game.galaxy.systems = {"Sol": system}

    tp = TurnProcessor(game)
    tp._process_movement(player)

    # Huge hull (2.0) at speed 150.0 (1.5) => 6.0 AM consumed
    assert am_storage.current_amount == pytest.approx(94.0)
