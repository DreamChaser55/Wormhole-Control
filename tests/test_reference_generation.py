"""Generated docs are deterministic, checkable and isolated from user libraries."""
import os
import shutil
import subprocess
import sys
from scripts.generate_reference import ROOT, replace_block, update_documents, version_table


def test_check_mode_reports_stale_blocks_without_writing(tmp_path):
    (tmp_path / 'docs').mkdir()
    shutil.copyfile(ROOT / 'docs/REFERENCE.md', tmp_path / 'docs/REFERENCE.md')
    shutil.copyfile(ROOT / 'docs/DEVELOPMENT.md', tmp_path / 'docs/DEVELOPMENT.md')
    shutil.copyfile(ROOT / 'README.md', tmp_path / 'README.md')
    blocks = {key: 'generated fixture' for key in
              ('components', 'abilities', 'order-count', 'planets', 'environment', 'unit-catalog', 'versions')}
    before = {p: p.read_bytes() for p in tmp_path.rglob('*.md')}
    assert update_documents(blocks, check=True, root=tmp_path) == ['docs/REFERENCE.md', 'docs/DEVELOPMENT.md']
    assert all(p.read_bytes() == content for p, content in before.items())
    assert update_documents(blocks, root=tmp_path) == ['docs/REFERENCE.md', 'docs/DEVELOPMENT.md']
    assert update_documents(blocks, check=True, root=tmp_path) == []
    assert update_documents(blocks, root=tmp_path) == []
    assert (tmp_path / 'README.md').read_bytes() == before[tmp_path / 'README.md']
    blocks['versions'] = 'changed version fixture'
    before = (tmp_path / 'docs/DEVELOPMENT.md').read_bytes()
    assert update_documents(blocks, check=True, root=tmp_path) == ['docs/DEVELOPMENT.md']
    assert (tmp_path / 'docs/DEVELOPMENT.md').read_bytes() == before


def test_versions_follow_literals_without_executing_modules(tmp_path):
    sources = {
        'save_manager.py': 'CURRENT_SAVE_VERSION = "test-save"',
        'game_ai/observation.py': 'OBSERVATION_SCHEMA_VERSION: int = 71',
        'game_ai/command_spec.py': 'CONTRACT_VERSION = 72',
        'game_ai/schema.py': 'TURN_PLAN_SCHEMA_NAME = "test-response"',
        'game_ai/adapters/openai_responses.py': 'PROMPT_CACHE_KEY = "test-cache"',
        'game_control_protocol.py': 'PROTOCOL_VERSION = 73',
        'unit_components/strikecraft.py': (
            'class StrikecraftBayComponent:\n    SCHEMA_VERSION = 74\n'
            'class StrikecraftWingComponent:\n    SCHEMA_VERSION = 75'),
    }
    for relative, source in sources.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('raise AssertionError("must never execute")\n' + source, encoding='utf-8')
    result = version_table(tmp_path)
    assert version_table(tmp_path) == result
    for value in ('test-save', '71', '72', 'test-response', 'test-cache', '73', '74', '75'):
        assert f'| {value} |' in result
    path = tmp_path / 'game_ai/observation.py'
    path.write_text('OBSERVATION_SCHEMA_VERSION = 81', encoding='utf-8')
    assert '| 81 |' in version_table(tmp_path)
    assert '| 71 |' not in version_table(tmp_path)


def test_generated_check_from_foreign_cwd_preserves_user_library(tmp_path):
    user_data = tmp_path / 'user'
    user_data.mkdir()
    library = user_data / 'custom_unit_templates.json'
    library.write_bytes(b'not a valid library; must not be accessed')
    env = dict(os.environ, WORMHOLE_USER_DATA_DIR=str(user_data))
    command = [sys.executable, str(ROOT / 'scripts/generate_reference.py'), '--check']
    result = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert library.read_bytes() == b'not a valid library; must not be accessed'
    assert not (tmp_path / 'theme_scaled.json').exists()


def test_block_replacement_preserves_authored_prose():
    text = 'Before\n<!-- BEGIN GENERATED: sample -->\nstale\n<!-- END GENERATED: sample -->\nAfter'
    result = replace_block(text, 'sample', 'fresh')
    assert result.startswith('Before\n') and result.endswith('\nAfter')
    assert '\nfresh\n' in result and 'stale' not in result
