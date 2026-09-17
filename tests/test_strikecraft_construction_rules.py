"""
tests/test_strikecraft_construction_rules.py

Verifies that strikecraft wings are excluded from constructor units (ConstructorComponent),
human Construct context menus, and AI interfaces (observation catalog, rules, and command validation),
and confirms that strikecraft wings are constructed solely by units with a StrikecraftBayComponent.
"""
from display_config import DisplayConfig
from unittest.mock import MagicMock
from constants import HullSize
from geometry import Position
from domain.units import Unit
from unit_components.constructor import Constructor
from unit_components.strikecraft import StrikecraftBayComponent
from unit_components.enums import WingType
from unit_orders.construction import ConstructOrder
from unit_orders.base import OrderStatus
from unit_templates import register_template, unregister_template
from game_ai.contracts import Command
from tests.support.units import ComponentUnit, ComponentPlayer


def test_constructor_buildable_units_excludes_strikecraft_wings():
    """Verify buildable_units property excludes default and custom strikecraft wings."""
    unit = ComponentUnit()
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
    unit = ComponentUnit()
    constructor = Constructor(unit)
    unit.add_component(constructor)

    assert constructor.can_build("FIGHTER_WING") is None
    assert constructor.can_build("BOMBER_WING") is None

    # Valid non-strikecraft templates should still be buildable
    assert constructor.can_build("SHIPYARD_MK1") is not None
    assert constructor.can_build("CONSTRUCTOR_MK1") is not None


def test_construct_order_fails_for_strikecraft_wings():
    """Verify that issuing a ConstructOrder for a strikecraft wing fails."""
    unit = ComponentUnit()
    constructor = Constructor(unit)
    unit.add_component(constructor)

    player = ComponentPlayer()
    player.id = unit.owner.id
    player.credits = 1000
    unit.game.players = [player]
    unit.owner = player

    order = ConstructOrder(unit, {
        "target_system_name": unit.in_system,
        "target_hex_coord": unit.in_hex,
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
    from domain.players import Player

    game = MagicMock()
    game.display_config = DisplayConfig()
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
    assert ("Construct...", "open_unit_catalog") in options
    assert not any(isinstance(action, str) and action.startswith('construct_') for _, action in options)


def test_ai_observation_construction_catalog_excludes_strikecraft_wings():
    """Verify AI observation construction_templates and unit details omit strikecraft wings."""
    from game_ai.observation import _construction_catalog

    player = ComponentPlayer()
    unit = ComponentUnit()
    unit.owner = player
    constructor = Constructor(unit)
    unit.add_component(constructor)

    catalog = _construction_catalog([unit], player)
    template_names = [entry["template_name"] for entry in catalog]

    assert "FIGHTER_WING" not in template_names
    assert "BOMBER_WING" not in template_names


def test_ai_construct_command_validation_rejects_strikecraft_wings():
    """Verify AI command execution rejects construct command for strikecraft wings."""
    from tests.support.commands import world, issue

    game, player, _, unit = world()
    unit.add_component(Constructor(unit))
    player.credits = 1000

    cmd = Command("construct", (unit.id,), template_name="FIGHTER_WING", position=(100, 100), system_name=unit.in_system, hex_coord=unit.in_hex)
    result = issue(game, player, cmd)

    assert not result.accepted
    assert any(err.code == "invalid_value" for err in result.errors)


def test_strikecraft_bay_sole_construction_intact():
    """Verify that StrikecraftBayComponent constructs strikecraft wings properly."""
    carrier = ComponentUnit()
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
    from unit_templates import UNIT_TEMPLATES
    assert carrier.owner.credits == 500 - UNIT_TEMPLATES["FIGHTER_WING"]["build_cost"]

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


def test_construct_catalog_window_excludes_strikecraft_wings(pygame_context):
    """Verify that UnitCatalogWindow and catalog_entries exclude strikecraft wings."""
    from gui.unit_catalog_window import UnitCatalogWindow, catalog_entries
    from gui.theme_loader import build_ui_manager
    from types import SimpleNamespace
    from geometry import Vector
    from unit_templates import UNIT_TEMPLATES

    entries = catalog_entries(UNIT_TEMPLATES)
    assert not any(e['template_name'] in ('FIGHTER_WING', 'BOMBER_WING') for e in entries)
    assert not any(e['hull_size'] == 'STRIKECRAFT_WING' or e['kind'] == 'wing' for e in entries)

    # Test with custom strikecraft wing template
    custom_name = "CUSTOM_ASSAULT_WING"
    register_template(custom_name, {
        "name": "Custom Assault",
        "hull_size": HullSize.STRIKECRAFT_WING,
        "build_time": 2,
        "build_cost": 180,
    })
    try:
        custom_entries = catalog_entries(UNIT_TEMPLATES)
        assert not any(e['template_name'] == custom_name for e in custom_entries)
    finally:
        unregister_template(custom_name)

    # Verify UI window dropdown options and entries
    from tests.support.campaigns import campaign, ship
    game = campaign()
    builder = ship(game, "Constructor Ship", owner=0, hull=HullSize.MEDIUM)
    builder.add_component(Constructor(builder))
    manager = build_ui_manager(DisplayConfig(1280, 720))
    gui = SimpleNamespace(game_instance=game, screen_res=Vector(1280, 720), manager=manager)
    gui.display_config = DisplayConfig(1280, 720)
    window = UnitCatalogWindow(gui, [builder], Position(200, 200), system_name=([builder])[0].in_system, hex_coord=([builder])[0].in_hex)
    try:
        kind_options = [opt[0] if isinstance(opt, tuple) else opt for opt in window.kind.options_list]
        hull_options = [opt[0] if isinstance(opt, tuple) else opt for opt in window.hull.options_list]
        assert 'wing' not in kind_options
        assert 'STRIKECRAFT_WING' not in hull_options
        assert not any(e['template_name'] in ('FIGHTER_WING', 'BOMBER_WING') for e in window.entries.values())
        assert not any(e['hull_size'] == 'STRIKECRAFT_WING' or e['kind'] == 'wing' for e in window.entries.values())
    finally:
        window.kill()
        manager.clear_and_reset()

