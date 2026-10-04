import json
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from singleplayer_bridge import onboarding, plugin
from singleplayer_bridge.config_file import read as read_bridge_config, write as write_bridge_config
from singleplayer_bridge.bootstrap import pack
from singleplayer_bridge.profiles import ensure_profile, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def welcome(tmp_path, monkeypatch):
    common = tmp_path / 'common'
    (common / 'plugins').mkdir(parents=True)
    write_bridge_config(common / 'mcdr-singleplayer-config.yml', {'token': 'keep-this-token', 'custom': 9})
    monkeypatch.setenv('MCDR_BRIDGE_COMMON', str(common))
    monkeypatch.setenv('MCDR_BRIDGE_HOST', 'Main')
    monkeypatch.setenv('MCDR_BRIDGE_LANGUAGE', 'zh_cn')
    monkeypatch.setenv('MCDR_BRIDGE_CLIENT_ID', 'client-a')
    monkeypatch.setattr(plugin, 'snapshot', lambda: dict(session='session-a', players=['Main'], host_player='Main'))
    monkeypatch.setattr(onboarding, '_shown', set())
    monkeypatch.setattr(onboarding, '_settings_shown', set())
    messages = []
    server = SimpleNamespace(tell=lambda host, text: messages.append(text), get_plugin_instance=lambda item: None)
    return common, server, messages


def commands(messages):
    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'clickEvent':
                    yield child
                else:
                    yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)
    return list(walk([m.to_json_object() for m in messages if hasattr(m, 'to_json_object')]))


def test_fresh_prompt_links_warning_and_no_settings_before_install(welcome):
    common, server, messages = welcome
    onboarding.prompt(server)
    text = '\n'.join(str(m) for m in messages)
    assert text.count(onboarding.WARNING) == 3
    assert '.\\mcdr-singleplayer\\plugindata' in text and '四级权限' in text
    clicks = str(commands(messages))
    assert '/!!spbridge install prime_backup' in clicks
    assert '/!!spbridge install chunk_backup' in clicks
    assert onboarding.PB_PAGE in clicks and onboarding.CB_PAGE in clicks
    assert '/!!spbridge config backup on' not in clicks
    assert read_bridge_config(common / 'mcdr-singleplayer-config.yml')['token'] == 'keep-this-token'
    count = len(messages)
    onboarding.prompt(server)
    assert len(messages) == count


def test_existing_plugins_skip_install_but_show_pb_options(welcome):
    common, server, messages = welcome
    for item in ['prime_backup', 'chunk_backup']:
        with zipfile.ZipFile(common / 'plugins' / (item + '.mcdr'), 'w') as z:
            z.writestr('mcdreforged.plugin.json', json.dumps(dict(id=item, version='test')))
    server.get_plugin_instance = lambda item: object() if item == 'prime_backup' else None
    onboarding.prompt(server)
    clicks = str(commands(messages))
    assert 'spbridge install' not in clicks
    assert '/!!spbridge config backup on' in clicks
    assert '/!!spbridge config auto_backup on' in clicks
    assert '/!!spbridge config auto_delete on' in clicks
    assert 'last' not in '\n'.join(str(m) for m in messages)


def test_ignore_is_common_and_force_show_does_not_clear_it(welcome, monkeypatch):
    common, server, messages = welcome
    onboarding.dismiss(SimpleNamespace(reply=lambda message: None))
    monkeypatch.setattr(plugin, 'snapshot', lambda: dict(session='other-world', players=['Main']))
    onboarding.prompt(server)
    assert messages == []
    onboarding.prompt(server, force=True)
    assert len(messages) > 0
    saved = read_bridge_config(common / 'mcdr-singleplayer-config.yml')
    assert saved['onboardingDismissed'] and saved['custom'] == 9


def test_intro_once_per_client_but_new_client_can_see_it(welcome, monkeypatch):
    _, server, messages = welcome
    onboarding.prompt(server)
    count = len(messages)
    monkeypatch.setattr(plugin, 'snapshot', lambda: dict(session='session-b', players=['Main']))
    onboarding.prompt(server)
    assert len(messages) == count
    monkeypatch.setenv('MCDR_BRIDGE_CLIENT_ID', 'client-b')
    monkeypatch.setattr(onboarding, '_shown', set())
    onboarding.prompt(server)
    assert len(messages) == count * 2


def test_install_failure_releases_busy_flag_and_allows_retry(welcome, monkeypatch):
    import time
    _, server, _ = welcome
    replies = []
    monkeypatch.setattr(plugin, 'prime_busy', lambda: False)
    def fail(*args):
        raise RuntimeError('simulated download failure')
    monkeypatch.setattr(onboarding, 'prepare_install', fail)
    server.logger = SimpleNamespace(exception=lambda message: None)
    source = SimpleNamespace(reply=replies.append, get_server=lambda: server)
    for _ in range(2):
        onboarding.install(source, 'prime_backup')
        deadline = time.monotonic() + 3
        while onboarding.installing() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not onboarding.installing()
    assert sum('安装失败' in reply for reply in replies) == 2


@pytest.mark.parametrize('item,upstream,adapter', [
    ('prime_backup', ['PrimeBackup-v1.13.1.pyz'], 'prime-backup-adapter'),
    ('chunk_backup', ['Candy_Tools-v1.0.2.mcdr', 'Chunk_BackUp-v2.0.3.mcdr'], 'chunk-backup-adapter')])
def test_install_verified_upstream_and_bind_current_world(welcome, tmp_path, monkeypatch, item, upstream, adapter):
    common, _, _ = welcome
    world = tmp_path / 'saves/test-world'
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'test')
    profile = ensure_profile(common, world)
    store = common / 'runtime/backup-adapters'
    store.mkdir(parents=True)
    pack(ROOT / adapter, store / ('singleplayer_' + item + '.mcdr'))
    def fetch(urls, target, digest):
        import hashlib
        source = ROOT / '.reference' / target.name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
        assert urls[0].startswith('https://github.com/')
        shutil.copy2(source, target)
    monkeypatch.setattr('singleplayer_bridge.bootstrap.download_checked', fetch)
    result = onboarding.prepare_install(common, profile, item)
    assert [p.name for p in result] == upstream + ['singleplayer_' + item + '.mcdr']
    assert all(p.parent == common / 'plugins' for p in result)
    if item == 'chunk_backup':
        assert read_json(profile / 'config/chunk_backup/config.json')['storage_root'] == './cb_files'
        assert read_json(profile / 'cb_files/.singleplayer-world.json')['world_path'] == str(world.resolve())
    else:
        assert read_json(profile / 'config/prime_backup/config.json')['backup']['targets'] == ['test-world']


def test_incompatible_installed_version_preserved(welcome, tmp_path):
    common, _, _ = welcome
    path = common / 'plugins/custom-pb.mcdr'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('mcdreforged.plugin.json', json.dumps(dict(id='prime_backup', version='1.14.0')))
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match='其他版本'):
        onboarding.prepare_install(common, tmp_path, 'prime_backup')
    assert path.read_bytes() == before


def test_unpacked_cb_is_detected_and_configured_on_next_world(welcome, tmp_path):
    common, server, messages = welcome
    write_json(common / 'plugins/chunk_backup/mcdreforged.plugin.json', dict(id='chunk_backup', version='2.0.3'))
    world = tmp_path / 'saves/next-world'
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'world')
    profile = ensure_profile(common, world)
    assert (profile / 'cb_files/.singleplayer-world.json').is_file()
    onboarding.prompt(server)
    assert '/!!spbridge install chunk_backup' not in str(commands(messages))


def test_fresh_bootstrap_keeps_backup_plugins_opt_in(tmp_path, monkeypatch):
    from singleplayer_bridge import bootstrap
    common = tmp_path / 'common'
    common.mkdir()
    (common / 'config.yml').write_text('{}', encoding='utf-8')
    (common / 'permission.yml').write_text('{}', encoding='utf-8')
    import os
    interpreter = common / 'runtime/.bridge-venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    resources = tmp_path / 'resources'
    resources.mkdir()
    (resources / 'requirements-prime-backup.txt').write_text('tested requirements', encoding='utf-8')
    (resources / 'runtime').mkdir()
    for folder, source in [('bridge-plugin', 'python'), ('adapter-plugin', 'prime-backup-adapter'), ('chunk-adapter-plugin', 'chunk-backup-adapter')]:
        shutil.copytree(ROOT / source, resources / folder, ignore=shutil.ignore_patterns('__pycache__'))
    monkeypatch.setattr(bootstrap.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(bootstrap, 'install_dependencies', lambda *args, **kwargs: None)
    monkeypatch.setattr(bootstrap, 'download_checked', lambda *args, **kwargs: pytest.fail('Fresh runtime must not download a backup plugin'))
    bootstrap.install(common, resources)
    assert sorted(p.name for p in (common / 'plugins').iterdir()) == ['singleplayer_bridge.mcdr']
    assert (common / 'runtime/backup-adapters/singleplayer_prime_backup.mcdr').exists()
    assert (common / 'runtime/backup-adapters/singleplayer_chunk_backup.mcdr').exists()
