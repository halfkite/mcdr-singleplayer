import io
import json
import time
from pathlib import Path

from singleplayer_bridge import supervisor


def controllers(tmp_path, monkeypatch):
    processes = []

    class Process:
        def __init__(self, args, **kwargs):
            self.stdin = io.StringIO()
            # The controller drains the console on a thread, so the mock needs a stream to read.
            self.stdout = io.StringIO()
            self.code = None
            self.environment = kwargs['env']
            processes.append(self)

        def poll(self):
            return self.code

        def wait(self, timeout=None):
            self.code = 0
            return 0

        def kill(self):
            self.code = -9

    monkeypatch.setattr(supervisor.subprocess, 'Popen', Process)
    monkeypatch.setattr(supervisor, 'configure_host', lambda *args: None)
    common = tmp_path / 'mcdr-singleplayer'
    common.mkdir()
    stages = []
    first = supervisor.Controller(common, common / 'config.yml', tmp_path / 'first.json', 'first', progress=stages.append)
    second = supervisor.Controller(common, common / 'config.yml', tmp_path / 'second.json', 'second')
    return common, first, second, processes, stages


def world_state(tmp_path, name, port):
    world = tmp_path / 'saves' / name
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'test')
    return dict(world_path=str(world), session=name, host_player='Host', bridge_port=port)


def test_lan_guest_at_menu_does_not_take_or_retire_the_hosts_controller(tmp_path, monkeypatch):
    common, guest, host, processes, stages = controllers(tmp_path, monkeypatch)
    state = world_state(tmp_path, 'host-world', 25591)
    other = world_state(tmp_path, 'other-world', 25592)
    try:
        guest.tick({})
        host.tick({})
        assert guest.lease is None and host.lease is None
        # Starting first does not reserve the runtime at the title screen.
        host.tick(state)
        assert host.process.environment['MCDR_BRIDGE_PORT'] == '25591'
        guest.tick({})  # Remote/LAN connections have no integrated world state.
        host.tick(state)
        assert len(processes) == 1 and not host.retiring
        assert host.process.stdin.getvalue() == ''
        guest.tick(other)
        assert guest.process is None and stages[-1] == 'waiting_instance'
        assert not host.retiring
        # Even after save-and-quit, outstanding plugin tasks keep the lease.
        host.tick({})
        guest.tick(other)
        assert guest.process is None
        host.process.code = 0
        host.tick({})
        assert host.lease is None
        guest.tick(other)
        assert len(processes) == 2 and guest.process.environment['MCDR_BRIDGE_PORT'] == '25592'
    finally:
        guest.close()
        host.close()


def test_controller_waits_for_installation_before_touching_a_world_profile(tmp_path, monkeypatch):
    common, host, _, processes, stages = controllers(tmp_path, monkeypatch)
    state = world_state(tmp_path, 'world', 25591)
    lease = supervisor.lock_common(common, '.installation.lock')
    try:
        host.tick(state)
        assert not processes and stages == ['waiting_instance']
        assert not (common / 'plugindata/world').exists()
    finally:
        lease.close()
    try:
        host.tick(state)
        assert host.process is not None
    finally:
        host.close()


def test_only_lan_host_is_automatically_promoted(tmp_path):
    from ruamel.yaml import YAML
    yaml = YAML()
    (tmp_path / 'permission.yml').write_text('guest: []\nuser: [LanGuest]\nhelper: []\nadmin: []\nowner: []\n', encoding='utf8')
    (tmp_path / 'config.yml').write_text('language: en_us\n', encoding='utf8')
    supervisor.configure_host(tmp_path, 'Host', 'zh_cn')
    permissions = yaml.load((tmp_path / 'permission.yml').read_text(encoding='utf8'))
    assert permissions['owner'] == ['Host']
    assert permissions['user'] == ['LanGuest']


def test_a_zero_filled_permission_file_does_not_stop_the_controller(tmp_path):
    """A crash or a full disk can leave the file full of NUL bytes, which is not valid YAML."""
    from ruamel.yaml import YAML
    yaml = YAML()
    (tmp_path / 'permission.yml').write_bytes(b'\x00' * 64)
    (tmp_path / 'config.yml').write_bytes(b'\x00' * 64)

    supervisor.configure_host(tmp_path, 'Host', 'zh_cn')

    permissions = yaml.load((tmp_path / 'permission.yml').read_text(encoding='utf8'))
    assert permissions['owner'] == ['Host']
    backups = list((tmp_path / 'runtime/history').iterdir())
    assert any(name.name.startswith('permission.yml.corrupt-') for name in backups)
    assert any(name.name.startswith('config.yml.corrupt-') for name in backups)
    # config.yml is MCDR's own file: it is moved aside so MCDR rewrites its defaults.
    assert not (tmp_path / 'config.yml').exists()


def test_a_corrupt_file_is_repaired_from_the_last_good_copy(tmp_path):
    """Damage must not silently wipe the other players' permissions."""
    from ruamel.yaml import YAML
    yaml = YAML()
    (tmp_path / 'permission.yml').write_text(
        'guest: []\nuser: [Helper1]\nhelper: []\nadmin: []\nowner: [Alice]\n', encoding='utf8')
    (tmp_path / 'config.yml').write_text('language: en_us\n', encoding='utf8')
    # The first pass parses cleanly, so it also records the known-good copy.
    supervisor.configure_host(tmp_path, 'Host', 'zh_cn')

    (tmp_path / 'permission.yml').write_bytes(b'\x00' * 96)
    supervisor.configure_host(tmp_path, 'Host', 'zh_cn')

    permissions = yaml.load((tmp_path / 'permission.yml').read_text(encoding='utf8'))
    assert permissions['user'] == ['Helper1'], 'the surviving permissions must come back'
    assert 'Alice' in permissions['owner'] and 'Host' in permissions['owner']


def test_the_child_log_rotates_instead_of_growing_without_bound(tmp_path):
    path = tmp_path / 'controller-child.log'
    log = supervisor.ChildLog(path, limit=200, keep=2)
    for _ in range(60):
        log.write('x' * 40 + '\n')
    log.close()
    assert path.stat().st_size < 300, 'the live log must stay near the cap'
    assert (tmp_path / 'controller-child.log.1').is_file()


def test_an_alternating_console_loop_is_stopped_too(tmp_path, monkeypatch):
    """The real loop pairs two messages, so counting consecutive identical lines never fires."""
    monkeypatch.setattr(supervisor, 'REPEAT_LIMIT', 5)
    path = tmp_path / 'controller-child.log'
    log = supervisor.ChildLog(path, limit=10 ** 6)
    flooded = []
    text = ("服务端已关闭，不能向其标准输入流输入命令\n被输入的命令: ''\n") * 40
    supervisor.ChildReader(io.StringIO(text), log, flooded.append).run()
    log.close()

    assert flooded, 'the paired loop has to be recognised as a flood'
    assert len(path.read_text(encoding='utf8').splitlines()) < 30, 'the flood must not be logged in full'


def test_a_zero_length_permission_file_is_rebuilt(tmp_path):
    """An interrupted write can leave zero bytes, which parses as "no document" instead of failing."""
    (tmp_path / 'permission.yml').write_bytes(b'')
    (tmp_path / 'config.yml').write_text('language: en_us\n', encoding='utf8')

    supervisor.configure_host(tmp_path, 'Host', 'zh_cn')

    from ruamel.yaml import YAML
    permissions = YAML().load((tmp_path / 'permission.yml').read_text(encoding='utf8'))
    assert permissions['owner'] == ['Host']


def test_a_repeating_console_line_stops_a_runaway_child(tmp_path, monkeypatch):
    """A closed stdin makes MCDR echo an empty command forever; that must not fill the disk."""
    monkeypatch.setattr(supervisor, 'REPEAT_LIMIT', 5)
    path = tmp_path / 'controller-child.log'
    log = supervisor.ChildLog(path, limit=10 ** 6)
    flooded = []
    stream = io.StringIO('服务端已关闭，不能向其标准输入流输入命令\n' * 50)
    supervisor.ChildReader(stream, log, flooded.append).run()
    log.close()

    assert flooded, 'the guard has to fire on a spinning console'
    assert path.read_text(encoding='utf8').count('服务端已关闭') == 5, 'logging stops at the limit'

def test_a_long_retire_is_offered_to_the_player_instead_of_being_killed(tmp_path, monkeypatch):
    """A backup or restore under way must never be aborted by the controller on its own."""
    common, guest, host, processes, stages = controllers(tmp_path, monkeypatch)
    host.tick(world_state(tmp_path, "host-world", 25591))
    process = host.process

    host.tick({})  # leaving the world retires the child, which may still be finishing tasks
    assert host.retiring and process.code is None

    monkeypatch.setattr(supervisor, "RETIRE_NOTICE_AFTER", 0)
    host.retired_at = time.monotonic() - 40
    host.tick({})

    record = json.loads((tmp_path / "retire-status.json").read_text(encoding="utf8"))
    assert record["stalled"] is True and record["seconds"] >= 40
    assert process.code is None, "the controller must wait instead of ending the child"


def test_the_player_can_stop_a_retiring_child(tmp_path, monkeypatch):
    common, guest, host, processes, stages = controllers(tmp_path, monkeypatch)
    host.tick(world_state(tmp_path, "host-world", 25591))
    process = host.process
    host.tick({})
    assert process.code is None

    (tmp_path / "terminate.request").write_text("", encoding="utf8")
    host.tick({})

    assert process.code is not None, "the child has to be ended when the player asks for it"
    assert not (tmp_path / "terminate.request").exists(), "the request is consumed once"
