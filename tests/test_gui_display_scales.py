"""Real widgets at supported physical pixel sizes; layout warnings are failures."""
from pathlib import Path
from unittest.mock import patch

import pygame
import pytest

from display_config import DisplayConfig
from gui.retrofit_gui import RetrofitWizardWindow
from gui.unit_editor_gui import UnitEditorWindow
from tests.support.campaigns import campaign, ship
from constants import HullSize

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
