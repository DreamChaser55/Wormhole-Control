"""Real widgets at supported physical pixel sizes; layout warnings are failures."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pygame
import pygame_gui
import pytest

from display_config import DisplayConfig
from gui.retrofit_gui import RetrofitWizardWindow
from gui.unit_editor_gui import UnitEditorWindow
from gui.unit_catalog_window import UnitCatalogWindow
from gui.theme_loader import build_ui_manager
from geometry import Position, Vector
from tests.support.campaigns import campaign, ship
from constants import HullSize
from unit_catalog import describe_template
from unit_components.constructor import instantiate_unit_from_template
from unit_templates import UNIT_TEMPLATES

pytestmark = [
    pytest.mark.filterwarnings('error:Finding font with id:UserWarning'),
    pytest.mark.filterwarnings('error:Trying to pre-load font id:UserWarning'),
    pytest.mark.filterwarnings('error:Label Rect is too small:UserWarning'),
]


@pytest.mark.parametrize('size', [(1280, 720), (1920, 1080), (2560, 1440)])
def test_application_views_at_explicit_display_sizes(game_factory, tmp_path, size):
    config = DisplayConfig(*size, fullscreen=False)
    with patch('application_bootstrap.discover_display_config', side_effect=AssertionError('unexpected discovery')), \
         patch('game.discover_display_config', side_effect=AssertionError('unexpected discovery')):
        game = game_factory(display_config=config)
    gui = game.gui
    assert game.screen.get_size() == size
    assert gui.display_config == config

    def capture(name):
        gui.manager.update(0.1)
        game.screen.fill((5, 10, 20))
        gui.manager.draw_ui(game.screen)
        pygame.image.save(game.screen, str(Path(tmp_path) / f'{name}.png'))

    gui.show_new_game_wizard()
    capture('wizard-map')
    gui.new_game_wizard.go_to_stage(2)
    capture('wizard-players')
    gui.close_new_game_wizard()

    editor = UnitEditorWindow(gui.manager, DisplayConfig(*size), game.custom_template_manager)
    editor.show()
    capture('designer')
    editor._display_entry.set_text('Feedback layout')
    entry = editor._engine_speed_entry
    entry.set_text('bad')
    entry.focus()
    entry.edit_position = 2
    entry.select_range = [1, 2]
    editor.process_event(pygame.event.Event(pygame_gui.UI_TEXT_ENTRY_CHANGED, ui_element=entry))
    capture('designer-invalid')
    assert entry.get_text() == 'bad' and entry.is_focused
    assert entry.edit_position == 2 and entry.select_range == [1, 2]
    assert entry.border_colour == pygame.Color('#FF6666')
    assert entry.tool_tip_text and 'Engines / Speed' in editor._summary_box.html_text
    assert not editor._save_button.is_enabled
    for widget in (entry, editor._summary_box, editor._capacity_excess_label,
                   editor._save_button, editor._save_as_button, editor._status_label):
        assert editor._panel.get_abs_rect().contains(widget.get_abs_rect())
    entry.set_text('100')
    editor.process_event(pygame.event.Event(pygame_gui.UI_TEXT_ENTRY_CHANGED, ui_element=entry))
    assert editor._save_button.is_enabled and entry.tool_tip_text is None
    assert entry.is_focused
    from gui.equipment_input import INPUT_FIELDS
    for spec in INPUT_FIELDS.values():
        getattr(editor, spec.widget).set_text('bad')
    editor.process_event(pygame.event.Event(pygame_gui.UI_TEXT_ENTRY_CHANGED, ui_element=entry))
    capture('designer-multiple-errors')
    assert len(editor._field_errors) == len(INPUT_FIELDS)
    assert editor._summary_box.scroll_bar is not None
    editor._summary_box.scroll_bar.set_scroll_from_start_percentage(1.0)
    capture('designer-errors-scrolled')
    assert editor._summary_box.scroll_bar.start_percentage > 0
    assert entry.is_focused
    editor.kill()

    world = campaign()
    target = ship(world, hull=HullSize.MEDIUM)
    constructor = ship(world, hull=HullSize.LARGE)
    retrofit = RetrofitWizardWindow(gui.manager, pygame.Vector2(*size), target, [constructor], initial_comp_key='Weapons')
    capture('retrofit')
    retrofit._turret_cd_entry.set_text('1.5')
    retrofit._sync_cost_and_summary()
    capture('retrofit-invalid')
    assert not retrofit._confirm_button.is_enabled
    assert 'integer' in retrofit._status_box.html_text
    assert retrofit._turret_cd_entry.tool_tip_text
    assert retrofit._turret_labels[0].get_relative_rect().height > 0
    retrofit.kill()

    assert game.start_new_game()
    capture('hud')
    dialog = gui.show_info_dialog('Campaign ready. Orders execute on the active player’s turn.', title='Ready')
    capture('dialog')
    assert game.screen.get_rect().contains(dialog.get_abs_rect())


def test_turn_processor_alias_has_one_owner(game_factory):
    game = game_factory(display_config=DisplayConfig(1280, 720, False))
    original = game.turn_processor
    assert game.turn_processor is original
    sentinel = object()
    game.turn_processor = sentinel
    assert game.turn_processor is sentinel
    game.turn_processor = original


@pytest.mark.parametrize('size', [(1280, 720), (1920, 1080), (2560, 1440)])
def test_wing_production_layout_at_explicit_display_sizes(pygame_context, tmp_path, size):
    from gui.wing_production_window import WingProductionWindow
    screen = pygame.display.set_mode(size)
    config = DisplayConfig(*size)
    manager = build_ui_manager(config)
    world = campaign()
    carrier = instantiate_unit_from_template('FLEET_CARRIER', world.players[0],
        'Sol', (0, 0), Position(100, 100), world.galaxy, world)
    carrier.strikecraft_bay_component.set_production(0, 'LONG_RANGE_BOMBER_WING')
    gui = SimpleNamespace(game_instance=world, screen_res=Vector(*size), manager=manager,
                          display_config=config)
    picker = WingProductionWindow(gui, carrier, 0)

    def capture(name):
        manager.update(0.1)
        screen.fill((5, 10, 20))
        manager.draw_ui(screen)
        pygame.image.save(screen, str(tmp_path / f'wing-production-{name}.png'))

    try:
        panel = picker.window.get_container().get_rect()
        assert screen.get_rect().contains(picker.window.get_abs_rect())
        widgets = [picker.list, picker.turret_dropdown, picker.defense_dropdown,
                   picker.details, picker.select_button, picker.cancel_button]
        for index, widget in enumerate(widgets):
            rect = widget.get_abs_rect()
            assert rect.width > 0 and rect.height > 0 and panel.contains(rect)
            assert all(not rect.colliderect(other.get_abs_rect()) for other in widgets[index+1:])
        capture('presets')
        assert picker.details.scroll_bar is not None
        picker.details.scroll_bar.set_scroll_from_start_percentage(1.0)
        capture('scrolled')
        assert picker.details.scroll_bar.start_percentage > 0
        for name, dropdown in [('turrets', picker.turret_dropdown), ('defenses', picker.defense_dropdown)]:
            button = dropdown.current_state.selected_option_button
            assert button.font.get_rect(button.text).width < button.get_abs_rect().width - 10
            dropdown.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED,
                ui_element=dropdown.current_state.open_button))
            capture(name)
            assert dropdown.current_state is dropdown.menu_states['expanded']
            options = dropdown.current_state.options_selection_list
            assert panel.contains(options.get_abs_rect())
            for item in options.item_list:
                button = item['button_element']
                if button is not None:
                    assert button.font.get_rect(item['text']).width < button.get_abs_rect().width - 10
            dropdown.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED,
                ui_element=dropdown.current_state.close_button))
            manager.update(0.1)
    finally:
        picker.close()
        manager.clear_and_reset()


@pytest.mark.parametrize('size', [(1280, 720), (1920, 1080), (2560, 1440)])
def test_catalog_layout_at_explicit_display_sizes(pygame_context, tmp_path, size):
    screen = pygame.display.set_mode(size)
    manager = build_ui_manager(DisplayConfig(*size))
    world = campaign()
    world.event_bus = SimpleNamespace(publish=lambda event: None)
    builder = instantiate_unit_from_template('CONSTRUCTOR_MK1', world.players[0],
        'Sol', (0, 0), Position(100, 100), world.galaxy, world)
    gui = SimpleNamespace(game_instance=world, screen_res=Vector(*size), manager=manager)
    gui.display_config = DisplayConfig(int(Vector(*size).x), int(Vector(*size).y))
    catalog = UnitCatalogWindow(gui, [builder], Position(200, 200), system_name=([builder])[0].in_system, hex_coord=([builder])[0].in_hex)

    def capture(name):
        manager.update(0.1)
        screen.fill((5, 10, 20))
        manager.draw_ui(screen)
        pygame.image.save(screen, str(tmp_path / f'catalog-{name}.png'))

    try:
        outer = catalog.window.get_abs_rect()
        assert screen.get_rect().contains(outer)
        assert outer.width >= size[0] * .95
        assert outer.height >= size[1] * .87
        panel = catalog.window.get_container().get_rect()
        widgets = [catalog.search, catalog.category, catalog.hull, catalog.kind,
                   catalog.affordability, catalog.list, catalog.details,
                   catalog.queue_button, catalog.build_button, catalog.price_label]
        for index, widget in enumerate(widgets):
            rect = widget.get_abs_rect()
            assert rect.width > 0 and rect.height > 0
            assert panel.contains(rect)
            assert all(not rect.colliderect(other.get_abs_rect())
                       for other in widgets[index + 1:])

        catalog.show_entry(describe_template('FLEET_CARRIER', UNIT_TEMPLATES['FLEET_CARRIER']))
        capture('fleet-carrier')
        for item in catalog.list.item_list:
            button = item['button_element']
            if button is not None:
                assert button.font.get_rect(item['text']).height < catalog.list.list_item_height
                assert button.font.get_rect(item['text']).width < button.get_abs_rect().width

        for button in (catalog.build_button, catalog.queue_button):
            assert button.font.get_rect(button.text).width < button.get_abs_rect().width - 10
        assert catalog.list.scroll_bar is not None
        assert catalog.details.scroll_bar is not None
        for scroll_bar in (catalog.list.scroll_bar, catalog.details.scroll_bar):
            scroll_bar.set_scroll_from_start_percentage(1.0)
        capture('scrolled')
        assert catalog.list.scroll_bar.start_percentage > 0
        assert catalog.details.scroll_bar.start_percentage > 0
        for name, dropdown in [('category', catalog.category), ('hull', catalog.hull)]:
            dropdown.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED,
                ui_element=dropdown.current_state.open_button))
            capture(name)
            assert dropdown.current_state is dropdown.menu_states['expanded']
            dropdown.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED,
                ui_element=dropdown.current_state.close_button))
            manager.update(0.1)

        catalog.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED,
                                                ui_element=catalog.queue_button))
        assert not catalog.window.alive()
    finally:
        catalog.kill()
        manager.clear_and_reset()
