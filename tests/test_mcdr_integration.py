"""Run the real MCDR plugin loader/reactors against a simulated game socket."""
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

from ruamel.yaml import YAML

from singleplayer_bridge.protocol import encode_frame, read_frame

ROOT = Path(__file__).resolve().parents[1]


def pack_plugin(target):
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for file in (ROOT / 'python').rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts and file.suffix != '.pyc' and not file.name.startswith('bridge_'):
                archive.write(file, file.relative_to(ROOT / 'python').as_posix())


def wait_until(predicate, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.025)
    raise AssertionError('condition did not become true')


def test_real_mcdr_chat_callbacks_version_permission_and_detach(tmp_path):
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(12)
    token = 'a' * 64
    config_path = tmp_path / 'game-bridge.json'
    config_path.write_text(json.dumps(dict(enabled=True, port=listener.getsockname()[1], token=token)))
    subprocess.run([sys.executable, '-m', 'mcdreforged', 'init'], cwd=tmp_path,
                   capture_output=True, check=True)
    pack_plugin(tmp_path / 'plugins' / 'singleplayer_bridge.mcdr')
    trace = tmp_path / 'trace.jsonl'
    probe = '''import json
from pathlib import Path
from mcdreforged.api.command import Literal
PLUGIN_METADATA = {'id': 'integration_probe', 'version': '1.0.0'}
def record(data):
    with Path('trace.jsonl').open('a', encoding='utf8') as output:
        output.write(json.dumps(data, ensure_ascii=False) + '\\n')
def on_load(server, prev):
    server.register_command(Literal('!!probe').runs(lambda source: source.reply('世界连接成功')).then(Literal('nested').then(Literal('leaf').runs(lambda source: source.reply('NESTED_OK')))))
def on_server_startup(server):
    record({'startup': server.get_server_information().version})
def on_player_joined(server, player, info):
    record({'join': player})
def on_user_info(server, info):
    if info.is_player:
        record({'chat': info.content, 'player': info.player})
def on_server_stop(server, code):
    record({'stop': code})
'''
    (tmp_path / 'plugins' / 'integration_probe.py').write_text(probe, encoding='utf8')
    yaml = YAML()
    config = yaml.load((tmp_path / 'config.yml').read_text(encoding='utf8'))
    config['language'] = 'en_us'
    config['advanced_console'] = False
    config['working_directory'] = str(tmp_path)
    config['start_command'] = [sys.executable, str(ROOT / 'python' / 'bridge_proxy.py'), '--config', str(config_path)]
    config['encoding'] = config['decoding'] = 'utf8'
    with (tmp_path / 'config.yml').open('w', encoding='utf8') as output:
        yaml.dump(config, output)
    log_path = tmp_path / 'integration.log'
    environment = dict(os.environ, PYTHONUTF8='1')
    with log_path.open('w', encoding='utf8') as log:
        process = subprocess.Popen([sys.executable, '-m', 'mcdreforged', 'start'], cwd=tmp_path,
                                   stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf8', env=environment)
        try:
            connection, _ = listener.accept()
            with connection, connection.makefile('rb') as stream:
                tree_chunks = {}
                def receive():
                    while True:
                        record = read_frame(stream)
                        if record['type'] != 'command_tree':
                            return record
                        tree_chunks.setdefault(record['revision'], {})[record['index']] = record['payload']
                connection.settimeout(12)
                assert read_frame(stream)['token'] == token
                ready = dict(type='ready', session='world-1', protocol=1, game_version='26.3',
                             world_path=str(tmp_path / '世界'), players=['Steve', 'Alex'], paused=False,
                             host_player='Alex', language='zh_cn')
                connection.sendall(encode_frame(ready))
                wait_until(lambda: trace.exists() and 'startup' in trace.read_text(encoding='utf8'))
                wait_until(lambda: 'MCDR command tree synchronized' in log_path.read_text(encoding='utf8'))
                permissions = yaml.load((tmp_path / 'permission.yml').read_text(encoding='utf8'))
                assert 'Alex' in permissions['owner'] and 'Steve' not in permissions['owner']
                entries = [json.loads(line) for line in trace.read_text(encoding='utf8').splitlines()]
                assert {'startup': '26.3'} in entries
                wait_until(lambda: '"join": "Steve"' in trace.read_text(encoding='utf8'))
                connection.sendall(encode_frame(dict(type='chat', session='world-1', player='Steve', text='!!probe')))
                request = receive()
                assert request['session'] == 'world-1'
                assert 'tellraw Steve' in request['command'] and '世界连接成功' in request['command']
                connection.sendall(encode_frame(dict(type='command_result', session='world-1', id=request['id'],
                                                    success=True, text='<Steve> !!probe')))
                connection.sendall(encode_frame(dict(type='chat', session='world-1', player='Steve', text='!!spbridge')))
                denied = receive()
                assert 'tellraw Steve' in denied['command']
                assert '世界连接成功' not in denied['command']  # the ordinary user cannot access admin status
                wait_until(lambda: '"chat": "!!spbridge"' in trace.read_text(encoding='utf8'))
                entries = [json.loads(line) for line in trace.read_text(encoding='utf8').splitlines()]
                assert sum(item.get('chat') == '!!probe' for item in entries) == 1
                assert sum(item.get('join') == 'Steve' for item in entries) == 1
                process.stdin.write('!!MCDR permission set Steve owner\n!!MCDR plugin reload singleplayer_bridge\n')
                process.stdin.flush()
                wait_until(lambda: 'Plugin singleplayer_bridge@0.4.2 reloaded' in log_path.read_text(encoding='utf8'))
                connection.sendall(encode_frame(dict(type='chat', session='world-1', player='Steve', text='!!spbridge status')))
                status = receive()
                assert '26.3' in status['command'] and '世界' in status['command']
                connection.sendall(encode_frame(dict(type='suggest_request', session='world-1', id='complete-1',
                    player='Steve', text='!!MCDR plugin reload singleplayer_b')))
                completion = receive()
                assert completion['type'] == 'suggest_result'
                assert completion['id'] == 'complete-1'
                assert '!!MCDR plugin reload singleplayer_bridge' in completion['suggestions']
                time.sleep(0.7)
                connection.sendall(encode_frame(dict(type='chat', session='world-1', player='Steve', text='!!probe nested leaf')))
                nested = receive()
                assert 'NESTED_OK' in nested['command']
                trees = [json.loads(''.join(parts[i] for i in sorted(parts))) for parts in tree_chunks.values()]
                assert any(root['name'] == '!!probe' and tree['nodes'][tree['nodes'][root['children'][0]]['children'][0]]['name'] == 'leaf'
                    for tree in trees for root in tree['nodes']), trees
                process.stdin.write('!!MCDR server stop\n')
                process.stdin.flush()
                assert not stream.readline()  # stop detaches the proxy, no game command is sent
                wait_until(lambda: '"stop"' in trace.read_text(encoding='utf8'))
                assert process.poll() is None  # MCDR stays available for the next world
                process.stdin.write('!!MCDR server exit\n')
                process.stdin.flush()
                process.wait(12)
                assert process.returncode == 0
        except Exception as exc:
            raise AssertionError(log_path.read_text(encoding='utf8')) from exc
        finally:
            listener.close()
            if process.poll() is None:
                process.terminate()
                process.wait(5)
