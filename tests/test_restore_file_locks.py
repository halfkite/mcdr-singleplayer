import json
import logging
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from singleplayer_bridge.backup_guard import wait_restore_ready
from singleplayer_bridge.restore_progress import RestoreProgress


@pytest.fixture
def occupied_world(tmp_path):
    world = tmp_path / 'saves/world'
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'original level')
    config = world / 'syncmatica/config.json'
    config.parent.mkdir()
    config.write_text('{"original":true}')
    progress = RestoreProgress({'progress_path': str(tmp_path / '.mcdr_restore_progress.json')},
                               world, 1, logging.getLogger('test'))
    return world, config, progress


@pytest.mark.skipif(os.name != 'nt', reason='Windows file sharing blocks replacing open readers')
def test_real_reader_blocks_restore_without_touching_world(occupied_world):
    world, config, progress = occupied_world
    process = subprocess.Popen([sys.executable, '-c',
        "import sys; f=open(sys.argv[1]); print('open',flush=True); sys.stdin.readline(); f.close()", str(config)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'open'
        with pytest.raises(RuntimeError, match='syncmatica/config.json'):
            wait_restore_ready(world, timeout=0.2, progress=progress)
        assert not progress.data['modified']
        assert (world / 'level.dat').read_bytes() == b'original level'
        assert json.loads(config.read_text()) == {'original': True}
    finally:
        process.communicate('\n', timeout=5)
    wait_restore_ready(world, timeout=0.2, progress=progress)


def test_transient_lock_is_waited_for_before_restoring(occupied_world, monkeypatch):
    from singleplayer_bridge import backup_guard
    world, config, progress = occupied_world
    ready = threading.Event()
    original = backup_guard._check_replaceable
    def probe(path):
        if path == config and not ready.is_set():
            raise PermissionError(13, 'file in use', str(path))
        return original(path)
    monkeypatch.setattr(backup_guard, '_check_replaceable', probe)
    timer = threading.Timer(0.15, ready.set)
    timer.start()
    try:
        wait_restore_ready(world, timeout=1, progress=progress)
        assert ready.is_set() and progress.data['stage'] == 'waiting_files'
        assert not progress.data['modified']
    finally:
        timer.cancel()


def test_chunk_guard_only_checks_the_files_it_will_replace(occupied_world, monkeypatch):
    from singleplayer_bridge import backup_guard
    world, config, progress = occupied_world
    region = world / 'region'
    region.mkdir()
    (region / 'r.0.0.mca').write_bytes(b'region')
    def probe(path):
        if path == config:
            pytest.fail('CB should not require replacing an unrelated config file')
    monkeypatch.setattr(backup_guard, '_check_replaceable', probe)
    wait_restore_ready(world, [region], timeout=0, progress=progress)
    assert not progress.data['modified']


@pytest.mark.skipif(os.name != 'nt', reason='Windows directory handles prevent moving their parent')
def test_open_child_folder_blocks_directory_move_despite_file_preflight(occupied_world, tmp_path):
    import ctypes
    from singleplayer_bridge.backup_guard import _windows_file_api
    from singleplayer_prime_backup.guards import move_world_to_trash
    world, config, progress = occupied_world
    kernel = _windows_file_api()
    handle = kernel.CreateFileW(str(config.parent), 1, 7, None, 3, 0x02000000, None)
    assert handle != ctypes.c_void_p(-1).value
    target = tmp_path / 'trash/world'
    target.parent.mkdir()
    try:
        # File Explorer directory handles can permit DELETE sharing but still
        # prevent renaming the parent world on Windows.
        wait_restore_ready(world, timeout=0, progress=progress)
        with pytest.raises(RuntimeError, match='File Explorer'):
            move_world_to_trash(world, target, progress=progress, timeout=0.1)
        assert not progress.data['modified']
        assert (world / 'level.dat').read_bytes() == b'original level'
        assert not target.exists()
        assert not json.loads(progress.path.read_text(encoding='utf8'))['modified']
    finally:
        kernel.CloseHandle(handle)
    move_world_to_trash(world, target, progress=progress, timeout=0)
    assert progress.data['modified'] and not world.exists()
    assert (target / 'level.dat').read_bytes() == b'original level'


def test_directory_move_waits_and_reports_unmodified_while_denied(occupied_world, tmp_path, monkeypatch):
    from singleplayer_prime_backup.guards import move_world_to_trash
    world, config, progress = occupied_world
    rename = os.rename
    attempts = []
    def transient(source, destination):
        attempts.append(1)
        if len(attempts) == 1:
            error = PermissionError('open child folder')
            error.winerror = 5
            raise error
        assert not json.loads(progress.path.read_text(encoding='utf8'))['detail']
        return rename(source, destination)
    updates = []
    update = progress.update
    def record(stage, *args, **kwargs):
        update(stage, *args, **kwargs)
        updates.append(dict(progress.data))
    monkeypatch.setattr(progress, 'update', record)
    monkeypatch.setattr(os, 'rename', transient)
    move_world_to_trash(world, tmp_path / 'old-world', progress=progress, timeout=1)
    waiting = [data for data in updates if data['stage'] == 'waiting_files']
    assert len(attempts) == 2 and waiting and not waiting[0]['modified']
    assert 'File Explorer' in waiting[0]['detail'] and progress.data['modified']
