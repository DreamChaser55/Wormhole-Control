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
         patch("rendering.sector_renderer.pygame.draw.lines") as mock_draw_lines, \
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


def test_draw_sector_view_draws_four_corner_selection_brackets():
    # Setup mock game, player, and renderer
    game = MagicMock()
    player1 = Player("Player 1", BLUE, is_human=True)
    game.players = [player1]
    game.current_player_index = 0
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.sector_view_mouse_hover_object = None
    game.is_dragging_selection_box = False

    renderer = SectorViewRenderer(game)
    renderer.screen = MagicMock()
    renderer.overlay_surface = MagicMock()

    # Setup StarSystem and Hex
    system = MagicMock()
    game.galaxy.systems = {"Sol": system}
    hex_obj = MagicMock()
    system.hexes = {(0, 0): hex_obj}

    # Create selected Unit
    unit = Unit(player1, Position(10, 10), (0, 0), "Sol", "Unit 1", HullSize.MEDIUM, game)
    unit.max_hit_points = 0  # set to 0 to avoid extra healthbar draw lines
    game.selected_objects = [unit]
    hex_obj.celestial_bodies = []
    hex_obj.units = [unit]

    # Patch pygame.draw functions and sector_coords_to_pixels to return the logical pos coordinates
    with patch("rendering.sector_renderer.pygame.draw.line") as mock_draw_line, \
         patch("rendering.sector_renderer.pygame.draw.circle") as mock_draw_circle, \
         patch("rendering.sector_renderer.pygame.draw.lines") as mock_draw_lines, \
         patch("rendering.sector_renderer.pygame.draw.rect") as mock_draw_rect, \
         patch("rendering.sector_renderer.pygame.draw.polygon") as mock_draw_polygon, \
         patch("rendering.sector_renderer.sector_coords_to_pixels", side_effect=lambda p: p), \
         patch("rendering.sector_renderer.draw_shape") as mock_draw_shape, \
         patch("rendering.sector_renderer.pygame.font.Font") as mock_font:

        renderer.draw_sector_view()

        # Selection brackets should call pygame.draw.lines exactly 4 times (one for each corner)
        assert len(mock_draw_lines.call_args_list) == 4

        # Extract the coordinate list arguments from mock_draw_lines (the 4th argument)
        called_points_lists = [call[0][3] for call in mock_draw_lines.call_args_list]

        from constants import SECTOR_VIEW_BASE_ICON_SIZE, SECTOR_CIRCLE_RADIUS_IN_PX, SECTOR_CIRCLE_RADIUS_LOGICAL
        expected_pixel_radius = int(SECTOR_VIEW_BASE_ICON_SIZE * SECTOR_CIRCLE_RADIUS_IN_PX / SECTOR_CIRCLE_RADIUS_LOGICAL)
        r = expected_pixel_radius + 5
        tick_length = 10

        left = 10 - r
        right = 10 + r
        top = 10 - r
        bottom = 10 + r

        expected_corners = [
            [(left + tick_length, top), (left, top), (left, top + tick_length)],
            [(right - tick_length, top), (right, top), (right, top + tick_length)],
            [(left + tick_length, bottom), (left, bottom), (left, bottom - tick_length)],
            [(right - tick_length, bottom), (right, bottom), (right, bottom - tick_length)]
        ]

        # Verify that all expected corner paths are in the called_points_lists (regardless of order)
        for expected in expected_corners:
            assert expected in called_points_lists


def test_draw_sector_view_draws_turn_notches():
    # Setup mock game, player, and renderer
    game = MagicMock()
    player1 = Player("Player 1", BLUE, is_human=True)
    game.players = [player1]
    game.current_player_index = 0
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.sector_view_mouse_hover_object = None
    game.is_dragging_selection_box = False

    renderer = SectorViewRenderer(game)
    renderer.screen = MagicMock()
    renderer.overlay_surface = MagicMock()

    # Setup StarSystem and Hex
    system = MagicMock()
    game.galaxy.systems = {"Sol": system}
    hex_obj = MagicMock()
    system.hexes = {(0, 0): hex_obj}

    # Create Unit with engines
    unit = Unit(player1, Position(0, 0), (0, 0), "Sol", "Unit 1", HullSize.MEDIUM, game)
    unit.max_hit_points = 0  # avoid healthbar rendering
    
    from unit_components import Engines
    engines = Engines(unit, speed=10.0)
    # Give it a move target
    engines.move_target = Position(35.0, 0.0)
    unit.add_component(engines)
    
    hex_obj.celestial_bodies = []
    hex_obj.units = [unit]

    # Patch pygame.draw functions and sector_coords_to_pixels to return the logical pos coordinates
    with patch("rendering.sector_renderer.pygame.draw.line") as mock_draw_line, \
         patch("rendering.sector_renderer.pygame.draw.circle") as mock_draw_circle, \
         patch("rendering.sector_renderer.pygame.draw.lines") as mock_draw_lines, \
         patch("rendering.sector_renderer.pygame.draw.rect") as mock_draw_rect, \
         patch("rendering.sector_renderer.pygame.draw.polygon") as mock_draw_polygon, \
         patch("rendering.sector_renderer.sector_coords_to_pixels", side_effect=lambda p: p), \
         patch("rendering.sector_renderer.draw_shape") as mock_draw_shape, \
         patch("rendering.sector_renderer.pygame.font.Font") as mock_font:

        renderer.draw_sector_view()

        # Let's see the arguments for mock_draw_line.
        # The main movement line is drawn from (0,0) to (35,0).
        # The notches are drawn perpendicular to this line at intervals of 10.0.
        # Since the line is on the x-axis, the notches will be vertical lines at x=10, x=20, x=30.
        drawn_lines = [call[0] for call in mock_draw_line.call_args_list]
        
        found_notches = 0
        for draw_call in drawn_lines:
            # draw_call is (surface, color, p_start, p_end, width)
            p_start, p_end = draw_call[2], draw_call[3]
            if (p_start == (10, 4) and p_end == (10, -4)) or (p_start == (10, -4) and p_end == (10, 4)):
                found_notches += 1
            elif (p_start == (20, 4) and p_end == (20, -4)) or (p_start == (20, -4) and p_end == (20, 4)):
                found_notches += 1
            elif (p_start == (30, 4) and p_end == (30, -4)) or (p_start == (30, -4) and p_end == (30, 4)):
                found_notches += 1
                
        assert found_notches == 3


def test_system_view_wormhole_lines():
    # Setup mock game, player, and renderer
    game = MagicMock()
    game.current_system_name = "Sol"
    game.system_view_mouse_hover_hex = None
    game.selected_objects = []
    
    renderer = SystemViewRenderer(game)
    renderer.screen = MagicMock()
    renderer.screen.get_height.return_value = 720
    renderer.overlay_surface = MagicMock()

    # Setup StarSystem and Hex with a Wormhole
    system = MagicMock()
    system.name = "Sol"
    system.radius = 3
    
    hex_obj = MagicMock()
    from entities import Wormhole
    wh = Wormhole(in_hex=(3, 0), in_system="Sol", exit_system_name="Vega")
    hex_obj.celestial_bodies = [wh]
    hex_obj.units = []
    
    system.hexes = {(3, 0): hex_obj}
    game.galaxy.systems = {"Sol": system}
    
    # Mock hex_to_pixel, pygame.draw.line, pygame.draw.polygon, pygame.draw.circle, and pygame.font.Font
    with patch("rendering.system_renderer.hex_to_pixel") as mock_hex_to_pixel, \
         patch("rendering.system_renderer.pygame.draw.line") as mock_draw_line, \
         patch("rendering.system_renderer.pygame.draw.polygon") as mock_draw_polygon, \
         patch("rendering.system_renderer.pygame.draw.circle") as mock_draw_circle, \
         patch("rendering.system_renderer.pygame.font.Font") as mock_font:
         
         # Setup mock font behavior
         mock_font_instance = MagicMock()
         mock_font.return_value = mock_font_instance
         mock_text_surface = MagicMock()
         mock_font_instance.render.return_value = mock_text_surface
         mock_text_rect = MagicMock()
         mock_text_surface.get_rect.return_value = mock_text_rect
         
         # Mock positions:
         # center (0,0) is at (500, 500)
         # wormhole (3,0) is at (800, 500)
         mock_hex_to_pixel.side_effect = lambda q, r: Position(500, 500) if (q == 0 and r == 0) else Position(800, 500)
         
         renderer.draw_system_view()
         
         # The code should draw a line from (800, 500) to the calculated edge.
         # dx = 800 - 500 = 300, dy = 0. dist = 300.
         # ux = 1.0, uy = 0.0.
         # edge_radius = (3 + 0.5) * SQRT3 * HEX_SIZE.
         # Let's verify that a line was drawn with WORMHOLE_LINE_COLOR.
         assert mock_draw_line.call_count == 1
         call_args = mock_draw_line.call_args_list[0][0]
         # call_args: (surface, color, start_pos, end_pos, width)
         # Verify color is WORMHOLE_LINE_COLOR
         from constants import WORMHOLE_LINE_COLOR
         assert call_args[1] == WORMHOLE_LINE_COLOR
         # Verify start_pos is wormhole center (800, 500)
         assert call_args[2] == (800, 500)
         # Verify end_pos.x is greater than start_pos.x (since it extends outwards)
         assert call_args[3][0] > 800
         # Verify end_pos.y is exactly 500 (since dy = 0)
         assert call_args[3][1] == 500
         # Verify width is 2
         assert call_args[4] == 2

         # Verify font is created and text is rendered with destination name
         mock_font.assert_called_once()
         mock_font_instance.render.assert_called_once_with("Vega", True, WORMHOLE_LINE_COLOR)

         # Verify the text rect is correctly aligned based on ux > 0.3 (should be midleft)
         mock_text_surface.get_rect.assert_called_once()
         # Verify screen.blit was called to draw the text
         renderer.screen.blit.assert_called_once_with(mock_text_surface, mock_text_rect)


def test_draw_sector_view_patrol_order_path():
    # 1. Setup mock game, player, and renderer
    game = MagicMock()
    player1 = Player("Player 1", BLUE, is_human=True)
    game.players = [player1]
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

    # 3. Create Unit with Commander component and PatrolOrder
    unit = Unit(player1, Position(10, 10), (0, 0), "Sol", "Unit 1", HullSize.MEDIUM, game)
    unit.max_hit_points = 0  # avoid healthbar rendering
    
    commander = MagicMock()
    unit.components[Commander] = commander
    
    # Mock PatrolOrder
    patrol_order = MagicMock()
    patrol_order.order_type = OrderType.PATROL
    patrol_order.parameters = {
        "waypoints": [
            {"system_name": "Sol", "hex_coord": (0, 0), "position": Position(100, 10)},
            {"system_name": "Sol", "hex_coord": (0, 0), "position": Position(200, 10)}
        ]
    }
    patrol_order.start_position = Position(10, 10)
    patrol_order.start_system_name = "Sol"
    patrol_order.start_hex_coord = (0, 0)
    patrol_order.current_waypoint_index = 0
    
    # Add a MoveOrder sub-order (which should be skipped)
    sub_move = MagicMock()
    sub_move.order_type = OrderType.MOVE
    sub_move.parameters = {
        "destination_system_name": "Sol",
        "destination_hex_coord": (0, 0),
        "destination_position": Position(100, 10)
    }
    sub_move.sub_orders = []
    patrol_order.sub_orders = [sub_move]
    
    commander.current_order = patrol_order
    commander.orders_queue = []
    
    hex_obj.celestial_bodies = []
    hex_obj.units = [unit]

    # Patch pygame.draw functions and sector_coords_to_pixels to return the logical pos coordinates
    with patch("rendering.sector_renderer.pygame.draw.line") as mock_draw_line, \
         patch("rendering.sector_renderer.pygame.draw.circle") as mock_draw_circle, \
         patch("rendering.sector_renderer.pygame.draw.lines") as mock_draw_lines, \
         patch("rendering.sector_renderer.pygame.draw.rect") as mock_draw_rect, \
         patch("rendering.sector_renderer.pygame.draw.polygon") as mock_draw_polygon, \
         patch("rendering.sector_renderer.sector_coords_to_pixels", side_effect=lambda p: p), \
         patch("rendering.sector_renderer.draw_shape") as mock_draw_shape, \
         patch("rendering.sector_renderer.pygame.font.Font") as mock_font, \
         patch("rendering.sector_renderer.pygame.mouse.get_pos", return_value=(0, 0)):

        # CASE 1: current_waypoint_index = 0
        patrol_order.current_waypoint_index = 0
        renderer.draw_sector_view()
        
        # Drawn lines should start from unit (10, 10) to W1 (100, 10), then W1 -> W2 (200, 10), then W2 -> S (10, 10), then S -> W1 (100, 10).
        line_calls = [call[0] for call in mock_draw_line.call_args_list]
        draw_lines_coords = [(call[2], call[3]) for call in line_calls]
        
        # Verify the path is a closed loop starting at unit's current move target (100, 10)
        # Expected lines: (Unit -> W1), (W1 -> W2), (W2 -> S), (S -> W1)
        assert ((10.0, 10.0), (100.0, 10.0)) in draw_lines_coords
        assert ((100.0, 10.0), (200.0, 10.0)) in draw_lines_coords
        assert ((200.0, 10.0), (10.0, 10.0)) in draw_lines_coords
        assert ((10.0, 10.0), (100.0, 10.0)) in draw_lines_coords
        
        # Reset mock
        mock_draw_line.reset_mock()
        
        # CASE 2: current_waypoint_index = 1
        patrol_order.current_waypoint_index = 1
        renderer.draw_sector_view()
        
        line_calls = [call[0] for call in mock_draw_line.call_args_list]
        draw_lines_coords = [(call[2], call[3]) for call in line_calls]
        
        # Expected lines: (Unit -> W2), (W2 -> S), (S -> W1), (W1 -> W2)
        assert ((10.0, 10.0), (200.0, 10.0)) in draw_lines_coords
        assert ((200.0, 10.0), (10.0, 10.0)) in draw_lines_coords
        assert ((10.0, 10.0), (100.0, 10.0)) in draw_lines_coords
        assert ((100.0, 10.0), (200.0, 10.0)) in draw_lines_coords
