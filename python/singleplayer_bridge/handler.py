import dataclasses
import time

from mcdreforged.api.types import Info, InfoSource, InfoActionFlag
from mcdreforged.handler.impl import VanillaHandler

from .protocol import DISCONNECT_COMMAND, STDOUT_PREFIX, ProtocolError, decode_frame, validate_event


@dataclasses.dataclass
class BridgeInfo(Info):
    bridge_event: dict = dataclasses.field(default_factory=dict)


class SingleplayerHandler(VanillaHandler):
    def get_name(self):
        return 'singleplayer_bridge_handler'

    def get_stop_command(self):
        return DISCONNECT_COMMAND

    def parse_server_stdout(self, text):
        info = BridgeInfo(InfoSource.SERVER, text)
        info.hour, info.min, info.sec = time.localtime()[3:6]
        info.logging_level = 'INFO'
        # Malformed diagnostics never fall back to parsing player-shaped log text.
        if not text.startswith(STDOUT_PREFIX):
            info.content = '[Bridge] ' + text
            return info
        try:
            event = validate_event(decode_frame(text[len(STDOUT_PREFIX):].encode('utf8')))
        except ProtocolError:
            info.content = '[Bridge] Invalid event discarded'
            info.logging_level = 'WARNING'
            return info
        info.bridge_event = event
        kind = event['type']
        if kind == 'chat':
            info.player = event['player']
            info.content = event['text']
        elif kind == 'player_joined':
            info.content = '{} joined the singleplayer world'.format(event['player'])
        elif kind == 'player_left':
            info.content = '{} left the singleplayer world'.format(event['player'])
        elif kind == 'world_info':
            info.content = 'Minecraft {} / {}'.format(event['game_version'], event['world_path'])
        elif kind == 'ready':
            info.content = '[Bridge] Singleplayer world ready'
        elif kind == 'world_stopped':
            info.content = '[Bridge] World closed; control session ended'
        elif kind in {'pause', 'heartbeat'}:
            info.content = '[Bridge] World {}'.format('paused' if event['paused'] else 'active')
            info.action_flag &= ~InfoActionFlag.echo_to_console
        elif kind == 'suggest_request':
            info.content = '[Bridge] Command completion requested'
            info.action_flag &= ~InfoActionFlag.echo_to_console
        else:
            info.content = event['text']
            if kind == 'error' or kind == 'command_result' and not event['success']:
                info.logging_level = 'WARNING'
        display = f'<{info.player}> {info.content}' if info.player else info.content
        info.raw_content = '[{:02}:{:02}:{:02}] [Bridge/{}]: {}'.format(
            info.hour, info.min, info.sec, info.logging_level, display)
        return info

    @staticmethod
    def _event(info):
        return info.bridge_event if isinstance(info, BridgeInfo) else {}

    def parse_player_joined(self, info):
        event = self._event(info)
        return event.get('player') if event.get('type') == 'player_joined' else None

    def parse_player_left(self, info):
        event = self._event(info)
        return event.get('player') if event.get('type') == 'player_left' else None

    def parse_server_version(self, info):
        event = self._event(info)
        return event.get('game_version') if event.get('type') == 'world_info' else None

    def parse_server_address(self, info):
        return None

    def test_server_startup_done(self, info):
        return self._event(info).get('type') == 'ready'

    def test_rcon_started(self, info):
        return False

    def test_server_stopping(self, info):
        return self._event(info).get('type') == 'world_stopped'
