"""MCDR-managed stdin/stdout proxy. No Minecraft or MCDR dependency required."""
from singleplayer_bridge.i18n import tr
from singleplayer_bridge.config_file import read as read_bridge_config
import argparse
import os
import json
import socket
import sys
import threading
import time
import uuid
from pathlib import Path

from .protocol import (
    CHECKED_PREFIX, COMPLETION_PREFIX, TREE_PREFIX, SAVE_AND_QUIT, DISCONNECT_COMMAND, MAX_COMMAND, PROTOCOL, STDOUT_PREFIX, ProtocolError,
    SocketFrames, encode_frame, string_field, validate_event,
)


class BridgeProxy:
    def __init__(self, config_path, stdin=None, stdout=None, stderr=None):
        self.config_path = Path(config_path)
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.output_lock = threading.Lock()
        self.connection = None
        self.session = None
        self.pending = {}
        self.paused = False

    def emit(self, event):
        validate_event(event)
        line = STDOUT_PREFIX + encode_frame(event).decode('utf8')
        with self.output_lock:
            self.stdout.write(line)
            self.stdout.flush()

    def error(self, text):
        self.emit({'type': 'error', 'text': text})

    def close(self):
        self.stop.set()
        with self.lock:
            if self.connection:
                try:
                    self.connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def read_config(self):
        if self.config_path.stat().st_size > 8192:
            raise ProtocolError('configuration exceeds limit')
        config = read_bridge_config(self.config_path)
        if not isinstance(config, dict):
            raise ProtocolError('invalid bridge configuration')
        port = config.get('port', 25585)
        token = config.get('token')
        if type(port) is not int or not 1 <= port <= 65535:
            raise ProtocolError('invalid bridge port')
        if not isinstance(token, str) or not 32 <= len(token) <= 256:
            raise ProtocolError('invalid bridge token')
        if config.get('enabled') is not True:
            raise ProtocolError('game bridge is disabled')
        return port, token

    def send_command(self, command, request_id=None):
        def reject(text):
            # Worker commands need a definite negative acknowledgment even when the
            # proxy rejects before writing to the game (e.g. a pause event just arrived).
            if request_id is not None and self.session:
                self.emit(dict(type='command_result', id=request_id, session=self.session, success=False, text=text))
            else:
                self.error(text)
        # This lock attaches the session at read time, rather than at reconnect time.
        with self.lock:
            if not self.connection or not self.session:
                reject(tr('error.command_discarded_no_world_connected'))
                return
            if self.paused and command != SAVE_AND_QUIT:
                reject(tr('error.command_discarded_world_paused_resume_the_game_first'))
                return
            if len(command) > MAX_COMMAND or '\x00' in command:
                reject(tr('error.command_discarded_invalid_or_oversized_command'))
                return
            if len(self.pending) >= 64:
                reject(tr('error.command_discarded_too_many_pending_requests'))
                return
            request_id = request_id or uuid.uuid4().hex
            if request_id in self.pending:
                self.error(tr('error.command_discarded_duplicate_request_id'))
                return
            deadline = time.time() + 10
            frame = {
                'type': 'command', 'id': request_id, 'session': self.session,
                'command': command, 'deadline': int(deadline * 1000),
            }
            self.pending[request_id] = deadline
            try:
                self.connection.sendall(encode_frame(frame))
            except ProtocolError:
                self.pending.pop(request_id, None)
                reject(tr('error.command_discarded_encoded_request_exceeds_frame_limit'))
            except OSError:
                self.pending.pop(request_id, None)
                self.error(tr('error.connection_lost_while_sending_command_command_will_not_be_replayed'))
                self.close()

    def stdin_loop(self):
        while not self.stop.is_set():
            line = self.stdin.readline(MAX_COMMAND + 2)
            if not line:
                self.close()
                return
            if len(line) > MAX_COMMAND + 1 or not line.endswith('\n'):
                # Drain the remainder so it cannot turn into a second command.
                while line and not line.endswith('\n'):
                    line = self.stdin.readline(MAX_COMMAND + 2)
                self.error(tr('error.command_discarded_invalid_or_oversized_input_line'))
                continue
            command = line.rstrip('\r\n')
            if command == DISCONNECT_COMMAND:
                self.close()
                return
            if command.startswith(TREE_PREFIX):
                try:
                    result = json.loads(command[len(TREE_PREFIX):])
                    string_field(result, 'revision', 128)
                    string_field(result, 'payload', 6000)
                    if not (type(result.get('total')) is int and 1 <= result['total'] <= 256
                            and type(result.get('index')) is int and 0 <= result['index'] < result['total']):
                        raise ProtocolError('invalid command tree chunk')
                    with self.lock:
                        if self.connection and result.get('session') == self.session:
                            self.connection.sendall(encode_frame(dict(result, type='command_tree')))
                except (ValueError, TypeError, OSError):
                    pass
                continue
            if command.startswith(COMPLETION_PREFIX):
                try:
                    result = json.loads(command[len(COMPLETION_PREFIX):])
                    string_field(result, 'id', 128)
                    if not isinstance(result.get('suggestions'), list) or len(result['suggestions']) > 100:
                        raise ProtocolError('invalid completion result')
                    with self.lock:
                        if self.connection and result.get('session') == self.session:
                            self.connection.sendall(encode_frame(dict(result, type='suggest_result')))
                except (ValueError, TypeError, OSError):
                    pass
                continue
            if command.startswith(CHECKED_PREFIX):
                try:
                    checked = json.loads(command[len(CHECKED_PREFIX):])
                    request_id = string_field(checked, 'id', 128)
                    command = string_field(checked, 'command', MAX_COMMAND)
                    if not request_id or '\r' in command or '\n' in command:
                        raise ProtocolError('invalid checked command')
                    self.send_command(command, request_id)
                except (ValueError, TypeError, AttributeError):
                    self.error(tr('error.command_discarded_invalid_checked_request'))
                continue
            if command.strip():
                self.send_command(command)

    def receive_event(self, event):
        validate_event(event)
        if event.get('session') != self.session:
            raise ProtocolError('event belongs to another world session')
        kind = event['type']
        if kind in {'ready', 'world_info'}:
            raise ProtocolError('unexpected second handshake')
        if kind == 'command_result':
            with self.lock:
                if self.pending.pop(event['id'], None) is None:
                    return
        if kind in {'pause', 'heartbeat'}:
            with self.lock:
                self.paused = event['paused']
        self.emit(event)
        now = time.time()
        with self.lock:
            expired = [key for key, deadline in self.pending.items() if deadline < now]
            for key in expired:
                del self.pending[key]
        if expired:
            self.error(tr('proxy.timeout', len(expired)))
        if kind == 'world_stopped':
            self.stop.set()

    def run(self):
        reader = threading.Thread(target=self.stdin_loop, name='bridge-stdin', daemon=True)
        reader.start()
        self.stderr.write('Waiting for the singleplayer bridge (loopback only)...\n')
        self.stderr.flush()
        connection = None
        try:
            while not self.stop.is_set():
                try:
                    port, token = self.read_config()
                except FileNotFoundError:
                    self.stop.wait(0.5)
                    continue
                try:
                    connection = socket.create_connection(('127.0.0.1', port), timeout=2)
                    break
                except OSError:
                    self.stop.wait(0.5)
            if connection is None:
                return 0
            with connection:
                frames = SocketFrames(connection)
                connection.sendall(encode_frame({'type': 'hello', 'protocol': PROTOCOL, 'token': token}))
                ready = validate_event(frames.read(self.stop, timeout=5))
                if ready['type'] != 'ready':
                    raise ProtocolError('bridge did not accept authentication')
                if os.environ.get('MCDR_BRIDGE_SESSION') and ready['session'] != os.environ['MCDR_BRIDGE_SESSION']:
                    raise ProtocolError('world session does not belong to this profile')
                if os.environ.get('MCDR_BRIDGE_WORLD_PATH') and Path(ready['world_path']).resolve() != Path(os.environ['MCDR_BRIDGE_WORLD_PATH']).resolve():
                    raise ProtocolError('world path does not belong to this profile')
                # Install snapshot before accepting stdin commands, and before startup listeners.
                with self.lock:
                    self.emit(dict(ready, type='world_info'))
                    self.emit(ready)
                    for player in ready['players']:
                        self.emit({'type': 'player_joined', 'session': ready['session'], 'player': player})
                    self.session = string_field(ready, 'session', 128)
                    self.paused = ready['paused']
                    self.connection = connection
                while not self.stop.is_set():
                    self.receive_event(frames.read(self.stop))
            return 0
        except (OSError, EOFError, ValueError, TypeError) as exc:
            if self.stop.is_set():
                return 0
            # Errors are deliberately generic: configuration and network data can contain secrets.
            self.error(tr('proxy.session_ended', type(exc).__name__))
            return 1
        finally:
            with self.lock:
                self.connection = None
                self.session = None
                self.pending.clear()
            self.stop.set()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='Game mcdr-singleplayer/mcdr-singleplayer-config.yml')
    parser.add_argument('--config-env', action='store_true')
    args = parser.parse_args()
    if args.config_env:
        args.config = Path(os.environ['MCDR_BRIDGE_CONFIG'])
    if args.config is None:
        parser.error('--config or --config-env is required')
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf8')
    try:
        return BridgeProxy(args.config).run()
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
