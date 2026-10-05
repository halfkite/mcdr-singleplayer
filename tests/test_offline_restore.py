import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from singleplayer_bridge import offline_restore
from singleplayer_bridge.profiles import write_json


def fixture_world(tmp_path):
    common = tmp_path / 'mcdr-singleplayer'
    profile = common / 'plugindata' / 'test-world'
    storage = profile / 'pb_files'
    storage.mkdir(parents=True)
    (common / 'plugins').mkdir()
    world = tmp_path / 'saves' / 'test-world'
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'current')
    write_json(profile / 'profile.json', {'world_path': str(world), 'folder': world.name})
    write_json(profile / 'config/prime_backup/config.json', {
        'storage_root': './pb_files',
        'backup': {'source_root': str(world.parent), 'source_root_use_mcdr_working_directory': False,
                   'targets': [world.name]}})
    database = storage / 'prime_backup.db'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE backup (id INTEGER, timestamp INTEGER, comment TEXT, '
                           'targets TEXT, tags TEXT, file_raw_size_sum INTEGER)')
        connection.executemany('INSERT INTO backup VALUES (?, ?, ?, ?, ?, ?)', [
            (1, 100, 'normal', json.dumps(['test-world']), '{}', 32),
            (2, 200, 'safety', json.dumps(['test-world']), '{"temporary": true}', 32),
            (3, 300, 'other', json.dumps(['other-world']), '{}', 32),
        ])
    return common, world, storage


def test_backup_picker_lists_only_this_world_and_includes_safety_backup(tmp_path):
    common, world, database = fixture_world(tmp_path)
    rows = offline_restore.backup_rows(database / 'prime_backup.db', world.name)
    assert [row['id'] for row in rows] == [2, 1]
    assert rows[0]['temporary'] is True
    assert rows[1]['temporary'] is False


def test_storage_root_cannot_escape_profile(tmp_path):
    common, world, _ = fixture_world(tmp_path)
    config_path = common / 'plugindata' / world.name / 'config/prime_backup/config.json'
    config = json.loads(config_path.read_text())
    config['storage_root'] = '../outside'
    write_json(config_path, config)
    with pytest.raises(RuntimeError, match='outside'):
        offline_restore.locations(common, world.name)


def test_offline_restore_preserves_previous_world_until_verified_export(tmp_path, monkeypatch):
    common, world, _ = fixture_world(tmp_path)
    archive = common / 'plugins/PrimeBackup-v1.13.1.pyz'
    archive.write_bytes(b'fixture')
    monkeypatch.setattr(offline_restore, 'prime_archive', lambda root: archive)

    def export(command, **kwargs):
        stage = Path(command[command.index('--output') + 1]) / world.name
        stage.mkdir(parents=True)
        (stage / 'level.dat').write_bytes(b'restored')
        return SimpleNamespace(returncode=0)

    history = offline_restore.restore(common, world.name, 1, runner=export)
    assert (world / 'level.dat').read_bytes() == b'restored'
    assert (history / world.name / 'level.dat').read_bytes() == b'current'
    progress = json.loads((common / 'runtime/.mcdr_restore_progress.json').read_text())
    assert progress['status'] == 'completed'
    assert progress['backup_id'] == 1


def test_export_failure_keeps_current_world_untouched(tmp_path, monkeypatch):
    common, world, _ = fixture_world(tmp_path)
    archive = common / 'plugins/PrimeBackup-v1.13.1.pyz'
    archive.write_bytes(b'fixture')
    monkeypatch.setattr(offline_restore, 'prime_archive', lambda root: archive)
    with pytest.raises(RuntimeError, match='could not verify'):
        offline_restore.restore(common, world.name, 1,
                                runner=lambda *args, **kwargs: SimpleNamespace(returncode=1))
    assert (world / 'level.dat').read_bytes() == b'current'
    progress = json.loads((common / 'runtime/.mcdr_restore_progress.json').read_text())
    assert progress['status'] == 'failed'
    assert progress['modified'] is False


def test_recovery_rejects_other_world_profile(tmp_path, monkeypatch):
    common, world, _ = fixture_world(tmp_path)
    profile = common / 'plugindata' / world.name
    write_json(profile / 'profile.json', {'world_path': str(tmp_path / 'other' / world.name), 'folder': 'different'})
    archive = common / 'plugins/PrimeBackup-v1.13.1.pyz'
    archive.write_bytes(b'fixture')
    monkeypatch.setattr(offline_restore, 'prime_archive', lambda root: archive)
    with pytest.raises(ValueError, match='profile does not match'):
        offline_restore.restore(common, world.name, 1)
    assert (world / 'level.dat').read_bytes() == b'current'


def test_successful_recovery_rebinds_a_moved_instance(tmp_path, monkeypatch):
    common, world, _ = fixture_world(tmp_path)
    profile = common / 'plugindata' / world.name
    old = tmp_path / 'old-computer/saves' / world.name
    write_json(profile / 'profile.json', {'world_path': str(old), 'folder': world.name})
    config_path = profile / 'config/prime_backup/config.json'
    config = json.loads(config_path.read_text())
    config['backup']['source_root'] = str(old.parent)
    write_json(config_path, config)
    pb_adapter = profile / 'config/singleplayer_prime_backup/config.json'
    write_json(pb_adapter, {'world_path': str(old), 'keep': True})
    marker = profile / 'cb_files/.singleplayer-world.json'
    write_json(marker, {'world_path': str(old)})
    write_json(profile / 'config/chunk_backup/config.json', {'server_root': str(old.parent),
        'backup': {'dimension': {'minecraft:overworld': {'world_name': world.name, 'region_folder': []}}}})
    cb_adapter = profile / 'config/singleplayer_chunk_backup/config.json'
    write_json(cb_adapter, {'world_path': str(old), 'keep': True})
    archive = common / 'plugins/PrimeBackup-v1.13.1.pyz'
    archive.write_bytes(b'fixture')
    monkeypatch.setattr(offline_restore, 'prime_archive', lambda root: archive)

    def export(command, **kwargs):
        stage = Path(command[command.index('--output') + 1]) / world.name
        stage.mkdir(parents=True)
        (stage / 'level.dat').write_bytes(b'restored')
        return SimpleNamespace(returncode=0)

    offline_restore.restore(common, world.name, 1, runner=export)
    assert json.loads((profile / 'profile.json').read_text())['world_path'] == str(world)
    assert json.loads(config_path.read_text())['backup']['source_root'] == str(world.parent)
    assert json.loads(marker.read_text())['world_path'] == str(world)
    assert json.loads((profile / 'config/chunk_backup/config.json').read_text())['server_root'] == str(world.parent)
    assert json.loads(pb_adapter.read_text()) == {'world_path': str(world), 'keep': True}
    assert json.loads(cb_adapter.read_text()) == {'world_path': str(world), 'keep': True}
