"""CI diagnostics remain useful without changing test outcomes."""
import io
from types import SimpleNamespace

from tests.support import ci_diagnostics


def test_kernel_memory_snapshot_and_missing_metrics(tmp_path):
    (tmp_path / 'self').mkdir()
    status = tmp_path / 'self/status'
    status.write_text('Name:\tpython\nVmRSS:\t1024 kB\nVmHWM:\t2048 kB\n')
    (tmp_path / 'meminfo').write_text('MemTotal: 8192 kB\nMemAvailable: 4096 kB\n')
    assert ci_diagnostics.resource_snapshot(tmp_path) == (
        'rss_kib=1024 peak_rss_kib=2048 available_kib=4096')
    status.unlink()
    assert ci_diagnostics.resource_snapshot(tmp_path) == (
        'rss_kib=unavailable peak_rss_kib=unavailable available_kib=4096')


def test_reports_module_boundaries_and_final_failure(tmp_path, monkeypatch):
    console = io.StringIO()
    monkeypatch.setattr(ci_diagnostics.sys, '__stdout__', console)
    monkeypatch.setattr(ci_diagnostics, 'resource_snapshot', lambda: 'rss_kib=42')
    reporter = ci_diagnostics.ResourceReporter(tmp_path)
    reporter.pytest_runtest_logstart('tests/one.py::test_a', None)
    reporter.pytest_runtest_logstart('tests/one.py::test_b', None)
    reporter.pytest_runtest_logstart('tests/two.py::test_c', None)
    reporter.pytest_sessionfinish(None, 1)
    lines = (tmp_path / 'resources.log').read_text().splitlines()
    assert len(lines) == 3
    assert 'tests/one.py' in lines[0] and 'tests/two.py' in lines[1]
    assert 'session finish (exit=1)' in lines[2]
    assert all(line in console.getvalue() for line in lines)


def test_unwritable_report_still_prints_diagnostics(tmp_path, monkeypatch):
    console = io.StringIO()
    monkeypatch.setattr(ci_diagnostics.sys, '__stdout__', console)
    blocked = tmp_path / 'file'
    blocked.write_text('not a directory')
    ci_diagnostics.ResourceReporter(blocked).report('module')
    assert '[CI resources] module:' in console.getvalue()
    assert 'Cannot save report:' in console.getvalue()


def test_reporting_requires_linux_ci_and_explicit_directory(tmp_path, monkeypatch):
    registrations = []
    config = SimpleNamespace(pluginmanager=SimpleNamespace(
        register=lambda plugin, name: registrations.append((plugin, name))))
    monkeypatch.setattr(ci_diagnostics.sys, 'platform', 'linux')
    monkeypatch.delenv('CI', raising=False)
    monkeypatch.setenv('WORMHOLE_CI_REPORT_DIR', str(tmp_path))
    ci_diagnostics.configure_diagnostics(config)
    assert not registrations
    monkeypatch.setenv('CI', 'true')
    monkeypatch.delenv('WORMHOLE_CI_REPORT_DIR')
    ci_diagnostics.configure_diagnostics(config)
    assert not registrations
    monkeypatch.setenv('WORMHOLE_CI_REPORT_DIR', str(tmp_path))
    monkeypatch.setattr(ci_diagnostics.sys, 'platform', 'win32')
    ci_diagnostics.configure_diagnostics(config)
    assert not registrations
    monkeypatch.setattr(ci_diagnostics.sys, 'platform', 'linux')
    ci_diagnostics.configure_diagnostics(config)
    assert len(registrations) == 1
