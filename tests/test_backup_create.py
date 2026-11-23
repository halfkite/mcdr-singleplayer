"""离线创建三类备份：PB 走官方 CLI，CB 按槽位布局，原版照原版格式。"""
import json
import zipfile
from pathlib import Path

import pytest

from singleplayer_bridge import backup_catalog, backup_create, chunk_restore, vanilla_restore
from singleplayer_bridge.profiles import write_json


def chunk_fixture(tmp_path):
    common = tmp_path / 'mcdr-singleplayer'
    world = tmp_path / 'saves' / 'w1'
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'L')
    region = world / 'dimensions/minecraft/overworld/region'
    region.mkdir(parents=True)
    (region / 'r.0.0.mca').write_bytes(b'R')
    profile = common / 'plugindata' / 'w1'
    profile.mkdir(parents=True)
    write_json(profile / 'profile.json', {'world_path': str(world), 'folder': 'w1'})
    write_json(profile / 'config/chunk_backup/config.json', {
        'server_root': str(world.parent), 'storage_root': './cb_files',
        'dynamic_storage': 'dynamic_storage', 'static_storage': 'static_storage',
        'overwrite_storage': 'overwrite',
        'backup': {'max_dynamic_slot': 3,
                   'dimension': {'minecraft:overworld': {
                       'integer_id': 0, 'world_name': 'w1',
                       'region_folder': ['dimensions/minecraft/overworld/region']}}}})
    return common, world, profile


def test_chunk_backup_writes_slot1_with_the_region_and_index(tmp_path):
    common, world, profile = chunk_fixture(tmp_path)
    result = backup_create.chunk(common, 'w1')
    assert result['files'] >= 1
    slot = profile / 'cb_files/dynamic_storage/slot1'
    assert (slot / 'info.json').is_file()
    copied = slot / 'w1/dimensions/minecraft/overworld/region/r.0.0.mca'
    assert copied.read_bytes() == b'R'
    # 上游槽位里带区域清单，回档时不会把它复制进存档。
    assert (copied.parent / 'index.json').is_file()
    info = __import__('json').loads((slot / 'info.json').read_text(encoding='utf8'))
    assert info['type'] == 'region'
    assert info['dimension'] == ['minecraft:overworld']
    # 新建的槽位应当能被列表读到并回档。
    rows = backup_catalog.catalog(common, 'w1')['chunk']['backups']
    assert [row['ref'] for row in rows] == ['chunk:dynamic/slot1']
    assert rows[0]['restorable'] is True


def test_new_chunk_backups_shift_older_slots_and_drop_past_the_limit(tmp_path):
    common, world, profile = chunk_fixture(tmp_path)
    base = profile / 'cb_files/dynamic_storage'
    for number in (1, 2, 3):
        (base / f'slot{number}').mkdir(parents=True)
        write_json(base / f'slot{number}/info.json', {'date': f'2026-01-0{number} 00:00:00',
            'type': 'region', 'dimension': ['minecraft:overworld'], 'total_size': 1})
    backup_create.chunk(common, 'w1')
    # 上限 3：最旧的 slot3 被丢弃，其余各后移一位，新备份占 slot1。
    kept = sorted(entry.name for entry in base.iterdir() if entry.is_dir())
    assert kept == ['slot1', 'slot2', 'slot3']
    newest = __import__('json').loads((base / 'slot1/info.json').read_text(encoding='utf8'))
    assert newest['date'] != '2026-01-01 00:00:00'
    oldest = __import__('json').loads((base / 'slot3/info.json').read_text(encoding='utf8'))
    assert oldest['date'] == '2026-01-02 00:00:00'


def test_chunk_backup_requires_a_configured_store(tmp_path):
    common = tmp_path / 'mcdr-singleplayer'
    world = tmp_path / 'saves' / 'w1'
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'L')
    (common / 'plugindata' / 'w1').mkdir(parents=True)
    write_json(common / 'plugindata/w1/profile.json', {'world_path': str(world), 'folder': 'w1'})
    with pytest.raises(RuntimeError):
        backup_create.chunk(common, 'w1')


def test_prime_backup_without_database_is_refused_not_faked(tmp_path):
    common, world, profile = chunk_fixture(tmp_path)
    write_json(profile / 'config/prime_backup/config.json', {'storage_root': './pb_files'})
    (profile / 'pb_files').mkdir(parents=True)
    # 没有 prime_backup.db 时不能凭空写一条备份记录。
    with pytest.raises(RuntimeError):
        backup_create.prime(common, 'w1')


def test_prime_backup_needs_the_plugin_itself(tmp_path):
    common, world, profile = chunk_fixture(tmp_path)
    write_json(profile / 'config/prime_backup/config.json', {'storage_root': './pb_files'})
    (profile / 'pb_files').mkdir(parents=True)
    (profile / 'pb_files/prime_backup.db').write_bytes(b'')
    with pytest.raises(FileNotFoundError):
        backup_create.prime(common, 'w1')


def test_backup_of_a_missing_world_is_refused(tmp_path):
    common = tmp_path / 'mcdr-singleplayer'
    (common / 'plugindata' / 'gone').mkdir(parents=True)
    (tmp_path / 'saves' / 'gone').mkdir(parents=True)
    for maker in (backup_create.chunk, backup_create.prime):
        with pytest.raises(FileNotFoundError):
            maker(common, 'gone')


def area_fixture(tmp_path):
    """三个区域文件，分别覆盖区块 (0,0)、(32,0)、(160,160)。"""
    common = tmp_path / 'mcdr-singleplayer'
    world = tmp_path / 'saves' / 'w1'
    region = world / 'dimensions/minecraft/overworld/region'
    region.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'L')
    for name in ('r.0.0.mca', 'r.1.0.mca', 'r.5.5.mca'):
        (region / name).write_bytes(b'R')
    profile = common / 'plugindata' / 'w1'
    profile.mkdir(parents=True)
    write_json(profile / 'profile.json', {'world_path': str(world), 'folder': 'w1'})
    write_json(profile / 'config/chunk_backup/config.json', {
        'server_root': str(world.parent), 'storage_root': './cb_files',
        'dynamic_storage': 'dynamic_storage', 'static_storage': 'static_storage',
        'overwrite_storage': 'overwrite',
        'backup': {'max_dynamic_slot': 3, 'dimension': {
            'minecraft:overworld': {'integer_id': 0, 'world_name': 'w1',
                                    'region_folder': ['dimensions/minecraft/overworld/region']}}}})
    return common, profile


def test_a_chunk_area_only_keeps_overlapping_region_files(tmp_path):
    common, profile = area_fixture(tmp_path)
    result = backup_create.chunk(common, 'w1', 'area', 'minecraft:overworld', (0, 0, 40, 40))
    folder = Path(result['slot']) / 'w1/dimensions/minecraft/overworld/region'
    kept = sorted(entry.name for entry in folder.iterdir() if entry.suffix == '.mca')
    # 0..40 覆盖 r.0.0（0-31）和 r.1.0（32-63），不覆盖 r.5.5（160-191）。
    assert kept == ['r.0.0.mca', 'r.1.0.mca']
    info = json.loads((Path(result['slot']) / 'info.json').read_text(encoding='utf8'))
    assert info['type'] == 'chunk'
    assert info['name'] == '0,0 -> 40,40'


def test_a_whole_dimension_backup_stays_fully_restorable(tmp_path):
    common, profile = area_fixture(tmp_path)
    result = backup_create.chunk(common, 'w1')
    info = json.loads((Path(result['slot']) / 'info.json').read_text(encoding='utf8'))
    assert info['type'] == 'region'
    rows = backup_catalog.catalog(common, 'w1')['chunk']['backups']
    assert rows[0]['restorable'] is True


def test_a_chunk_area_backup_can_still_be_restored_offline(tmp_path):
    """选区备份也要能回档：上游恢复本来就是复制槽位里已有的区域文件。

    这里锁住修法：``type=chunk`` 不再被当成「不可离线回档」，实际恢复也走得通。
    """
    common, profile = area_fixture(tmp_path)
    result = backup_create.chunk(common, 'w1', 'area', 'minecraft:overworld', (0, 0, 40, 40))
    ref = 'chunk:dynamic/slot1'
    rows = {row['ref']: row for row in backup_catalog.catalog(common, 'w1')['chunk']['backups']}
    assert rows[ref]['restorable'] is True
    assert rows[ref]['reason'] == ''

    world = tmp_path / 'saves' / 'w1'
    region = world / 'dimensions/minecraft/overworld/region'
    (region / 'r.0.0.mca').write_bytes(b'NEW')
    # 选区外的文件本来就没进备份，回档后保持现状。
    (region / 'r.5.5.mca').write_bytes(b'KEEP')
    restored = chunk_restore.restore(common, 'w1', ref)
    assert restored['files'] >= 1
    assert (region / 'r.0.0.mca').read_bytes() == b'R'
    assert (region / 'r.5.5.mca').read_bytes() == b'KEEP'


def test_a_custom_slot_is_still_listed_as_not_restorable(tmp_path):
    """组合备份由上游拼多份子备份，离线路径不猜它的结构。"""
    common, profile = area_fixture(tmp_path)
    base = profile / 'cb_files/dynamic_storage'
    (base / 'slot1').mkdir(parents=True)
    write_json(base / 'slot1/info.json', {'date': '2026-01-01 00:00:00', 'type': 'custom',
        'dimension': ['minecraft:overworld'], 'total_size': 1})
    rows = backup_catalog.catalog(common, 'w1')['chunk']['backups']
    assert rows[0]['restorable'] is False
    assert rows[0]['reason'] == 'mcdr-singleplayer.catalog.custom_type'


def test_an_area_without_region_files_is_refused(tmp_path):
    common, profile = area_fixture(tmp_path)
    with pytest.raises(ValueError):
        backup_create.chunk(common, 'w1', '', 'minecraft:overworld', (9000, 9000, 9100, 9100))
    # 拒绝时不能留下一个空槽位。
    base = profile / 'cb_files/dynamic_storage'
    assert not (base / 'slot1').exists()


def test_an_unknown_dimension_is_refused(tmp_path):
    common, profile = area_fixture(tmp_path)
    with pytest.raises(ValueError):
        backup_create.chunk(common, 'w1', '', 'minecraft:unknown')
