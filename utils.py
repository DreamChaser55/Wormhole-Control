import typing
import os
import sys
import time

# Type definitions
HexCoord = typing.Tuple[int, int]
ContextMenuOption = typing.Tuple[str, str]

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
        print(f"Function {func.__name__} took {end_time - start_time:.6f} seconds to execute.")
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
