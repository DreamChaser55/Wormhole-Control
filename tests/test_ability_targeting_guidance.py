import pytest
from unittest.mock import MagicMock, patch
import pygame
from geometry import Position
from entities import Unit
from constants import HullSize
from unit_components import AbilityComponent, AbilityType
from gui.sidebar.panels_unit import build_unit_panel
from input_processor import InputProcessor
from events import UseAbilityEvent
from rendering.sector_renderer.sector_overlay_renderer import SectorOverlayRenderer


class MockPlayer:
    def __init__(self, name="Test Player", player_id=1):
        self.id = player_id
        self.name = name
        self.color = (0, 200, 255)


def test_ability_component_sidebar_data_unit_targeting_guidance():
    game = MagicMock()
    game.pending_ability = ("ion_bolt", True, False)
    player = MockPlayer()
    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    comp = AbilityComponent(unit, [AbilityType.ION_BOLT])
    unit.add_component(comp)

    sidebar_data = comp.get_sidebar_data(game)
    texts = [item.get('text', '') for item in sidebar_data if item.get('type') == 'label']

    assert any("TARGETING: Ion Bolt" in t for t in texts)
    assert any("Right-Click target unit to cast" in t for t in texts)
    assert any("Press ESC to cancel" in t for t in texts)


def test_ability_component_sidebar_data_pos_targeting_guidance():
    game = MagicMock()
    game.pending_ability = ("microjump", False, True)
    player = MockPlayer()
    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    comp = AbilityComponent(unit, [AbilityType.MICROJUMP])
    unit.add_component(comp)

    sidebar_data = comp.get_sidebar_data(game)
    texts = [item.get('text', '') for item in sidebar_data if item.get('type') == 'label']

    assert any("TARGETING: Microjump" in t for t in texts)
    assert any("Right-Click target location to cast" in t for t in texts)
    assert any("Press ESC to cancel" in t for t in texts)


def test_unit_panel_top_level_targeting_banner():
    game = MagicMock()
    game.pending_ability = ("ion_bolt", True, False)
    player = MockPlayer()
    game.players = [player]
    game.current_player_index = 0
    game.selected_unit_tab = 'basic_info'

    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    comp = AbilityComponent(unit, [AbilityType.ION_BOLT])
    unit.add_component(comp)

    panel_data = build_unit_panel(game, unit)
    texts = [item.get('text', '') for item in panel_data if item.get('type') == 'label']

    assert any("TARGETING: Ion Bolt" in t for t in texts)
    assert any("Right-Click target unit to cast (ESC to cancel)" in t for t in texts)


def test_sector_overlay_targeting_mode_renderer():
    pygame.font.init()
    game = MagicMock()
    game.pending_ability = ("ion_bolt", True, False)
    game.sector_view_mouse_hover_object = None

    parent = MagicMock()
    parent.game = game
    parent.screen = pygame.Surface((1280, 720))
    parent.overlay_surface = pygame.Surface((1280, 720), pygame.SRCALPHA)
    parent._font_cache = {}

    renderer = SectorOverlayRenderer(parent)

    with patch('pygame.mouse.get_pos', return_value=(500, 300)):
        # Should execute without errors and draw onto overlay_surface
        renderer.draw_targeting_mode_overlay()


def test_sector_overlay_targeting_mode_renders_range_ring():
    pygame.font.init()
    player = MockPlayer()
    game = MagicMock()
    game.current_system_name = "Sol"
    game.current_sector_coord = (0, 0)
    game.pending_ability = ("microjump", False, True)
    game.sector_view_mouse_hover_object = None

    caster = Unit(owner=player, position=Position(100, 200), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    game.selected_objects = [caster]

    parent = MagicMock()
    parent.game = game
    parent.screen = pygame.Surface((1280, 720))
    parent.overlay_surface = pygame.Surface((1280, 720), pygame.SRCALPHA)
    parent._font_cache = {}
    parent._coords_to_pixels.return_value = Position(500, 400)
    parent.get_dynamic_sector_radius.return_value = 3000.0

    renderer = SectorOverlayRenderer(parent)

    with patch('pygame.mouse.get_pos', return_value=(500, 300)):
        renderer.draw_targeting_mode_overlay()

    parent._draw_range_ring.assert_called_once()
    args = parent._draw_range_ring.call_args[0]
    assert args[0] == 500  # cx
    assert args[1] == 400  # cy
    assert args[2] == 360  # radius_px (600.0 * 3000 / 5000 = 360)
    assert args[3] == (200, 100, 255)  # ring color



def test_input_processor_left_click_protection_in_targeting_mode():
    game = MagicMock()
    game.pending_ability = ("ion_bolt", True, False)
    game.view_mode = 'sector'
    player = MockPlayer()
    game.players = [player]
    game.current_player_index = 0

    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    game.selected_objects = [unit]

    ip = InputProcessor(game)

    with patch('pygame.key.get_mods', return_value=0):
        with patch('input_processor.is_pixel_in_sector', return_value=True):
            # Left click (button 1) should be consumed, leaving selection intact and pending_ability active
            ip.handle_mouse_click(1, Position(100, 100))
            assert game.pending_ability == ("ion_bolt", True, False)
            assert game.selected_objects == [unit]


def test_input_processor_right_click_empty_space_for_unit_ability():
    game = MagicMock()
    game.pending_ability = ("ion_bolt", True, False)
    game.view_mode = 'sector'
    player = MockPlayer()
    game.players = [player]
    game.current_player_index = 0
    game.sector_view_mouse_hover_object = None  # Empty space

    unit = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    game.selected_objects = [unit]

    ip = InputProcessor(game)

    with patch('pygame.key.get_mods', return_value=0):
        with patch('input_processor.is_pixel_in_sector', return_value=True):
            with patch.object(game.event_bus, 'publish') as mock_publish:
                # Right click on empty space for unit-only ability should be consumed without firing event
                ip.handle_mouse_click(3, Position(100, 100))
                mock_publish.assert_not_called()
                assert game.pending_ability == ("ion_bolt", True, False)


def test_input_processor_right_click_target_unit_fires_event():
    game = MagicMock()
    game.pending_ability = ("ion_bolt", True, False)
    game.view_mode = 'sector'
    player = MockPlayer()
    enemy = MockPlayer("Enemy", 2)
    game.players = [player, enemy]
    game.current_player_index = 0

    caster = Unit(owner=player, position=Position(0, 0), in_hex=(0, 0), in_system="Sol", name="Caster", hull_size=HullSize.MEDIUM, game=game)
    target_unit = Unit(owner=enemy, position=Position(100, 100), in_hex=(0, 0), in_system="Sol", name="Target Enemy", hull_size=HullSize.MEDIUM, game=game)
    game.selected_objects = [caster]
    game.sector_view_mouse_hover_object = target_unit

    ip = InputProcessor(game)

    with patch('pygame.key.get_mods', return_value=0):
        with patch('input_processor.is_pixel_in_sector', return_value=True):
            with patch.object(game.event_bus, 'publish') as mock_publish:
                ip.handle_mouse_click(3, Position(100, 100))
                mock_publish.assert_called_once()
                event = mock_publish.call_args[0][0]
                assert isinstance(event, UseAbilityEvent)
                assert event.ability_type_str == "ion_bolt"
                assert event.target_unit == target_unit
                assert game.pending_ability is None
