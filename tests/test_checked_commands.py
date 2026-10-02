import threading
from types import SimpleNamespace

import pytest

from singleplayer_bridge import plugin
from singleplayer_bridge.handler import BridgeInfo
from mcdreforged.api.types import InfoSource
from singleplayer_bridge.protocol import CHECKED_PREFIX
import json


def observe(event):
    info = BridgeInfo(InfoSource.SERVER, '')
    info.bridge_event = event
    plugin.observe(info)


def test_checked_command_waits_for_matching_real_result_and_rejects_failure():
    plugin.reset()
    observe(dict(type='world_info', session='checked-world', world_path='D:/world', game_version='26.3'))
    def execute(line):
        request = json.loads(line[len(CHECKED_PREFIX):])
        observe(dict(type='command_result', session='checked-world', id='another-id', success=True, text='fake'))
        observe(dict(type='command_result', session='checked-world', id=request['id'], success=False, text='real failure'))
    with pytest.raises(RuntimeError, match='real failure'):
        plugin.execute_checked(SimpleNamespace(execute=execute), 'save-all flush', timeout=.1)
    plugin.reset()


def test_proxy_detach_is_not_world_shutdown():
    plugin.reset()
    observe(dict(type='world_info', session='still-open', world_path='D:/world', game_version='26.3'))
    plugin.reset()
    with pytest.raises(RuntimeError, match='detached'):
        plugin.wait_world_closed('still-open', timeout=.01)
    observe(dict(type='world_info', session='really-closed', world_path='D:/world', game_version='26.3'))
    observe(dict(type='world_stopped', session='really-closed'))
    plugin.wait_world_closed('really-closed', timeout=.01)
