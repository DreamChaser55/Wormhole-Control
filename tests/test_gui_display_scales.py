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

    editor = UnitEditorWindow(gui.manager, pygame.Vector2(*size), game.custom_template_manager)
    editor.show()
    capture('designer')
    editor.kill()

    world = campaign()
    target = ship(world, hull=HullSize.MEDIUM)
    constructor = ship(world, hull=HullSize.LARGE)
    retrofit = RetrofitWizardWindow(gui.manager, pygame.Vector2(*size), target, [constructor], initial_comp_key='Weapons')
    capture('retrofit')
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
    assert game.turn_manager is original
    sentinel = object()
    game.turn_manager = sentinel
    assert game.turn_processor is sentinel
    game.turn_processor = original


@pytest.mark.parametrize('size', [(1280, 720), (1920, 1080), (2560, 1440)])
def test_catalog_layout_at_explicit_display_sizes(pygame_context, tmp_path, size):
    screen = pygame.display.set_mode(size)
    manager = build_ui_manager(Vector(*size))
    world = campaign()
    world.event_bus = SimpleNamespace(publish=lambda event: None)
    builder = instantiate_unit_from_template('CONSTRUCTOR_MK1', world.players[0],
        'Sol', (0, 0), Position(100, 100), world.galaxy, world)
    gui = SimpleNamespace(game_instance=world, screen_res=Vector(*size), manager=manager)
    catalog = UnitCatalogWindow(gui, [builder], Position(200, 200))

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

        catalog.process_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED,
                                                ui_element=catalog.queue_button))
        assert catalog.window.alive()
        for button in (catalog.build_button, catalog.queue_button):
            assert button.font.get_rect(button.text).width < button.get_abs_rect().width - 10
        capture('queued')
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
    finally:
        catalog.kill()
        manager.clear_and_reset()
