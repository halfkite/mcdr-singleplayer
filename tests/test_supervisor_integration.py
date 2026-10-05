"""Two saves, real MCDR loader and stock PB, one shared config/plugins/permissions."""
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from singleplayer_bridge.bootstrap import configure_common, pack
from singleplayer_bridge.profiles import write_json, read_json
from singleplayer_bridge.protocol import encode_frame, read_frame
from singleplayer_bridge.supervisor import Controller

ROOT = Path(__file__).resolve().parents[1]


def wait(predicate, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError('Timeout')


def test_controller_waits_switches_profiles_and_preserves_shared_files(tmp_path):
    common = tmp_path / 'common'
    common.mkdir()
    (common / '.').mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'mcdreforged', 'init'], cwd=common / '.', check=True, capture_output=True)
    configure_common(common, Path(sys.executable), ROOT / 'python')
    # Player joins register previously unknown names in MCDR's shared permission file.
    from ruamel.yaml import YAML
    yaml = YAML()
    permission = yaml.load((common / 'permission.yml').read_text(encoding='utf8'))
    permission['user'] = ['Steve']
    with (common / 'permission.yml').open('w', encoding='utf8') as output:
        yaml.dump(permission, output)
    bridge_source = tmp_path / 'bridge-plugin'
    shutil.copytree(ROOT / 'python/singleplayer_bridge', bridge_source / 'singleplayer_bridge', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT / 'python/mcdreforged.plugin.json', bridge_source / 'mcdreforged.plugin.json')
    pack(bridge_source, common / 'plugins/singleplayer_bridge.mcdr')
    pack(ROOT / 'prime-backup-adapter', common / 'plugins/singleplayer_prime_backup.mcdr')
    shutil.copy2(ROOT / '.reference/PrimeBackup-v1.13.1.pyz', common / 'plugins/PrimeBackup.pyz')
    (common / 'plugins/profile_probe.py').write_text('''from pathlib import Path
import json
PLUGIN_METADATA = {'id': 'profile_probe', 'version': '1.0.0'}
def on_load(server, previous):
    config = server.load_config_simple(default_config={'setting': 'initial'})
    path = Path(server.get_data_folder()) / 'state.json'
    state = json.loads(path.read_text()) if path.exists() else {'loads': 0}
    state['loads'] += 1
    path.write_text(json.dumps(state))
    server.logger.info('PROFILE_PROBE_READY ' + str(state['loads']))
''', encoding='utf8')
    shared_before = {name: hashlib.sha256((common / '.' / name).read_bytes()).hexdigest() for name in ('config.yml', 'permission.yml')}
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(20)
    game_config = tmp_path / 'bridge.json'
    write_json(game_config, dict(enabled=True, token='a' * 64, port=listener.getsockname()[1]))
    controller = Controller(common, game_config, tmp_path / 'session.json', 'test', sys.executable)
    connections = []
    guest = None
    try:
        controller.tick({})
        assert controller.process is None
        for index, name in enumerate(['世界 A', '世界 B', '世界 A']):
            world = tmp_path / 'saves' / name
            world.mkdir(parents=True, exist_ok=True)
            (world / 'level.dat').write_bytes(b'test')
            session = f'world-{index}'
            state = dict(world_path=str(world), session=session)
            controller.tick(state)
            connection, _ = listener.accept()
            connections.append(connection)
            stream = connection.makefile('rb')
            connection.settimeout(20)
            assert read_frame(stream)['token'] == 'a' * 64
            connection.sendall(encode_frame(dict(type='ready', protocol=1, session=session,
                world_path=str(world), game_version='26.3', players=['Steve'], paused=False)))
            profile = common / 'plugindata' / name
            wait(lambda: (profile / 'config/profile_probe/state.json').exists())
            expected = 2 if index == 2 else 1
            wait(lambda: read_json(profile / 'config/profile_probe/state.json')['loads'] == expected)
            log = common / 'log' / profile.name / 'controller-child.log'
            wait(lambda: 'singleplayer_prime_backup@0.5.1 loaded' in log.read_text(encoding='utf8'))
            assert (common / 'log' / profile.name / 'MCDR.log').is_file()
            assert 'Fail to load' not in log.read_text(encoding='utf8')
            if index == 0:
                # Starting another client while the real MCDR host is live must wait
                # without rewriting its configuration or terminating the host child.
                attempted = subprocess.run([sys.executable, str(ROOT / 'python/bridge_bootstrap.py'),
                    '--common', str(common), '--resources', str(tmp_path / 'not-needed-while-locked'),
                    '--client-id', 'guest'], capture_output=True, timeout=20)
                assert attempted.returncode == 2, attempted.stderr.decode('utf8', errors='replace')
                assert read_json(common / 'runtime/clients/guest/install-progress.json')['stage'] == 'waiting_instance'
                guest_state = tmp_path / 'guest.json'
                write_json(guest_state, dict(client_id='guest', world_path=None, session=None))
                guest = subprocess.Popen([sys.executable, str(ROOT / 'python/bridge_supervisor.py'),
                    '--common', str(common), '--config', str(game_config), '--state', str(guest_state),
                    '--client-id', 'guest', '--parent-pid', str(os.getpid())],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(0.6)
                assert guest.poll() is None
                assert controller.process.poll() is None and not controller.retiring
                for shared, digest in shared_before.items():
                    assert hashlib.sha256((common / shared).read_bytes()).hexdigest() == digest
            connection.sendall(encode_frame(dict(type='world_stopped', session=session)))
            connection.close()
            stream.close()
            def stopped():
                controller.tick({})
                return controller.process is None
            wait(stopped)
        assert read_json(common / 'plugindata/世界 B/config/profile_probe/state.json')['loads'] == 1
        for name, digest in shared_before.items():
            assert hashlib.sha256((common / '.' / name).read_bytes()).hexdigest() == digest
    finally:
        if guest:
            guest.terminate()
            guest.wait(10)
        for connection in connections:
            connection.close()
        listener.close()
        if controller.process and controller.process.poll() is None:
            controller.retire()
            try:
                controller.process.wait(15)
            except subprocess.TimeoutExpired:
                import psutil
                for process in psutil.Process(controller.process.pid).children(recursive=True):
                    process.kill()
                controller.process.kill()
                controller.process.wait()
        controller.close()
