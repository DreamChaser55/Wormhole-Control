from unittest.mock import MagicMock, patch
from entities import Unit, Player, OrderType
from constants import HullSize, BLUE
from geometry import Position
from unit_components import Commander
from rendering.sector_renderer import SectorViewRenderer
from rendering.system_renderer import SystemViewRenderer
from rendering.galaxy_renderer import GalaxyViewRenderer

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
        # Unit 3's starting position (30, 30) must NOT be drawn (as it is owned by a different player, even though selected)
        assert (30, 30) not in starts
        # Unit 2's starting position (20, 20) must NOT be drawn (not turn player, not selected/hovered)
        assert (20, 20) not in starts


def test_system_view_order_lines_only_for_active_player():
    game = MagicMock()
    player1 = Player("Player 1", BLUE, is_human=True)
    player2 = Player("Player 2", (255, 0, 0), is_human=True)
    game.players = [player1, player2]
    game.current_player_index = 0  # Player 1's turn
    game.current_system_name = "Sol"
    game.system_view_mouse_hover_hex = None

    renderer = SystemViewRenderer(game)
    renderer.screen = MagicMock()
    renderer.overlay_surface = MagicMock()

    system = MagicMock()
    system.name = "Sol"
    system.hexes = {(0, 0): MagicMock()}
    system.get_units_in_hex.return_value = []
    game.galaxy.systems = {"Sol": system}

    # Unit 1: Player 1 (active player), selected, has order
    unit1 = Unit(player1, Position(10, 10), (0, 0), "Sol", "Unit 1", HullSize.MEDIUM, game)
    commander1 = MagicMock()
    order1 = MagicMock()
    order1.order_type = OrderType.MOVE
    order1.parent_order = None
    order1.sub_orders = []
    order1.parameters = {"destination_system_name": "Sol", "destination_hex_coord": (1, 1)}
    commander1.current_order = order1
    commander1.orders_queue = []
    unit1.components[Commander] = commander1

    # Unit 2: Player 2 (inactive player), selected, has order
    unit2 = Unit(player2, Position(20, 20), (0, 0), "Sol", "Unit 2", HullSize.MEDIUM, game)
    commander2 = MagicMock()
    order2 = MagicMock()
    order2.order_type = OrderType.MOVE
    order2.parent_order = None
    order2.sub_orders = []
    order2.parameters = {"destination_system_name": "Sol", "destination_hex_coord": (2, 2)}
    commander2.current_order = order2
    commander2.orders_queue = []
    unit2.components[Commander] = commander2

    game.selected_objects = [unit1, unit2]

    # Patch system_renderer drawing functions
    with patch("rendering.system_renderer.pygame.draw.line") as mock_draw_line, \
         patch("rendering.system_renderer.pygame.draw.circle") as mock_draw_circle, \
         patch("rendering.system_renderer.hex_to_pixel", side_effect=lambda q, r: Position(q * 10, r * 10)):

         renderer._draw_system_view_order_lines(system)

         # Extract end coordinate of drawn line calls (the 4th argument in pygame.draw.line)
         ends = [call[0][3] for call in mock_draw_line.call_args_list]

         # Unit 1's destination (1, 1) -> (10, 10) in hex coords must be drawn
         assert (10, 10) in ends
         # Unit 2's destination (2, 2) -> (20, 20) in hex coords must NOT be drawn (since Player 2 is not active)
         assert (20, 20) not in ends


def test_galaxy_view_order_lines_only_for_active_player():
    game = MagicMock()
    player1 = Player("Player 1", BLUE, is_human=True)
    player2 = Player("Player 2", (255, 0, 0), is_human=True)
    game.players = [player1, player2]
    game.current_player_index = 0  # Player 1's turn
    game.current_system_name = "Sol"

    renderer = GalaxyViewRenderer(game)
    renderer.screen = MagicMock()
    renderer.overlay_surface = MagicMock()

    sol_system = MagicMock()
    sol_system.name = "Sol"
    sol_system.position = Position(0, 0)

    proxima_system = MagicMock()
    proxima_system.name = "Proxima"
    proxima_system.position = Position(100, 100)

    game.galaxy.systems = {"Sol": sol_system, "Proxima": proxima_system}

    # Unit 1: Player 1 (active player), selected, has reach waypoint order
    unit1 = Unit(player1, Position(0, 0), (0, 0), "Sol", "Unit 1", HullSize.MEDIUM, game)
    commander1 = MagicMock()
    order1 = MagicMock()
    order1.order_type = OrderType.REACH_WAYPOINT
    order1.parent_order = None
    order1.sub_orders = []
    order1.parameters = {"destination_system_name": "Proxima"}
    commander1.current_order = order1
    commander1.orders_queue = []
    unit1.components[Commander] = commander1

    # Unit 2: Player 2 (inactive player), selected, has reach waypoint order
    unit2 = Unit(player2, Position(0, 0), (0, 0), "Sol", "Unit 2", HullSize.MEDIUM, game)
    commander2 = MagicMock()
    order2 = MagicMock()
    order2.order_type = OrderType.REACH_WAYPOINT
    order2.parent_order = None
    order2.sub_orders = []
    order2.parameters = {"destination_system_name": "Proxima"}
    commander2.current_order = order2
    commander2.orders_queue = []
    unit2.components[Commander] = commander2

    game.selected_objects = [unit1, unit2]

    # Patch galaxy_renderer drawing functions
    with patch("rendering.galaxy_renderer.pygame.draw.line") as mock_draw_line, \
         patch("rendering.galaxy_renderer.logical_to_screen_galaxy", side_effect=lambda pos, rect: pos):

         renderer.draw_galaxy_view_order_lines()

         # Since Unit 1 targets Proxima (100, 100) and is active, it must be drawn.
         # If both units were drawn, we would have 6 line calls (3 lines per unit).
         # Since only Unit 1 is active, we expect 3 line calls.
         assert len(mock_draw_line.call_args_list) == 3
