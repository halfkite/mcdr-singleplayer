import io
from pathlib import Path

from singleplayer_bridge import supervisor


def controllers(tmp_path, monkeypatch):
    processes = []

    class Process:
        def __init__(self, args, **kwargs):
            self.stdin = io.StringIO()
            self.code = None
            self.environment = kwargs['env']
            processes.append(self)

        def poll(self):
            return self.code

        def wait(self):
            self.code = 0
            return 0

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
