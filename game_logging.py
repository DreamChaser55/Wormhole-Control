"""Application logging configuration for Wormhole Control."""
from contextlib import ExitStack
import logging


THIRD_PARTY_LOGGERS = (
    "openai",
    "openai._base_client",
    "httpx",
    "httpx2",
    "httpcore",
    "httpcore.connection",
    "httpcore.connection_pool",
    "httpcore.http11",
    "httpcore.proxy",
)

# Keep ownership independent of root attachment: callers may detach our handlers.
_application_handlers: list[logging.Handler] = []


class ThirdPartyPayloadFilter(logging.Filter):
    """Drop verbose SDK records even if a child logger enables DEBUG itself."""

    def filter(self, record):
        is_client_record = any(
            record.name == name or record.name.startswith(name + ".")
            for name in THIRD_PARTY_LOGGERS
        )
        return not is_client_record or record.levelno >= logging.WARNING


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
    """Replace root logging destinations during explicit application setup.

    Detach all root handlers, but flush and close only handlers created here,
    including any already detached by callers. External handlers remain owned by
    their callers; the borrowed stderr stream is never closed.

    Install filtered stderr output and, when log_to_file is True, truncate
    game.log in the working directory after closing the previous destinations.
    False leaves the file untouched apart from flushing an old owned handler.
    Cleanup errors propagate after all owned handlers have been processed. A
    file-opening error propagates with the new stderr handler still usable and
    owned. Returns None; importing this module does not configure logging.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # These clients include complete request bodies in DEBUG records. The game
    # records its own bounded AI telemetry, so library logs must never contain
    # observations, memory, model output, or credentials.
    for logger_name in THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Attempt every flush/close even if an earlier cleanup operation fails.
    with ExitStack() as cleanup:
        for handler in _application_handlers:
            cleanup.callback(handler.close)
            cleanup.callback(handler.flush)
        _application_handlers.clear()

    fmt = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'

    stream_handler = logging.StreamHandler()
    stream_handler.addFilter(ThirdPartyPayloadFilter())
    stream_handler.setFormatter(GameLogFormatter(fmt))
    _application_handlers.append(stream_handler)
    root_logger.addHandler(stream_handler)

    if log_to_file:
        file_handler = logging.FileHandler("game.log", mode='w')
        file_handler.addFilter(ThirdPartyPayloadFilter())
        file_handler.setFormatter(GameLogFormatter(fmt))
        _application_handlers.append(file_handler)
        root_logger.addHandler(file_handler)
