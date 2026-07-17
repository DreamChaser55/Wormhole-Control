import pytest
from unittest.mock import MagicMock, patch
import pygame
import pygame_gui
from geometry import Position
from gui import GUI_Handler
from input_processor import InputProcessor

class DummyGame:
    def __init__(self):
        self.view_mode = 'sector'
        self.game_started = True
        self.sector_zoom = 1.0
        self.sector_pan_offset = Position(0, 0)
        self.sector_target_zoom = 1.0
        self.zoom_anchor_pixel = None
        self.zoom_anchor_logical = None
        self.gui = MagicMock()
        self.is_running = True
        self.current_system_name = None
        self.current_sector_coord = None
        self.selected_objects = []
        self.pending_ability = None
        self.galaxy = MagicMock()

    def end_turn(self):
        pass

    def update_view_specific_labels(self):
        pass

class MockKeys:
    def __init__(self, pressed):
        self.pressed = pressed
    def __getitem__(self, key):
        return self.pressed.get(key, False)

def test_is_any_text_entry_focused():
    # Initialize pygame and UIManager
    pygame.init()
    pygame.display.set_mode((100, 100))
    game = DummyGame()
    
    # We construct a real GUI_Handler (which sets up self.manager)
    gui_handler = GUI_Handler(Position(800, 600), game)
    
    # Check initially false
    assert gui_handler.is_any_text_entry_focused() is False
    
    # Add a UITextEntryLine
    entry = pygame_gui.elements.UITextEntryLine(
        relative_rect=pygame.Rect(10, 10, 100, 30),
        manager=gui_handler.manager
    )
    
    # Initially not focused
    assert gui_handler.is_any_text_entry_focused() is False
    
    # Focus it
    entry.focus()
    assert gui_handler.is_any_text_entry_focused() is True
    
    # Unfocus it
    entry.unfocus()
    assert gui_handler.is_any_text_entry_focused() is False

def test_camera_panning_blocked_when_focused():
    game = DummyGame()
    ip = InputProcessor(game)
    
    # Mock keys: K_LEFT is pressed
    mock_keys = MockKeys({pygame.K_LEFT: True})
    
    # Case 1: text entry is focused -> panning should NOT occur
    with patch('pygame.key.get_pressed', return_value=mock_keys), \
         patch.object(ip.gui, 'is_any_text_entry_focused', return_value=True), \
         patch('pygame.event.get', return_value=[]):
        ip.handle_input(time_delta=0.1)
        assert game.sector_pan_offset.x == 0
        
    # Case 2: text entry is NOT focused -> panning should occur
    with patch('pygame.key.get_pressed', return_value=mock_keys), \
         patch.object(ip.gui, 'is_any_text_entry_focused', return_value=False), \
         patch('pygame.event.get', return_value=[]):
        ip.handle_input(time_delta=0.1)
        # Left arrow shifts the camera offset to the right (adds to offset.x)
        assert game.sector_pan_offset.x > 0

def test_shortcuts_blocked_when_focused():
    game = DummyGame()
    ip = InputProcessor(game)
    
    # Case 1: focused, press 'g' (switch to galaxy view) -> should be blocked
    event_g = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g)
    game.view_mode = 'sector'
    with patch.object(ip.gui, 'is_any_text_entry_focused', return_value=True), \
         patch.object(ip.gui, 'process_event', return_value=None), \
         patch.object(ip.gui, 'is_ingame_menu_open', return_value=False), \
         patch.object(ip.gui, 'is_unit_editor_open', return_value=False), \
         patch('pygame.event.get', return_value=[event_g]):
        ip.handle_input()
        assert game.view_mode == 'sector'  # remains unchanged

    # Case 2: NOT focused, press 'g' -> should trigger galaxy view
    with patch.object(ip.gui, 'is_any_text_entry_focused', return_value=False), \
         patch.object(ip.gui, 'process_event', return_value=None), \
         patch.object(ip.gui, 'is_ingame_menu_open', return_value=False), \
         patch.object(ip.gui, 'is_unit_editor_open', return_value=False), \
         patch('pygame.event.get', return_value=[event_g]):
        ip.handle_input()
        assert game.view_mode == 'galaxy'

def test_esc_unfocuses_text_entry():
    pygame.init()
    pygame.display.set_mode((100, 100))
    game = DummyGame()
    
    gui_handler = GUI_Handler(Position(800, 600), game)
    entry = pygame_gui.elements.UITextEntryLine(
        relative_rect=pygame.Rect(10, 10, 100, 30),
        manager=gui_handler.manager
    )
    entry.focus()
    assert entry.is_focused is True
    
    ip = InputProcessor(game)
    ip.gui = gui_handler  # Use our real GUI_Handler with the manager and focused entry
    
    # Press ESC
    event_esc = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
    with patch.object(gui_handler, 'process_event', return_value=None), \
         patch.object(gui_handler, 'is_ingame_menu_open', return_value=False), \
         patch.object(gui_handler, 'is_unit_editor_open', return_value=False), \
         patch('pygame.event.get', return_value=[event_esc]):
        ip.handle_input()
        
    # Verify that the text entry was unfocused
    assert entry.is_focused is False
