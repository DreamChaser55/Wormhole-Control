

import builtins
from pathlib import Path
from geometry import Vector
from utils import resource_path

def test_resource_paths_ignore_cwd_and_support_bundles(tmp_path, monkeypatch):
    path = resource_path('theme.json')
    monkeypatch.chdir(tmp_path)
    assert resource_path('theme.json') == path and Path(path).is_file()
    monkeypatch.setattr('sys._MEIPASS', str(tmp_path), raising=False)
    assert resource_path('theme.json') == str(tmp_path / 'theme.json')


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
