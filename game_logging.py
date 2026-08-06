"""Application logging configuration for Wormhole Control."""
import logging


class GameLogFormatter(logging.Formatter):
    """Custom logging formatter that includes the date only on the first logged line."""

    def __init__(self, fmt=None, datefmt=None, style='%'):
        super().__init__(fmt, datefmt, style)
        self.first_record = True

    def formatTime(self, record, datefmt=None):
        if self.first_record:
            self.first_record = False
            self.default_time_format = '%Y-%m-%d %H:%M:%S'
        else:
            self.default_time_format = '%H:%M:%S'
        return super().formatTime(record, datefmt)


def setup_logging(log_to_file: bool = False):
    """Configure logging for the application.

    When log_to_file is False (e.g. during module import / test execution),
    logs are directed to standard output only and game.log is untouched.
    When log_to_file is True (e.g. during main game launch), game.log is initialized in 'w' mode.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(GameLogFormatter(fmt))
    root_logger.addHandler(stream_handler)

    if log_to_file:
        file_handler = logging.FileHandler("game.log", mode='w')
        file_handler.setFormatter(GameLogFormatter(fmt))
        root_logger.addHandler(file_handler)
