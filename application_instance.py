"""Process-wide, OS-held application lease, independent of checkout and port."""
from __future__ import annotations

import errno
import os
from pathlib import Path
import tempfile
from threading import Lock
from typing import BinaryIO


ALREADY_RUNNING_EXIT_CODE = 3


class AlreadyRunningError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Wormhole Control is already running. Close the existing game before starting another process.")


def instance_lock_path() -> Path:
    # Windows' temp directory is already per-user; Unix needs the user ID too.
    user = str(os.getuid()) if hasattr(os, "getuid") else "user"
    return Path(tempfile.gettempdir()) / f"wormhole-control-{user}.instance.lock"


_mutex = Lock()
_held: dict[Path, tuple[BinaryIO, int]] = {}


class InstanceLease:
    """Close exactly once; the OS also releases the lock after a crash."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.closed = False

    def close(self) -> None:
        with _mutex:
            if self.closed:
                return
            self.closed = True
            stream, references = _held[self.path]
            if references > 1:
                _held[self.path] = stream, references - 1
            else:
                del _held[self.path]
                stream.close()

    def __enter__(self) -> InstanceLease:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def acquire_instance(path: Path | None = None) -> InstanceLease:
    """Acquire before opening logs/windows; embedded tests may supply a private path.

    Never delete the lock file: deleting a locked inode would allow another
    process to acquire a different file. Contents are not a liveness/PID check.
    """
    path = (path or instance_lock_path()).resolve()
    with _mutex:
        if path in _held:
            stream, references = _held[path]
            _held[path] = stream, references + 1
            return InstanceLease(path)
        stream = path.open("a+b")
        try:
            # Windows locks one existing byte; a+b never truncates another writer.
            if path.stat().st_size == 0:
                stream.write(b"1")
                stream.flush()
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise AlreadyRunningError() from exc
            raise
        except BaseException:
            stream.close()
            raise
        _held[path] = stream, 1
        return InstanceLease(path)
