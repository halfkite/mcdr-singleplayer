import io
import json
import socket
import threading
import time

import pytest

from singleplayer_bridge.proxy import BridgeProxy
from singleplayer_bridge.config_file import write as write_bridge_config
from singleplayer_bridge.protocol import ProtocolError, encode_frame, read_frame


class Output(io.StringIO):
    def __init__(self):
        super().__init__()
        self.lock = threading.Lock()

    def write(self, text):
        with self.lock:
            return super().write(text)

    def records(self):
        with self.lock:
            return [json.loads(line[4:]) for line in self.getvalue().splitlines()]


def test_automatic_connection_uses_its_own_port_without_rewriting_shared_config(tmp_path, monkeypatch):
    path = tmp_path / 'config.yml'
    write_bridge_config(path, dict(enabled=True, token='a' * 64, port=25585))
    before = path.read_bytes()
    proxy = BridgeProxy(path)
    monkeypatch.setenv('MCDR_BRIDGE_PORT', '25591')
    assert proxy.read_config() == (25591, 'a' * 64)
    assert path.read_bytes() == before
    monkeypatch.setenv('MCDR_BRIDGE_PORT', '0')
    with pytest.raises(ProtocolError):
        proxy.read_config()
    monkeypatch.setenv('MCDR_BRIDGE_PORT', 'not-a-port')
    with pytest.raises(ProtocolError):
        proxy.read_config()


def test_no_command_queue_without_world_and_no_command_when_paused(tmp_path):
    output = Output()
    proxy = BridgeProxy(tmp_path / 'config.json', stdout=output)
    proxy.send_command('say old-world')
    assert not proxy.pending
    assert 'no world' in output.records()[0]['text']
    proxy.connection = object()
    proxy.session = 'world'
    proxy.paused = True
    proxy.send_command('say paused')
    assert not proxy.pending
    assert 'paused' in output.records()[-1]['text']


def test_cross_session_event_rejected(tmp_path):
    proxy = BridgeProxy(tmp_path / 'config.json', stdout=Output())
    proxy.session = 'world-2'
    with pytest.raises(ProtocolError):
        proxy.receive_event(dict(type='chat', session='world-1', player='Steve', text='!!help'))


def test_checked_command_pause_rejection_acknowledges_without_network_or_timeout(tmp_path):
    output = Output()
    proxy = BridgeProxy(tmp_path / 'config.json', stdout=output)
    proxy.connection = object()  # Any attempted socket send would fail this test.
    proxy.session = 'current-world'
    proxy.paused = True
    proxy.send_command('save-off', 'checked-id')
    assert not proxy.pending
    result = output.records()[0]
    assert result['type'] == 'command_result' and result['id'] == 'checked-id' and result['session'] == 'current-world'
    assert result['success'] is False and 'world paused' in result['text']


@pytest.mark.parametrize('binding', ['MCDR_BRIDGE_SESSION', 'MCDR_BRIDGE_WORLD_PATH'])
def test_profile_lease_rejects_other_world_before_startup(tmp_path, monkeypatch, binding):
    from singleplayer_bridge.installation_progress import InstallationProgress
    monkeypatch.setenv('MCDR_BRIDGE_COMMON', str(tmp_path))
    monkeypatch.setenv('MCDR_BRIDGE_CLIENT_ID', 'failing-client')
    progress = InstallationProgress(tmp_path, 'failing-client')
    progress.report('starting')
    monkeypatch.setenv(binding, 'old-session' if binding.endswith('SESSION') else str(tmp_path / 'old-world'))
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(5)
    config = tmp_path / 'mcdr-singleplayer-config.yml'
    write_bridge_config(config, dict(enabled=True, port=listener.getsockname()[1], token='a' * 64))
    reader, writer = socket.socketpair()
    output = Output()
    proxy = BridgeProxy(config, stdin=reader.makefile('r'), stdout=output, stderr=io.StringIO())
    results = []
    worker = threading.Thread(target=lambda: results.append(proxy.run()), daemon=True)
    worker.start()
    try:
        connection, _ = listener.accept()
        with connection, connection.makefile('rb') as stream:
            read_frame(stream)
            connection.sendall(encode_frame(dict(type='ready', session='new-session', protocol=1, game_version='26.3',
                world_path=str(tmp_path / 'new-world'), players=['Steve'], paused=False)))
        worker.join(5)
        assert results == [1]
        assert [event['type'] for event in output.records()] == ['error']
        assert json.loads(progress.path.read_text())['stage'] == 'failed'
    finally:
        proxy.close()
        writer.close()
        reader.close()
        listener.close()


@pytest.mark.parametrize('players', [['Steve'], ['Steve', '1', 'ab']])
def test_real_socket_handshake_command_and_world_close(tmp_path, players):
    token = 'a' * 64
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    listener.settimeout(5)
    config = tmp_path / 'mcdr-singleplayer-config.yml'
    write_bridge_config(config, dict(enabled=True, port=listener.getsockname()[1], token=token))
    stdin_reader, stdin_writer = socket.socketpair()
    output = Output()
    proxy = BridgeProxy(config, stdin=stdin_reader.makefile('r', encoding='utf8'), stdout=output, stderr=io.StringIO())
    results = []
    worker = threading.Thread(target=lambda: results.append(proxy.run()), daemon=True)
    worker.start()
    try:
        connection, _ = listener.accept()
        with connection, connection.makefile('rb') as stream:
            connection.settimeout(5)
            assert read_frame(stream) == dict(type='hello', protocol=1, token=token)
            ready = dict(type='ready', session='world', protocol=1, game_version='26.3',
                         world_path='D:/世界', players=players, paused=False)
            connection.sendall(encode_frame(ready))
            deadline = time.monotonic() + 5
            while proxy.session is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert [r['type'] for r in output.records()] == ['world_info', 'ready'] + ['player_joined'] * len(players)
            assert [r['player'] for r in output.records() if r['type'] == 'player_joined'] == players
            stdin_writer.sendall('say 世界\n'.encode())
            request = read_frame(stream)
            assert request['type'] == 'command' and request['session'] == 'world'
            assert request['command'] == 'say 世界'
            connection.sendall(encode_frame(dict(type='command_result', session='world', id=request['id'],
                                                success=True, text='世界')))
            connection.sendall(encode_frame(dict(type='player_joined', session='world', player='2')))
            connection.sendall(encode_frame(dict(type='player_left', session='world', player='2')))
            connection.sendall(encode_frame(dict(type='world_stopped', session='world')))
        worker.join(5)
        assert results == [0]
        assert output.records()[-1]['type'] == 'world_stopped'
        assert any(r['type'] == 'player_left' and r['player'] == '2' for r in output.records())
        assert not proxy.pending
    finally:
        proxy.close()
        listener.close()
        stdin_writer.close()
        stdin_reader.close()
