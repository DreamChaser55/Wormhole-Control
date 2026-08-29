import logging

logger = logging.getLogger(__name__)

import typing
import os
import sys
import time
import uuid

# Type definitions
class HexCoord(typing.NamedTuple):
    """Axial coordinates for the hex grid (q: axial column/diagonal, r: axial row)."""
    q: int
    r: int

ContextMenuOption = typing.Union[
    typing.Tuple[str, str],                                                  # Flat option: (label, action_id)
    typing.Tuple[str, typing.List[typing.Any]],                              # Submenu parent: (label, [(label, action_id), ...])
    typing.Tuple[str, typing.Tuple[typing.List[typing.Any], typing.Any]]     # Submenu with custom target: (label, (sub_options, sub_target))
]

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def timeit(func):
    """A decorator that prints the execution time of the function it decorates."""
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        logger.debug(f"Function {func.__name__} took {end_time - start_time:.6f} seconds to execute.")
        return result
    return wrapper

class Timer:
    """A simple timer class that can be used to time code execution."""
    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.is_running = False

    def start(self):
        """Starts the timer."""
        self.start_time = time.perf_counter()
        self.is_running = True

    def stop(self):
        """Stops the timer."""
        self.end_time = time.perf_counter()
        self.is_running = False

    def get_elapsed_time(self) -> float:
        """Returns the elapsed time in milliseconds."""
        if self.is_running:
            return (time.perf_counter() - self.start_time) * 1000
        elif self.end_time:
            return (self.end_time - self.start_time) * 1000
        else:
            return 0.0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stop()

    def __str__(self):
        return f"Elapsed Time: {self.get_elapsed_time():.4f} ms"


class ProfileTimer:
    """A context manager for profiling code blocks. It only runs and prints if PROFILE is enabled."""
    def __init__(self, name: str):
        self.name = name
        self.timer = Timer()

    def __enter__(self):
        from constants import PROFILE
        if PROFILE:
            self.timer.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        from constants import PROFILE
        if PROFILE:
            self.timer.stop()
            logger.debug(f"  [Profile] {self.name} took: {self.timer}")


def color_to_hex(color) -> str:
    """Converts an (R, G, B) or (R, G, B, A) tuple or pygame.Color object to a hex string '#RRGGBB'."""
    if color is None:
        return "#A0A0B0"
    try:
        if hasattr(color, 'r') and isinstance(color.r, int) and isinstance(color.g, int) and isinstance(color.b, int):
            return f"#{color.r:02x}{color.g:02x}{color.b:02x}"
        if isinstance(color, (tuple, list)) and len(color) >= 3:
            return f"#{int(color[0]):02x}{int(color[1]):02x}{int(color[2]):02x}"
    except Exception:
        pass
    return "#A0A0B0"


def generate_short_id(prefix: str = "", length: int = 8) -> str:
    """Generates a concise hexadecimal identifier string (8 chars by default)."""
    token = uuid.uuid4().hex[:length]
    return f"{prefix}{token}" if prefix else token



