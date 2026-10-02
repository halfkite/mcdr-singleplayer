import sqlite3
from pathlib import Path

import pytest

from singleplayer_bridge.layout import migrate_legacy, organize_layout
from singleplayer_bridge.profiles import ensure_profile, profile_path, read_json, write_json
from singleplayer_bridge.supervisor import lock_common


def fixture(tmp):
    source = tmp / 'old-mcdr'; source.mkdir()
    common = tmp / 'game/mcdr-singleplayer'; common.mkdir(parents=True)
    world = tmp / 'game/saves/世界'; world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'untouched-world')
    old = source / 'worlds' / world.name
    write_json(old / 'profile.json', {'world_path': str(world), 'folder': world.name})
    write_json(old / 'config/prime_backup/config.json', {'enabled': False,
        'storage_root': str(old / 'data/prime_backup'), 'scheduled_backup': {'enabled': True, 'interval': '2h'},
        'backup': {'source_root': str(world.parent), 'source_root_use_mcdr_working_directory': False, 'targets': [world.name]}})
    write_json(old / 'config/singleplayer_bridge/config.json', {'recommendation_version': '0.3.2', 'language': 'en_us',
        'backup_enabled': False, 'auto_backup': True, 'auto_delete': False})
    store = old / 'data/prime_backup'; store.mkdir(parents=True)
    with sqlite3.connect(store / 'backup.db') as db:
        db.execute('CREATE TABLE backup(id INTEGER, comment TEXT)')
        db.execute('INSERT INTO backup VALUES (7, "existing backup")')
    (store / 'blob').write_bytes(b'backup-pool-content')
    (source / 'config.yml').write_text('old-common-config')
    (source / 'permission.yml').write_text('old-owner-permission')
    (source / 'plugins').mkdir()
    (source / 'plugins/probe.py').write_text('# legacy plugin')
    write_json(common / 'runtime/.legacy-layout.json', {'source': str(source)})
    return common, source, old, world


def test_034_layout_is_grouped_and_default_config_backups_are_removed(tmp_path):
    common = tmp_path / 'game/mcdr-singleplayer'
    (common / 'config').mkdir(parents=True)
    (common / 'config/config.json').write_text('{"enabled":true}')
    (common / 'config.yml').write_text('language: en_us\n')
    (common / 'config.yml.before-20261002-162642-239250').write_text('default copy')
    (common / 'plugins').mkdir()
    (common / 'plugins/probe.py').write_text('plugin')
    (common / 'data/World').mkdir(parents=True)
    (common / 'data/World/profile.json').write_text('{}')
    (common / 'bootstrap-resources-0.3.4').mkdir()
    (common / 'bootstrap-resources-0.3.4/bridge_bootstrap.py').write_text('installer')
    (common / 'controller.log').write_text('log')

    organize_layout(common)

    assert {path.name for path in common.iterdir()} == {'date', 'log', 'runtime'}
    assert (common / 'runtime/config/config.json').read_text() == '{"enabled":true}'
    assert (common / 'runtime/config/config.yml').is_file()
    assert (common / 'runtime/config/plugins/probe.py').read_text() == 'plugin'
    assert (common / 'runtime/bootstrap-resources-0.3.4/bridge_bootstrap.py').is_file()
    assert (common / 'date/World/profile.json').is_file()
    assert (common / 'log/controller.log').read_text() == 'log'
    assert not list(common.rglob('config.yml.before-*'))


def test_migration_preserves_database_policies_sources_and_rebinds_storage(tmp_path):
    common, source, old, world = fixture(tmp_path)
    migrate_legacy(common)
    profile = ensure_profile(common, world)
    assert profile == common / 'date' / world.name
    config = read_json(profile / 'config/prime_backup/config.json')
    assert config['storage_root'] == str(profile / 'data/prime_backup')
    assert config['enabled'] is False
    assert config['scheduled_backup']['interval'] == '2h'
    with sqlite3.connect(profile / 'data/prime_backup/backup.db') as db:
        assert db.execute('SELECT * FROM backup').fetchall() == [(7, 'existing backup')]
    assert (profile / 'data/prime_backup/blob').read_bytes() == b'backup-pool-content'
    assert read_json(old / 'config/prime_backup/config.json')['storage_root'] == str(old / 'data/prime_backup')
    assert (old / 'data/prime_backup/backup.db').read_bytes() == (profile / 'data/prime_backup/backup.db').read_bytes()
    assert (common / 'runtime/config/config.yml').read_text() == (source / 'config.yml').read_text()
    assert (common / 'runtime/config/plugins/probe.py').read_bytes() == (source / 'plugins/probe.py').read_bytes()
    assert read_json(common / 'runtime/.legacy-layout.json')['completed']
    assert {path.name for path in common.iterdir()} == {'date', 'log', 'runtime'}
    assert (world / 'level.dat').read_bytes() == b'untouched-world'
    migrate_legacy(common)
    assert not list((profile / 'config/prime_backup').glob('config.json.before-*'))


def test_migration_does_not_overwrite_existing_profile_or_common_settings(tmp_path):
    common, source, old, world = fixture(tmp_path)
    (common / 'runtime/config').mkdir(parents=True)
    (common / 'runtime/config/config.yml').write_text('new-config')
    destination = common / 'date' / world.name; destination.mkdir(parents=True)
    (destination / 'keep').write_text('existing-data')
    with pytest.raises(ValueError, match='already exists'):
        migrate_legacy(common)
    assert (destination / 'keep').read_text() == 'existing-data'
    assert not (destination / 'profile.json').exists()
    assert (common / 'runtime/config/config.yml').read_text() == 'new-config'
    assert not read_json(common / 'runtime/.legacy-layout.json').get('completed')


def test_live_legacy_controller_blocks_import(tmp_path):
    common, source, _, _ = fixture(tmp_path)
    lock = lock_common(source)
    try:
        with pytest.raises(OSError):
            migrate_legacy(common)
        assert not (common / 'runtime/config/config.yml').exists()
    finally:
        lock.close()
    migrate_legacy(common)


def test_interrupted_migration_resumes_only_its_committed_profiles(tmp_path):
    common, _, _, world = fixture(tmp_path)
    migrate_legacy(common)
    marker = read_json(common / 'runtime/.legacy-layout.json'); marker.pop('completed')
    write_json(common / 'runtime/.legacy-layout.json', marker)
    migrate_legacy(common)
    assert read_json(common / 'runtime/.legacy-layout.json')['completed']
    assert (common / 'date' / world.name / 'data/prime_backup/blob').read_bytes() == b'backup-pool-content'


@pytest.mark.parametrize('name', ['plugins', 'runtime', 'log', 'config'])
def test_world_names_can_match_top_level_group_names(tmp_path, name):
    assert profile_path(tmp_path, name) == tmp_path / 'date' / name
