"""Actual renderers and open controls respect changing ownership disclosure."""
import pygame
import pytest

from tests.support.campaigns import campaign
from tests.test_planetary_intel import world, scout


def scene(game_factory):
    game = game_factory()
    game.__dict__.update(vars(campaign()))
    game.galaxy.game = game
    game.gui.show_game_ui()
    game.reset_system_camera()
    game.reset_sector_camera()
    return game


@pytest.mark.parametrize('mode', ['galaxy', 'system', 'sector'])
@pytest.mark.parametrize('remembered', [False, True])
def test_selected_world_rendering_does_not_reveal_unseen_changes(game_factory, monkeypatch, mode, remembered):
    game = scene(game_factory)
    body = world(game, owner=None)
    unit = scout(game, body)
    unit.position.x = 4000
    game.players[1].homeworld_id = body.id
    if remembered:
        game.players[0].planetary_intel[body.id] = {'owner_id': game.players[1].id, 'observed_turn': 2}
    game.selected_objects = [body]
    game.view_mode = mode
    monkeypatch.setattr(pygame.time, 'get_ticks', lambda: 1000)
    def render():
        game.recompute_visibility()
        game.screen.fill((0, 0, 0))
        game.overlay_surface.fill((0, 0, 0, 0))
        renderer = getattr(game.renderer, mode + '_renderer')
        getattr(renderer, 'draw_' + mode + '_view')()
        game.screen.blit(game.overlay_surface, (0, 0))
        return pygame.image.tobytes(game.screen, 'RGB')
    before = render()
    body.owner = game.players[1]
    body.population = 80
    body.fortification_level = 3
    body.defense_readiness = .3
    assert render() == before


def test_open_dialog_refreshes_on_sensor_loss_and_closes_on_hotseat_and_load(game_factory, tmp_path):
    from gui.planetary_window import PlanetaryWindow
    from tests.test_planetary_warfare import vessel
    from save_manager import save_game_to_file
    game = scene(game_factory)
    body = world(game)
    unit = vessel(game, body, troops=40)
    unit.sensors_component.long_range_hexes = 1
    game.recompute_visibility()
    dialog = game.gui.planetary_window = PlanetaryWindow(game.gui, unit, body, 'invade_planet')
    assert 'Success chance:' in dialog.preview.html_text
    unit.sensors_component.long_range_hexes = unit.sensors_component.short_range_radius = 0
    game.recompute_visibility()
    assert 'Unknown until sensor contact returns' in dialog.preview.html_text
    assert 'Last observed: turn 7' in dialog.preview.html_text
    assert dialog.submit.is_enabled and dialog.append.is_enabled
    game.current_player_index = 1
    game.recompute_visibility()
    assert game.gui.planetary_window is None
    game.current_player_index = 0
    unit.sensors_component.long_range_hexes = 1
    game.recompute_visibility()
    game.gui.planetary_window = PlanetaryWindow(game.gui, unit, body, 'invade_planet')
    saved = tmp_path / 'ownership.json'
    assert save_game_to_file(game, str(saved))
    assert game.load_game(str(saved))
    assert game.gui.planetary_window is None
