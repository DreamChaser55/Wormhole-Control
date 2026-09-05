import subprocess
import sys
import pytest


def test_clean_process_import_game_and_renderer():
    """Smoke test: Ensure game and renderer can be cleanly imported in a fresh process."""
    result = subprocess.run(
        [sys.executable, "-c", "import game; import renderer"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Importing game and renderer failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


def test_clean_process_import_rendering_galaxy_renderer():
    """Smoke test: Ensure rendering.galaxy_renderer can be cleanly imported in isolation."""
    result = subprocess.run(
        [sys.executable, "-c", "import rendering.galaxy_renderer"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Importing rendering.galaxy_renderer failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


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
