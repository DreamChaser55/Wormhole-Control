"""Generated docs are deterministic, checkable and isolated from user libraries."""
import os
import shutil
import subprocess
import sys
from scripts.generate_reference import ROOT, replace_block, update_documents


def test_check_mode_reports_stale_blocks_without_writing(tmp_path):
    (tmp_path / 'docs').mkdir()
    shutil.copyfile(ROOT / 'docs/REFERENCE.md', tmp_path / 'docs/REFERENCE.md')
    shutil.copyfile(ROOT / 'README.md', tmp_path / 'README.md')
    blocks = {key: 'generated fixture' for key in
              ('components', 'abilities', 'order-count', 'planets', 'environment', 'unit-catalog')}
    before = {p: p.read_bytes() for p in tmp_path.rglob('*.md')}
    assert update_documents(blocks, check=True, root=tmp_path) == ['docs/REFERENCE.md']
    assert all(p.read_bytes() == content for p, content in before.items())
    assert update_documents(blocks, root=tmp_path) == ['docs/REFERENCE.md']
    assert update_documents(blocks, check=True, root=tmp_path) == []
    assert update_documents(blocks, root=tmp_path) == []
    assert (tmp_path / 'README.md').read_bytes() == before[tmp_path / 'README.md']


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
