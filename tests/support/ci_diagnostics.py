"""Opt-in Linux CI memory diagnostics, independent of application imports."""
import os
from pathlib import Path
import sys


def resource_snapshot(proc=Path('/proc')):
    """Read kernel values in KiB; unavailable metrics must not fail tests."""
    metrics = {}
    for path, fields in (
        (proc / 'self/status', {'VmRSS': 'rss', 'VmHWM': 'peak_rss'}),
        (proc / 'meminfo', {'MemAvailable': 'available'}),
    ):
        try:
            for line in path.read_text(encoding='utf-8').splitlines():
                key, _, value = line.partition(':')
                if key in fields:
                    metrics[fields[key]] = int(value.split()[0])
        except (OSError, ValueError, IndexError):
            pass
    return ' '.join(f'{name}_kib={metrics.get(name, "unavailable")}'
                    for name in ('rss', 'peak_rss', 'available'))


class ResourceReporter:
    def __init__(self, directory):
        self.path = Path(directory) / 'resources.log'
        self.last_module = None

    def report(self, label):
        line = f'[CI resources] {label}: {resource_snapshot()}'
        print('\n' + line, file=sys.__stdout__, flush=True)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(line + '\n')
        except OSError as error:
            print(f'[CI resources] Cannot save report: {type(error).__name__}',
                  file=sys.__stdout__, flush=True)

    def pytest_runtest_logstart(self, nodeid, location):
        module = nodeid.split('::', 1)[0]
        if module != self.last_module:
            self.last_module = module
            self.report(module)

    def pytest_sessionfinish(self, session, exitstatus):
        self.report(f'session finish (exit={int(exitstatus)})')


def configure_diagnostics(config):
    directory = os.environ.get('WORMHOLE_CI_REPORT_DIR')
    if (sys.platform == 'linux' and directory
            and os.environ.get('CI', '').lower() in ('1', 'true')):
        config.pluginmanager.register(ResourceReporter(directory), 'ci-resources')
