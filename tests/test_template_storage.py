"""Migration and write-failure tests use isolated libraries and registry snapshots."""
import json
from types import SimpleNamespace
import pytest
from constants import HullSize
from custom_unit_templates import CustomTemplateManager, CustomUnitTemplate, TemplatePersistenceError
from unit_templates import UNIT_TEMPLATES
from pathlib import Path
from utils import user_data_path


def design(name='Storage Test'):
    template = CustomUnitTemplate(name, HullSize.MEDIUM)
    template.components.has_engine = True
    return template


def legacy_library(tmp_path):
    path = tmp_path / 'legacy.json'
    manager = CustomTemplateManager(data_file=path)
    assert manager.save_design(design()) == []
    return path


def test_migration_copies_bytes_once_and_preserves_legacy(tmp_path):
    legacy = legacy_library(tmp_path)
    payload = legacy.read_bytes()
    target = tmp_path / 'user' / 'designs.json'
    manager = CustomTemplateManager(data_file=target, legacy_file=legacy)
    manager.load_from_file()
    assert manager.last_load_error is None
    assert target.read_bytes() == legacy.read_bytes() == payload
    assert manager.get_design('Storage Test') is not None
    assert manager.delete_design('Storage Test')
    manager.load_from_file()
    assert manager.designs == {}  # Empty user library must not resurrect legacy designs.
    assert legacy.read_bytes() == payload


def test_explicit_storage_disables_legacy_discovery(tmp_path):
    manager = CustomTemplateManager(data_file=tmp_path / 'library.json')
    manager.load_from_file()
    assert manager.designs == {} and manager.legacy_file is None


def test_default_manager_migrates_to_environment_override(tmp_path, monkeypatch):
    legacy = legacy_library(tmp_path)
    monkeypatch.setenv('WORMHOLE_USER_DATA_DIR', str(tmp_path / 'user'))
    monkeypatch.setattr('custom_unit_templates._DATA_FILE', None)
    monkeypatch.setattr('custom_unit_templates.resource_path', lambda _: str(legacy))
    manager = CustomTemplateManager()
    manager.load_from_file()
    assert manager.data_file == tmp_path / 'user' / 'custom_unit_templates.json'
    assert manager.data_file.read_bytes() == legacy.read_bytes()


def test_concurrent_user_library_wins_migration(tmp_path, monkeypatch):
    legacy = legacy_library(tmp_path)
    target = tmp_path / 'user.json'
    manager = CustomTemplateManager(data_file=target, legacy_file=legacy)
    import os
    link = os.link
    def competing_library(source, destination):
        target.write_text('{}')
        return link(source, destination)
    monkeypatch.setattr('custom_unit_templates.os.link', competing_library)
    manager.load_from_file()
    assert manager.last_load_error is None and manager.designs == {}
    assert target.read_text() == '{}'
    assert not list(tmp_path.glob('*.tmp'))


def test_corrupt_existing_library_never_falls_back_or_overwrites(tmp_path):
    legacy = legacy_library(tmp_path)
    target = tmp_path / 'user.json'
    manager = CustomTemplateManager(data_file=target, legacy_file=legacy)
    manager.load_from_file()
    before = dict(manager.designs), dict(UNIT_TEMPLATES)
    target.write_bytes(b'broken')
    manager.load_from_file()
    assert manager.last_load_error is not None
    assert (manager.designs, UNIT_TEMPLATES) == before
    with pytest.raises(TemplatePersistenceError):
        manager.save_to_file()
    assert target.read_bytes() == b'broken'


@pytest.mark.parametrize('payload', [b'{', b'[]', b'{"broken": 42}', b'{"broken": {"hull_size": "NO_SUCH_HULL"}}'])
def test_malformed_migration_never_creates_destination(tmp_path, payload):
    legacy = tmp_path / 'legacy.json'
    legacy.write_bytes(payload)
    target = tmp_path / 'user.json'
    manager = CustomTemplateManager(data_file=target, legacy_file=legacy)
    before = dict(UNIT_TEMPLATES)
    manager.load_from_file()
    assert manager.last_load_error is not None
    assert not target.exists() and legacy.read_bytes() == payload
    assert UNIT_TEMPLATES == before
    with pytest.raises(TemplatePersistenceError):
        manager.save_design(design())


def test_failed_migration_can_be_retried(tmp_path, monkeypatch):
    legacy = legacy_library(tmp_path)
    target = tmp_path / 'user.json'
    manager = CustomTemplateManager(data_file=target, legacy_file=legacy)
    write = manager._atomic_write
    def fail(*args, **kwargs):
        raise TemplatePersistenceError('no storage')
    monkeypatch.setattr(manager, '_atomic_write', fail)
    manager.load_from_file()
    assert manager.last_load_error is not None and not target.exists()
    monkeypatch.setattr(manager, '_atomic_write', write)
    manager.load_from_file()
    assert manager.last_load_error is None and target.read_bytes() == legacy.read_bytes()


@pytest.mark.parametrize('operation', ['save', 'rename', 'delete'])
def test_failed_write_preserves_disk_manager_and_registry(tmp_path, monkeypatch, operation):
    target = tmp_path / 'library.json'
    manager = CustomTemplateManager(data_file=target)
    manager.save_design(design())
    disk, designs, registry = target.read_bytes(), dict(manager.designs), dict(UNIT_TEMPLATES)
    def fail(*args):
        raise PermissionError('injected replacement failure')
    monkeypatch.setattr('custom_unit_templates.os.replace', fail)
    with pytest.raises(TemplatePersistenceError):
        if operation == 'delete':
            manager.delete_design('Storage Test')
        else:
            manager.save_design(design('New Name'), original_name='Storage Test' if operation == 'rename' else None)
    assert target.read_bytes() == disk
    assert manager.designs == designs and UNIT_TEMPLATES == registry
    assert not list(tmp_path.glob('*.tmp'))


def test_rename_delete_round_trip(tmp_path):
    target = tmp_path / 'library.json'
    manager = CustomTemplateManager(data_file=target)
    assert manager.save_design(design()) == []
    assert manager.save_design(design('Renamed'), original_name='storage test') == []
    restored = CustomTemplateManager(data_file=target)
    restored.load_from_file()
    assert restored.list_design_names() == ['Renamed']
    assert 'Storage Test' not in UNIT_TEMPLATES
    assert restored.delete_design('RENAMED')
    assert json.loads(target.read_text()) == {}


def test_historical_over_capacity_design_can_migrate(tmp_path):
    legacy = legacy_library(tmp_path)
    raw = json.loads(legacy.read_text())
    raw['Storage Test']['engine_speed'] = 10000
    legacy.write_text(json.dumps(raw))
    manager = CustomTemplateManager(data_file=tmp_path / 'user.json', legacy_file=legacy)
    manager.load_from_file()
    assert manager.last_load_error is None
    assert manager.get_design('Storage Test').components.engine_speed == 10000


@pytest.mark.parametrize('operation', ['save', 'delete'])
def test_editor_reports_storage_failure_without_success(monkeypatch, operation):
    from gui.unit_editor_gui import template_io
    def fail(*args, **kwargs):
        raise TemplatePersistenceError('Disk write failed')
    editor = SimpleNamespace(template_manager=SimpleNamespace(save_design=fail, delete_design=fail),
                             _editing_name='Storage Test')
    statuses, modals = [], []
    monkeypatch.setattr(template_io, 'set_status', lambda *args, **kwargs: statuses.append((args, kwargs)))
    monkeypatch.setattr(template_io, '_show_editor_modal', lambda *args, **kwargs: modals.append(args))
    result = template_io.execute_save(editor, design()) if operation == 'save' else template_io.do_delete(editor)
    assert result is None and editor._editing_name == 'Storage Test'
    assert statuses[-1][1]['error'] is True
    assert 'Failed' in modals[-1][1]


@pytest.mark.parametrize('platform,variable,subdir', [
    ('win32', 'LOCALAPPDATA', ''), ('darwin', None, 'Library/Application Support'),
    ('linux', 'XDG_DATA_HOME', ''),
])
def test_user_storage_defaults(platform, variable, subdir, tmp_path, monkeypatch):
    monkeypatch.delenv('WORMHOLE_USER_DATA_DIR')
    monkeypatch.setattr('sys.platform', platform)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    if variable:
        monkeypatch.setenv(variable, str(tmp_path))
    assert user_data_path() == tmp_path / subdir / 'WormholeControl'


def test_user_storage_override(tmp_path, monkeypatch):
    monkeypatch.setenv('WORMHOLE_USER_DATA_DIR', str(tmp_path))
    assert user_data_path() == tmp_path
    monkeypatch.setenv('WORMHOLE_USER_DATA_DIR', 'relative')
    with pytest.raises(ValueError, match='absolute'):
        user_data_path()
