"""Resource lifetimes at GUI test boundaries, including unsuccessful tests."""
import gc
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import weakref

import pygame
import pygame_gui

from tests.support.pygame_runtime import drain_events, release_gui_resources


def test_draining_releases_event_payload(pygame_context):
    class Payload:
        pass

    payload = Payload()
    reference = weakref.ref(payload)
    pygame.event.post(pygame.event.Event(pygame.USEREVENT, payload=payload))
    del payload
    assert reference() is not None

    drain_events()
    assert reference() is None
    assert pygame.event.get() == []


def test_cleanup_releases_multiple_managers_and_widgets(pygame_context):
    def create():
        manager = pygame_gui.UIManager((1280, 720))
        widget = pygame_gui.elements.UIButton(
            pygame.Rect(0, 0, 100, 30), 'Test', manager=manager)
        references = [weakref.ref(manager), weakref.ref(widget)]
        pygame.event.post(pygame.event.Event(
            pygame_gui.UI_BUTTON_PRESSED, ui_element=widget))
        widget.kill()
        manager.clear_and_reset()
        return references

    references = [reference for _ in range(3) for reference in create()]
    gc.collect()
    assert any(reference() is not None for reference in references)
    release_gui_resources()
    assert all(reference() is None for reference in references)
    assert pygame.get_init()


def test_failed_test_releases_factory_games_and_injected_reference(tmp_path):
    # Exercise actual pytest/unittest finalizer ordering in an isolated process.
    # Deliberately retain the factory and test instance, but not the games.
    script = tmp_path / 'test_failure_cleanup.py'
    script.write_text(textwrap.dedent('''
        import gc
        import unittest
        import weakref
        import pygame
        import pytest
        from pygame_gui.core.utility import get_default_manager

        references = []
        retained = []

        def remember(factory):
            game = factory()
            references.extend([weakref.ref(game), weakref.ref(game.gui.manager)])

        @pytest.mark.usefixtures('game_factory')
        class TestFailure(unittest.TestCase):
            def test_failure(self):
                retained.extend([self, self.make_game])
                remember(self.make_game)
                remember(self.make_game)
                self.fail('intentional cleanup probe')

        def test_resources_released():
            gc.collect()
            assert not hasattr(retained[0], 'make_game')
            assert get_default_manager() is None
            assert all(reference() is None for reference in references)
            assert pygame.get_init()
    '''), encoding='utf-8')
    environment = os.environ.copy()
    environment.pop('WORMHOLE_CI_REPORT_DIR', None)
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '-p', 'tests.conftest', '-p',
         'no:cacheprovider', '-q', '--tb=short', '-c', str(root / 'pytest.ini'),
         '--rootdir', str(tmp_path), '--confcutdir', str(tmp_path),
         '--basetemp', str(tmp_path / 'child-temp'),
         str(script)],
        cwd=root, env=environment, capture_output=True, text=True, timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert 'intentional cleanup probe' in output, output
    assert '1 failed, 1 passed' in output, output


def test_translation_state_is_restored_after_success_and_failure(tmp_path):
    # Exercise real fixture ordering, including raw managers and failed teardown.
    script = tmp_path / 'test_translation_isolation.py'
    script.write_text(textwrap.dedent('''
        import json
        from pathlib import Path

        import i18n
        import pygame
        import pygame_gui
        import pytest
        from pygame_gui.core.utility import translate

        paths = i18n.load_path
        baseline = []
        for name in ('first', 'second'):
            directory = Path(__file__).parent / name
            directory.mkdir()
            (directory / f'{name}.en.json').write_text(
                json.dumps({'en': {'label': f'{name} translation'}}), encoding='utf-8')
            baseline.append(str(directory))
        paths[:] = baseline
        i18n.set('locale', 'fr')
        i18n.set('file_format', 'py')

        def assert_restored():
            assert i18n.load_path is paths
            assert i18n.get('load_path') is paths
            assert paths == baseline
            assert i18n.get('locale') == 'fr'
            assert i18n.get('file_format') == 'py'

        @pytest.mark.parametrize('attempt', range(2))
        def test_raw_managers(pygame_context, attempt):
            assert_restored()
            managers = []
            try:
                for _ in range(3):
                    manager = pygame_gui.UIManager((1280, 720))
                    managers.append(manager)
                    for key, expected in (
                        ('pygame-gui.OK', 'OK'),
                        ('first.label', 'first translation'),
                        ('second.label', 'second translation'),
                        ('Literal text. Still unchanged.', 'Literal text. Still unchanged.'),
                    ):
                        pygame_gui.elements.UILabel(
                            pygame.Rect(0, 0, 400, 40), key, manager=manager)
                        assert translate(key) == expected
            finally:
                for manager in managers:
                    manager.clear_and_reset()

        @pytest.fixture
        def failed_teardown(game_factory):
            assert_restored()
            game_factory()
            game_factory()
            yield
            raise RuntimeError('intentional translation teardown failure')

        def test_failure(failed_teardown):
            pytest.fail('intentional translation test failure')

        def test_next_case_sees_original_state():
            assert_restored()
    '''), encoding='utf-8')
    environment = os.environ.copy()
    environment.pop('WORMHOLE_CI_REPORT_DIR', None)
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', '-p', 'tests.conftest', '-p',
         'no:cacheprovider', '-q', '--tb=short', '-c', str(root / 'pytest.ini'),
         '--rootdir', str(tmp_path), '--confcutdir', str(tmp_path),
         '--basetemp', str(tmp_path / 'child-temp'), str(script)],
        cwd=root, env=environment, capture_output=True, text=True, timeout=60,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert 'intentional translation test failure' in output, output
    assert 'intentional translation teardown failure' in output, output
    assert '1 failed, 3 passed, 1 error' in output, output
