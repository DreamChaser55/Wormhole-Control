"""Application logging configuration for Wormhole Control."""
from contextlib import ExitStack
from copy import copy
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re


THIRD_PARTY_LOGGERS = (
    "openai",
    "openai._base_client",
    "httpx",
    "httpx2",
    "httpcore",
    "httpcore2",
    "httpcore.connection",
    "httpcore.connection_pool",
    "httpcore.http11",
    "httpcore.proxy",
)

# Inspect rendered output as well as logger identity: transports can rename their
# packages, and warning/error records can contain response headers or exceptions.
_SENSITIVE_HTTP_METADATA = re.compile(
    r"\b(?:authorization|(?:x-)?api-key|openai-(?:organization|project|processing-ms)|"
    r"x-(?:request-id|client-request-id|ratelimit-[\w-]+)|set-cookie)\b",
    re.IGNORECASE,
)

# Keep ownership independent of root attachment: callers may detach our handlers.
_application_handlers: list[logging.Handler] = []
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3


def rotate_startup_log(path):
    """Rotate raw child stderr between processes, before a new writer opens it."""
    path = Path(path)
    if not path.exists() or path.stat().st_size < LOG_MAX_BYTES:
        return
    for index in range(LOG_BACKUP_COUNT, 0, -1):
        source = path if index == 1 else Path(f'{path}.{index - 1}')
        destination = Path(f'{path}.{index}')
        if source.exists():
            source.replace(destination)


def format_unit_for_log(unit: object) -> str:
    """Identify a unit from its current fields, even after removal from the world.

    Diagnostic callers may supply incomplete objects; missing names/IDs remain
    explicit without requiring a galaxy lookup or importing domain classes.
    """
    name = getattr(unit, "name", None)
    unit_id = getattr(unit, "id", None)
    return f"{name if name is not None else 'Unit'} (id:{unit_id if unit_id is not None else 'unknown'})"


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

    def format(self, record):
        rendered = super().format(record)
        if not _SENSITIVE_HTTP_METADATA.search(rendered):
            return rendered
        safe = copy(record)
        safe.msg, safe.args = '[HTTP metadata redacted]', ()
        safe.exc_info = safe.exc_text = safe.stack_info = None
        # Preserve this record's already-formatted timestamp, including the date.
        safe.message = safe.msg
        return self.formatMessage(safe)

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

    Install filtered stderr output and, when log_to_file is True, append to
    rotating game.log in the working directory after closing previous destinations.
    INFO is normal; WORMHOLE_DEBUG_LOG=true opts into DEBUG traces. The active
    file rotates at 5 MiB with three retained backups.
    False leaves the file untouched apart from flushing an old owned handler.
    Cleanup errors propagate after all owned handlers have been processed. A
    file-opening error propagates with the new stderr handler still usable and
    owned. Returns None; importing this module does not configure logging.
    """
    root_logger = logging.getLogger()
    level = logging.DEBUG if os.environ.get('WORMHOLE_DEBUG_LOG', '').lower() in {'1', 'true', 'yes'} else logging.INFO
    root_logger.setLevel(level)

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
    stream_handler.setLevel(level)
    stream_handler.addFilter(ThirdPartyPayloadFilter())
    stream_handler.setFormatter(GameLogFormatter(fmt))
    _application_handlers.append(stream_handler)
    root_logger.addHandler(stream_handler)

    if log_to_file:
        file_handler = RotatingFileHandler("game.log", mode='a', encoding='utf-8',
                                          maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
        file_handler.setLevel(level)
        file_handler.addFilter(ThirdPartyPayloadFilter())
        file_handler.setFormatter(GameLogFormatter(fmt))
        _application_handlers.append(file_handler)
        root_logger.addHandler(file_handler)
