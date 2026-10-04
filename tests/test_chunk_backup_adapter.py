import json
import logging
import threading
import sys
from types import SimpleNamespace

import pytest

import singleplayer_chunk_backup as adapter
from singleplayer_bridge.backup_guard import checked_path
from singleplayer_bridge.chunk_backup_config import prepare, rebind
from singleplayer_bridge.restore_progress import current_restore, exclusive_backup


@pytest.fixture
def bound(monkeypatch, tmp_path):
    world = tmp_path / 'saves/world'
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'world')
    profile = tmp_path / 'mcdr-singleplayer/plugindata/world'
    prepare(profile, world)
    monkeypatch.chdir(profile)
    raw = rebind({}, profile, world)
    config = SimpleNamespace(**{k: v for k, v in raw.items() if k != 'backup'},
        static_storage='static_storage', dynamic_storage='dynamic_storage', overwrite_storage='overwrite',
        backup=SimpleNamespace(**raw['backup']))
    state = {'session': 's', 'world_path': str(world), 'paused': False}
    calls = []
    def execute(server, command):
        calls.append(command)
    def close(session, timeout):
        calls.append('world_closed')
        state.clear()
    bridge = SimpleNamespace(snapshot=lambda: dict(state), execute_checked=execute, wait_world_closed=close,
        restore_progress_context=lambda: {'progress_path': str(tmp_path / '.mcdr_restore_progress.json'), 'session': 's'})
    server = SimpleNamespace(logger=logging.getLogger('test'), is_server_running=lambda: bool(state),
        start=lambda: calls.append('UNSAFE_START'), stop=lambda: calls.append('UNSAFE_STOP'))
    monkeypatch.setattr(adapter, '_world', str(world))
    monkeypatch.setattr(adapter, '_server', server)
    monkeypatch.setattr(adapter, 'bridge', lambda: bridge)
    task = SimpleNamespace(config=config, ctx={'backup_id': 1}, server=server)
    manager = SimpleNamespace(config=config, storage_root=config.storage_root, region_storage='dynamic_storage', backup_slot='slot1')
    info = SimpleNamespace(dimension=['minecraft:overworld'])
    return SimpleNamespace(world=world, profile=profile, task=task, config=config, state=state, calls=calls,
        manager=manager, info=info, path=tmp_path / '.mcdr_restore_progress.json', server=server)


def test_restore_waits_for_real_world_close_then_completes(bound):
    stages = []
    def write_regions(manager, info):
        assert not bound.state
        stages.append(json.loads(bound.path.read_text())['stage'])
    def original(task):
        task.server.stop()
        task.server.wait_until_stop()
        adapter.region_wrapper(write_regions)(bound.manager, bound.info)
        task.server.start()
    adapter.task_wrapper(original, True)(bound.task)
    assert bound.calls == ['__bridge_save_and_quit__', 'world_closed']
    assert stages == ['restoring']
    result = json.loads(bound.path.read_text())
    assert result['status'] == 'completed' and result['modified']
    assert bound.task.server is bound.server and current_restore.get() is None


def test_abort_never_claims_completion_or_stops_world(bound):
    adapter.task_wrapper(lambda task: None, True)(bound.task)
    result = json.loads(bound.path.read_text())
    assert result['status'] == 'cancelled' and not result['modified']
    assert bound.state['session'] == 's' and not bound.calls


def test_radius_backup_reads_one_atomic_player_snapshot(bound, monkeypatch):
    # No NBT, locale or display-name parsing; negative/scientific coordinates remain numeric.
    point_module = SimpleNamespace(Point3D=lambda x, y, z: SimpleNamespace(x=x, y=y, z=z))
    monkeypatch.setitem(sys.modules, 'chunk_backup.types.point', point_module)
    expected = dict(player='Player0', x=-1.25e3, y=-59.5, z=2.01, dimension='minecraft:the_nether')
    def execute(server, command):
        bound.calls.append(command)
        return {'text': json.dumps(expected)}
    monkeypatch.setattr(adapter.bridge(), 'execute_checked', execute)
    result = adapter.position_wrapper(lambda *args: pytest.fail('Legacy output parser was used'))(
        SimpleNamespace(config=bound.config), 'Player0')
    assert bound.calls == ['__bridge_player_data__ Player0']
    assert result['dimension'] == 'minecraft:the_nether' and result['position'].x == -1250


@pytest.mark.parametrize('change', [dict(player='Other'), dict(x=float('nan')), dict(y=True), dict(dimension='../world')])
def test_position_response_cannot_select_wrong_player_or_invalid_region(bound, monkeypatch, change):
    expected = dict(player='Player0', x=1, y=2, z=3, dimension='minecraft:overworld') | change
    monkeypatch.setattr(adapter.bridge(), 'execute_checked', lambda *args: {'text': json.dumps(expected)})
    with pytest.raises(RuntimeError, match='Invalid bridge player position'):
        adapter.position_wrapper(lambda *args: None)(SimpleNamespace(config=bound.config), 'Player0')


def test_position_query_rejects_selector_before_sending_command(bound):
    with pytest.raises(RuntimeError, match='Invalid Chunk Backup player name'):
        adapter.position_wrapper(lambda *args: None)(SimpleNamespace(config=bound.config), '@a')
    assert not bound.calls


def test_failed_restore_disables_upstream_restart_and_keeps_modified(bound):
    class Failure(RuntimeError):
        need_start = True
    def fail(manager, info):
        raise Failure('merge failed')
    def original(task):
        bound.state.clear()
        adapter.region_wrapper(fail)(bound.manager, bound.info)
    with pytest.raises(Failure) as caught:
        adapter.task_wrapper(original, True)(bound.task)
    assert caught.value.need_start is False
    result = json.loads(bound.path.read_text())
    assert result['status'] == 'failed' and result['modified']
    assert bound.task.server is bound.server and current_restore.get() is None


def test_automatic_rollback_is_reported_as_failure_not_requested_restore_success(bound):
    def original(task):
        bound.state.clear()
        def fail(*args):
            raise RuntimeError('first merge failed')
        try:
            adapter.region_wrapper(fail)(bound.manager, bound.info)
        except RuntimeError:
            bound.manager.backup_slot = 'overwrite'
            adapter.region_wrapper(lambda *args: None)(bound.manager, bound.info)
        task.server.start()
    adapter.task_wrapper(original, True)(bound.task)
    result = json.loads(bound.path.read_text())
    assert result['status'] == 'failed' and result['modified'] and 'rolled back' in result['detail']


def test_swallowed_player_data_error_cannot_unlock_world(bound):
    manager = SimpleNamespace(config=bound.config, storage_root=bound.config.storage_root, uuid=['invalid-uuid'])
    def original(task):
        bound.state.clear()
        adapter.region_wrapper(lambda *args: None)(bound.manager, bound.info)
        try:
            adapter.player_wrapper(lambda *args: None)(manager)
        except ValueError:
            pass  # Upstream reports player errors but otherwise returns success.
        task.server.start()
    with pytest.raises(RuntimeError, match='player data'):
        adapter.task_wrapper(original, True)(bound.task)
    assert json.loads(bound.path.read_text())['status'] == 'failed'


def test_cross_world_and_unsafe_region_paths_fail_before_shutdown(bound):
    bound.config.backup.dimension['minecraft:overworld']['world_name'] = 'other'
    with pytest.raises(RuntimeError, match='another world'):
        adapter.task_wrapper(lambda *args: pytest.fail('must not run'), True)(bound.task)
    assert not bound.calls and not json.loads(bound.path.read_text())['modified']
    bound.config.backup.dimension['minecraft:overworld']['world_name'] = 'world'
    bound.config.backup.dimension['minecraft:overworld']['region_folder'] = ['../other/region']
    with pytest.raises(RuntimeError, match='outside'):
        adapter.binding(bound.config)


def test_unbound_backup_store_is_not_adopted(bound):
    marker = bound.profile / 'cb_files/.singleplayer-world.json'
    marker.unlink()
    (marker.parent / 'foreign-slot').mkdir()
    with pytest.raises(ValueError, match='cannot adopt'):
        prepare(bound.profile, bound.world)
    with pytest.raises(RuntimeError, match='not bound'):
        adapter.binding(bound.config)


def test_backup_plugins_cannot_run_at_same_time(bound):
    entered = threading.Event()
    with exclusive_backup():
        def competitor():
            with pytest.raises(RuntimeError, match='Another backup'):
                adapter.task_wrapper(lambda task: pytest.fail('must not run'), True)(bound.task)
            entered.set()
        thread = threading.Thread(target=competitor)
        thread.start()
        thread.join(2)
        assert entered.is_set()
    assert not bound.path.exists()


def test_windows_junction_is_rejected(tmp_path):
    import os
    if os.name != 'nt':
        pytest.skip('Windows junction regression')
    import subprocess
    outside = tmp_path / 'outside'
    outside.mkdir()
    root = tmp_path / 'root'
    root.mkdir()
    link = root / 'link'
    subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], check=True, capture_output=True)
    try:
        with pytest.raises(RuntimeError, match='junctions'):
            checked_path(root, 'link/test')
    finally:
        # Remove only the known test junction, without recursing into its target.
        os.rmdir(link)
