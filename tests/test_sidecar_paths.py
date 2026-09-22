"""Sidecar exporters must not follow persisted IDs or links outside their roots."""
import os
import subprocess

import pytest

from game_ai.memory import AgentMemory, write_memory_sidecar
from persistence_paths import validate_identity
from save_manager import write_comms_sidecar, save_game_to_file
from tests.support.campaigns import campaign


INVALID_IDS = [None, False, 123, {}, [], '', '.', '..', '../escape', '..\\escape',
               '/absolute', '\\rooted', 'C:\\escape', 'C:escape', '\\\\server\\share',
               '\\\\?\\C:\\escape', 'a/b', 'a\\b', 'a:b', 'a.b', 'a ', ' a', 'a\n',
               'é', 'CON', 'con', 'PrN', 'AUX', 'nul', 'COM1', 'com9', 'LPT1', 'lpt9']


def export(root, kind, campaign_id='campaign', agent_id='agent'):
    if kind == 'memory':
        return write_memory_sidecar(root, campaign_id=campaign_id, agent_id=agent_id,
                                    player_name='AI', memory=AgentMemory())
    return write_comms_sidecar(root, campaign_id=campaign_id, conversations=[], players=[])


def paths(root, kind):
    if kind == 'memory':
        return root / 'agent_memory', root / 'agent_memory/campaign/agent/memory.md'
    return root / 'comms', root / 'comms/campaign/comms.md'


@pytest.mark.parametrize('value', INVALID_IDS)
@pytest.mark.parametrize('kind,field', [('memory', 'campaign_id'), ('memory', 'agent_id'), ('comms', 'campaign_id')])
def test_unsafe_identity_rejected_before_any_write(tmp_path, kind, field, value):
    root = tmp_path / 'saves'
    sentinel = tmp_path / 'memory.md'
    sentinel.write_text('untouched', encoding='utf-8')
    with pytest.raises(ValueError, match=field):
        export(root, kind, **{field: value})
    assert not root.exists()
    assert sentinel.read_text(encoding='utf-8') == 'untouched'


@pytest.mark.parametrize('value', ['0123abcd', 'integrity', 'test-campaign_123', '_', '-', 'com10', 'con-1'])
def test_readable_portable_identities_preserved(value):
    assert validate_identity(value, 'identity') == value


@pytest.mark.parametrize('kind', ['memory', 'comms'])
def test_valid_export_atomically_replaces_expected_sidecar(tmp_path, kind):
    _base, target = paths(tmp_path, kind)
    target.parent.mkdir(parents=True)
    target.write_text('old', encoding='utf-8')
    assert export(tmp_path, kind) == target
    assert target.read_text(encoding='utf-8').startswith('# ')
    assert not target.with_suffix('.md.tmp').exists()


def symlink_or_skip(link, target, *, directory):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f'Symbolic links unavailable: {exc}')


@pytest.mark.parametrize('kind', ['memory', 'comms'])
@pytest.mark.parametrize('redirect', ['base', 'campaign', 'target', 'temporary'])
def test_export_rejects_existing_symlink_escape(tmp_path, kind, redirect):
    root, outside = tmp_path / 'saves', tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    sentinel = outside / 'sentinel.md'
    sentinel.write_text('untouched', encoding='utf-8')
    base, target = paths(root, kind)
    if redirect in ('base', 'campaign'):
        link = base if redirect == 'base' else base / 'campaign'
        link.parent.mkdir(parents=True, exist_ok=True)
        symlink_or_skip(link, outside, directory=True)
    else:
        target.parent.mkdir(parents=True)
        link = target if redirect == 'target' else target.with_suffix('.md.tmp')
        symlink_or_skip(link, sentinel, directory=False)
    with pytest.raises(ValueError, match='escapes'):
        export(root, kind)
    assert sentinel.read_text(encoding='utf-8') == 'untouched'
    assert set(outside.iterdir()) == {sentinel}


@pytest.mark.skipif(os.name != 'nt', reason='Windows junction semantics')
@pytest.mark.parametrize('kind', ['memory', 'comms'])
@pytest.mark.parametrize('redirect', ['base', 'campaign'])
def test_export_rejects_existing_junction_escape(tmp_path, kind, redirect):
    root, outside = tmp_path / 'saves', tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    sentinel = outside / 'sentinel.md'
    sentinel.write_text('untouched', encoding='utf-8')
    base, _target = paths(root, kind)
    link = base if redirect == 'base' else base / 'campaign'
    link.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)],
                   check=True, capture_output=True)
    try:
        with pytest.raises(ValueError, match='escapes'):
            export(root, kind)
        assert sentinel.read_text(encoding='utf-8') == 'untouched'
        assert set(outside.iterdir()) == {sentinel}
    finally:
        # Remove the junction itself, never its target directory or contents.
        os.rmdir(link)


@pytest.mark.parametrize('field', ['campaign_id', 'persistent_id', 'agent_id'])
def test_invalid_live_identity_cannot_be_silently_regenerated_on_save(tmp_path, monkeypatch, field):
    game = campaign()
    owner = game if field == 'campaign_id' else game.players[0]
    setattr(owner, field, None)
    monkeypatch.setattr('save_manager.SAVES_DIR', str(tmp_path / 'saves'))
    with pytest.raises(ValueError, match=field):
        save_game_to_file(game, 'rejected.json')
    assert getattr(owner, field) is None
    assert not (tmp_path / 'saves').exists()
