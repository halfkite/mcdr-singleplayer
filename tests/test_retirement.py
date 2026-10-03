import threading
from types import SimpleNamespace

from singleplayer_bridge import plugin


def test_retirement_waits_for_backup_work_and_then_detaches(monkeypatch):
    busy = threading.Event()
    busy.set()
    retired = threading.Event()
    calls = []
    server = SimpleNamespace(is_server_running=lambda: True,
        stop=lambda: calls.append('stop'), wait_until_stop=lambda: calls.append('wait'),
        exit=lambda: (calls.append('exit'), retired.set()))
    monkeypatch.setattr(plugin, 'prime_busy', busy.is_set)
    monkeypatch.setattr(plugin, '_retiring', threading.Event())
    plugin.retire(SimpleNamespace(get_server=lambda: server))
    assert not retired.wait(0.65)
    assert calls == []
    busy.clear()
    assert retired.wait(2)
    assert calls == ['stop', 'wait', 'exit']


def test_chunk_queue_keeps_profile_alive_after_world_disconnect(monkeypatch):
    busy = threading.Event()
    busy.set()
    queue = SimpleNamespace(unfinished_size=lambda: int(busy.is_set()))
    manager = SimpleNamespace(worker_heavy=SimpleNamespace(task_queue=queue), worker_light=SimpleNamespace(task_queue=queue))
    server = SimpleNamespace(get_plugin_instance=lambda name: SimpleNamespace(task_manager=manager))
    monkeypatch.setattr(plugin, '_server', server)
    assert plugin.prime_busy()
    busy.clear()
    assert not plugin.prime_busy()
