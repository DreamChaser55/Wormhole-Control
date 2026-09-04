"""Unit tests verifying that non-solid celestial bodies (fields, storms, nebulae)
cannot be selected by clicking inside their radius in sector view, and can only
be selected via the sidebar of the hex they are in.
"""
import pytest
from unittest.mock import MagicMock
from constants import (
    PlanetType, StarType, NebulaType, StormType, FieldDensity,
    SECTOR_CIRCLE_RADIUS_LOGICAL, SECTOR_CIRCLE_RADIUS_IN_PX
)
from geometry import Position
from entities import (
    Star, Planet, Moon, Wormhole, ColonizableAsteroid, MetalAsteroid, Comet,
    AsteroidField, IceField, DebrisField, Nebula, Storm,
    NON_SOLID_CELESTIAL_BODIES, Player
)
from galaxy import Galaxy, StarSystem, Hex
from input_processor import InputProcessor
from game import Game


def test_is_solid_attribute_on_celestial_bodies():
    """Verify is_solid is False for fields, storms, nebulae, and True for solid bodies."""
    # Non-solid
    debris = DebrisField(in_hex=(0, 0), in_system="Sol")
    asteroid_field = AsteroidField(in_hex=(0, 0), in_system="Sol")
    ice_field = IceField(in_hex=(0, 0), in_system="Sol")
    nebula = Nebula(in_hex=(0, 0), in_system="Sol", nebula_type=NebulaType.HYDROGEN)
    storm = Storm(in_hex=(0, 0), in_system="Sol", storm_type=StormType.PLASMA)

    for non_solid in (debris, asteroid_field, ice_field, nebula, storm):
        assert non_solid.is_solid is False
        assert isinstance(non_solid, NON_SOLID_CELESTIAL_BODIES)

    # Solid bodies
    star = Star(in_system="Sol", star_type=StarType.G_TYPE)
    planet = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.TERRAN)
    moon = Moon(in_hex=(0, 0), in_system="Sol")
    wormhole = Wormhole(in_hex=(0, 0), in_system="Sol", exit_system_name="Alpha")
    col_asteroid = ColonizableAsteroid(in_hex=(0, 0), in_system="Sol")
    metal_asteroid = MetalAsteroid(in_hex=(0, 0), in_system="Sol")
    comet = Comet(in_hex=(0, 0), in_system="Sol")

    for solid in (star, planet, moon, wormhole, col_asteroid, metal_asteroid, comet):
        assert solid.is_solid is True
        assert not isinstance(solid, NON_SOLID_CELESTIAL_BODIES)


def _setup_mock_game_in_sector():
    game = MagicMock()
    game.view_mode = 'sector'
    game.current_system_name = 'Sol'
    game.current_sector_coord = (0, 0)
    game.sector_zoom = 1.0
    game.sector_pan_offset = Position(0, 0)
    game.selected_objects = []
    game.sector_view_mouse_hover_object = None
    game.is_unit_visible = MagicMock(return_value=True)
    game.is_minefield_visible = MagicMock(return_value=True)
    game.pending_ability = None

    galaxy = Galaxy(num_systems=0)
    system = StarSystem("Sol", Position(0, 0))
    hex_obj = Hex(0, 0, "Sol")
    system.hexes[(0, 0)] = hex_obj
    galaxy.systems["Sol"] = system
    game.galaxy = galaxy

    p1 = Player(name="Player 1", color=(0, 100, 255))
    game.players = [p1]
    game.current_player_index = 0
    game.current_player = p1

    gui = MagicMock()
    gui.is_mouse_over_context_menu = MagicMock(return_value=False)
    gui.is_mouse_over_gui_panels = MagicMock(return_value=False)
    game.gui = gui

    return game, hex_obj, gui


def test_sector_hover_ignores_non_solid_celestial_bodies():
    """Non-solid celestial bodies (fields, storms, nebulae) must never be hovered in sector view."""
    game, hex_obj, gui = _setup_mock_game_in_sector()

    debris = DebrisField(in_hex=(0, 0), in_system="Sol")
    debris.id = 101
    nebula = Nebula(in_hex=(0, 0), in_system="Sol", nebula_type=NebulaType.HYDROGEN)
    nebula.id = 102
    storm = Storm(in_hex=(0, 0), in_system="Sol", storm_type=StormType.PLASMA)
    storm.id = 103
    hex_obj.celestial_bodies = [debris, nebula, storm]

    input_proc = InputProcessor(game)

    # Mouse at center of screen (where logical position 0,0 maps to)
    from sector_utils import sector_coords_to_pixels
    center_px = sector_coords_to_pixels(Position(0, 0), game.sector_zoom, game.sector_pan_offset)

    input_proc.update_hover_states(center_px)
    assert game.sector_view_mouse_hover_object is None


def test_sector_click_does_not_select_non_solid_celestial_bodies():
    """Clicking inside the radius of non-solid bodies must NOT select them."""
    game, hex_obj, gui = _setup_mock_game_in_sector()

    nebula = Nebula(in_hex=(0, 0), in_system="Sol", nebula_type=NebulaType.HYDROGEN)
    nebula.id = 102
    hex_obj.celestial_bodies = [nebula]

    input_proc = InputProcessor(game)
    from sector_utils import sector_coords_to_pixels
    center_px = sector_coords_to_pixels(Position(0, 0), game.sector_zoom, game.sector_pan_offset)

    # Hover and left-click inside nebula
    input_proc.update_hover_states(center_px)
    input_proc.handle_mouse_click(1, center_px)

    # Should remain unselected (empty)
    assert game.selected_objects == []

    # Right-click inside nebula should open context menu targeting Position, not the nebula
    input_proc.handle_mouse_click(3, center_px)
    gui.open_context_menu.assert_called_once()
    target_arg = gui.open_context_menu.call_args[0][2]
    assert isinstance(target_arg, Position)
    assert target_arg != nebula


def test_solid_celestial_bodies_remain_hoverable_and_clickable():
    """Solid bodies like planets remain fully hoverable and selectable by clicking."""
    game, hex_obj, gui = _setup_mock_game_in_sector()

    planet = Planet(in_hex=(0, 0), in_system="Sol", planet_type=PlanetType.TERRAN)
    planet.id = 201
    planet.position = Position(0, 0)
    hex_obj.celestial_bodies = [planet]

    input_proc = InputProcessor(game)
    from sector_utils import sector_coords_to_pixels
    center_px = sector_coords_to_pixels(Position(0, 0), game.sector_zoom, game.sector_pan_offset)

    input_proc.update_hover_states(center_px)
    assert game.sector_view_mouse_hover_object == planet

    input_proc.handle_mouse_click(1, center_px)
    assert game.selected_objects == [planet]


def test_non_solid_celestial_bodies_selectable_via_hex_sidebar():
    """Non-solid celestial bodies can be selected via the hex sidebar."""
    game, hex_obj, gui = _setup_mock_game_in_sector()

    debris = DebrisField(in_hex=(0, 0), in_system="Sol")
    debris.id = 301
    debris.name = "Debris Field 301"
    nebula = Nebula(in_hex=(0, 0), in_system="Sol", nebula_type=NebulaType.HYDROGEN)
    nebula.id = 302
    nebula.name = "Hydrogen Nebula 302"
    hex_obj.celestial_bodies = [debris, nebula]
    game.galaxy.systems["Sol"].celestial_bodies_by_id[debris.id] = debris
    game.galaxy.systems["Sol"].celestial_bodies_by_id[nebula.id] = nebula

    # When hex is selected
    game.selected_objects = [hex_obj]
    game.sidebar_needs_update = True
    Game.update_side_bar_content(game)

    gui.update_side_bar_content.assert_called_once()
    payload = gui.update_side_bar_content.call_args[0][0]

    # Verify buttons for debris and nebula exist
    body_buttons = [item for item in payload if item.get('type') == 'button' and item.get('action_id') == 'select_celestial_body']
    assert len(body_buttons) == 2
    assert body_buttons[0]['target_data'] == 301
    assert body_buttons[1]['target_data'] == 302

    # Click nebula button via GUI action
    Game.handle_gui_action(game, {'action': 'select_celestial_body', 'body_id': 302})
    assert game.selected_objects == [nebula]
    assert game.sidebar_needs_update is True

    # Check celestial body panel has "◀ Back to Hex" button
    gui.update_side_bar_content.reset_mock()
    Game.update_side_bar_content(game)
    gui.update_side_bar_content.assert_called_once()
    body_panel = gui.update_side_bar_content.call_args[0][0]

    back_btn = next((b for b in body_panel if b.get('type') == 'button' and b.get('action_id') == 'select_hex'), None)
    assert back_btn is not None
    assert back_btn['target_data'] == (0, 0)

    # Click "◀ Back to Hex"
    Game.handle_gui_action(game, {'action': 'select_hex', 'hex_coord': (0, 0)})
    assert game.selected_objects == [hex_obj]


def test_sector_view_sidebar_defaults_to_current_hex_when_nothing_selected():
    """When in sector view and nothing is selected, sidebar displays the current hex panel."""
    game, hex_obj, gui = _setup_mock_game_in_sector()

    storm = Storm(in_hex=(0, 0), in_system="Sol", storm_type=StormType.MAGNETIC)
    storm.id = 401
    hex_obj.celestial_bodies = [storm]

    # Empty selection in sector view
    game.selected_objects = []
    game.sidebar_needs_update = True

    Game.update_side_bar_content(game)
    gui.update_side_bar_content.assert_called_once()
    payload = gui.update_side_bar_content.call_args[0][0]

    # It should display the hex panel containing the storm button
    storm_btn = next((b for b in payload if b.get('type') == 'button' and b.get('action_id') == 'select_celestial_body'), None)
    assert storm_btn is not None
    assert storm_btn['target_data'] == 401
