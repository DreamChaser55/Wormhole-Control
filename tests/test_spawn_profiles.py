"""Unit and integration tests for player and unit spawn profiles."""
import os
import pytest
import pygame
import pygame_gui
from unittest.mock import MagicMock, patch

os.environ["SDL_VIDEODRIVER"] = "dummy"

from constants import HullSize, PLANET_RADIUS, Vector
from entities import Planet, Player, Unit
from game_settings import (
    GameSettings,
    PlayerConfig,
    SpawnProfile,
    DEFAULT_SPAWN_PROFILE,
    normalize_spawn_profile,
)
from game_control_protocol import _parse_new_game_settings, ProtocolError
from player_controller import PlayerController
import game_setup


def test_spawn_profile_enum_and_normalization():
    assert SpawnProfile.NORMAL.value == "normal"
    assert SpawnProfile.TESTING.value == "testing"
    assert SpawnProfile.NORMAL.display_name == "Normal"
    assert SpawnProfile.TESTING.display_name == "Testing"

    assert normalize_spawn_profile(None) == DEFAULT_SPAWN_PROFILE
    assert normalize_spawn_profile("normal") == SpawnProfile.NORMAL
    assert normalize_spawn_profile("NORMAL") == SpawnProfile.NORMAL
    assert normalize_spawn_profile("Testing") == SpawnProfile.TESTING
    assert normalize_spawn_profile("testing") == SpawnProfile.TESTING
    assert normalize_spawn_profile(SpawnProfile.TESTING) == SpawnProfile.TESTING
    assert normalize_spawn_profile("invalid") == DEFAULT_SPAWN_PROFILE


def test_game_settings_spawn_profile_default_and_custom():
    settings_default = GameSettings()
    assert settings_default.spawn_profile == SpawnProfile.NORMAL

    settings_testing = GameSettings(spawn_profile=SpawnProfile.TESTING)
    assert settings_testing.spawn_profile == SpawnProfile.TESTING

    settings_str = GameSettings(spawn_profile="testing")
    assert settings_str.spawn_profile == SpawnProfile.TESTING


def test_codex_protocol_spawn_profile_parsing():
    base_settings_dict = {
        "players": [
            {"name": "Codex", "controller": "codex", "team_id": 1, "color": [30, 120, 255]},
            {"name": "AI", "controller": "openai", "team_id": 2, "color": [220, 40, 40]},
        ],
        "num_systems": 10,
    }

    # Default (omitted)
    s1 = _parse_new_game_settings(base_settings_dict)
    assert s1.spawn_profile == SpawnProfile.NORMAL

    # Explicit normal
    dict_normal = dict(base_settings_dict, spawn_profile="normal")
    s2 = _parse_new_game_settings(dict_normal)
    assert s2.spawn_profile == SpawnProfile.NORMAL

    # Explicit testing
    dict_testing = dict(base_settings_dict, spawn_profile="testing")
    s3 = _parse_new_game_settings(dict_testing)
    assert s3.spawn_profile == SpawnProfile.TESTING

    # Invalid profile
    dict_invalid = dict(base_settings_dict, spawn_profile="superman")
    with pytest.raises(ProtocolError) as exc:
        _parse_new_game_settings(dict_invalid)
    assert "Invalid spawn_profile" in str(exc.value)

    # Non-string profile
    dict_bad_type = dict(base_settings_dict, spawn_profile=123)
    with pytest.raises(ProtocolError) as exc:
        _parse_new_game_settings(dict_bad_type)
    assert "must be a string" in str(exc.value)


class MockGame:
    def __init__(self):
        self.gui = MagicMock()
        self.galaxy = None
        self.players = []
        self.current_player_index = 0
        self.turn_number = 1
        self.campaign_id = "test_camp"
        self.view_mode = "galaxy"
        self.game_started = False
        self.visibility = None
        self.visibility_dirty = False

    def recompute_visibility(self):
        pass

    def update_side_bar_content(self):
        pass

    def update_player_turn_display(self):
        pass


def test_start_new_game_normal_spawn_profile():
    """Verify normal profile places players in separate systems with 4 starter units."""
    game = MockGame()
    settings = GameSettings(
        player_configs=[
            PlayerConfig("P1", (30, 120, 255), controller=PlayerController.HUMAN, team_id=1),
            PlayerConfig("P2", (220, 40, 40), controller=PlayerController.HUMAN, team_id=2),
            PlayerConfig("P3", (255, 210, 0), controller=PlayerController.HUMAN, team_id=3),
        ],
        num_systems=15,
        starting_population=40,
        spawn_profile=SpawnProfile.NORMAL,
    )

    success = game_setup.start_new_game(game, settings=settings)
    assert success is True
    assert len(game.players) == 3

    # Check each player has a homeworld in a distinct system
    player_systems = {}
    for player in game.players:
        # Find player's homeworld planet
        homeworlds = []
        for sys_name, sys_obj in game.galaxy.systems.items():
            for hex_coord, body in sys_obj.get_all_celestial_bodies():
                if isinstance(body, Planet) and body.owner == player:
                    homeworlds.append((sys_name, hex_coord, body))

        assert len(homeworlds) == 1, f"Expected exactly 1 homeworld planet for {player.name}"
        sys_name, hw_hex, planet = homeworlds[0]
        assert planet.population == 40
        player_systems[player] = sys_name

        # Find units owned by player
        owned_units = []
        for sys_name_i, sys_obj in game.galaxy.systems.items():
            for unit, hex_coord in sys_obj.get_all_units():
                if unit.owner == player:
                    owned_units.append((sys_name_i, hex_coord, unit))

        # Normal profile spawns exactly 4 units
        assert len(owned_units) == 4, f"Expected 4 units for {player.name}, found {len(owned_units)}"

        # All units should be in the homeworld hex
        for unit_sys, unit_hex, unit in owned_units:
            assert unit_sys == sys_name
            assert unit_hex == hw_hex
            assert unit.name.startswith(player.name)
            # Check distance from planet at (0, 0)
            dist_from_planet = (unit.position.x ** 2 + unit.position.y ** 2) ** 0.5
            assert dist_from_planet > PLANET_RADIUS, f"Unit {unit.name} placed inside planet collision radius"

        # Check unit template types
        unit_names = [u.name for _, _, u in owned_units]
        assert any("Shipyard" in name or "Station" in name for name in unit_names)
        assert any("Constructor" in name for name in unit_names)
        assert any("Colonizer" in name for name in unit_names)
        assert any("Harvester" in name for name in unit_names)

        # Check colonizer unit has ColonyComponent
        colonizer = next(u for _, _, u in owned_units if "Colonizer" in u.name)
        assert colonizer.colony_component is not None

    # Verify all 3 players are in different systems
    distinct_systems = set(player_systems.values())
    assert len(distinct_systems) == 3, f"Expected 3 distinct systems, got {player_systems}"


def test_start_new_game_testing_spawn_profile():
    """Verify testing profile spawns all players in Sol with the full testing fleet."""
    game = MockGame()
    settings = GameSettings(
        player_configs=[
            PlayerConfig("P1", (30, 120, 255), controller=PlayerController.HUMAN, team_id=1),
            PlayerConfig("P2", (220, 40, 40), controller=PlayerController.HUMAN, team_id=2),
        ],
        num_systems=15,
        starting_population=50,
        spawn_profile=SpawnProfile.TESTING,
    )

    success = game_setup.start_new_game(game, settings=settings)
    assert success is True
    assert len(game.players) == 2

    # Check that both players spawn in the same system (Sol or fallback)
    for player in game.players:
        owned_units = []
        for sys_name, sys_obj in game.galaxy.systems.items():
            for unit, hex_coord in sys_obj.get_all_units():
                if unit.owner == player:
                    owned_units.append((sys_name, hex_coord, unit))

        # Testing profile spawns 5 ships + 5 stations + 1 carrier = 11 units
        assert len(owned_units) == 11, f"Expected 11 testing units for {player.name}, found {len(owned_units)}"


def test_new_game_wizard_spawn_profile_ui():
    """Test NewGameWizard UI spawn profile button, cycling, snapshot, and settings generation."""
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    manager = pygame_gui.UIManager((1280, 720))

    from gui.layout_new_game_wizard import NewGameWizard

    wizard = NewGameWizard(manager, Vector(1280, 720), 1.0, 1.0)
    wizard.go_to_stage(2)
    assert wizard._spawn_profile == SpawnProfile.NORMAL
    assert wizard._spawn_profile_button is not None
    assert wizard._spawn_profile_button.text == "Normal"

    # Simulate button press to cycle
    cycle_event = pygame.event.Event(
        pygame_gui.UI_BUTTON_PRESSED,
        ui_element=wizard._spawn_profile_button,
    )
    result = wizard.process_event(cycle_event)
    assert result is None
    assert wizard._spawn_profile == SpawnProfile.TESTING
    assert wizard._spawn_profile_button.text == "Testing"

    # Cycle again back to Normal
    wizard.process_event(cycle_event)
    assert wizard._spawn_profile == SpawnProfile.NORMAL
    assert wizard._spawn_profile_button.text == "Normal"

    # Test snapshot & restore
    wizard._spawn_profile = SpawnProfile.TESTING
    snap = wizard._snapshot()
    assert snap["spawn_profile"] == "testing"

    wizard._spawn_profile = SpawnProfile.NORMAL
    wizard._restore_snapshot(snap)
    assert wizard._spawn_profile == SpawnProfile.TESTING
    assert wizard._spawn_profile_button.text == "Testing"

    # Test start action output
    action = wizard._build_start_action()
    assert action["action"] == "start_new_game_with_settings"
    assert action["settings"].spawn_profile == SpawnProfile.TESTING

    wizard.kill()
    pygame.quit()
