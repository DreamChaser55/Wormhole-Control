from player_controller import PlayerController
import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame
pygame.init()
pygame.display.set_mode((1280, 720))
from unittest.mock import MagicMock
from geometry import Position
from entities import Minefield, Player
from unit_components import MinefieldType
from input_processor import InputProcessor
from sector_utils import get_minefield_dot_pixel_positions, sector_coords_to_pixels
from galaxy import Galaxy, StarSystem, Hex


class MockPlayer:
    _counter = 1
    def __init__(self, name="Player 1", color=(0, 255, 0), player_id=None, team_id=None):
        if player_id is not None:
            self.id = player_id
        else:
            self.id = MockPlayer._counter
            MockPlayer._counter += 1
        self.name = name
        self.controller = PlayerController.HUMAN
        self.team_id = team_id if team_id is not None else self.id
        self.color = color


class MockGame:
    def __init__(self):
        self.view_mode = "sector"
        self.game_started = True
        self.current_system_name = "Sol"
        self.current_sector_coord = (0, 0)
        self.sector_zoom = 1.0
        self.sector_pan_offset = Position(0, 0)
        self.players = [MockPlayer("Player 1", (0, 255, 0)), MockPlayer("Player 2", (255, 0, 0))]
        self.current_player_index = 0
        self.selected_objects = []
        self.sidebar_needs_update = False
        self.sector_view_mouse_hover_object = None
        self.galaxy = Galaxy(num_systems=0)
        sys = StarSystem("Sol", Position(0, 0))
        sys.hexes[(0, 0)] = Hex(0, 0, "Sol")
        self.galaxy.systems["Sol"] = sys
        self.gui = MagicMock()
        self.gui.is_mouse_over_context_menu.return_value = False
        self.visibility = None

    def is_unit_visible(self, unit):
        return True

    def is_minefield_visible(self, minefield):
        if self.visibility is None:
            return True
        return minefield.owner == self.players[self.current_player_index]


def test_anti_ship_minefield_dot_hover_and_click_selection():
    game = MockGame()
    p1 = game.players[0]
    hex_obj = game.galaxy.systems["Sol"].hexes[(0, 0)]

    # Create Anti-Ship minefield at logical (0, 0)
    mf_ship = Minefield(
        owner=p1,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        minefield_type=MinefieldType.ANTI_SHIP,
        mines_remaining=5
    )
    hex_obj.add_minefield(mf_ship)

    input_proc = InputProcessor(game)

    # Get dot positions
    dot_positions = get_minefield_dot_pixel_positions(mf_ship.position, mf_ship.mines_remaining, game.sector_zoom, game.sector_pan_offset)
    assert len(dot_positions) == 5

    # Mouse over the first dot
    first_dot = Position(dot_positions[0][0], dot_positions[0][1])
    input_proc.update_hover_states(first_dot)
    assert game.sector_view_mouse_hover_object == mf_ship

    # Left-click on the first dot selects the minefield
    input_proc.handle_mouse_click(1, first_dot)
    assert game.selected_objects == [mf_ship]
    assert game.sidebar_needs_update is True


def test_anti_strikecraft_minefield_diamond_hover_and_click_selection():
    game = MockGame()
    p1 = game.players[0]
    hex_obj = game.galaxy.systems["Sol"].hexes[(0, 0)]

    # Create Anti-Strikecraft minefield at logical (50, 50)
    mf_sc = Minefield(
        owner=p1,
        position=Position(50, 50),
        in_hex=(0, 0),
        in_system="Sol",
        minefield_type=MinefieldType.ANTI_STRIKECRAFT,
        mines_remaining=3
    )
    hex_obj.add_minefield(mf_sc)

    input_proc = InputProcessor(game)

    # Get dot positions
    dot_positions = get_minefield_dot_pixel_positions(mf_sc.position, mf_sc.mines_remaining, game.sector_zoom, game.sector_pan_offset)
    assert len(dot_positions) == 3

    # Mouse over the second diamond
    second_dot = Position(dot_positions[1][0], dot_positions[1][1])
    input_proc.update_hover_states(second_dot)
    assert game.sector_view_mouse_hover_object == mf_sc

    # Left-click on the second diamond selects the minefield
    input_proc.handle_mouse_click(1, second_dot)
    assert game.selected_objects == [mf_sc]
    assert game.sidebar_needs_update is True


def test_invisible_enemy_minefield_not_selectable_by_clicking_dots():
    game = MockGame()
    p1 = game.players[0]
    p2 = game.players[1]
    game.visibility = MagicMock()  # Enable fog-of-war check
    hex_obj = game.galaxy.systems["Sol"].hexes[(0, 0)]

    # Enemy minefield
    mf_enemy = Minefield(
        owner=p2,
        position=Position(0, 0),
        in_hex=(0, 0),
        in_system="Sol",
        minefield_type=MinefieldType.ANTI_SHIP,
        mines_remaining=5
    )
    hex_obj.add_minefield(mf_enemy)

    input_proc = InputProcessor(game)
    dot_positions = get_minefield_dot_pixel_positions(mf_enemy.position, mf_enemy.mines_remaining, game.sector_zoom, game.sector_pan_offset)
    target_pos = Position(dot_positions[0][0], dot_positions[0][1])

    # Mouse over dot position
    input_proc.update_hover_states(target_pos)
    assert game.sector_view_mouse_hover_object is None

    # Click position
    input_proc.handle_mouse_click(1, target_pos)
    assert game.selected_objects == []
