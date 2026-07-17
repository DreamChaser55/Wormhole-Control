import pytest
from unittest.mock import MagicMock, patch
from sector_utils import sector_coords_to_pixels, pixels_to_sector_coords
from geometry import Position
from game import Game
from input_processor import InputProcessor
import pygame

@pytest.fixture(autouse=True)
def mock_pygame_keys():
    # Provide a list/dict that returns False for all keys to prevent
    # pygame.error: video system not initialized.
    mock_keys = [False] * 512
    with patch('pygame.key.get_pressed', return_value=mock_keys):
        yield

def test_camera_coordinate_conversion():
    # 1. Base conversion check (zoom=1.0, pan=0,0)
    logical_pos = Position(100.0, -100.0)
    pixel_pos = sector_coords_to_pixels(logical_pos)
    
    # 2. Conversion with zoom and pan
    zoom = 2.0
    pan_offset = Position(50, -50)
    pixel_pos_zoomed = sector_coords_to_pixels(logical_pos, zoom, pan_offset)
    
    # Under zoom=2.0 and pan=50,-50, the offset from center should be doubled plus the pan_offset
    # pixel = center + pan + (logical * radius_px / radius_logical) * zoom
    from constants import SECTOR_CIRCLE_CENTER_IN_PX, SECTOR_CIRCLE_RADIUS_IN_PX, SECTOR_CIRCLE_RADIUS_LOGICAL
    
    expected_x = int(SECTOR_CIRCLE_CENTER_IN_PX.x + pan_offset.x + (logical_pos.x * SECTOR_CIRCLE_RADIUS_IN_PX * zoom) / SECTOR_CIRCLE_RADIUS_LOGICAL)
    expected_y = int(SECTOR_CIRCLE_CENTER_IN_PX.y + pan_offset.y + (logical_pos.y * SECTOR_CIRCLE_RADIUS_IN_PX * zoom) / SECTOR_CIRCLE_RADIUS_LOGICAL)
    
    assert pixel_pos_zoomed.x == expected_x
    assert pixel_pos_zoomed.y == expected_y
    
    # 3. Roundtrip test
    logical_back = pixels_to_sector_coords(pixel_pos_zoomed, zoom, pan_offset)
    assert abs(logical_pos.x - logical_back.x) <= 2.0
    assert abs(logical_pos.y - logical_back.y) <= 2.0

def test_game_camera_reset():
    game = DummyGame()
    # Mock behavior of reset_sector_camera directly since DummyGame doesn't inherit from Game
    game.sector_zoom = 1.5
    game.sector_pan_offset = Position(100, 200)
    
    Game.reset_sector_camera(game)
    assert game.sector_zoom == 1.0
    assert game.sector_pan_offset.x == 0
    assert game.sector_pan_offset.y == 0

def test_zoom_to_mouse_pointer():
    game = DummyGame()
    game.view_mode = 'sector'
    game.game_started = True
    game.sector_zoom = 1.0
    game.sector_pan_offset = Position(0, 0)
    
    # Mock pygame.mouse.get_pos to return a point 100 pixels away from sector center
    from constants import SECTOR_CIRCLE_CENTER_IN_PX
    mouse_x = SECTOR_CIRCLE_CENTER_IN_PX.x + 100
    mouse_y = SECTOR_CIRCLE_CENTER_IN_PX.y - 100
    
    with patch('pygame.mouse.get_pos', return_value=(mouse_x, mouse_y)):
        # Zoom in (scroll_y > 0)
        Game.handle_mouse_wheel(game, 1)
        
        # New zoom should be 1.1
        assert game.sector_zoom == 1.1
        
        # Pan offset should shift to center zoom on mouse pointer
        # rx = 100, ry = -100
        # O_new = R_x - (R_x - O_old) * (Z_new / Z_old)
        # O_new = 100 - (100 - 0) * 1.1 = -10
        assert abs(game.sector_pan_offset.x - (-10.0)) < 1e-5
        assert abs(game.sector_pan_offset.y - (10.0)) < 1e-5

class DummyGame:
    def __init__(self):
        self.view_mode = 'sector'
        self.game_started = True
        self.sector_zoom = 1.0
        self.sector_pan_offset = Position(0, 0)
        self.is_dragging_camera = False
        self.camera_drag_last_pos = Position(0, 0)
        self.gui = MagicMock()

def test_input_processor_drag_pan():
    game = DummyGame()
    ip = InputProcessor(game)
    
    # Test middle click mouse down
    event_down = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=2)
    with patch('pygame.mouse.get_pos', return_value=(300, 400)), \
         patch.object(ip.gui, 'process_event', return_value=None), \
         patch.object(ip.gui, 'is_ingame_menu_open', return_value=False), \
         patch.object(ip.gui, 'is_unit_editor_open', return_value=False), \
         patch.object(ip, 'handle_mouse_click') as mock_click, \
         patch('pygame.event.get', return_value=[event_down]):
        
        ip.handle_input()
        assert game.is_dragging_camera is True
        assert game.camera_drag_last_pos.x == 300
        assert game.camera_drag_last_pos.y == 400
        
    # Test mouse motion
    event_motion = pygame.event.Event(pygame.MOUSEMOTION, pos=(320, 390))
    with patch('pygame.event.get', return_value=[event_motion]), \
         patch('pygame.mouse.get_pos', return_value=(320, 390)), \
         patch.object(ip.gui, 'process_event', return_value=None), \
         patch.object(ip.gui, 'is_ingame_menu_open', return_value=False), \
         patch.object(ip.gui, 'is_unit_editor_open', return_value=False):
        
        ip.handle_input()
        # Delta: dx = 20, dy = -10
        # Offset should update accordingly
        assert game.sector_pan_offset.x == 20
        assert game.sector_pan_offset.y == -10
        assert game.camera_drag_last_pos.x == 320
        assert game.camera_drag_last_pos.y == 390
        
    # Test middle click mouse up
    event_up = pygame.event.Event(pygame.MOUSEBUTTONUP, button=2)
    with patch('pygame.event.get', return_value=[event_up]), \
         patch('pygame.mouse.get_pos', return_value=(320, 390)), \
         patch.object(ip.gui, 'process_event', return_value=None), \
         patch.object(ip.gui, 'is_ingame_menu_open', return_value=False), \
         patch.object(ip.gui, 'is_unit_editor_open', return_value=False):
         
        ip.handle_input()
        assert game.is_dragging_camera is False
