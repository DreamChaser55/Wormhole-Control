"""Concurrent process exclusion and crash-safe release, using isolated leases."""
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from application_instance import acquire_instance, ALREADY_RUNNING_EXIT_CODE
from game_control_protocol import ControlService


def run_child(source, *args, cwd=None):
    return subprocess.run([sys.executable, '-c', source, *map(str, args)], cwd=cwd,
                          capture_output=True, text=True, timeout=15)


def test_second_process_on_another_port_fails_before_log_or_window_creation(tmp_path):
    path = tmp_path / 'instance.lock'
    log = tmp_path / 'game.log'
    log.write_bytes(b'Live campaign log\n')
    root = Path(__file__).resolve().parents[1]
    service = ControlService(SimpleNamespace(instance_path=path), port=0)
    service.start()
    try:
        child = run_child('import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); '
            'from game import main; sys.exit(main(["--smoke-test", "--port", "0"], instance_path=Path(sys.argv[2])))',
            root, path, cwd=tmp_path)
        assert child.returncode == ALREADY_RUNNING_EXIT_CODE
        assert 'already running' in child.stderr
        assert log.read_bytes() == b'Live campaign log\n'
        assert service.is_running
    finally:
        service.shutdown()
    with acquire_instance(path):
        pass


def test_crashed_process_releases_lease_and_stale_file_does_not_block(tmp_path):
    path = tmp_path / 'instance.lock'
    child = run_child('import os, sys; from pathlib import Path; from application_instance import acquire_instance; '
                      'lease = acquire_instance(Path(sys.argv[1])); os._exit(0)', path)
    assert child.returncode == 0
    assert path.exists()
    with acquire_instance(path):
        child = run_child('import sys; from pathlib import Path; from application_instance import acquire_instance, AlreadyRunningError; '
                          '\ntry: acquire_instance(Path(sys.argv[1]))\nexcept AlreadyRunningError: sys.exit(3)', path)
        assert child.returncode == ALREADY_RUNNING_EXIT_CODE


def test_bind_failure_releases_process_lease(tmp_path):
    path = tmp_path / 'instance.lock'
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        service = ControlService(SimpleNamespace(instance_path=path), port=occupied.getsockname()[1])
        with pytest.raises(OSError):
            service.start()
        assert not service.is_running
    child = run_child('import sys; from pathlib import Path; from application_instance import acquire_instance; '
                      'lease = acquire_instance(Path(sys.argv[1]))', path)
    assert child.returncode == 0, child.stderr


def test_thread_start_failure_releases_socket_and_lease(tmp_path, monkeypatch):
    path = tmp_path / 'instance.lock'
    service = ControlService(SimpleNamespace(instance_path=path), port=0)
    def fail_start(_thread):
        raise RuntimeError('injected start failure')
    with monkeypatch.context() as startup:
        startup.setattr('game_control_protocol.threading.Thread.start', fail_start)
        with pytest.raises(RuntimeError, match='injected start failure'):
            service.start()
    assert not service.is_running
    child = run_child('import sys; from pathlib import Path; from application_instance import acquire_instance; '
                      'lease = acquire_instance(Path(sys.argv[1]))', path)
    assert child.returncode == 0, child.stderr
