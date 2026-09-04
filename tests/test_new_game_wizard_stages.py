"""Unit and integration tests for the two-stage New Game Wizard and home star system assignment."""
from __future__ import annotations

import os
import pygame
import pygame_gui
import pytest
from unittest.mock import MagicMock

os.environ["SDL_VIDEODRIVER"] = "dummy"
pygame.init()
pygame.font.init()

from constants import Vector
from game_settings import GameSettings, PlayerConfig, SpawnProfile, PLAYER_COLOR_PALETTE
from player_controller import PlayerController
from gui.layout_new_game_wizard import NewGameWizard
from rendering.galaxy_renderer import draw_galaxy_preview, get_system_at_preview_point
import game_setup
from entities import Planet


class MockGame:
    def __init__(self):
        self.gui = MagicMock()
        self.gui.galaxy_generation_rect = pygame.Rect(0, 0, 800, 600)
        self.galaxy = None
        self.players = []
        self.current_player_index = 0
        self.turn_number = 1
        self.campaign_id = "test_wizard_stage"
        self.view_mode = "galaxy"
        self.game_started = False
        self.visibility = None
        self.visibility_dirty = False
        self.selected_objects = []
        self.screen = MagicMock()
        self.overlay_surface = MagicMock()

    def recompute_visibility(self):
        pass

    def update_side_bar_content(self):
        pass

    def update_player_turn_display(self):
        pass


@pytest.fixture
def wizard_env():
    pygame.font.init()
    screen = pygame.display.set_mode((1280, 720))
    manager = pygame_gui.UIManager((1280, 720))
    wizard = NewGameWizard(manager, Vector(1280, 720), 1.0, 1.0)
    yield wizard, manager, screen
    wizard.kill()


def test_wizard_stage_1_initial_state(wizard_env):
    """Wizard starts in Stage 1 with map generation sliders and map preview."""
    wizard, manager, screen = wizard_env
    assert wizard._stage == 1
    assert "Stage 1" in wizard.window.window_display_title

    # Sliders should be present
    assert wizard._num_systems_slider is not None
    assert wizard._sys_radius_min_slider is not None
    assert wizard._sys_radius_max_slider is not None
    assert wizard._wormhole_density_slider is not None
    assert wizard._min_dist_slider is not None
    assert wizard._max_dist_slider is not None

    # Stage 1 action buttons
    assert wizard.next_button is not None
    assert wizard.cancel_button is not None
    assert wizard.back_button is None

    # Map should be pre-generated for preview
    assert wizard._generated_galaxy is not None
    assert len(wizard._generated_galaxy.systems) == wizard._num_systems

    # Preview panel should exist
    assert wizard._preview_panel is not None


def test_wizard_stage_1_no_galaxy_topology_guide_text(wizard_env):
    """Verify that the galaxy topology guide text and bullet labels are removed from Stage 1."""
    wizard, manager, screen = wizard_env
    assert wizard._stage == 1

    stage_texts = []
    for elem in wizard._stage_elements:
        if hasattr(elem, "text"):
            stage_texts.append(elem.text)
        elif hasattr(elem, "html_text"):
            stage_texts.append(elem.html_text)

    combined_text = " ".join(stage_texts)
    assert "Galaxy Topology Guide" not in combined_text
    assert "Star count & distances" not in combined_text
    assert "Wormhole density sets natural conduits" not in combined_text


def test_wizard_stage_1_regenerate_map(wizard_env):
    """Clicking Generate Map re-generates procedural galaxy preview."""
    wizard, manager, screen = wizard_env
    old_galaxy = wizard._generated_galaxy

    gen_event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": wizard._generate_map_btn})
    res = wizard.process_event(gen_event)
    assert res is None
    assert wizard._generated_galaxy is not None
    assert wizard._generated_galaxy is not old_galaxy


def test_wizard_stage_1_validation_blocks_next_on_invalid_map(wizard_env):
    """Inverted radius or distance prevents advancing to Stage 2 and displays error."""
    wizard, manager, screen = wizard_env

    # Invert radius: min 8, max 4
    wizard._sys_radius_min_slider.set_current_value(8)
    wizard._sys_radius_max_slider.set_current_value(4)

    next_event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": wizard.next_button})
    res = wizard.process_event(next_event)
    assert res is not None
    assert res["action"] == "wizard_settings_error"
    assert res["title"] == "Invalid Game Settings"
    assert wizard._stage == 1

    # Fix radius, invert distance: min 180, max 120
    wizard._sys_radius_min_slider.set_current_value(4)
    wizard._sys_radius_max_slider.set_current_value(8)
    wizard._min_dist_slider.set_current_value(180)
    wizard._max_dist_slider.set_current_value(120)

    res = wizard.process_event(next_event)
    assert res is not None
    assert res["action"] == "wizard_settings_error"
    assert "strictly less than Max System Distance" in res["message"]
    assert wizard._stage == 1


def test_wizard_transition_to_stage_2_and_back(wizard_env):
    """Advancing to Stage 2 creates player and economy controls; Back preserves state."""
    wizard, manager, screen = wizard_env

    # Advance to Stage 2
    next_event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": wizard.next_button})
    res = wizard.process_event(next_event)
    assert res is None
    assert wizard._stage == 2
    assert "Stage 2" in wizard.window.window_display_title

    # Stage 2 widgets created
    assert wizard._spawn_profile_button is not None
    assert wizard._home_mode_button is not None
    assert len(wizard._player_name_entries) == wizard._num_players
    assert len(wizard._player_color_swatches) == wizard._num_players
    assert len(wizard._player_type_buttons) == wizard._num_players
    assert len(wizard._player_home_buttons) == wizard._num_players
    assert wizard._credits_entry is not None
    assert wizard._metal_entry is not None
    assert wizard._crystal_entry is not None
    assert wizard._population_entry is not None
    assert wizard.back_button is not None
    assert wizard.start_button is not None
    assert wizard.next_button is None

    # Change player 1 name and starting credits
    wizard._player_name_entries[0].set_text("Commander Shepard")
    wizard._credits_entry.set_text("45000")

    # Navigate Back to Stage 1
    back_event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": wizard.back_button})
    res = wizard.process_event(back_event)
    assert res is None
    assert wizard._stage == 1

    # Navigate forward again to Stage 2
    res = wizard.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": wizard.next_button}))
    assert res is None
    assert wizard._stage == 2
    assert wizard._player_name_entries[0].get_text() == "Commander Shepard"
    assert wizard._credits_entry.get_text() == "45000"


def test_wizard_home_system_selection_and_cycling(wizard_env):
    """Test cycling home systems and clicking on map preview to assign a home system."""
    wizard, manager, screen = wizard_env
    wizard.go_to_stage(2)

    # Initial mode is random
    assert wizard._home_system_mode == "random"

    # Cycle home mode button to Specified
    mode_event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": wizard._home_mode_button})
    wizard.process_event(mode_event)
    assert wizard._home_system_mode == "specified"

    # Available systems in generated galaxy
    sys_names = sorted(list(wizard._generated_galaxy.systems.keys()))
    assert len(sys_names) > 0

    # Cycle Player 1 home system forward
    cycle_next_btn = wizard._player_home_next_btns[0]
    wizard.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": cycle_next_btn}))
    assert wizard._player_home_systems[0] == sys_names[0]
    assert wizard._player_home_buttons[0].text == sys_names[0]

    # Cycle Player 1 home system again
    wizard.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": cycle_next_btn}))
    expected_second = sys_names[1] if len(sys_names) > 1 else sys_names[0]
    assert wizard._player_home_systems[0] == expected_second
    assert wizard._player_home_buttons[0].text == expected_second

    # Test assigning via map preview click
    target_sys = sys_names[-1]
    preview_rect = wizard._get_preview_screen_rect()
    # Mock get_system_at_preview_point to simulate clicking on target_sys
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "gui.layout_new_game_wizard.get_system_at_preview_point",
            lambda *args, **kwargs: target_sys,
        )
        click_pos = (preview_rect.centerx, preview_rect.centery)
        mouse_event = pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            {"button": 1, "pos": click_pos},
        )
        wizard.process_event(mouse_event)

        # Player 1 should now be assigned target_sys
        assert wizard._player_home_systems[0] == target_sys
        assert wizard._player_home_buttons[0].text == target_sys
        # And focus should advance to Player 2
        assert wizard._selected_player_index_for_home == 1


def test_gui_process_event_routes_map_preview_click():
    """Verify that gui.process_event routes MOUSEBUTTONDOWN events to NewGameWizard for map preview click."""
    from gui.handler import GUI_Handler
    from rendering.galaxy_renderer import logical_to_screen_galaxy

    mock_game = type(
        "MockGame",
        (),
        {
            "screen_res": Vector(1280, 720),
            "view_mode": "galaxy",
            "galaxy_border_color": (0, 0, 0),
            "galaxy": None,
            "players": [],
            "selected_objects": [],
        },
    )()
    gui = GUI_Handler(Vector(1280, 720), mock_game)
    gui.show_new_game_wizard()
    wizard = gui.new_game_wizard
    wizard.go_to_stage(2)

    preview_rect = wizard._get_preview_screen_rect()
    first_sys_name = list(wizard._generated_galaxy.systems.keys())[0]
    first_sys = wizard._generated_galaxy.systems[first_sys_name]
    sys_screen_pos = logical_to_screen_galaxy(first_sys.position, preview_rect)
    click_pos = (int(sys_screen_pos.x), int(sys_screen_pos.y))

    # Send MOUSEBUTTONDOWN through GUI handler process_event
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": click_pos})
    action = gui.process_event(event)

    assert action == {"action": "ui_handled"}
    assert wizard._home_system_mode == "specified"
    assigned_sys = wizard._player_home_systems[0]
    assert assigned_sys in wizard._generated_galaxy.systems
    assert assigned_sys != "Random"
    assert wizard._player_home_buttons[0].text == assigned_sys
    assert wizard._selected_player_index_for_home == 1
    gui.close_new_game_wizard()


def test_wizard_start_action_generates_valid_settings(wizard_env):
    """Pressing Start Game outputs GameSettings with pregenerated_galaxy and home systems."""
    wizard, manager, screen = wizard_env
    wizard.go_to_stage(2)

    # Set distinct home systems in specified mode
    wizard._home_system_mode = "specified"
    sys_names = sorted(list(wizard._generated_galaxy.systems.keys()))
    wizard._player_home_systems[0] = sys_names[0]
    wizard._player_home_systems[1] = sys_names[1]
    wizard._player_home_systems[2] = sys_names[2]

    # Unique colors
    wizard._player_color_indices[0] = 0
    wizard._player_color_indices[1] = 1
    wizard._player_color_indices[2] = 2

    start_event = pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": wizard.start_button})
    action = wizard.process_event(start_event)
    assert action is not None
    assert action["action"] == "start_new_game_with_settings"

    settings = action["settings"]
    assert isinstance(settings, GameSettings)
    assert settings.pregenerated_galaxy is wizard._generated_galaxy
    assert settings.home_system_assignment_mode == "specified"
    assert settings.player_configs[0].home_system_name == sys_names[0]
    assert settings.player_configs[1].home_system_name == sys_names[1]
    assert settings.player_configs[2].home_system_name == sys_names[2]


def test_start_new_game_integration_with_pregenerated_galaxy_and_home_systems(wizard_env):
    """Full integration test: game_setup.start_new_game creates game with exact assigned home systems."""
    wizard, manager, screen = wizard_env
    wizard.go_to_stage(2)

    sys_names = sorted(list(wizard._generated_galaxy.systems.keys()))
    p1_sys = sys_names[0]
    p2_sys = sys_names[2]

    wizard._num_players = 2
    wizard._home_system_mode = "specified"
    wizard._player_color_indices[0] = 0
    wizard._player_color_indices[1] = 1
    wizard._player_home_systems[0] = p1_sys
    wizard._player_home_systems[1] = p2_sys

    action = wizard._build_start_action()
    settings = action["settings"]

    game = MockGame()
    success = game_setup.start_new_game(game, settings=settings)
    assert success is True
    assert game.galaxy is wizard._generated_galaxy
    assert len(game.players) == 2

    # Verify Player 1 homeworld is in p1_sys
    p1_hw = game.galaxy.get_celestial_body_by_id(game.players[0].homeworld_id)
    assert p1_hw is not None
    assert p1_hw.in_system == p1_sys
    assert p1_hw.owner == game.players[0]

    # Verify Player 2 homeworld is in p2_sys
    p2_hw = game.galaxy.get_celestial_body_by_id(game.players[1].homeworld_id)
    assert p2_hw is not None
    assert p2_hw.in_system == p2_sys
    assert p2_hw.owner == game.players[1]


def test_codex_protocol_home_system_parsing():
    """Verify Codex protocol correctly parses player home_system_name and assignment mode."""
    from game_control_protocol import _parse_new_game_settings

    payload = {
        "players": [
            {"name": "Codex", "controller": "codex", "team_id": 1, "color": [30, 120, 255], "home_system_name": "Vega"},
            {"name": "AI", "controller": "openai", "team_id": 2, "color": [220, 40, 40], "home_system_name": "Sol"},
        ],
        "home_system_assignment_mode": "specified",
        "num_systems": 10,
    }

    settings = _parse_new_game_settings(payload)
    assert settings.home_system_assignment_mode == "specified"
    assert settings.player_configs[0].home_system_name == "Vega"
    assert settings.player_configs[1].home_system_name == "Sol"


def test_wizard_validation_catches_invalid_home_system(wizard_env):
    """Wizard validation flags specified home systems that do not exist in the galaxy."""
    wizard, manager, screen = wizard_env
    wizard.go_to_stage(2)

    wizard._home_system_mode = "specified"
    wizard._player_home_systems[0] = "NonExistentSystem42"

    errs = wizard.get_validation_errors()
    assert any("does not exist in the galaxy" in e for e in errs)


def test_wizard_player_select_hint_label(wizard_env):
    """Verify that 'Home:' label stays clean and 'click to select' is displayed on the right of the active player row."""
    wizard, manager, screen = wizard_env
    wizard.go_to_stage(2)

    # In random mode, all select hint labels are empty
    assert wizard._home_system_mode == "random"
    for lbl in wizard._player_home_labels:
        assert lbl.text == "Home:"
    for lbl in wizard._player_select_labels:
        assert lbl.text == ""

    # Switch to specified mode
    wizard._cycle_home_mode()
    assert wizard._home_system_mode == "specified"

    # Home labels should still be "Home:" (no ▶)
    for lbl in wizard._player_home_labels:
        assert lbl.text == "Home:"

    # Player 1 (index 0) is selected by default -> displays "click to select"
    assert wizard._selected_player_index_for_home == 0
    assert wizard._player_select_labels[0].text == "click to select"
    assert wizard._player_select_labels[1].text == ""

    # Clicking Player 2's home button shifts focus to Player 2
    p2_home_btn = wizard._player_home_buttons[1]
    wizard.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, {"ui_element": p2_home_btn}))
    assert wizard._selected_player_index_for_home == 1
    assert wizard._player_select_labels[0].text == ""
    assert wizard._player_select_labels[1].text == "click to select"

    # Clicking Player 3's select label shifts focus to Player 3
    p3_select_lbl = wizard._player_select_labels[2]
    lbl_rect = p3_select_lbl.get_abs_rect()
    click_pos = (lbl_rect.centerx, lbl_rect.centery)
    wizard.process_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": click_pos}))
    assert wizard._selected_player_index_for_home == 2
    assert wizard._player_select_labels[0].text == ""
    assert wizard._player_select_labels[1].text == ""
    assert wizard._player_select_labels[2].text == "click to select"


def test_wizard_enlarged_dimensions_and_preview_scale(wizard_env):
    """Verify that wizard window is enlarged to 1180x640 logical reference and map preview is spacious."""
    from gui.layout_new_game_wizard import _WIN_W, _WIN_H
    wizard, manager, screen = wizard_env

    # Sizing constants
    assert _WIN_W == 1180
    assert _WIN_H == 640

    # Window geometry (accounting for UIWindow shadow padding)
    shadow_pad = getattr(wizard.window, "shadow_width", 0)
    assert wizard.window.rect.width - 2 * shadow_pad == 1180
    assert wizard.window.rect.height - 2 * shadow_pad == 640
    # Centered horizontally: (1280 - 1180) / 2 = 50
    assert wizard.window.rect.left + shadow_pad == 50
    # Centered vertically: (720 - 640) / 2 = 40
    assert wizard.window.rect.top + shadow_pad == 40

    # Container size is spacious
    content_w, content_h = wizard.window.get_container().get_size()
    assert content_w >= 1150
    assert content_h >= 590

    # Preview rect should be significantly larger than the old 420x410 viewport
    preview_rect = wizard._get_preview_screen_rect()
    assert preview_rect.width >= 550
    assert preview_rect.height >= 450


def test_wizard_stage_2_layout_and_economy_grid(wizard_env):
    """Verify that Stage 2 contains side-by-side mode row, spacious player rows, and 2x2 economy grid."""
    wizard, manager, screen = wizard_env
    wizard.go_to_stage(2)

    # Spawn profile and Home mode controls
    assert wizard._spawn_profile_button is not None
    assert wizard._home_mode_button is not None
    assert wizard._spawn_profile_button.text == "Normal"
    assert "Mode: Random" in wizard._home_mode_button.text

    # Verify side-by-side placement (both have the same relative y position in the scroll container)
    spawn_rect = wizard._spawn_profile_button.get_relative_rect()
    home_rect = wizard._home_mode_button.get_relative_rect()
    assert spawn_rect.top == home_rect.top
    assert home_rect.left > spawn_rect.right

    # 2x2 Economy grid entries
    assert wizard._credits_entry is not None
    assert wizard._metal_entry is not None
    assert wizard._crystal_entry is not None
    assert wizard._population_entry is not None

    cred_rect = wizard._credits_entry.get_relative_rect()
    crys_rect = wizard._crystal_entry.get_relative_rect()
    met_rect = wizard._metal_entry.get_relative_rect()
    pop_rect = wizard._population_entry.get_relative_rect()

    # Credits & Crystal on row 1
    assert cred_rect.top == crys_rect.top
    assert crys_rect.left > cred_rect.right

    # Metal & Population on row 2
    assert met_rect.top == pop_rect.top
    assert pop_rect.left > met_rect.right
    assert met_rect.top > cred_rect.bottom

    # Player block name entry and controller buttons are widened
    name_rect = wizard._player_name_entries[0].get_relative_rect()
    assert name_rect.width >= 140
    ctrl_rect = wizard._player_type_buttons[0].get_relative_rect()
    assert ctrl_rect.width >= 100



