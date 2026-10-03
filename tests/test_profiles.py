import io
import hashlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from singleplayer_bridge.profiles import child, ensure_profile, import_configs, read_json, recommend, write_json, validate_prime_binding
from singleplayer_bridge.bootstrap import download_checked, install_dependencies


def world(tmp, name):
    path = tmp / 'saves' / name
    path.mkdir(parents=True)
    (path / 'level.dat').write_bytes(b'world')
    return path


def test_isolated_worlds_import_only_settings_and_rebind_backup(tmp_path):
    common = tmp_path / 'common'
    a = ensure_profile(common, world(tmp_path, '世界 A'))
    b = ensure_profile(common, world(tmp_path, '世界 B'))
    assert read_json(a / 'config/prime_backup/config.json')['enabled'] is True
    recommend(a)
    write_json(a / 'config/probe/config.json', {'custom': True})
    write_json(a / 'config/probe/players.json', {'data': 'never copy'})
    write_json(a / 'config/probe/data/settings.json', {'data': 'never copy'})
    (a / 'data').mkdir()
    (a / 'data/db.sqlite').write_bytes(b'db')
    imported = import_configs(common, b, a.name)
    assert imported == ['probe/config.json']
    assert not (b / 'config/probe/players.json').exists()
    assert not (b / 'config/probe/data').exists()
    assert not (b / 'data/db.sqlite').exists()
    copied = import_configs(common, b, a.name, replace=True)
    assert 'prime_backup/config.json' in copied
    config = read_json(b / 'config/prime_backup/config.json')
    assert config['backup']['targets'] == ['世界 B']
    assert config['storage_root'] == './pb_files'
    assert validate_prime_binding(b)
    assert list((b / 'config/prime_backup').glob('config.json.before-*'))


def test_world_name_collision_and_external_store_are_rejected(tmp_path):
    common = tmp_path / 'common'
    first = world(tmp_path / 'instance1', 'same')
    second = world(tmp_path / 'instance2', 'same')
    profile = ensure_profile(common, first)
    with pytest.raises(ValueError, match='different world'):
        ensure_profile(common, second)
    config = read_json(profile / 'config/prime_backup/config.json')
    config['storage_root'] = str(tmp_path / 'shared-db')
    write_json(profile / 'config/prime_backup/config.json', config)
    with pytest.raises(ValueError, match='inside the current profile'):
        ensure_profile(common, first)


def test_chunk_backup_profiles_import_policy_without_backup_slots(tmp_path):
    common = tmp_path / 'common'
    plugins = common / 'plugins'
    plugins.mkdir(parents=True)
    with zipfile.ZipFile(plugins / 'chunk_backup.mcdr', 'w') as archive:
        archive.writestr('mcdreforged.plugin.json', json.dumps(dict(id='chunk_backup', version='2.0.3')))
    a = ensure_profile(common, world(tmp_path, 'A'))
    b = ensure_profile(common, world(tmp_path, 'B'))
    config = read_json(a / 'config/chunk_backup/config.json')
    config['command'] = dict(restore_countdown_sec=7)
    write_json(a / 'config/chunk_backup/config.json', config)
    (a / 'cb_files/slot-data').write_bytes(b'backup')
    assert 'chunk_backup/config.json' in import_configs(common, b, 'A', replace=True)
    imported = read_json(b / 'config/chunk_backup/config.json')
    assert imported['command']['restore_countdown_sec'] == 7
    assert imported['storage_root'] == './cb_files'
    assert all(dim['world_name'] == 'B' for dim in imported['backup']['dimension'].values())
    assert read_json(b / 'config/singleplayer_chunk_backup/config.json')['world_path'] == str(tmp_path / 'saves/B')
    assert not (b / 'cb_files/slot-data').exists()


def test_import_does_not_classify_yaml_player_state_as_configuration(tmp_path):
    common = tmp_path / 'common'
    a = ensure_profile(common, world(tmp_path, 'a'))
    b = ensure_profile(common, world(tmp_path, 'b'))
    folder = a / 'config/probe'
    folder.mkdir()
    (folder / 'config.yml').write_text('setting: true')
    (folder / 'players.yml').write_text('private_state: true')
    (folder / 'counter.json').write_text('{"state":1}')
    assert import_configs(common, b, 'a') == ['probe/config.yml']
    assert not (b / 'config/probe/players.yml').exists()


@pytest.mark.parametrize('name', ['../x', '..', 'x/y', 'CON', 'x.', 'x ', 'C:\\outside'])
def test_profile_paths_are_bounded(tmp_path, name):
    with pytest.raises(ValueError):
        child(tmp_path, name)


def test_download_falls_back_and_rejects_modified_mirror(tmp_path):
    calls = []
    good = b'official release'
    def opener(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise TimeoutError()
        return io.BytesIO(b'tampered' if len(calls) == 2 else good)
    destination = tmp_path / 'plugin.pyz'
    download_checked(['https://official', 'https://badmirror', 'https://goodmirror'], destination,
                     hashlib.sha256(good).hexdigest(), opener)
    assert len(calls) == 3
    assert destination.read_bytes() == good
    assert not destination.with_name('plugin.pyz.download').exists()


def test_pip_falls_back_without_changing_global_python():
    calls = []
    def runner(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0 if len(calls) == 2 else 1)
    install_dependencies('isolated-python', 'requirements.txt', ['https://official', 'https://mirror'], runner)
    assert calls[0][0] == calls[1][0] == 'isolated-python'
    assert 'https://mirror' in calls[1]
