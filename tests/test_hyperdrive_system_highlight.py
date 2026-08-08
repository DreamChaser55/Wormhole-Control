"""Tests for hyperdrive inter-sector jump distance hexgrid highlight in System View."""
from unittest.mock import MagicMock, patch
import pytest
import pygame

from constants import BLUE, HullSize, HYPERDRIVE_RANGE_HEX_FILL_COLOR, MAX_UNIT_XP, XP_JUMP_RANGE_BONUS
from entities import Player, Unit
from geometry import Position
from rendering.system_renderer import SystemViewRenderer
from unit_components import Hyperdrive, HyperdriveType


@pytest.fixture
def system_renderer_setup():
    game = MagicMock()
    player = Player("Player 1", BLUE, is_human=True)
    game.players = [player]
    game.current_player_index = 0
    game.current_system_name = "Sol"
    game.view_mode = 'system'
    game.selected_unit_tab = 'components'
    game.selected_component_name = 'Hyperdrive'

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
    hd = Hyperdrive(unit, drive_type=HyperdriveType.BASIC, jump_range=5)
    unit.add_component(hd)
    game.selected_objects = [unit]

    renderer = SystemViewRenderer(game)
    renderer.screen = pygame.Surface((800, 600))
    renderer.overlay_surface = pygame.Surface((800, 600), pygame.SRCALPHA)

    return renderer, game, system, unit


def test_hyperdrive_jump_range_highlight_drawn_when_all_conditions_met(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_hyperdrive_jump_range_highlight(system)

        # Check hex polygon fill drawing for hexes within range (0,0), (1,0), (0,1), (5,5)
        assert mock_draw_polygon.called
        polygon_fill_colors = [call[0][1] for call in mock_draw_polygon.call_args_list]
        assert HYPERDRIVE_RANGE_HEX_FILL_COLOR in polygon_fill_colors
        # (10, 10) is distance 10 > jump_range 5, so it should not be drawn
        assert mock_draw_polygon.call_count == 4


def test_hyperdrive_jump_range_highlight_hidden_when_tab_is_basic_info(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    game.selected_unit_tab = 'basic_info'

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_hyperdrive_jump_range_highlight(system)
        mock_draw_polygon.assert_not_called()


def test_hyperdrive_jump_range_highlight_hidden_when_other_component_selected(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    game.selected_component_name = 'Commander'

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_hyperdrive_jump_range_highlight(system)
        mock_draw_polygon.assert_not_called()


def test_hyperdrive_jump_range_highlight_hidden_when_view_mode_not_system(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    game.view_mode = 'sector'

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_hyperdrive_jump_range_highlight(system)
        mock_draw_polygon.assert_not_called()


def test_hyperdrive_jump_range_highlight_hidden_for_unit_without_hyperdrive(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    unit.remove_component(Hyperdrive)

    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_hyperdrive_jump_range_highlight(system)
        mock_draw_polygon.assert_not_called()


def test_hyperdrive_jump_range_highlight_accounts_for_xp_bonus(system_renderer_setup):
    renderer, game, system, unit = system_renderer_setup
    # Add a hex at distance 6 (within effective range 6 when max XP gives +20% to range 5)
    system.hexes[(6, 0)] = MagicMock()

    # With 0 XP, distance 6 hex is out of range (base range = 5)
    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_hyperdrive_jump_range_highlight(system)
        count_base_xp = mock_draw_polygon.call_count

    # Max XP increases range from 5 to 6
    unit.experience_points = MAX_UNIT_XP
    with patch.object(pygame.draw, 'polygon') as mock_draw_polygon:
        renderer._draw_hyperdrive_jump_range_highlight(system)
        count_max_xp = mock_draw_polygon.call_count

    assert count_max_xp == count_base_xp + 1
