from player_controller import PlayerController
"""Automated tests for unit context menu disambiguation when multiple units overlap under cursor."""
import pytest
from unittest.mock import MagicMock, patch
import pygame
import pygame_gui

from geometry import Position, Vector
from constants import HullSize
from entities import Unit
from input_processor import (
    InputProcessor,
    get_units_under_mouse,
    build_sector_unit_disambiguation_menu,
    build_sector_context_menu_options,
)
from gui.context_menu import (
    open_context_menu,
    close_context_menu,
    handle_button_index,
)


class MockPlayer:
    _counter = 1
    def __init__(self, name="Test Player", player_id=None, team_id=None):
        if player_id is not None:
            self.id = player_id
        else:
            self.id = MockPlayer._counter
            MockPlayer._counter += 1
        self.name = name
        self.controller = PlayerController.HUMAN
        self.team_id = team_id if team_id is not None else self.id

    def is_allied_with(self, other):
        if other is None:
            return False
        return getattr(self, 'team_id', None) == getattr(other, 'team_id', None)

    def is_enemy_of(self, other):
        if other is None:
            return False
        return not self.is_allied_with(other)


@pytest.fixture(autouse=True)
def setup_pygame():
    pygame.init()
    try:
        pygame.display.set_mode((1280, 720))
    except Exception:
        pass


def _create_mock_game():
    game = MagicMock()
    game.pending_ability = None
    player1 = MockPlayer("Player 1", player_id=1, team_id=1)
    player2 = MockPlayer("Player 2", player_id=2, team_id=2)
    game.players = [player1, player2]
    game.current_player_index = 0
    game.current_player = player1
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.view_mode = 'sector'
    game.sector_zoom = 1.0
    game.sector_pan_offset = Position(0, 0)
    game.is_unit_visible = MagicMock(return_value=True)

    system = MagicMock()
    hex_obj = MagicMock()
    hex_obj.units = []
    hex_obj.celestial_bodies = []
    hex_obj.minefields = []
    system.hexes = {(0, 0): hex_obj}
    game.galaxy = MagicMock()
    game.galaxy.systems = {"Sol": system}

    return game, player1, player2, hex_obj


def test_get_units_under_mouse_multiple_units():
    game, player1, player2, hex_obj = _create_mock_game()

    unit1 = Unit(owner=player1, position=Position(100, 100), in_hex=(0, 0), in_system="Sol", name="Unit A", hull_size=HullSize.MEDIUM, game=game)
    unit2 = Unit(owner=player2, position=Position(100, 100), in_hex=(0, 0), in_system="Sol", name="Unit B", hull_size=HullSize.LARGE, game=game)
    unit3 = Unit(owner=player1, position=Position(5000, 5000), in_hex=(0, 0), in_system="Sol", name="Far Unit", hull_size=HullSize.SMALL, game=game)
    hex_obj.units = [unit1, unit2, unit3]

    with patch('input_processor.hover_tracker.sector_coords_to_pixels', side_effect=lambda pos, zoom, pan: pos):
        with patch('input_processor.hover_tracker.sector_radius_to_pixels', return_value=30.0):
            # Click directly over Position(100, 100)
            matching = get_units_under_mouse(game, Position(100, 100))
            assert len(matching) == 2
            assert unit1 in matching
            assert unit2 in matching
            assert unit3 not in matching


def test_get_units_under_mouse_filters_invisible():
    game, player1, player2, hex_obj = _create_mock_game()

    unit1 = Unit(owner=player1, position=Position(100, 100), in_hex=(0, 0), in_system="Sol", name="Visible Unit", hull_size=HullSize.MEDIUM, game=game)
    unit2 = Unit(owner=player2, position=Position(100, 100), in_hex=(0, 0), in_system="Sol", name="Cloaked Unit", hull_size=HullSize.MEDIUM, game=game)
    hex_obj.units = [unit1, unit2]

    # Cloaked unit is invisible
    game.is_unit_visible = lambda u: u.name == "Visible Unit"

    with patch('input_processor.hover_tracker.sector_coords_to_pixels', side_effect=lambda pos, zoom, pan: pos):
        with patch('input_processor.hover_tracker.sector_radius_to_pixels', return_value=30.0):
            matching = get_units_under_mouse(game, Position(100, 100))
            assert len(matching) == 1
            assert matching[0] == unit1


def test_build_sector_unit_disambiguation_menu():
    game, player1, player2, hex_obj = _create_mock_game()

    # Actor unit selected by player 1
    actor = Unit(owner=player1, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Player Battleship", hull_size=HullSize.LARGE, game=game)
    from unit_components import Weapons, Turret, TurretType, TurretVariant
    weapons = Weapons(actor)
    weapons.turrets.append(Turret(TurretType.MASS_DRIVER, 10, 500, 2, actor, variant=TurretVariant.STANDARD))
    actor.add_component(weapons)
    game.selected_objects = [actor]

    unit_friendly = Unit(owner=player1, position=Position(100, 100), in_hex=(0, 0), in_system="Sol", name="Ally Frigate", hull_size=HullSize.SMALL, game=game)
    unit_enemy = Unit(owner=player2, position=Position(100, 100), in_hex=(0, 0), in_system="Sol", name="Enemy Cruiser", hull_size=HullSize.MEDIUM, game=game)

    options, target = build_sector_unit_disambiguation_menu(game, [unit_friendly, unit_enemy], Position(100, 100))

    assert target == [unit_friendly, unit_enemy]
    assert len(options) == 2

    # Verify first entry (Friendly Unit)
    label1, sub_data1 = options[0]
    assert "Ally Frigate" in label1
    assert "Player 1" in label1
    sub_opts1, sub_target1 = sub_data1
    assert sub_target1 == unit_friendly
    # Friendly options should have Protect, View Unit Info, etc.
    action_ids1 = [opt[1] for opt in sub_opts1 if isinstance(opt[1], str)]
    assert "protect_unit" in action_ids1
    assert "view_unit" in action_ids1

    # Verify second entry (Enemy Unit)
    label2, sub_data2 = options[1]
    assert "Enemy Cruiser" in label2
    assert "Player 2" in label2
    sub_opts2, sub_target2 = sub_data2
    assert sub_target2 == unit_enemy
    # Enemy options should have Attack Hull, View Unit Info, etc.
    action_ids2 = [opt[1] for opt in sub_opts2 if isinstance(opt[1], str)]
    assert "attack_unit" in action_ids2
    assert "view_unit" in action_ids2


def test_mouse_handler_right_click_triggers_disambiguation():
    game, player1, player2, hex_obj = _create_mock_game()

    unit1 = Unit(owner=player1, position=Position(100, 100), in_hex=(0, 0), in_system="Sol", name="Unit A", hull_size=HullSize.MEDIUM, game=game)
    unit2 = Unit(owner=player2, position=Position(100, 100), in_hex=(0, 0), in_system="Sol", name="Unit B", hull_size=HullSize.LARGE, game=game)
    hex_obj.units = [unit1, unit2]

    ip = InputProcessor(game)

    with patch('input_processor.mouse_handler.is_pixel_in_sector', return_value=True):
        with patch('input_processor.mouse_handler.pixels_to_sector_coords', return_value=Position(100, 100)):
            with patch('input_processor.mouse_handler.get_units_under_mouse', return_value=[unit1, unit2]):
                with patch.object(game.gui, 'open_context_menu') as mock_open:
                    ip.handle_mouse_click(3, Position(100, 100))
                    mock_open.assert_called_once()
                    args = mock_open.call_args[0]
                    opened_options = args[1]
                    assert len(opened_options) == 2
                    assert "Unit A" in opened_options[0][0]
                    assert "Unit B" in opened_options[1][0]


def test_disambiguation_submenu_navigation_selection_and_back():
    manager = pygame_gui.UIManager((1280, 720))
    gui = MagicMock()
    gui.screen_res = Vector(1280, 720)
    gui.manager = manager
    gui.context_menu_panel = None
    gui.context_menu_buttons = []
    gui.context_menu_options = []
    gui.context_menu_target = None
    gui.context_menu_submenus = {}
    gui.context_menu_parent_options = None
    gui.context_menu_parent_position = None
    gui.context_menu_anchor = None
    gui.context_menu_history = []

    unit_a = MagicMock(name="Unit A")
    unit_b = MagicMock(name="Unit B")

    options_a = [("Protect", "protect_unit"), ("View Info", "view_unit")]
    options_b = [("Attack Hull", "attack_unit"), ("View Info", "view_unit")]

    disambiguation_options = [
        ("Unit A (Player 1)", (options_a, unit_a)),
        ("Unit B (Player 2)", (options_b, unit_b)),
    ]

    click_pos = Position(400, 300)
    open_context_menu(gui, click_pos, disambiguation_options, target=[unit_a, unit_b])

    assert len(gui.context_menu_buttons) == 2
    assert 0 in gui.context_menu_submenus
    assert 1 in gui.context_menu_submenus

    # 1. Click Unit B (index 1) to enter Unit B's submenu
    action_drilldown = handle_button_index(gui, 1)
    assert action_drilldown == {'action': 'ui_handled'}
    assert gui.context_menu_target == unit_b
    assert len(gui.context_menu_options) == 3
    assert gui.context_menu_options[0] == ("Back", "__submenu_back__")
    assert gui.context_menu_options[1] == ("Attack Hull", "attack_unit")

    # 2. Click Back (index 0)
    action_back = handle_button_index(gui, 0)
    assert action_back == {'action': 'ui_handled'}
    assert len(gui.context_menu_options) == 2
    assert "Unit A" in gui.context_menu_options[0][0]
    assert "Unit B" in gui.context_menu_options[1][0]
    assert gui.context_menu_target == [unit_a, unit_b]

    # 3. Click Unit A (index 0) to enter Unit A's submenu
    action_drilldown_a = handle_button_index(gui, 0)
    assert action_drilldown_a == {'action': 'ui_handled'}
    assert gui.context_menu_target == unit_a
    assert gui.context_menu_options[1] == ("Protect", "protect_unit")

    # 4. Select "Protect" (index 1 in Unit A's submenu)
    action_protect = handle_button_index(gui, 1)
    assert action_protect == {
        'action': 'context_menu_select',
        'action_id': 'protect_unit',
        'target': unit_a
    }
    assert gui.context_menu_panel is None


def test_single_unit_falls_back_to_direct_menu():
    game, player1, player2, hex_obj = _create_mock_game()

    unit1 = Unit(owner=player1, position=Position(100, 100), in_hex=(0, 0), in_system="Sol", name="Sole Unit", hull_size=HullSize.MEDIUM, game=game)
    hex_obj.units = [unit1]

    ip = InputProcessor(game)

    with patch('input_processor.mouse_handler.is_pixel_in_sector', return_value=True):
        with patch('input_processor.mouse_handler.pixels_to_sector_coords', return_value=Position(100, 100)):
            with patch('input_processor.mouse_handler.get_units_under_mouse', return_value=[unit1]):
                with patch.object(game.gui, 'open_context_menu') as mock_open:
                    ip.handle_mouse_click(3, Position(100, 100))
                    mock_open.assert_called_once()
                    args = mock_open.call_args[0]
                    opened_options = args[1]
                    target = args[2]
                    # Directly opens unit1's context menu with target == unit1
                    assert target == unit1
                    action_ids = [opt[1] for opt in opened_options if isinstance(opt[1], str)]
                    assert "view_unit" in action_ids
