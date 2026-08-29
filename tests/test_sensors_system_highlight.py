from player_controller import PlayerController
"""Tests for sensors inter-sector range hexgrid highlight in System View."""
from unittest.mock import MagicMock, patch
import pytest
import pygame

from constants import BLUE, HullSize, SENSOR_RANGE_HEX_FILL_COLOR, DARK_RED
from entities import Player, Unit
from geometry import Position
from rendering.system_renderer import SystemViewRenderer
from unit_components import Sensors


@pytest.fixture
def system_renderer_setup():
    game = MagicMock()
    player = Player("Player 1", BLUE, controller=PlayerController.HUMAN)
    game.players = [player]
    game.current_player_index = 0
    game.current_system_name = "Sol"
    game.view_mode = 'system'
    game.selected_unit_tab = 'components'
    game.selected_component_name = 'Sensors'

    system = MagicMock()
    system.name = "Sol"
    system.hexes = {
        (0, 0): MagicMock(),
        (1, 0): MagicMock(),
        (0, 1): MagicMock(),
        (3, 2): MagicMock(),
        (10, 10): MagicMock()
    }
    game.galaxy.systems = {"Sol": system}

    unit = Unit(player, Position(0, 0), (0, 0), "Sol", "Scout Ship", HullSize.MEDIUM, game)
    sensors = Sensors(unit, short_range_radius=2000.0, long_range_hexes=5)
    unit.add_component(sensors)
    game.selected_objects = [unit]

    renderer = SystemViewRenderer(game)
    renderer.screen = pygame.Surface((800, 600))
    renderer.overlay_surface = pygame.Surface((800, 600), pygame.SRCALPHA)

    return renderer, game, system, unit


def test_sensors_range_highlight_drawn_when_all_conditions_met(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_sensors_range_highlight(system)

        # Check hex polygon fill drawing for hexes within range (0,0), (1,0), (0,1), (3,2)
        assert mock_draw_polygon.called
        polygon_fill_colors = [call[0][1] for call in mock_draw_polygon.call_args_list]
        assert SENSOR_RANGE_HEX_FILL_COLOR in polygon_fill_colors
        # (10, 10) is distance 10 > long_range_hexes 5, so it should not be drawn
        assert mock_draw_polygon.call_count == 4


def test_sensors_range_highlight_hidden_when_tab_is_basic_info(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    game.selected_unit_tab = 'basic_info'

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_sensors_range_highlight(system)
        mock_draw_polygon.assert_not_called()


def test_sensors_range_highlight_hidden_when_other_component_selected(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    game.selected_component_name = 'Commander'

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_sensors_range_highlight(system)
        mock_draw_polygon.assert_not_called()


def test_sensors_range_highlight_hidden_when_view_mode_not_system(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    game.view_mode = 'sector'

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_sensors_range_highlight(system)
        mock_draw_polygon.assert_not_called()


def test_sensors_range_highlight_hidden_for_unit_without_sensors(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    unit.remove_component(Sensors)

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_sensors_range_highlight(system)
        mock_draw_polygon.assert_not_called()


def test_sensors_range_highlight_hidden_when_sensors_destroyed(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    unit.sensors_component.current_hit_points = 0

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_sensors_range_highlight(system)
        mock_draw_polygon.assert_not_called()


def test_sensors_range_highlight_hidden_when_long_range_hexes_zero(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    unit.sensors_component.long_range_hexes = 0

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_sensors_range_highlight(system)
        mock_draw_polygon.assert_not_called()


def test_enemy_presence_dark_red_hex_highlight(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    game.system_view_mouse_hover_hex = None

    target_hex_obj = system.hexes[(1, 0)]
    hidden_enemy_unit = MagicMock()
    target_hex_obj.units = [hidden_enemy_unit]
    game.is_unit_visible.side_effect = lambda u: u != hidden_enemy_unit
    game.hex_has_presence.side_effect = lambda sys_name, h_coord: h_coord == (1, 0)

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer.draw_system_view()

        # Verify that DARK_RED fill polygon was drawn for hex (1, 0)
        draw_colors = [call[0][1] for call in mock_draw_polygon.call_args_list]
        assert DARK_RED in draw_colors
