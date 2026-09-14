"""Equipment help coverage, modal input isolation and real-widget layout."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pygame
import pygame_gui
import pytest

from constants import HullSize
from custom_unit_templates import CustomTemplateManager
from display_config import DisplayConfig
from geometry import Position
from gui.theme_loader import build_ui_manager
from gui.unit_editor_gui import UnitEditorWindow
from gui.unit_editor_gui.catalog import COMPONENT_ROWS, COMPONENT_DESCRIPTIONS
from gui.unit_editor_gui.descriptions import component_description, ability_description
from gui.unit_editor_gui.save_dialog import SaveConfirmationDialog
from unit_components.abilities import ABILITY_DEFINITIONS
from unit_components.enums import AbilityType


pytestmark = [
    pytest.mark.filterwarnings("error:Finding font with id:UserWarning"),
    pytest.mark.filterwarnings("error:Trying to pre-load font id:UserWarning"),
    pytest.mark.filterwarnings("error:Label Rect is too small:UserWarning"),
]


def press(button):
    return pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=button)


@pytest.fixture
def editor(pygame_context):
    manager = build_ui_manager(DisplayConfig(1280, 720))
    window = UnitEditorWindow(manager, DisplayConfig(1280, 720), CustomTemplateManager())
    window.show()
    yield window
    window.kill()
    manager.clear_and_reset()


def test_help_covers_all_equipment_without_changing_design(editor):
    editor._on_hull_changed("STRIKECRAFT_WING")
    editor._select_component("has_ability_component")
    assert not editor._comp_toggles["has_hangar"].is_enabled
    assert not editor._ability_buttons["tracking_lock"].is_enabled
    before = deepcopy(editor._comp)
    selected = editor._selected_component_key
    scrolls = [editor._comp_scroll_container, editor._ability_scroll_container]
    for container in scrolls:
        container.vert_scroll_bar.set_scroll_from_start_percentage(0.7)
    editor.manager.update(0.1)
    positions = [container.vert_scroll_bar.start_percentage for container in scrolls]
    expected_keys = {row["key"] for row in COMPONENT_ROWS} | {"has_counter_intelligence"}
    assert set(editor._comp_help_buttons) == set(COMPONENT_DESCRIPTIONS) == expected_keys
    assert set(editor._ability_help_buttons) == {kind.value for kind in AbilityType}

    for buttons, describe in [(editor._comp_help_buttons, component_description),
                               (editor._ability_help_buttons, ability_description)]:
        for key, button in buttons.items():
            assert button.is_enabled
            editor.process_event(press(button))
            dialog = editor._description_dialog
            title, body = describe(key)
            assert dialog.window.window_display_title == title
            assert dialog.text_box.html_text == body
            assert "<b>Key rules</b>" in body
            editor.process_event(press(dialog.close_button))
            assert editor._description_dialog is None
            assert not dialog.window.alive()
    assert editor._comp == before
    assert editor._selected_component_key == selected
    assert [container.vert_scroll_bar.start_percentage for container in scrolls] == positions


def test_descriptions_follow_definitions_and_explain_special_cases(monkeypatch):
    definition = ABILITY_DEFINITIONS[AbilityType.TRACKING_LOCK]
    monkeypatch.setitem(ABILITY_DEFINITIONS, AbilityType.TRACKING_LOCK,
                        replace(definition, antimatter_cost=123, cooldown=17,
                                description="Track <wings> & protect allies."))
    _, body = ability_description("tracking_lock")
    assert "123 AM" in body and "17 turns" in body
    assert "Anti-Strikecraft turret" in body
    assert "Track &lt;wings&gt; &amp; protect allies." in body
    for name in ("ghost_fleet", "fuel_cache"):
        body = ability_description(name)[1]
        assert "Persistent deployment (no expiry)" in body
        assert "Instant / one-shot" not in body
        assert "across the galaxy" in body
    assert "Any legal position in the same sector" in ability_description("microjump")[1]
    assert "Nebula and position inside it" in ability_description("nebula_catalyst")[1]
    assert "Requires:</b> Abilities, Sensors, Antimatter Storage" in ability_description("nebula_catalyst")[1]
    assert "warp gates" not in component_description("has_constructor_component")[1]
    assert "no passive discovery" in component_description("has_counter_intelligence")[1]


def test_dialog_lifecycle_and_save_modal_priority(editor):
    editor.process_event(press(editor._comp_help_buttons["has_engine"]))
    dialog = editor._description_dialog
    editor.process_event(press(editor._comp_help_buttons["has_hangar"]))
    assert editor._description_dialog is dialog
    editor.hide()
    assert not dialog.window.alive()
    assert editor._description_dialog is None
    editor.show()
    assert editor._description_dialog is None
    editor._save_dialog = SaveConfirmationDialog(editor.manager, editor.screen_res, "Existing")
    editor.process_event(press(editor._comp_help_buttons["has_engine"]))
    assert editor._description_dialog is None
    editor._save_dialog.kill()
    editor._save_dialog = None
    editor.process_event(press(editor._comp_help_buttons["has_engine"]))
    dialog = editor._description_dialog
    editor.kill()
    assert not dialog.window.alive()
    assert not dialog.text_box.alive()


def test_modal_captures_real_input_pipeline(game_factory, monkeypatch):
    game = game_factory(display_config=DisplayConfig(1280, 720, False))
    gui = game.gui
    gui.open_unit_editor(game.custom_template_manager)
    editor = gui.unit_editor_window
    game.view_mode = "system"
    game.game_started = True
    game.system_pan_offset = Position(0, 0)
    monkeypatch.setattr(pygame.key, "get_pressed", lambda: {pygame.K_RIGHT: True})
    monkeypatch.setattr(game, "handle_mouse_wheel", Mock())
    monkeypatch.setattr(game, "ensure_system_camera", Mock())
    # Open through the same router used by the game loop.
    gui.process_event(press(editor._comp_help_buttons["has_engine"]))
    dialog = editor._description_dialog
    before = deepcopy(editor._comp)
    name_before = editor._display_entry.get_text()
    selected = editor._selected_component_key
    editor._display_entry.focus()
    scroll = editor._comp_scroll_container.vert_scroll_bar
    scroll.hovered = True
    scroll_before = scroll.start_percentage
    pygame.event.clear()
    for event in [
        press(editor._comp_toggles["has_engine"]), press(editor._comp_select_btns["has_hangar"]),
        press(editor._save_button), press(editor._close_button),
        press(gui.unit_editor_button), press(gui.end_turn_button),
        pygame.event.Event(pygame_gui.UI_DROP_DOWN_MENU_CHANGED, ui_element=editor._hull_dropdown, text="HUGE"),
        pygame.event.Event(pygame_gui.UI_TEXT_ENTRY_CHANGED, ui_element=editor._engine_speed_entry, text="999"),
        pygame.event.Event(pygame.TEXTINPUT, text="changed"),
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(1, 1)),
        pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=1),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_e),
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g),
    ]:
        pygame.event.post(event)
    game.input_processor.handle_input()
    assert editor._description_dialog is dialog
    assert editor._comp == before
    assert editor._hull_size == HullSize.MEDIUM
    assert editor._hull_dropdown.selected_option[0] == "MEDIUM"
    assert editor._selected_component_key == selected
    assert editor._display_entry.get_text() == name_before
    assert scroll.start_percentage == scroll_before
    assert editor.is_visible
    assert editor._save_dialog is None
    assert game.view_mode == "system"
    assert game.system_pan_offset == Position(0, 0)
    game.handle_mouse_wheel.assert_not_called()
    # Escape takes priority even if an editor field previously had focus.
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    game.input_processor.handle_input()
    assert editor._description_dialog is None
    assert editor.is_visible
    # Native title-bar X creates a close event asynchronously; let it pass through the router.
    gui.process_event(press(editor._comp_help_buttons["has_engine"]))
    dialog = editor._description_dialog
    gui.process_event(press(dialog.window.close_window_button))
    game.input_processor.handle_input()
    assert not dialog.window.alive()
    assert editor._description_dialog is None
    assert editor.is_visible


@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080), (2560, 1440)])
def test_help_layout_at_display_scales(pygame_context, tmp_path, size):
    config = DisplayConfig(*size)
    screen = pygame.display.set_mode(size)
    manager = build_ui_manager(config)
    editor = UnitEditorWindow(manager, config, CustomTemplateManager())
    editor.show()

    def capture(name):
        manager.update(0.1)
        screen.fill((5, 10, 20))
        manager.draw_ui(screen)
        pygame.image.save(screen, str(tmp_path / f"help-{name}.png"))

    try:
        for key, button in editor._comp_toggles.items():
            help_button = editor._comp_help_buttons[key]
            cost = editor._comp_cost_labels[key]
            arrow = editor._comp_select_btns[key]
            assert button.relative_rect.right < help_button.relative_rect.left
            assert help_button.relative_rect.right < cost.relative_rect.left
            assert cost.relative_rect.right < arrow.relative_rect.left
            assert not button.relative_rect.colliderect(help_button.relative_rect)
        editor._select_component("has_ability_component")
        capture("abilities")
        for equipped in (False, True):
            editor._comp.has_sensors = equipped
            editor._comp.has_antimatter_storage = equipped
            editor._update_ability_toggle_labels()
            last_bottom = 0
            for name, button in editor._ability_buttons.items():
                help_button = editor._ability_help_buttons[name]
                assert button.relative_rect.top >= last_bottom
                assert help_button.relative_rect.top == button.relative_rect.top
                assert button.relative_rect.right < help_button.relative_rect.left
                assert help_button.relative_rect.right <= editor._col_w - 20
                last_bottom = max(button.relative_rect.bottom, help_button.relative_rect.bottom)
        editor._ability_scroll_container.vert_scroll_bar.set_scroll_from_start_percentage(1.0)
        capture("abilities-scrolled")
        editor._select_component("has_intelligence_component")
        capture("intelligence")
        assert not editor._intel_ci_btn.relative_rect.colliderect(
            editor._comp_help_buttons["has_counter_intelligence"].relative_rect)
        for key in ("has_antimatter_storage", "has_cloaking_device"):
            editor.process_event(press(editor._comp_help_buttons[key]))
            dialog = editor._description_dialog
            capture(key)
            assert screen.get_rect().contains(dialog.window.get_abs_rect())
            assert not dialog.text_box.get_abs_rect().colliderect(dialog.close_button.get_abs_rect())
            editor.close_description()
        editor._select_component("has_ability_component")
        editor.process_event(press(editor._ability_help_buttons["nebula_catalyst"]))
        capture("nebula-catalyst")
        assert screen.get_rect().contains(editor._description_dialog.window.get_abs_rect())
        editor.close_description()
        editor.show_description("Long equipment description", "Equipment operating rules.<br><br>" * 80)
        dialog = editor._description_dialog
        assert dialog.text_box.scroll_bar is not None
        dialog.text_box.scroll_bar.set_scroll_from_start_percentage(1.0)
        capture("long-description-scrolled")
        assert dialog.text_box.scroll_bar.start_percentage > 0
    finally:
        editor.kill()
        manager.clear_and_reset()
