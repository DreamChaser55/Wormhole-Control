from __future__ import annotations

import os
import subprocess
import sys
import pytest

pytestmark = pytest.mark.smoke


def test_clean_process_import_game_and_renderer():
    """Smoke test: Ensure game and renderer can be cleanly imported in a fresh process."""
    result = subprocess.run(
        [sys.executable, "-c", "import game; import renderer"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=15,
    )
    assert result.returncode == 0, f"Importing game and renderer failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


def test_clean_process_import_rendering_modules():
    """Smoke test: Ensure all rendering modules can be cleanly imported in isolation."""
    modules = [
        "rendering.drawing_utils",
        "rendering.galaxy_renderer",
        "rendering.main_menu_renderer",
        "rendering.system_renderer",
        "rendering.sector_renderer",
    ]
    script = "; ".join(f"import {mod}" for mod in modules)
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=15,
    )
    assert result.returncode == 0, f"Importing rendering modules failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


def test_galaxy_renderer_annotations_valid():
    """Ensure annotations on preview functions in rendering.galaxy_renderer do not raise NameError."""
    import rendering.galaxy_renderer as gr

    # Verify annotations dictionary exists and does not trigger NameError
    assert hasattr(gr.draw_galaxy_preview, "__annotations__")
    assert hasattr(gr.get_system_at_preview_point, "__annotations__")

    # If get_annotations or get_type_hints is available, verify resolution works cleanly
    try:
        import inspect
        if hasattr(inspect, "get_annotations"):
            ann1 = inspect.get_annotations(gr.draw_galaxy_preview)
            ann2 = inspect.get_annotations(gr.get_system_at_preview_point)
            assert "galaxy" in ann1
            assert "screen_pos" in ann2
    except Exception as e:
        pytest.fail(f"Failed to evaluate annotations on galaxy_renderer preview functions: {e}")


def test_clean_process_launch_smoke_test():
    """Smoke test: Launch game.py --smoke-test in a fresh subprocess and verify clean startup and shutdown."""
    env = os.environ.copy()
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"

    result = subprocess.run(
        [sys.executable, "game.py", "--smoke-test", "--smoke-test-frames", "3"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=env,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"Launch smoke test failed (code {result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )


def test_in_process_game_launch_and_tick():
    """Smoke test: Initialize Game in-process, tick 1 frame of update and draw, and shut down cleanly."""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    from game import Game
    game = Game()
    try:
        assert game.view_mode == "main_menu"
        assert game.is_running is True
        assert game.gui is not None
        assert game.renderer is not None
        assert game.control_service.is_running is True

        # Exercise one frame
        time_delta = 1.0 / 60.0
        game.update(time_delta)
        game.draw()
    finally:
        game.control_service.shutdown()
        game.ai_coordinator.shutdown()
        import pygame
        pygame.quit()


def test_clean_process_pytest_collection():
    """Smoke test: Verify all test files can be imported and collected by pytest without syntax/import errors."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"Pytest collection failed (code {result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
