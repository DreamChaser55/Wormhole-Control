"""Regression tests for GUI and rendering performance optimizations."""
from __future__ import annotations

from unittest.mock import patch

import pygame
import pytest
from pygame_gui.core.ui_appearance_theme import UIAppearanceTheme

from display_config import DisplayConfig
from game_settings import GameSettings
from gui.theme_loader import build_ui_manager
from rendering.drawing_utils import get_cached_font


def test_fast_combined_id_cache_matches_pygame_gui_and_validates_lengths(pygame_context):
    manager = build_ui_manager(DisplayConfig(1280, 720, False))
    theme = manager.get_theme()
    assert getattr(theme, "_wormhole_fast_combined_ids", False) is True

    # Compare against an unpatched UIAppearanceTheme on a 5-level nested hierarchy
    baseline_theme = UIAppearanceTheme(manager.resource_loader, locale="en")
    cases = [
        (
            [None, None, None, None, None],
            ["panel", "container", "container", "container", "label"],
            [None, None, None, None, None],
            ["#side_bar_info_panel", "#root_container", "#view_container", "#scrollable_container", "#sidebar_info_label"],
        ),
        (
            [None, None],
            ["window", "button"],
            [None, "@action_btn"],
            ["#dialog", "#ok_button"],
        ),
        ([None], ["label"], [None], [None]),
        (None, None, None, None),
    ]
    for eb, ei, ci, oi in cases:
        expected = baseline_theme.build_all_combined_ids(eb, ei, ci, oi)
        first = theme.build_all_combined_ids(eb, ei, ci, oi)
        second = theme.build_all_combined_ids(eb, ei, ci, oi)
        assert first == expected
        assert second is first

    with pytest.raises(ValueError):
        theme.build_all_combined_ids([None], ["panel", "label"], [None], ["#a"])


def test_visual_debug_mode_disabled_by_default(game_factory):
    game = game_factory(display_config=DisplayConfig(1280, 720, False))
    assert game.gui.manager.visual_debug_active is False


def test_hud_updates_skip_redundant_rebuilds_until_state_changes(game_factory):
    game = game_factory(display_config=DisplayConfig(1280, 720, False))
    assert game.start_new_game(settings=GameSettings(num_systems=6))
    game.update_player_turn_display()
    game.update_view_specific_labels()

    gui = game.gui
    with (
        patch.object(gui.top_bar_panel, "rebuild", wraps=gui.top_bar_panel.rebuild) as top_rebuild,
        patch.object(gui.side_bar_info_panel, "rebuild", wraps=gui.side_bar_info_panel.rebuild) as side_rebuild,
        patch.object(gui.player_color_indicator, "rebuild", wraps=gui.player_color_indicator.rebuild) as ind_rebuild,
        patch.object(gui.player_turn_label, "set_text", wraps=gui.player_turn_label.set_text) as turn_set_text,
        patch.object(gui.view_mode_label, "set_text", wraps=gui.view_mode_label.set_text) as view_set_text,
    ):
        # Consecutive frames with unchanged state should not rebuild panels or re-parse HTML
        game.update_player_turn_display()
        game.update_view_specific_labels()
        assert top_rebuild.call_count == 0
        assert side_rebuild.call_count == 0
        assert ind_rebuild.call_count == 0
        assert turn_set_text.call_count == 0
        assert view_set_text.call_count == 0

        # Changing active player's color and turn number must trigger exactly one refresh
        game.current_player.color = (12, 234, 56)
        game.turn_number += 1
        game.update_player_turn_display()
        assert top_rebuild.call_count == 1
        assert side_rebuild.call_count == 1
        assert ind_rebuild.call_count == 1
        assert turn_set_text.call_count == 1


def test_unit_editor_detaches_hidden_sprites_and_reattaches_on_reopen(game_factory):
    game = game_factory(display_config=DisplayConfig(1280, 720, False))
    assert game.start_new_game(settings=GameSettings(num_systems=6))
    ui_group = game.gui.manager.ui_group
    baseline_count = len(ui_group.sprites())

    game.gui.open_unit_editor(game.custom_template_manager)
    open_count = len(ui_group.sprites())
    assert open_count > baseline_count + 100

    game.gui.close_unit_editor()
    assert not game.gui.is_unit_editor_open()
    assert len(ui_group.sprites()) == baseline_count

    game.gui.open_unit_editor(game.custom_template_manager)
    assert game.gui.is_unit_editor_open()
    assert len(ui_group.sprites()) == open_count

    game.gui.close_unit_editor()
    assert len(ui_group.sprites()) == baseline_count


def test_cached_font_reuses_instance_and_recovers_after_reinit(pygame_context):
    f1 = get_cached_font(None, 16)
    f2 = get_cached_font(None, 16)
    assert f1 is f2

    pygame.font.quit()
    f3 = get_cached_font(None, 16)
    assert f3 is not f1
    assert f3.get_height() > 0
