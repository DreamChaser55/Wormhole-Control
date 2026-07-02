import pytest
from unittest.mock import MagicMock, patch
from entities import Unit, Player
from constants import HullSize, BLUE
from geometry import Position
from rendering.sector_renderer import SectorViewRenderer

def test_draw_sector_view_draws_lines_for_all_turn_player_units():
    # 1. Setup mock game, players, and renderer
    game = MagicMock()
    player1 = Player("Player 1", BLUE, is_human=True)
    player2 = Player("Player 2", (255, 0, 0), is_human=True)
    game.players = [player1, player2]
    game.current_player_index = 0  # Player 1's turn
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.selected_objects = []
    game.sector_view_mouse_hover_object = None
    game.is_dragging_selection_box = False

    renderer = SectorViewRenderer(game)
    renderer.screen = MagicMock()
    renderer.overlay_surface = MagicMock()

    # 2. Setup StarSystem and Hex
    system = MagicMock()
    game.galaxy.systems = {"Sol": system}
    hex_obj = MagicMock()
    system.hexes = {(0, 0): hex_obj}

    # 3. Create units with distinct positions
    # Unit 1: Owned by current turn player (Player 1), has move target, NOT selected/hovered
    unit1 = Unit(player1, Position(10, 10), (0, 0), "Sol", "Unit 1", HullSize.MEDIUM, game)
    from unit_components import Engines
    engines1 = Engines(unit1, speed=10)
    engines1.move_target = Position(50, 50)
    unit1.add_component(engines1)

    # Unit 2: Owned by other player (Player 2), has move target, NOT selected/hovered (should NOT draw lines)
    unit2 = Unit(player2, Position(20, 20), (0, 0), "Sol", "Unit 2", HullSize.MEDIUM, game)
    engines2 = Engines(unit2, speed=10)
    engines2.move_target = Position(50, 50)
    unit2.add_component(engines2)

    # Unit 3: Owned by other player (Player 2), has move target, IS selected (should draw lines)
    unit3 = Unit(player2, Position(30, 30), (0, 0), "Sol", "Unit 3", HullSize.MEDIUM, game)
    engines3 = Engines(unit3, speed=10)
    engines3.move_target = Position(50, 50)
    unit3.add_component(engines3)
    game.selected_objects = [unit3]

    hex_obj.celestial_bodies = []
    hex_obj.units = [unit1, unit2, unit3]

    # Patch pygame.draw functions and sector_coords_to_pixels to return the logical pos coordinates
    with patch("rendering.sector_renderer.pygame.draw.line") as mock_draw_line, \
         patch("rendering.sector_renderer.pygame.draw.circle") as mock_draw_circle, \
         patch("rendering.sector_renderer.pygame.draw.rect") as mock_draw_rect, \
         patch("rendering.sector_renderer.pygame.draw.polygon") as mock_draw_polygon, \
         patch("rendering.sector_renderer.sector_coords_to_pixels", side_effect=lambda p: p), \
         patch("rendering.sector_renderer.draw_shape") as mock_draw_shape, \
         patch("rendering.sector_renderer.pygame.font.Font") as mock_font, \
         patch("rendering.sector_renderer.pygame.mouse.get_pos", return_value=(0, 0)):

        renderer.draw_sector_view()

        # Extract start coordinate of drawn line calls (the 3rd argument in pygame.draw.line)
        starts = [call[0][2] for call in mock_draw_line.call_args_list]

        # Unit 1's starting position (10, 10) must be drawn
        assert (10, 10) in starts
        # Unit 3's starting position (30, 30) must be drawn (as it is selected)
        assert (30, 30) in starts
        # Unit 2's starting position (20, 20) must NOT be drawn (not turn player, not selected/hovered)
        assert (20, 20) not in starts
