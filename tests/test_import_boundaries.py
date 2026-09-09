"""Fresh processes catch eager facades and transient display initialization."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.check_import_boundaries import core_paths, violations

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('first', ['domain.units', 'unit_orders.base', 'unit_components.enums', 'galaxy'])
def test_core_imports_without_pygame_or_gui(first):
    script = f'''
import importlib, sys
class BlockPresentation:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {{'pygame', 'pygame_gui', 'gui', 'rendering', 'game', 'game_actions'}}:
            raise AssertionError('Core imported ' + fullname)
sys.meta_path.insert(0, BlockPresentation())
for module in [{first!r}, 'constants', 'domain.players', 'domain.communications', 'domain.celestials', 'domain.minefields', 'domain.units', 'unit_orders.registry', 'turn_processor', 'visibility', 'galaxy', 'game_settings']:
    importlib.import_module(module)
import entities
import unit_orders, unit_components
for facade in (entities, unit_orders, unit_components):
    for name in facade.__all__:
        getattr(facade, name)
from domain.units import Unit
from domain.identity import GameObject
from unit_orders.base import Order
assert entities.Unit is Unit and entities.GameObject is GameObject and entities.Order is Order
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_application_import_never_touches_platform_state():
    script = '''
import ctypes, importlib, logging, os, sys
from unittest.mock import patch
import pygame
def forbidden(*args, **kwargs):
    raise AssertionError('Import touched platform state')
before = tuple(logging.getLogger().handlers)
with patch('pygame.init', forbidden), patch('pygame.display.init', forbidden), patch('pygame.display.quit', forbidden), patch('pygame.display.Info', forbidden), patch('pygame.display.set_mode', forbidden), patch('pygame.display.get_init', forbidden):
    if os.name == 'nt':
        ctypes.windll.shcore.SetProcessDpiAwareness = forbidden
        ctypes.windll.user32.SetProcessDPIAware = forbidden
    import constants
    import game
assert not any(m == 'gui' or m.startswith('gui.') or m == 'rendering' or m.startswith('rendering.') for m in sys.modules)
assert tuple(logging.getLogger().handlers) == before
'''
    env = os.environ.copy()
    env.pop('SDL_VIDEODRIVER', None)
    result = subprocess.run([sys.executable, '-c', script], cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr


def test_static_core_boundaries():
    assert [error for path in core_paths() for error in violations(path)] == []


def test_boundary_check_includes_deferred_imports_but_allows_annotations(tmp_path):
    path = tmp_path / 'example.py'
    path.write_text('from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from game import Game\ndef f():\n    import pygame\n')
    assert violations(path) == ['example.py:5: core imports pygame']
