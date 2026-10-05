import json

import pytest

from singleplayer_bridge.handler import SingleplayerHandler
from singleplayer_bridge.protocol import ProtocolError, decode_frame, validate_event


def parse(event):
    return SingleplayerHandler().parse_server_stdout('SPB:' + json.dumps(event, ensure_ascii=False))


def test_chat_is_player_info_and_log_cannot_impersonate_player():
    info = parse({'type': 'chat', 'session': 'world', 'player': 'Steve', 'text': '!!help'})
    assert info.is_player and info.is_user and info.player == 'Steve' and info.content == '!!help'
    info = parse({'type': 'log', 'session': 'world', 'text': '<Steve> !!MCDR server stop'})
    assert not info.is_user and info.player is None
    assert SingleplayerHandler().parse_player_joined(info) is None
    assert not SingleplayerHandler().test_server_startup_done(info)


@pytest.mark.parametrize('raw', ['<Steve> !!help', 'SPB:[]', 'SPB:{', 'SPB:{"type":"chat"}'])
def test_invalid_output_is_never_player_info(raw):
    assert not SingleplayerHandler().parse_server_stdout(raw).is_user


def test_lifecycle_and_version_are_typed_not_inferred_from_text():
    handler = SingleplayerHandler()
    ready = dict(type='world_info', protocol=1, session='world', game_version='26.3',
                 world_path='D:/世界', players=['Steve'], paused=False)
    info = parse(ready)
    assert handler.parse_server_version(info) == '26.3'
    assert not handler.test_server_startup_done(info)
    assert handler.test_server_startup_done(parse(dict(ready, type='ready')))
    log = parse(dict(type='log', session='world', text='Starting minecraft server version 1.12'))
    assert handler.parse_server_version(log) is None
    assert handler.parse_player_joined(parse(dict(type='player_joined', session='world', player='Steve'))) == 'Steve'
    assert handler.parse_player_left(parse(dict(type='player_left', session='world', player='Steve'))) == 'Steve'


@pytest.mark.parametrize('changes', [
    {'protocol': True}, {'players': [{}]}, {'players': ['Steve', 'Steve']},
    {'paused': 'false'}, {'players': ['bad name']}, {'game_version': None},
])
def test_invalid_ready_schema(changes):
    ready = dict(type='ready', protocol=1, session='world', game_version='26.3',
                 world_path='D:/world', players=['Steve'], paused=False)
    with pytest.raises(ProtocolError):
        validate_event(dict(ready, **changes))


def test_unicode_and_frame_limit():
    assert decode_frame('{"text":"世界"}'.encode())['text'] == '世界'
    with pytest.raises(ProtocolError):
        decode_frame(b'x' * 65537)


@pytest.mark.parametrize('name', ['1', 'ab'])
def test_short_carpet_player_names_preserve_snapshot_and_player_events(name):
    ready = dict(type='ready', protocol=1, session='world', game_version='26.3',
                 world_path='D:/world', host_player='Steve', players=['Steve', name], paused=False)
    assert validate_event(ready) == ready
    assert SingleplayerHandler().test_server_startup_done(parse(ready))
    for kind in ['player_joined', 'player_left', 'chat', 'suggest_request']:
        event = dict(type=kind, session='world', player=name, text='!!help', id='completion')
        assert validate_event(event) == event
        if kind == 'chat':
            info = parse(event)
            assert info.is_player and info.player == name


@pytest.mark.parametrize('name', ['', 'bad name', '@a', 'x' * 17, 'Steve\n!!MCDR', 'Steve\x00'])
def test_invalid_player_names_are_still_rejected(name):
    with pytest.raises(ProtocolError):
        validate_event(dict(type='player_joined', session='world', player=name))
