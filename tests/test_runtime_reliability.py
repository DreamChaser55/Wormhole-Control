"""Boundary regressions for WC-015 and source-independent assets."""
import builtins
from pathlib import Path
from types import SimpleNamespace

import pytest

from galaxy import StarSystem
from geometry import Vector
from game_control_protocol import ControlService
from game_ai.commands import CommandGateway
from game_ai.contracts import Command, CommandBatch
from tests.test_ai_order_contract_v2 import world
from utils import resource_path, user_data_path


def test_missing_and_valid_hex_lookups():
    system = object.__new__(StarSystem)
    sector = SimpleNamespace(units=[object()], celestial_bodies=[object()])
    system.hexes = {(0, 0): sector}
    assert system.get_units_in_hex((9, 9)) == []
    assert system.get_celestial_bodies_in_hex((9, 9)) == []
    assert system.get_units_in_hex((0, 0)) is sector.units
    assert system.get_celestial_bodies_in_hex((0, 0)) is sector.celestial_bodies


@pytest.mark.parametrize('origin,destination,coord,success', [
    ('missing', 'Sol', (0, 0), False), ('Sol', 'missing', (0, 0), False),
    ('Sol', 'Other', (99, 99), False), ('Sol', 'Other', (0, 0), True),
])
def test_transfer_validation_preserves_membership(origin, destination, coord, success):
    game, player, _, unit = world()
    galaxy = game.galaxy
    galaxy.systems['Other'] = StarSystem('Other', Vector(500, 0), radius=2)
    before = (unit.in_system, unit.in_hex)
    result = galaxy.move_unit_between_systems(unit, origin, destination, coord)
    assert result is success
    if success:
        assert unit in galaxy.systems['Other'].get_units_in_hex((0, 0))
        assert unit not in galaxy.systems['Sol'].get_units_in_hex(before[1])
    else:
        assert (unit.in_system, unit.in_hex) == before
        assert unit in galaxy.systems['Sol'].get_units_in_hex(before[1])
        assert unit not in galaxy.systems['Other'].get_units_in_hex((0, 0))


@pytest.mark.parametrize('host', ['localhost', '0.0.0.0', '::1', '192.0.2.1', None])
def test_control_rejects_unsupported_hosts(host):
    with pytest.raises(ValueError, match='127.0.0.1'):
        ControlService(None, host=host, port=0)
    assert not ControlService(None, host='127.0.0.1', port=0).is_running


@pytest.mark.parametrize('stage', ['prepare', 'commit'])
def test_command_diagnostics_are_private_and_preserve_results(stage, monkeypatch, caplog):
    game, player, _, unit = world()
    gateway = CommandGateway(game)
    secret = 'PRIVATE-COMMAND-EXCEPTION'
    def failure(*args, **kwargs):
        raise RuntimeError(secret)
    command = Command('set_stance', (unit.id,), stance='attack_same_sector')
    if stage == 'prepare':
        monkeypatch.setattr(gateway, '_prepare', failure)
    else:
        monkeypatch.setattr(unit.commander_component, 'set_stance', failure)
    result = gateway.apply_batch(player, CommandBatch((command,)))
    assert not result.accepted
    assert result.errors[0].code == ('invalid_command' if stage == 'prepare' else 'commit_failed')
    assert result.applied_count == 0
    assert result.requires_observation is (stage == 'commit')
    assert secret not in caplog.text and secret not in str(result)
    assert f'stage={stage}' in caplog.text
    assert 'index=0 type=set_stance exception=RuntimeError' in caplog.text
    assert 'test_runtime_reliability.py' in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_resource_paths_ignore_cwd_and_support_bundles(tmp_path, monkeypatch):
    path = resource_path('theme.json')
    monkeypatch.chdir(tmp_path)
    assert resource_path('theme.json') == path and Path(path).is_file()
    monkeypatch.setattr('sys._MEIPASS', str(tmp_path), raising=False)
    assert resource_path('theme.json') == str(tmp_path / 'theme.json')


@pytest.mark.parametrize('platform,variable,subdir', [
    ('win32', 'LOCALAPPDATA', ''), ('darwin', None, 'Library/Application Support'),
    ('linux', 'XDG_DATA_HOME', ''),
])
def test_user_storage_defaults(platform, variable, subdir, tmp_path, monkeypatch):
    monkeypatch.delenv('WORMHOLE_USER_DATA_DIR')
    monkeypatch.setattr('sys.platform', platform)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    if variable:
        monkeypatch.setenv(variable, str(tmp_path))
    assert user_data_path() == tmp_path / subdir / 'WormholeControl'


def test_user_storage_override(tmp_path, monkeypatch):
    monkeypatch.setenv('WORMHOLE_USER_DATA_DIR', str(tmp_path))
    assert user_data_path() == tmp_path
    monkeypatch.setenv('WORMHOLE_USER_DATA_DIR', 'relative')
    with pytest.raises(ValueError, match='absolute'):
        user_data_path()


def test_themes_are_scaled_in_memory_without_writes(tmp_path, monkeypatch):
    import pygame
    from gui import theme_loader
    pygame.font.init()
    original = builtins.open
    def read_only(file, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in 'wax+'), f'Unexpected write: {file}'
        return original(file, mode, *args, **kwargs)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtins, 'open', read_only)
    for scale in (1.0, 1.5):
        monkeypatch.setattr(theme_loader, 'TEXT_SCALE', scale)
        manager = theme_loader.build_ui_manager(Vector(1280, 720))
        assert manager.ui_theme.get_font_dictionary().known_font_paths['dejavu_sans']
        assert manager.ui_theme.get_font_info(['defaults'])['size'] == int(12 * scale)
    assert not list(tmp_path.iterdir())
