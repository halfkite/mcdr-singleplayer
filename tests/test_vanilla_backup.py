"""原版备份与「创建配置」：不依赖任何插件，也不许写到存档之外。"""
import json
import zipfile

import pytest

from singleplayer_bridge import backup_catalog, backup_setup, vanilla_restore
from singleplayer_bridge.i18n import tr
from singleplayer_bridge.profiles import write_json


def fixture(tmp_path):
    common = tmp_path / 'mcdr-singleplayer'
    world = tmp_path / 'saves' / 'w1'
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'LEVEL-1')
    (world / 'region').mkdir()
    (world / 'region' / 'r.0.0.mca').write_bytes(b'R1')
    common.mkdir()
    return common, world


def test_vanilla_backup_roundtrip_keeps_the_world_folder_as_root(tmp_path):
    common, world = fixture(tmp_path)
    made = vanilla_restore.create(common, 'w1')
    archive = __import__('pathlib').Path(made['path'])
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zipped:
        names = zipped.namelist()
    # 原版格式以存档文件夹名为根，游戏自己的「备份此存档」也认这份。
    assert 'w1/level.dat' in names
    assert 'w1/region/r.0.0.mca' in names
    assert not any(name.startswith('/') for name in names)

    (world / 'level.dat').write_bytes(b'LEVEL-2')
    (world / 'region' / 'r.0.0.mca').write_bytes(b'R2')
    ref = 'vanilla:' + archive.name
    result = vanilla_restore.restore(common, 'w1', ref)
    assert result['files'] == 2
    assert (world / 'level.dat').read_bytes() == b'LEVEL-1'
    assert (world / 'region' / 'r.0.0.mca').read_bytes() == b'R1'


def test_vanilla_rows_only_list_this_save(tmp_path):
    common, world = fixture(tmp_path)
    other = tmp_path / 'saves' / 'w2'
    other.mkdir(parents=True)
    (other / 'level.dat').write_bytes(b'OTHER')
    vanilla_restore.create(common, 'w1')
    vanilla_restore.create(common, 'w2')
    rows = backup_catalog.vanilla_rows(common, 'w1')['backups']
    assert len(rows) == 1
    assert rows[0]['ref'].endswith('_w1.zip')
    assert rows[0]['restorable'] is True
    # 备份库目录不存在时是空列表，而不是错误。
    assert backup_catalog.vanilla_rows(common, 'absent')['backups'] == []


def test_same_second_backups_do_not_overwrite_each_other(tmp_path):
    common, world = fixture(tmp_path)
    first = vanilla_restore.create(common, 'w1')
    second = vanilla_restore.create(common, 'w1')
    assert first['path'] != second['path']
    assert len(backup_catalog.vanilla_rows(common, 'w1')['backups']) == 2


def test_vanilla_restore_rejects_a_backup_of_another_save(tmp_path):
    common, world = fixture(tmp_path)
    other = tmp_path / 'saves' / 'w2'
    other.mkdir(parents=True)
    (other / 'level.dat').write_bytes(b'OTHER')
    made = vanilla_restore.create(common, 'w2')
    name = made['path'].split('\\')[-1]
    with pytest.raises(ValueError):
        vanilla_restore.restore(common, 'w1', 'vanilla:' + name)


def test_vanilla_restore_refuses_entries_outside_the_world(tmp_path):
    common, world = fixture(tmp_path)
    folder = common.parent / 'backups'
    folder.mkdir()
    escape = folder / '2026-01-01_00-00-00_w1.zip'
    with zipfile.ZipFile(escape, 'w') as zipped:
        zipped.writestr('w1/level.dat', b'X')
        zipped.writestr('w1/../../evil.txt', b'X')
    with pytest.raises(ValueError):
        vanilla_restore.restore(common, 'w1', 'vanilla:' + escape.name)
    # 越界条目被拒绝时，存档不能被改动。
    assert (world / 'level.dat').read_bytes() == b'LEVEL-1'


def test_vanilla_restore_requires_level_dat(tmp_path):
    common, world = fixture(tmp_path)
    folder = common.parent / 'backups'
    folder.mkdir()
    broken = folder / '2026-01-01_00-00-00_w1.zip'
    with zipfile.ZipFile(broken, 'w') as zipped:
        zipped.writestr('w1/region/r.0.0.mca', b'R')
    with pytest.raises(ValueError):
        vanilla_restore.restore(common, 'w1', 'vanilla:' + broken.name)


def test_create_config_builds_both_plugin_configs(tmp_path):
    common, world = fixture(tmp_path)
    assert backup_catalog.catalog(common, 'w1')['prime']['error'] == \
        'mcdr-singleplayer.catalog.missing_profile'
    backup_setup.prime(common, 'w1')
    backup_setup.chunk(common, 'w1')
    value = backup_catalog.catalog(common, 'w1')
    # PB 现在只是缺数据库，CB 已完全可用；两者都不再是「没有配置」。
    assert value['prime']['error'] == 'mcdr-singleplayer.catalog.missing_prime_database'
    assert value['chunk']['error'] == ''
    assert value['vanilla']['error'] == ''
    profile = common / 'plugindata' / 'w1'
    assert (profile / 'config/prime_backup/config.json').is_file()
    assert (profile / 'config/chunk_backup/config.json').is_file()
    assert (profile / 'cb_files').is_dir()


def test_creating_a_config_twice_keeps_the_existing_settings(tmp_path):
    common, world = fixture(tmp_path)
    backup_setup.chunk(common, 'w1')
    path = common / 'plugindata/w1/config/chunk_backup/config.json'
    config = json.loads(path.read_text(encoding='utf8'))
    config['storage_root'] = './custom_cb'
    write_json(path, config)
    backup_setup.chunk(common, 'w1')
    again = json.loads(path.read_text(encoding='utf8'))
    assert again['storage_root'] == './custom_cb'


def test_config_creation_refuses_a_save_without_level_dat(tmp_path):
    common = tmp_path / 'mcdr-singleplayer'
    common.mkdir()
    (tmp_path / 'saves' / 'gone').mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        backup_setup.prime(common, 'gone')
    with pytest.raises(FileNotFoundError):
        backup_setup.chunk(common, 'gone')


def redirected(tmp_path):
    """存档被模组重定向到游戏目录之外，profile.json 记录的是真实路径。"""
    game = tmp_path / 'game'
    (game / 'mcdr-singleplayer').mkdir(parents=True)
    # 游戏目录下的 saves 留一个同名空壳，用来证明代码没有去那里找。
    (game / 'saves' / 'w1').mkdir(parents=True)
    real = tmp_path / 'elsewhere' / 'saves' / 'w1'
    real.mkdir(parents=True)
    (real / 'level.dat').write_bytes(b'LEVEL-1')
    profile = game / 'mcdr-singleplayer' / 'plugindata' / 'w1'
    profile.mkdir(parents=True)
    write_json(profile / 'profile.json', {'world_path': str(real), 'folder': 'w1'})
    return game / 'mcdr-singleplayer', real


def test_paths_follow_the_recorded_save_location(tmp_path):
    common, real = redirected(tmp_path)
    _, world = backup_catalog.paths(common, 'w1')
    assert world == real
    # 原版备份跟着真实存档根走，而不是游戏目录。
    assert backup_catalog.vanilla_dir(common, 'w1') == real.parent / '_Backups'


def test_vanilla_backup_uses_the_redirected_backup_folder(tmp_path):
    common, real = redirected(tmp_path)
    made = vanilla_restore.create(common, 'w1')
    archive = __import__('pathlib').Path(made['path'])
    assert archive.parent == real.parent / '_Backups'
    rows = backup_catalog.vanilla_rows(common, 'w1')['backups']
    assert len(rows) == 1
    # 游戏目录下那个同名空壳不能被当成存档。
    assert not any((tmp_path / 'game' / 'backups').glob('*')) if \
        (tmp_path / 'game' / 'backups').is_dir() else True


def test_old_game_directory_backups_are_still_listed(tmp_path):
    """更早的版本把备份放在 <游戏目录>/backups，仍要能看能回。"""
    common, real = redirected(tmp_path)
    legacy = tmp_path / 'game' / 'backups'
    legacy.mkdir()
    with zipfile.ZipFile(legacy / '2025-01-02_03-04-05_w1.zip', 'w') as zipped:
        zipped.writestr('w1/level.dat', b'OLD')
    rows = backup_catalog.vanilla_rows(common, 'w1')['backups']
    assert [row['ref'] for row in rows] == ['vanilla:2025-01-02_03-04-05_w1.zip']
    (real / 'level.dat').write_bytes(b'NEW')
    vanilla_restore.restore(common, 'w1', rows[0]['ref'])
    assert (real / 'level.dat').read_bytes() == b'OLD'
