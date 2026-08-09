"""Unit tests for antimatter consumption by HyperspaceInhibitionFieldEmitter."""
import pytest
from unittest.mock import MagicMock

from entities import Unit
from galaxy import Galaxy, StarSystem, Hex
from utils import HexCoord
from geometry import Position, Circle
from constants import HullSize, INHIBITOR_ANTIMATTER_COST_PER_50_RADIUS
from unit_components.inhibitor import HyperspaceInhibitionFieldEmitter
from unit_components.antimatter import AntimatterStorage


def make_unit(name="Inhibitor Vessel", in_system="Sol", in_hex=(0, 0), position=None):
    if position is None:
        position = Position(0.0, 0.0)
    mock_game = MagicMock()
    mock_player = MagicMock()
    mock_player.name = "Player 1"
    unit = Unit(
        owner=mock_player,
        position=position,
        in_hex=in_hex,
        in_system=in_system,
        name=name,
        hull_size=HullSize.MEDIUM,
        game=mock_game
    )
    return unit


def test_inhibitor_antimatter_cost_scaling():
    """Verify get_antimatter_cost_per_turn computes cost linearly with radius."""
    mock_unit = MagicMock(spec=Unit)
    
    emitter_50 = HyperspaceInhibitionFieldEmitter(unit=mock_unit, radius=50.0)
    assert emitter_50.get_antimatter_cost_per_turn() == 5.0

    emitter_100 = HyperspaceInhibitionFieldEmitter(unit=mock_unit, radius=100.0)
    assert emitter_100.get_antimatter_cost_per_turn() == 10.0

    emitter_25 = HyperspaceInhibitionFieldEmitter(unit=mock_unit, radius=25.0)
    assert emitter_25.get_antimatter_cost_per_turn() == 2.5


def test_active_inhibitor_consumes_antimatter_on_update():
    """Verify active inhibitor consumes antimatter on component update."""
    unit = make_unit()
    unit.antimatter_component.current_amount = 50.0

    emitter = HyperspaceInhibitionFieldEmitter(unit=unit, radius=50.0)
    unit.add_component(emitter)
    emitter.turn_on()

    assert emitter.is_active is True
    assert unit.antimatter_component.current_amount == 50.0

    # Perform per-turn update
    emitter.update()

    assert emitter.is_active is True
    assert unit.antimatter_component.current_amount == 45.0


def test_active_inhibitor_autodeactivates_when_antimatter_depleted():
    """Verify inhibitor auto-deactivates when antimatter reserve is insufficient."""
    unit = make_unit()
    unit.antimatter_component.current_amount = 3.0

    emitter = HyperspaceInhibitionFieldEmitter(unit=unit, radius=50.0)  # requires 5.0 AM
    unit.add_component(emitter)
    emitter.turn_on()

    assert emitter.is_active is True

    # Perform update with insufficient antimatter (3.0 < 5.0)
    emitter.update()

    assert emitter.is_active is False
    # Antimatter amount remains unchanged because consumption failed
    assert unit.antimatter_component.current_amount == 3.0


def test_active_inhibitor_autodeactivates_and_removes_hex_zone():
    """Verify auto-deactivation cleans up dynamic inhibition zone from current sector hex."""
    galaxy = Galaxy()
    system = StarSystem("Alpha Centauri", Position(0.0, 0.0))
    hex_coord = HexCoord(0, 0)
    hex_obj = Hex(0, 0, in_system="Alpha Centauri")
    system.hexes[hex_coord] = hex_obj
    galaxy.systems["Alpha Centauri"] = system

    unit = make_unit(in_system="Alpha Centauri", in_hex=hex_coord)
    unit.in_galaxy = galaxy
    unit.id = 12345
    unit.antimatter_component.current_amount = 2.0

    emitter = HyperspaceInhibitionFieldEmitter(unit=unit, radius=50.0)
    unit.add_component(emitter)

    # Register dynamic inhibition zone on hex and turn on emitter
    emitter.turn_on()
    hex_obj.dynamic_inhibition_zones[unit.id] = Circle(center=unit.position, radius=emitter.radius)
    assert unit.id in hex_obj.dynamic_inhibition_zones

    # Update should auto-deactivate and clean up hex zone
    emitter.update()

    assert emitter.is_active is False
    assert unit.id not in hex_obj.dynamic_inhibition_zones


def test_inactive_inhibitor_does_not_consume_antimatter():
    """Verify inactive inhibitor does not consume antimatter during update."""
    unit = make_unit()
    unit.antimatter_component.current_amount = 50.0

    emitter = HyperspaceInhibitionFieldEmitter(unit=unit, radius=50.0)
    unit.add_component(emitter)
    # Emitter is inactive

    emitter.update()

    assert emitter.is_active is False
    assert unit.antimatter_component.current_amount == 50.0


def test_active_inhibitor_without_antimatter_storage_autodeactivates():
    """Verify active inhibitor without antimatter storage auto-deactivates on update."""
    unit = make_unit()
    unit.remove_component(AntimatterStorage)
    assert unit.antimatter_component is None

    emitter = HyperspaceInhibitionFieldEmitter(unit=unit, radius=50.0)
    unit.add_component(emitter)
    emitter.turn_on()

    emitter.update()

    assert emitter.is_active is False
