import json
import logging
from pathlib import Path
from types import SimpleNamespace

from singleplayer_bridge.restore_progress import RestoreProgress, current_restore


def test_atomic_progress_survives_world_disconnect_and_reports_real_completion(tmp_path):
    path = tmp_path / '.mcdr_restore_progress.json'
    progress = RestoreProgress({'progress_path': str(path), 'session': 'world-session'}, tmp_path / 'saves/world', 7, logging.getLogger('test'))
    for stage in ('checking', 'saving', 'safety_backup', 'restoring'):
        progress.update(stage)
        record = json.loads(path.read_text(encoding='utf8'))
        assert record['stage'] == stage and record['session'] == 'world-session' and record['backup_id'] == 7
        assert record['status'] == 'running'
    assert record['modified']
    progress.exported = True
    progress.finish()
    assert json.loads(path.read_text())['status'] == 'completed'
    assert not list(tmp_path.glob('*.tmp'))


def test_cancelled_restore_never_claims_completion_and_failed_restore_retains_lock(tmp_path):
    path = tmp_path / '.mcdr_restore_progress.json'
    progress = RestoreProgress({'progress_path': str(path), 'session': 's'}, tmp_path / 'world', 1, logging.getLogger('test'))
    progress.finish()
    assert json.loads(path.read_text())['status'] == 'cancelled'
    progress.update('restoring')
    progress.update('failed', 'failed', 'verification failed')
    record = json.loads(path.read_text())
    assert record['status'] == 'failed' and record['modified'] and record['detail'] == 'verification failed'
    retry = RestoreProgress({'progress_path': str(path)}, tmp_path / 'world', 1, logging.getLogger('test'))
    assert retry.data['session'] == 's'
    assert retry.data['operation'] != progress.data['operation']


def test_invalid_status_destination_cannot_overwrite_other_files(tmp_path):
    path = tmp_path / 'level.dat'
    path.write_bytes(b'world')
    progress = RestoreProgress({'progress_path': str(path)}, tmp_path / 'world', 1, logging.getLogger('test'))
    progress.update('restoring')
    assert path.read_bytes() == b'world'


def test_terminal_progress_retries_transient_windows_read_lock(tmp_path, monkeypatch):
    path = tmp_path / '.mcdr_restore_progress.json'
    progress = RestoreProgress({'progress_path': str(path), 'session': 's'}, tmp_path / 'world', 1, logging.getLogger('test'))
    progress.update('restoring')
    replace = Path.replace
    attempts = []
    def locked(source, target):
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError('UI reader has the status file open')
        return replace(source, target)
    monkeypatch.setattr(Path, 'replace', locked)
    progress.exported = True
    progress.finish()
    assert len(attempts) == 3 and json.loads(path.read_text())['status'] == 'completed'
    assert not list(tmp_path.glob('*.tmp'))


def test_real_adapter_hooks_publish_action_stages_and_failure(monkeypatch, tmp_path):
    import errno
    import sys
    import singleplayer_prime_backup as adapter
    path = tmp_path / '.mcdr_restore_progress.json'
    world = tmp_path / 'world'
    world.mkdir()
    stages = []
    cleanup_attempts = []
    fail = [False]
    class Create:
        def run(self):
            stages.append(json.loads(path.read_text())['stage'])
    class Export:
        def run(self):
            current_restore.get().update('restoring')
            stages.append(json.loads(path.read_text())['stage'])
            if fail[0]:
                raise RuntimeError('verification failure')
            Temp().erase()
            return []
    class Temp:
        def erase(self):
            cleanup_attempts.append(1)
            if len(cleanup_attempts) == 1:
                raise OSError(errno.ENOTEMPTY, 'Directory not empty')
    original_temp_erase = Temp.erase
    class Restore:
        backup_id = 1
        fail_soft = False
        verify_blob = True
        server = object()
        def run(self):
            current_restore.get().update('saving')
            Create().run()
            Export().run()
    class Backup:
        def run(self): pass
    class Trash:
        def add(self, *args):
            raise AssertionError('Non-atomic copy/delete fallback must not run')
    modules = {
        'prime_backup.mcdr.task.backup.create_backup_task': SimpleNamespace(CreateBackupTask=Backup),
        'prime_backup.mcdr.task.backup.restore_backup_task': SimpleNamespace(RestoreBackupTask=Restore),
        'prime_backup.action.create_backup_action': SimpleNamespace(CreateBackupAction=Create),
        'prime_backup.action.export_backup_action_directory': SimpleNamespace(
            ExportBackupToDirectoryAction=Export, _TrashBin=Trash, _ExportTempDirectory=Temp),
    }
    instance = object()
    server = SimpleNamespace(get_plugin_instance=lambda name: instance,
        get_plugin_metadata=lambda name: SimpleNamespace(version='1.13.1'), logger=logging.getLogger('test'))
    monkeypatch.setattr(adapter, '_server', server)
    monkeypatch.setattr(adapter, '_prime_instance', None)
    monkeypatch.setattr(adapter, '_patches', [])
    monkeypatch.setattr(adapter, '_world_path', str(world))
    monkeypatch.setattr(adapter, 'bridge', lambda: SimpleNamespace(restore_progress_context=lambda: dict(progress_path=str(path), session='s')))
    monkeypatch.setattr(adapter, 'preflight', lambda task, restore=False: world)
    monkeypatch.setattr(adapter, 'check_backup', lambda *args: None)
    monkeypatch.setattr(adapter, 'wait_restore_ready', lambda *args, **kwargs: None)
    # Patch only this adapter's importer, not Python's global importlib module.
    monkeypatch.setattr(adapter, 'importlib', SimpleNamespace(import_module=lambda name: modules[name]))
    monkeypatch.setitem(sys.modules, 'prime_backup.action.get_backup_action', SimpleNamespace(GetBackupAction=lambda *a, **k: SimpleNamespace(run=lambda: None)))
    adapter._install()
    Restore().run()
    assert stages == ['safety_backup', 'restoring']
    assert len(cleanup_attempts) == 2
    assert json.loads(path.read_text())['status'] == 'completed' and current_restore.get() is None
    fail[0] = True
    import pytest
    with pytest.raises(RuntimeError, match='verification failure'):
        Restore().run()
    assert json.loads(path.read_text())['status'] == 'failed' and current_restore.get() is None
    # A new lock appearing after preflight must not let shutil.move partially
    # delete the original world. Simulate denial of the atomic directory move.
    (world / 'level.dat').write_bytes(b'original level')
    trash = Trash()
    trash.trash_bin_path = tmp_path / 'trash'
    trash.trashes = []
    def denied(*args):
        raise PermissionError('directory rename blocked')
    import os
    monkeypatch.setattr(os, 'rename', denied)
    token = current_restore.set(RestoreProgress({'progress_path': str(path)}, world, 1, logging.getLogger('test')))
    try:
        with pytest.raises(PermissionError, match='rename blocked'):
            trash.add(world, Path(world.name))
        assert (world / 'level.dat').read_bytes() == b'original level' and not trash.trashes
    finally:
        current_restore.reset(token)
    adapter.on_unload(server)
    assert Temp.erase is original_temp_erase


def test_cleanup_failures_never_turn_a_finished_restore_into_a_failure(monkeypatch, tmp_path):
    """Prime Backup runs its scratch cleanup after the world is already written."""
    import errno
    import sys
    import singleplayer_prime_backup as adapter

    temp_dir = tmp_path / '.prime_backup.export_temp_1_2'
    (temp_dir / 'trash_bin').mkdir(parents=True)
    calls = []

    class Temp:
        def __init__(self):
            self._ExportTempDirectory__temp_dir_path = temp_dir

        def prepare(self):
            calls.append('prepare')
            if calls.count('prepare') == 1:
                raise OSError(errno.ENOTEMPTY, 'Directory not empty', str(temp_dir / 'trash_bin'))

        def erase(self):
            calls.append('erase')
            raise OSError(errno.ENOTEMPTY, 'Directory not empty', str(temp_dir / 'trash_bin'))

    class Action:
        def run(self, *args, **kwargs):
            return []

    modules = {
        'prime_backup.mcdr.task.backup.create_backup_task': SimpleNamespace(CreateBackupTask=Action),
        'prime_backup.mcdr.task.backup.restore_backup_task': SimpleNamespace(RestoreBackupTask=Action),
        'prime_backup.action.create_backup_action': SimpleNamespace(CreateBackupAction=Action),
        'prime_backup.action.export_backup_action_directory': SimpleNamespace(
            ExportBackupToDirectoryAction=Action, _TrashBin=SimpleNamespace(add=lambda *args: None),
            _ExportTempDirectory=Temp),
    }
    server = SimpleNamespace(get_plugin_instance=lambda name: object(),
        get_plugin_metadata=lambda name: SimpleNamespace(version='1.13.1'), logger=logging.getLogger('test'))
    monkeypatch.setattr(adapter, '_server', server)
    monkeypatch.setattr(adapter, '_prime_instance', None)
    monkeypatch.setattr(adapter, '_patches', [])
    monkeypatch.setattr(adapter, '_world_path', str(tmp_path / 'world'))
    monkeypatch.setattr(adapter, 'importlib', SimpleNamespace(import_module=lambda name: modules[name]))
    # Fail on the first attempt instead of waiting out the real retry window.
    monkeypatch.setattr(adapter, 'retry_temp_cleanup', lambda action, timeout=0, on_retry=None: action())
    monkeypatch.setitem(sys.modules, 'prime_backup.action.get_backup_action',
                        SimpleNamespace(GetBackupAction=lambda *args, **kwargs: Action()))
    adapter._install()

    # The rescue path only applies while a restore is running, which is when the progress is set.
    world = tmp_path / 'world'
    world.mkdir(exist_ok=True)
    token = current_restore.set(RestoreProgress(
        {'progress_path': str(tmp_path / '.progress.json')}, world, 1, logging.getLogger('test')))
    try:
        temp = Temp()
        temp.prepare()
        assert calls.count('prepare') == 2, 'the cleanup has to be retried on a fresh directory'
        assert list(tmp_path.glob('*.stale-*')), 'the directory that could not be removed is kept aside'

        temp.erase()  # must never raise: the world is already restored at this point
        assert calls.count('erase') == 1
    finally:
        current_restore.reset(token)
    adapter.on_unload(server)
