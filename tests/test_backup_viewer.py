"""The edit-screen viewer must read both stores and never invent a restore point."""
import json
import sqlite3

import pytest

from singleplayer_bridge import backup_catalog, chunk_restore
from singleplayer_bridge.profiles import write_json


def fixture(tmp_path):
    common = tmp_path / 'mcdr-singleplayer'
    profile = common / 'plugindata' / 'w1'
    world = tmp_path / 'saves' / 'w1'
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'live')
    store = profile / 'cb_files'
    store.mkdir(parents=True)
    write_json(profile / 'profile.json', {'world_path': str(world), 'folder': 'w1'})
    config = {
        'server_root': str(world.parent), 'storage_root': './cb_files',
        'static_storage': 'static_storage', 'dynamic_storage': 'dynamic_storage',
        'overwrite_storage': 'overwrite',
        'backup': {'dimension': {'minecraft:overworld': {'integer_id': 0, 'world_name': 'w1',
            'region_folder': ['dimensions/minecraft/overworld/region']}}},
    }
    write_json(profile / 'config/chunk_backup/config.json', config)
    return common, profile, world, store, config


def add_slot(store, kind, name, region=b'BACKUP', **override):
    """One slot: its descriptor plus the region folder the world would receive."""
    slot = store / kind / name
    folder = slot / 'w1' / 'dimensions/minecraft/overworld/region'
    folder.mkdir(parents=True)
    (folder / 'r.0.0.mca').write_bytes(region)
    write_json(folder / 'index.json', {'type': 'region'})
    info = dict(type='region', operator='Console', date='2026-01-02 03:04:05',
                dimension=['minecraft:overworld'], comment='slot ' + name, total_size=len(region))
    info.update(override)
    write_json(slot / 'info.json', info)
    return slot

def test_catalog_lists_prime_and_chunk_without_requiring_the_other_store(tmp_path):
    common, profile, world, store, _ = fixture(tmp_path)
    storage = profile / 'pb_files'
    storage.mkdir()
    with sqlite3.connect(storage / 'prime_backup.db') as connection:
        connection.execute('CREATE TABLE backup (id INTEGER, timestamp INTEGER, creator TEXT, '
                           'comment TEXT, targets TEXT, tags TEXT, file_raw_size_sum INTEGER)')
        connection.executemany('INSERT INTO backup VALUES (?, ?, ?, ?, ?, ?, ?)', [
            (1, 1700000000, 'player', 'keep', json.dumps(['w1']), '{}', 10),
            (2, 1700000100, 'player', 'other', json.dumps(['w2']), '{}', 10),
        ])
    write_json(profile / 'config/prime_backup/config.json', {'storage_root': './pb_files'})
    add_slot(store, 'dynamic_storage', 'slot1')

    value = backup_catalog.catalog(common, 'w1')
    assert value['world'] == 'w1'
    # Only this folder's records are listed, and the neighbouring world is ignored.
    assert [row['id'] for row in value['prime']['backups']] == [1]
    assert value['prime']['backups'][0]['ref'] == 'prime:1'
    assert [row['ref'] for row in value['chunk']['backups']] == ['chunk:dynamic/slot1']
    assert value['chunk']['backups'][0]['restorable'] is True
    # The recorded operator is shown instead of an empty field.
    assert value['prime']['backups'][0]['operator'] == 'player'


def test_upstream_translated_comments_are_readable(tmp_path):
    common, profile, world, store, _ = fixture(tmp_path)
    storage = profile / 'pb_files'
    storage.mkdir()
    rows = [
        (1, 1700000000, 'prime_backup:pre_restore', '__pb_translated__:pre_restore:9', 10, '{}'),
        (2, 1700000100, 'prime_backup:pre_restore', '__pb_translated__:pre_restore', 10, '{}'),
        (3, 1700000200, 'Steve', 'written by hand', 10, '{}'),
        # An unknown marker keeps its raw text instead of becoming an empty string.
        (4, 1700000300, 'Steve', '__pb_translated__:unknown_key', 10, '{}'),
    ]
    with sqlite3.connect(storage / 'prime_backup.db') as connection:
        connection.execute('CREATE TABLE backup (id INTEGER, timestamp INTEGER, creator TEXT, '
                           'comment TEXT, targets TEXT, tags TEXT, file_raw_size_sum INTEGER)')
        connection.executemany('INSERT INTO backup VALUES (?, ?, ?, ?, ?, ?, ?)',
                               [(i, t, c, m, json.dumps(['w1']), tags, s) for i, t, c, m, s, tags in rows])
    write_json(profile / 'config/prime_backup/config.json', {'storage_root': './pb_files'})

    listed = {row['id']: row['comment'] for row in backup_catalog.catalog(common, 'w1')['prime']['backups']}
    # The upstream marker is rendered in the user's language, matches its own wording.
    assert listed[1] == 'Automatic backup before restoring to #9'
    assert listed[2] == 'Automatic backup before restore'
    assert listed[3] == 'written by hand'
    assert listed[4] == '__pb_translated__:unknown_key'


def test_prime_database_without_the_expected_columns_is_reported_not_raised(tmp_path):
    common, profile, world, store, _ = fixture(tmp_path)
    storage = profile / 'pb_files'
    storage.mkdir()
    with sqlite3.connect(storage / 'prime_backup.db') as connection:
        connection.execute('CREATE TABLE unrelated (a INTEGER)')
    write_json(profile / 'config/prime_backup/config.json', {'storage_root': './pb_files'})
    value = backup_catalog.catalog(common, 'w1')
    # A damaged database must not take the whole viewer down with it.
    assert value['prime']['backups'] == []
    assert value['prime']['error']


def test_catalog_reports_each_store_failure_independently(tmp_path):
    common, profile, world, store, _ = fixture(tmp_path)
    add_slot(store, 'dynamic_storage', 'slot1')
    value = backup_catalog.catalog(common, 'w1')
    # Prime Backup is simply not configured yet; Chunk Backup must still be listed.
    assert value['prime']['backups'] == []
    assert value['prime']['error'] == 'mcdr-singleplayer.catalog.missing_prime_backup'
    assert len(value['chunk']['backups']) == 1


def test_chunk_area_backups_are_restorable_but_custom_ones_are_not(tmp_path):
    """选区备份（type=chunk）可以离线回档，组合备份（type=custom）不可以。

    上游恢复本来就是复制槽位里已有的区域文件，所以选区备份只是少了几个文件，
    不需要额外的合并逻辑；组合备份把多份子备份拼在一起，离线路径不去猜。
    """
    common, profile, world, store, _ = fixture(tmp_path)
    add_slot(store, 'dynamic_storage', 'slot1', type='chunk')
    add_slot(store, 'dynamic_storage', 'slot2', type='custom')
    rows = {row['ref']: row for row in backup_catalog.catalog(common, 'w1')['chunk']['backups']}
    assert rows['chunk:dynamic/slot1']['restorable'] is True
    assert rows['chunk:dynamic/slot1']['reason'] == ''
    assert rows['chunk:dynamic/slot2']['restorable'] is False
    assert rows['chunk:dynamic/slot2']['reason'] == 'mcdr-singleplayer.catalog.custom_type'


def test_a_slot_bound_to_another_save_location_is_not_restorable(tmp_path):
    common, profile, world, store, config = fixture(tmp_path)
    config['server_root'] = str(tmp_path / 'elsewhere')
    write_json(profile / 'config/chunk_backup/config.json', config)
    add_slot(store, 'dynamic_storage', 'slot1')
    row = backup_catalog.catalog(common, 'w1')['chunk']['backups'][0]
    assert row['restorable'] is False
    assert row['reason'] == 'mcdr-singleplayer.catalog.store_moved'


def test_catalog_refuses_a_store_outside_the_profile(tmp_path):
    common, profile, world, store, config = fixture(tmp_path)
    config['storage_root'] = '../outside'
    write_json(profile / 'config/chunk_backup/config.json', config)
    value = backup_catalog.catalog(common, 'w1')
    assert value['chunk']['backups'] == []
    assert value['chunk']['error'] == 'mcdr-singleplayer.catalog.chunk_outside_profile'


def test_overwrite_slot_is_labelled_as_a_safety_snapshot(tmp_path):
    common, profile, world, store, _ = fixture(tmp_path)
    # The plugin writes the overwrite slot directly under the store, not in a slot folder.
    folder = store / 'overwrite' / 'w1' / 'dimensions/minecraft/overworld/region'
    folder.mkdir(parents=True)
    write_json(folder / 'index.json', {'type': 'region'})
    write_json(store / 'overwrite/info.json', dict(type='region', operator='Console',
        date='2026-01-03 04:05:06', dimension=['minecraft:overworld'], comment='pre-restore',
        total_size=4))
    rows = backup_catalog.catalog(common, 'w1')['chunk']['backups']
    assert [row['ref'] for row in rows] == ['chunk:overwrite']
    assert rows[0]['temporary'] is True
    assert rows[0]['restorable'] is True


def test_restore_copies_the_slot_and_snapshots_the_current_world(tmp_path):
    common, profile, world, store, _ = fixture(tmp_path)
    current = world / 'dimensions/minecraft/overworld/region'
    current.mkdir(parents=True)
    (current / 'r.0.0.mca').write_bytes(b'CURRENT')
    (current / 'extra.mca').write_bytes(b'EXTRA')
    add_slot(store, 'dynamic_storage', 'slot1')

    chunk_restore.restore(common, 'w1', 'chunk:dynamic/slot1')

    assert (current / 'r.0.0.mca').read_bytes() == b'BACKUP'
    # The slot never carries its own marker into the world.
    assert not (current / 'index.json').exists()
    # A file the slot does not contain survives, matching the plugin's own restore.
    assert (current / 'extra.mca').read_bytes() == b'EXTRA'
    # The pre-restore state becomes the overwrite slot.
    overwrite = store / 'overwrite'
    assert (overwrite / 'w1/dimensions/minecraft/overworld/region/r.0.0.mca').read_bytes() == b'CURRENT'
    assert json.loads((overwrite / 'info.json').read_text(encoding='utf8'))['type'] == 'region'
    progress = json.loads((common / 'runtime/.mcdr_restore_progress.json').read_text(encoding='utf8'))
    assert progress['status'] == 'completed'
    assert progress['world_name'] == 'w1'


def test_restore_accepts_a_chunk_area_slot(tmp_path):
    """选区备份能直接回档：复制槽位里已有的区域文件即可。"""
    common, profile, world, store, _ = fixture(tmp_path)
    current = world / 'dimensions/minecraft/overworld/region'
    current.mkdir(parents=True)
    (current / 'r.0.0.mca').write_bytes(b'CURRENT')
    add_slot(store, 'dynamic_storage', 'slot1', type='chunk')
    result = chunk_restore.restore(common, 'w1', 'chunk:dynamic/slot1')
    assert result['files'] >= 1
    assert (current / 'r.0.0.mca').read_bytes() == b'BACKUP'


def test_restore_still_refuses_a_custom_slot(tmp_path):
    common, profile, world, store, _ = fixture(tmp_path)
    add_slot(store, 'dynamic_storage', 'slot1', type='custom')
    with pytest.raises(chunk_restore.UnsupportedSlot):
        chunk_restore.restore(common, 'w1', 'chunk:dynamic/slot1')


def test_restore_rejects_an_unknown_reference(tmp_path):
    common, profile, world, store, _ = fixture(tmp_path)
    with pytest.raises(ValueError):
        chunk_restore.restore(common, 'w1', 'chunk:dynamic/slot9')
    with pytest.raises(ValueError):
        chunk_restore.restore(common, 'w1', 'not-a-slot')


def test_restore_keeps_the_world_when_the_slot_is_missing(tmp_path):
    common, profile, world, store, _ = fixture(tmp_path)
    (world / 'level.dat').write_bytes(b'live')
    current = world / 'dimensions/minecraft/overworld/region'
    current.mkdir(parents=True)
    (current / 'r.0.0.mca').write_bytes(b'CURRENT')
    slot = add_slot(store, 'dynamic_storage', 'slot1')
    (slot / 'w1/dimensions/minecraft/overworld/region/r.0.0.mca').unlink()
    with pytest.raises(RuntimeError):
        chunk_restore.restore(common, 'w1', 'chunk:dynamic/slot1')
    # A failed selection never touches the live world.
    assert (current / 'r.0.0.mca').read_bytes() == b'CURRENT'
