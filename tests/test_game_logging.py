"""Logging configuration owns its destinations without owning callers' resources."""
from contextlib import ExitStack
import io
import logging
import sys

import pytest

import game_logging


@pytest.fixture(autouse=True)
def isolated_logging(tmp_path, monkeypatch):
    """Restore process logging and close test-owned files even after assertion failures."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    names = (*game_logging.THIRD_PARTY_LOGGERS, "wormhole_logging_test",
             *(name + ".lifecycle_test" for name in game_logging.THIRD_PARTY_LOGGERS))
    loggers = [root, *(logging.getLogger(name) for name in names)]
    levels = {logger: logger.level for logger in loggers}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(game_logging, "_application_handlers", [])
    for handler in original_handlers:
        root.removeHandler(handler)
    try:
        yield
    finally:
        try:
            with ExitStack() as cleanup:
                for handler in root.handlers[:]:
                    root.removeHandler(handler)
                for handler in game_logging._application_handlers:
                    # FileHandler.close flushes files; pytest may already have
                    # closed its borrowed console stream between test phases.
                    cleanup.callback(handler.close)
                game_logging._application_handlers.clear()
        finally:
            for handler in original_handlers:
                root.addHandler(handler)
            for logger, level in levels.items():
                logger.setLevel(level)


@pytest.mark.parametrize("initial_file", [False, True])
@pytest.mark.parametrize("replacement_file", [False, True])
def test_repeated_setup_closes_owned_handlers_without_duplicate_output(
    initial_file, replacement_file, capsys, tmp_path,
):
    root = logging.getLogger()
    console = sys.stderr
    game_logging.setup_logging(log_to_file=initial_file)
    for index in range(3):
        old_handlers = root.handlers[:]
        old_files = [handler.stream for handler in old_handlers
                     if isinstance(handler, logging.FileHandler)]

        game_logging.setup_logging(log_to_file=replacement_file)

        assert all(handler._closed for handler in old_handlers)
        assert all(stream.closed for stream in old_files)
        assert all(handler not in root.handlers for handler in old_handlers)
        assert len(root.handlers) == 1 + replacement_file
        assert game_logging._application_handlers == root.handlers
        assert not console.closed
        message = f"application-record-{index}"
        logging.getLogger("wormhole_logging_test").debug(message)
        assert capsys.readouterr().err.count(message) == 1
        if replacement_file:
            contents = (tmp_path / "game.log").read_text()
            assert contents.count(message) == 1
            if index:
                assert f"application-record-{index - 1}" not in contents


def test_replacement_closes_old_file_before_opening_new_one(monkeypatch):
    game_logging.setup_logging(log_to_file=True)
    old_stream = logging.getLogger().handlers[-1].stream
    file_handler_class = logging.FileHandler

    def open_after_close(*args, **kwargs):
        assert old_stream.closed
        return file_handler_class(*args, **kwargs)

    monkeypatch.setattr(logging, "FileHandler", open_after_close)
    game_logging.setup_logging(log_to_file=True)


def test_detached_owned_file_is_closed_and_released(tmp_path):
    game_logging.setup_logging(log_to_file=True)
    root = logging.getLogger()
    old_handler = root.handlers[-1]
    old_stream = old_handler.stream
    logging.getLogger("wormhole_logging_test").info("before-detach")
    root.removeHandler(old_handler)

    game_logging.setup_logging(log_to_file=False)

    assert old_stream.closed
    assert old_handler not in game_logging._application_handlers
    path = tmp_path / "game.log"
    assert "before-detach" in path.read_text()
    moved = path.rename(tmp_path / "released.log")
    moved.unlink()
    assert not moved.exists()


@pytest.mark.parametrize("existing_file", [False, True])
def test_stream_only_setup_does_not_create_or_truncate_log(tmp_path, existing_file):
    path = tmp_path / "game.log"
    if existing_file:
        path.write_text("previous run\n")
    game_logging.setup_logging(log_to_file=False)
    game_logging.setup_logging(log_to_file=False)
    logging.getLogger("wormhole_logging_test").info("console only")
    assert path.exists() == existing_file
    if existing_file:
        assert path.read_text() == "previous run\n"


@pytest.mark.parametrize("file_handler", [False, True])
def test_external_handlers_are_detached_without_closing_or_reconfiguration(
    tmp_path, file_handler,
):
    external_stream = io.StringIO()
    path = tmp_path / "external.log"
    handler = logging.FileHandler(path) if file_handler else logging.StreamHandler(external_stream)
    stream = handler.stream
    formatter = logging.Formatter("external: %(message)s")
    record_filter = logging.Filter()
    handler.setFormatter(formatter)
    handler.setLevel(logging.ERROR)
    handler.addFilter(record_filter)
    try:
        logging.getLogger().addHandler(handler)
        game_logging.setup_logging(log_to_file=True)
        game_logging.setup_logging(log_to_file=False)
        assert handler not in logging.getLogger().handlers
        assert not handler._closed
        assert not stream.closed
        assert handler.formatter is formatter
        assert handler.level == logging.ERROR
        assert handler.filters == [record_filter]
        # The original owner can use the handler again after setup detaches it.
        handler.handle(logging.LogRecord("external", logging.ERROR, __file__, 1,
                                         "still usable", (), None))
        handler.flush()
        contents = path.read_text() if file_handler else external_stream.getvalue()
        assert contents == "external: still usable\n"
    finally:
        handler.close()


@pytest.mark.parametrize("log_to_file", [False, True])
def test_third_party_http_clients_cannot_emit_debug_request_bodies(
    log_to_file, capsys, tmp_path,
):
    game_logging.setup_logging(log_to_file=log_to_file)
    game_logging.setup_logging(log_to_file=log_to_file)
    for name in game_logging.THIRD_PARTY_LOGGERS:
        assert logging.getLogger(name).getEffectiveLevel() >= logging.WARNING
        child = logging.getLogger(name + ".lifecycle_test")
        child.setLevel(logging.DEBUG)
        for level in (logging.DEBUG, logging.INFO):
            record = logging.LogRecord(child.name, level, __file__, 1,
                                       "request body: secret", (), None)
            assert all(not handler.filter(record) for handler in logging.getLogger().handlers)
            child.log(level, "request body: secret")
        child.warning("safe-provider-warning")
    logging.getLogger("wormhole_logging_test").debug("application-debug")

    outputs = [capsys.readouterr().err]
    if log_to_file:
        outputs.append((tmp_path / "game.log").read_text())
    for output in outputs:
        assert "secret" not in output
        assert output.count("safe-provider-warning") == len(game_logging.THIRD_PARTY_LOGGERS)
        assert output.count("application-debug") == 1


def test_file_open_failure_retains_owned_console_and_allows_retry(tmp_path, capsys):
    console = sys.stderr
    game_logging.setup_logging(log_to_file=True)
    old_stream = logging.getLogger().handlers[-1].stream
    # A directory at the log path fails on Windows and POSIX without permission tricks.
    game_logging.setup_logging(log_to_file=False)
    path = tmp_path / "game.log"
    path.unlink()
    path.mkdir()

    with pytest.raises(OSError):
        game_logging.setup_logging(log_to_file=True)

    assert old_stream.closed
    handlers = logging.getLogger().handlers[:]
    assert len(handlers) == 1
    assert game_logging._application_handlers == handlers
    logging.getLogger("wormhole_logging_test").warning("console survives")
    assert capsys.readouterr().err.count("console survives") == 1
    assert not console.closed
    path.rmdir()
    game_logging.setup_logging(log_to_file=True)
    assert handlers[0]._closed
    logging.getLogger("wormhole_logging_test").info("file recovered")
    assert "file recovered" in path.read_text()


def test_flush_failure_still_closes_every_owned_handler(monkeypatch):
    game_logging.setup_logging(log_to_file=True)
    old_handlers = logging.getLogger().handlers[:]
    old_stream = old_handlers[-1].stream

    def fail_flush():
        raise OSError("flush failed")

    with monkeypatch.context() as patch:
        patch.setattr(old_handlers[-1], "flush", fail_flush)
        with pytest.raises(OSError, match="flush failed"):
            game_logging.setup_logging(log_to_file=False)

    assert old_stream.closed
    assert all(handler._closed for handler in old_handlers)
    assert not game_logging._application_handlers
    assert not logging.getLogger().handlers
