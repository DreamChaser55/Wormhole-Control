"""Library loading and write-failure tests use isolated libraries and registry snapshots."""
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


def test_missing_library_ignores_repository_legacy_file(tmp_path, monkeypatch):
    import utils
    root = tmp_path / 'checkout'
    legacy = root / 'data' / 'custom_unit_templates.json'
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b'broken legacy input')
    monkeypatch.chdir(root)
    monkeypatch.setattr(utils, 'resource_path', lambda _: str(legacy))
    monkeypatch.setenv('WORMHOLE_USER_DATA_DIR', str(tmp_path / 'user'))
    manager = CustomTemplateManager()
    manager.load_from_file()
    assert manager.last_load_error is None and manager.designs == {}
    assert not manager.data_file.exists()
    assert legacy.read_bytes() == b'broken legacy input'


def test_explicit_missing_library_is_empty(tmp_path):
    target = tmp_path / 'missing.json'
    manager = CustomTemplateManager(data_file=target)
    manager.load_from_file()
    assert manager.last_load_error is None and manager.designs == {}
    assert not target.exists()


def test_default_manager_reads_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv('WORMHOLE_USER_DATA_DIR', str(tmp_path))
    manager = CustomTemplateManager()
    assert manager.save_design(design()) == []
    restored = CustomTemplateManager()
    restored.load_from_file()
    assert restored.data_file == tmp_path / 'custom_unit_templates.json'
    assert restored.get_design('Storage Test') is not None


@pytest.mark.parametrize('payload', [b'{', b'[]', b'{"broken": 42}', b'{"broken": {"hull_size": "NO_SUCH_HULL"}}'])
def test_malformed_library_preserves_state_and_blocks_writes(tmp_path, payload):
    target = tmp_path / 'user.json'
    manager = CustomTemplateManager(data_file=target)
    manager.save_design(design())
    before = dict(manager.designs), dict(UNIT_TEMPLATES)
    target.write_bytes(payload)
    manager.load_from_file()
    assert manager.last_load_error is not None
    assert target.read_bytes() == payload
    assert (manager.designs, UNIT_TEMPLATES) == before
    with pytest.raises(TemplatePersistenceError):
        manager.save_design(design('Another'))
    with pytest.raises(TemplatePersistenceError):
        manager.save_to_file()


def test_failed_load_can_be_retried(tmp_path):
    target = tmp_path / 'user.json'
    manager = CustomTemplateManager(data_file=target)
    manager.save_design(design())
    payload = target.read_bytes()
    target.write_bytes(b'broken')
    manager.load_from_file()
    assert manager.last_load_error is not None
    target.write_bytes(payload)
    manager.load_from_file()
    assert manager.last_load_error is None
    assert manager.save_design(design('Another')) == []


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


def test_historical_over_capacity_design_can_load(tmp_path):
    target = tmp_path / 'user.json'
    manager = CustomTemplateManager(data_file=target)
    manager.save_design(design())
    raw = json.loads(target.read_text())
    raw['Storage Test']['engine_speed'] = 10000
    target.write_text(json.dumps(raw))
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
