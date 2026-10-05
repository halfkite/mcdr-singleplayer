"""Versioned, bounded newline-delimited JSON protocol shared with the game bridge."""
import json
import re
import socket
import time

PROTOCOL = 1
MAX_FRAME = 65536
MAX_COMMAND = 16384
STDOUT_PREFIX = 'SPB:'
DISCONNECT_COMMAND = '__bridge_disconnect__'
CHECKED_PREFIX = '__bridge_request__'
COMPLETION_PREFIX = '__bridge_complete__'
TREE_PREFIX = '__bridge_commands__'
SAVE_AND_QUIT = '__bridge_save_and_quit__'
# Carpet fake players and offline profiles may have one- or two-character names.
PLAYER_PATTERN = re.compile(r'[A-Za-z0-9_]{1,16}')
EVENT_TYPES = frozenset({
    'ready', 'world_info', 'chat', 'player_joined', 'player_left', 'log',
    'command_result', 'pause', 'heartbeat', 'world_stopped', 'error', 'suggest_request',
})


class ProtocolError(ValueError):
    pass


def string_field(record, key, limit=32768):
    value = record.get(key)
    if not isinstance(value, str) or len(value) > limit or '\x00' in value:
        raise ProtocolError(f'invalid {key}')
    return value


def decode_frame(raw):
    if len(raw) > MAX_FRAME:
        raise ProtocolError('frame exceeds limit')
    try:
        record = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ProtocolError('invalid JSON frame') from exc
    if not isinstance(record, dict):
        raise ProtocolError('frame must be an object')
    return record


def encode_frame(record):
    data = json.dumps(record, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')
    if len(data) + 1 > MAX_FRAME:
        raise ProtocolError('frame exceeds limit')
    return data + b'\n'


def validate_event(record):
    kind = record.get('type')
    if not isinstance(kind, str) or kind not in EVENT_TYPES:
        raise ProtocolError('unsupported event type')
    if kind != 'error' or 'session' in record:
        if not string_field(record, 'session', 128):
            raise ProtocolError('empty session')
    if kind in {'ready', 'world_info'}:
        if type(record.get('protocol')) is not int or record['protocol'] != PROTOCOL:
            raise ProtocolError('unsupported protocol version')
        string_field(record, 'game_version', 128)
        string_field(record, 'world_path', 4096)
        if 'progress_path' in record:
            string_field(record, 'progress_path', 4096)
        if 'host_player' in record and not PLAYER_PATTERN.fullmatch(string_field(record, 'host_player', 16)):
            raise ProtocolError('invalid host player')
        if 'language' in record and not re.fullmatch(r'[a-zA-Z0-9_-]{1,32}', string_field(record, 'language', 32)):
            raise ProtocolError('invalid client language')
        players = record.get('players')
        if not isinstance(players, list) or len(players) > 1024:
            raise ProtocolError('invalid players snapshot')
        for player in players:
            if not isinstance(player, str) or not PLAYER_PATTERN.fullmatch(player):
                raise ProtocolError('invalid player name')
        if len(set(players)) != len(players):
            raise ProtocolError('duplicate players snapshot')
    if kind in {'chat', 'player_joined', 'player_left', 'suggest_request'}:
        if not PLAYER_PATTERN.fullmatch(string_field(record, 'player', 16)):
            raise ProtocolError('invalid player name')
    if kind in {'chat', 'log', 'command_result', 'error', 'suggest_request'}:
        string_field(record, 'text')
    if kind == 'command_result':
        string_field(record, 'id', 128)
        if type(record.get('success')) is not bool:
            raise ProtocolError('invalid result flag')
    if kind == 'suggest_request':
        string_field(record, 'id', 128)
        if len(record['text']) > 2048:
            raise ProtocolError('completion request exceeds limit')
    if kind in {'pause', 'heartbeat', 'ready', 'world_info'}:
        if type(record.get('paused')) is not bool:
            raise ProtocolError('invalid pause flag')
    return record


def read_frame(stream):
    raw = stream.readline(MAX_FRAME + 1)
    if not raw:
        raise EOFError('bridge disconnected')
    if not raw.endswith(b'\n'):
        raise ProtocolError('unterminated or oversized frame')
    return decode_frame(raw)


class SocketFrames:
    """Cancellable socket framing without the timeout pitfalls of socket.makefile()."""
    def __init__(self, connection):
        self.connection = connection
        self.connection.settimeout(0.5)
        self.buffer = bytearray()

    def read(self, stop_event, timeout=15):
        deadline = time.monotonic() + timeout
        while not stop_event.is_set():
            end = self.buffer.find(b'\n')
            if end >= 0:
                if end + 1 > MAX_FRAME:
                    raise ProtocolError('frame exceeds limit')
                raw = bytes(self.buffer[:end])
                del self.buffer[:end + 1]
                return decode_frame(raw)
            if len(self.buffer) >= MAX_FRAME:
                raise ProtocolError('frame exceeds limit')
            if time.monotonic() > deadline:
                raise TimeoutError('bridge heartbeat timed out')
            try:
                data = self.connection.recv(8192)
            except socket.timeout:
                continue
            if not data:
                raise EOFError('bridge disconnected')
            self.buffer.extend(data)
        raise EOFError('bridge cancelled')
