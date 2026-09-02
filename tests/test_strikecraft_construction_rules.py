"""
tests/test_strikecraft_construction_rules.py

Verifies that strikecraft wings are excluded from constructor units (ConstructorComponent),
human Construct context menus, and AI interfaces (observation catalog, rules, and command validation),
and confirms that strikecraft wings are constructed solely by units with a StrikecraftBayComponent.
"""
from unittest.mock import MagicMock
import pytest

from constants import HullSize
from geometry import Position
from entities import Unit
from unit_components import Constructor, StrikecraftBayComponent, WingType
from unit_orders import ConstructOrder, OrderStatus
from unit_templates import UNIT_TEMPLATES, register_template, unregister_template
from tests.test_unit_components import MockUnit, MockPlayer
from game_ai.contracts import Command


def test_constructor_buildable_units_excludes_strikecraft_wings():
    """Verify buildable_units property excludes default and custom strikecraft wings."""
    unit = MockUnit()
    constructor = Constructor(unit)
    unit.add_component(constructor)

    buildable_names = [b.unit_template_name for b in constructor.buildable_units]
    assert "FIGHTER_WING" not in buildable_names
    assert "BOMBER_WING" not in buildable_names

    # Test with custom template of STRIKECRAFT_WING hull size
    custom_name = "CUSTOM_INTERCEPTOR_WING"
    register_template(custom_name, {
        "name": "Custom Interceptor",
        "hull_size": HullSize.STRIKECRAFT_WING,
        "build_time": 2,
        "build_cost": 150
    })
    try:
        updated_names = [b.unit_template_name for b in constructor.buildable_units]
        assert custom_name not in updated_names
    finally:
        unregister_template(custom_name)


def test_constructor_can_build_rejects_strikecraft_wings():
    """Verify can_build returns None for strikecraft wing templates."""
    unit = MockUnit()
    constructor = Constructor(unit)
    unit.add_component(constructor)

    assert constructor.can_build("FIGHTER_WING") is None
    assert constructor.can_build("BOMBER_WING") is None

    # Valid non-strikecraft templates should still be buildable
    assert constructor.can_build("SHIPYARD_MK1") is not None
    assert constructor.can_build("CONSTRUCTOR_MK1") is not None


def test_construct_order_fails_for_strikecraft_wings():
    """Verify that issuing a ConstructOrder for a strikecraft wing fails."""
    unit = MockUnit()
    constructor = Constructor(unit)
    unit.add_component(constructor)

    player = MockPlayer()
    player.id = unit.owner.id
    player.credits = 1000
    unit.game.players = [player]
    unit.owner = player

    order = ConstructOrder(unit, {
        "unit_template_name": "FIGHTER_WING",
        "target_position": Position(100, 100)
    })

    galaxy = MagicMock()
    order.execute(galaxy)

    assert order.status == OrderStatus.FAILED
    assert constructor.current_construction_target is None
    assert player.credits == 1000


def test_context_menu_construct_options_exclude_strikecraft_wings():
    """Verify right-click Construct submenu options do not list strikecraft wings."""
    from input_processor.context_menu_builder import build_sector_context_menu_options
    from entities import Player

    game = MagicMock()
    player = Player(name="Player 1", color=(0, 255, 0))
    game.players = [player]
    game.current_player_index = 0

    unit = Unit(
        owner=player,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        name="Constructor Ship",
        hull_size=HullSize.MEDIUM,
        game=game
    )
    constructor = Constructor(unit)
    unit.add_component(constructor)
    game.selected_objects = [unit]

    options, _ = build_sector_context_menu_options(game, clicked_object=None, clicked_sector_coord=Position(50, 50))
    construct_entry = next((opt for opt in options if isinstance(opt, tuple) and opt[0] == "Construct"), None)

    assert construct_entry is not None
    sub_options = construct_entry[1]
    action_ids = [action for label, action in sub_options]

    assert "construct_FIGHTER_WING" not in action_ids
    assert "construct_BOMBER_WING" not in action_ids
    for label, action in sub_options:
        assert "fighter wing" not in label.lower()
        assert "bomber wing" not in label.lower()


def test_ai_observation_construction_catalog_excludes_strikecraft_wings():
    """Verify AI observation construction_templates and unit details omit strikecraft wings."""
    from game_ai.observation import _construction_catalog

    player = MockPlayer()
    unit = MockUnit()
    unit.owner = player
    constructor = Constructor(unit)
    unit.add_component(constructor)

    catalog = _construction_catalog([unit], player)
    template_names = [entry["template_name"] for entry in catalog]

    assert "FIGHTER_WING" not in template_names
    assert "BOMBER_WING" not in template_names


def test_ai_construct_command_validation_rejects_strikecraft_wings():
    """Verify AI command execution rejects construct command for strikecraft wings."""
    from tests.test_ai_order_contract_v2 import world, issue

    game, player, _, unit = world()
    unit.add_component(Constructor(unit))
    player.credits = 1000

    cmd = Command("construct", (unit.id,), template_name="FIGHTER_WING", position=(100, 100))
    result = issue(game, player, cmd)

    assert not result.accepted
    assert any(err.code == "invalid_value" for err in result.errors)


def test_strikecraft_bay_sole_construction_intact():
    """Verify that StrikecraftBayComponent constructs strikecraft wings properly."""
    carrier = MockUnit()
    carrier.owner.credits = 500
    bay = StrikecraftBayComponent(carrier, max_slots=2)
    carrier.add_component(bay)
    bay.build_wing_type = WingType.FIGHTER

    galaxy = MagicMock()
    mock_system = MagicMock()
    galaxy.systems = {"Sol": mock_system}
    carrier.in_galaxy = galaxy
    carrier.in_system = "Sol"
    carrier.in_hex = (0, 0)
    carrier.position = Position(0, 0)

    # First tick starts construction
    bay.update(galaxy)
    assert bay.constructing
    assert carrier.owner.credits == 350  # 500 - 150

    # Progress turn 1
    bay.update(galaxy)
    assert bay.constructing
    assert bay.construction_progress == 1

    # Progress turn 2 (completes)
    bay.update(galaxy)
    assert not bay.constructing
    assert len(bay.docked_units) == 1

    docked_wing = bay.docked_units[0]
    assert docked_wing.hull_size == HullSize.STRIKECRAFT_WING
    assert docked_wing.strikecraft_wing_component is not None
    assert docked_wing.strikecraft_wing_component.wing_type == WingType.FIGHTER
