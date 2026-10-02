from __future__ import annotations
import os
from pathlib import Path
import subprocess
import sys
import pytest


pytestmark = pytest.mark.smoke


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


def test_clean_process_launch_smoke_test(tmp_path):
    """Smoke test: Launch game.py --smoke-test in a fresh subprocess and verify clean startup and shutdown."""
    env = os.environ.copy()
    env["SDL_VIDEODRIVER"] = "dummy"
    env["SDL_AUDIODRIVER"] = "dummy"

    script = ('import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); '
              'from game import main; sys.exit(main(sys.argv[3:], instance_path=Path(sys.argv[2])))')
    result = subprocess.run(
        [sys.executable, '-c', script, str(Path(__file__).resolve().parents[1]),
         str(tmp_path / 'instance.lock'), "--smoke-test", "--smoke-test-frames", "3", "--port", "0"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=env,
        cwd=tmp_path,
        timeout=15,
    )
    assert result.returncode == 0, (
        f"Launch smoke test failed (code {result.returncode}):\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
