"""
tests/test_dock_context_menu.py

Tests for disambiguated context menu docking options:
- "Dock in Hangar" for Tiny ships targeting Hangar carriers.
- "Dock in Strikecraft Bay" for Strikecraft wings targeting Strikecraft Bay carriers.
- Mixed selection handling in context menu and action dispatching.
- OrderSystem handle_dock support for strikecraft wings.
"""

import pytest
from unittest.mock import MagicMock
from geometry import Position
from constants import HullSize
from entities import Player, Unit
from galaxy import Galaxy, StarSystem
from unit_components import HangarComponent, StrikecraftBayComponent, StrikecraftWingComponent, Commander
from events import DockEvent
from input_processor.context_menu_builder import build_sector_context_menu_options
from input_processor.context_actions import handle_context_menu_action


@pytest.fixture
def dock_setup():
    p1 = Player("Player 1", (0, 0, 255))
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


def test_dock_in_hangar_option_for_tiny_ship(dock_setup):
    p1, galaxy, system, game = dock_setup

    tiny_ship = Unit(p1, Position(10, 10), (0, 0), "Sol", "Scout", HullSize.TINY, game)
    tiny_ship.add_component(Commander(tiny_ship))
    system.hexes[(0, 0)].add_unit(tiny_ship)

    carrier = Unit(p1, Position(20, 20), (0, 0), "Sol", "Hangar Carrier", HullSize.LARGE, game)
    carrier.add_component(Commander(carrier))
    carrier.add_component(HangarComponent(carrier, max_slots=2))
    system.hexes[(0, 0)].add_unit(carrier)

    game.selected_objects = [tiny_ship]

    options, target = build_sector_context_menu_options(game, carrier, (0, 0))
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    option_labels = [opt[0] for opt in options if isinstance(opt[0], str)]

    assert "dock_in_hangar" in action_ids
    assert "Dock in Hangar" in option_labels
    assert "dock_in_strikecraft_bay" not in action_ids
    assert "Dock in Strikecraft Bay" not in option_labels


def test_dock_in_strikecraft_bay_option_for_wing(dock_setup):
    p1, galaxy, system, game = dock_setup

    wing = Unit(p1, Position(10, 10), (0, 0), "Sol", "Fighter Wing", HullSize.STRIKECRAFT_WING, game)
    wing.add_component(Commander(wing))
    wing.add_component(StrikecraftWingComponent(wing))
    system.hexes[(0, 0)].add_unit(wing)

    carrier = Unit(p1, Position(20, 20), (0, 0), "Sol", "Bay Carrier", HullSize.LARGE, game)
    carrier.add_component(Commander(carrier))
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=2))
    system.hexes[(0, 0)].add_unit(carrier)

    game.selected_objects = [wing]

    options, target = build_sector_context_menu_options(game, carrier, (0, 0))
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    option_labels = [opt[0] for opt in options if isinstance(opt[0], str)]

    assert "dock_in_strikecraft_bay" in action_ids
    assert "Dock in Strikecraft Bay" in option_labels
    assert "dock_in_hangar" not in action_ids
    assert "Dock in Hangar" not in option_labels


def test_both_dock_options_for_mixed_selection_on_dual_carrier(dock_setup):
    p1, galaxy, system, game = dock_setup

    tiny_ship = Unit(p1, Position(10, 10), (0, 0), "Sol", "Scout", HullSize.TINY, game)
    tiny_ship.add_component(Commander(tiny_ship))
    system.hexes[(0, 0)].add_unit(tiny_ship)

    wing = Unit(p1, Position(15, 15), (0, 0), "Sol", "Fighter Wing", HullSize.STRIKECRAFT_WING, game)
    wing.add_component(Commander(wing))
    wing.add_component(StrikecraftWingComponent(wing))
    system.hexes[(0, 0)].add_unit(wing)

    carrier = Unit(p1, Position(20, 20), (0, 0), "Sol", "Super Carrier", HullSize.HUGE, game)
    carrier.add_component(Commander(carrier))
    carrier.add_component(HangarComponent(carrier, max_slots=2))
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=2))
    system.hexes[(0, 0)].add_unit(carrier)

    game.selected_objects = [tiny_ship, wing]

    options, target = build_sector_context_menu_options(game, carrier, (0, 0))
    action_ids = [opt[1] for opt in options if isinstance(opt[1], str)]
    option_labels = [opt[0] for opt in options if isinstance(opt[0], str)]

    assert "dock_in_hangar" in action_ids
    assert "Dock in Hangar" in option_labels
    assert "dock_in_strikecraft_bay" in action_ids
    assert "Dock in Strikecraft Bay" in option_labels


def test_context_action_dock_in_hangar_filters_to_compatible_units(dock_setup):
    p1, galaxy, system, game = dock_setup

    tiny_ship = Unit(p1, Position(10, 10), (0, 0), "Sol", "Scout", HullSize.TINY, game)
    wing = Unit(p1, Position(15, 15), (0, 0), "Sol", "Fighter Wing", HullSize.STRIKECRAFT_WING, game)
    carrier = Unit(p1, Position(20, 20), (0, 0), "Sol", "Super Carrier", HullSize.HUGE, game)
    carrier.add_component(HangarComponent(carrier, max_slots=2))
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=2))

    game.selected_objects = [tiny_ship, wing]
    handle_context_menu_action(game, "dock_in_hangar", carrier)

    game.event_bus.publish.assert_called_once()
    published_event = game.event_bus.publish.call_args[0][0]
    assert isinstance(published_event, DockEvent)
    assert published_event.units == [tiny_ship]
    assert published_event.target_carrier == carrier


def test_context_action_dock_in_strikecraft_bay_filters_to_wings(dock_setup):
    p1, galaxy, system, game = dock_setup

    tiny_ship = Unit(p1, Position(10, 10), (0, 0), "Sol", "Scout", HullSize.TINY, game)
    wing = Unit(p1, Position(15, 15), (0, 0), "Sol", "Fighter Wing", HullSize.STRIKECRAFT_WING, game)
    carrier = Unit(p1, Position(20, 20), (0, 0), "Sol", "Super Carrier", HullSize.HUGE, game)
    carrier.add_component(HangarComponent(carrier, max_slots=2))
    carrier.add_component(StrikecraftBayComponent(carrier, max_slots=2))

    game.selected_objects = [tiny_ship, wing]
    handle_context_menu_action(game, "dock_in_strikecraft_bay", carrier)

    game.event_bus.publish.assert_called_once()
    published_event = game.event_bus.publish.call_args[0][0]
    assert isinstance(published_event, DockEvent)
    assert published_event.units == [wing]
    assert published_event.target_carrier == carrier


def test_order_system_handle_dock_creates_order_for_wing(dock_setup):
    from order_system import OrderSystem
    from unit_orders import DockOrder

    p1, galaxy, system, game = dock_setup
    order_sys = OrderSystem(game, game.event_bus)

    wing = Unit(p1, Position(10, 10), (0, 0), "Sol", "Fighter Wing", HullSize.STRIKECRAFT_WING, game)
    wing.add_component(Commander(wing))
    carrier = Unit(p1, Position(20, 20), (0, 0), "Sol", "Bay Carrier", HullSize.LARGE, game)

    order_sys.handle_dock(DockEvent([wing], carrier, False))

    assert isinstance(wing.commander_component.current_order, DockOrder)
