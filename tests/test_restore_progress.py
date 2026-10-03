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
    import sys
    import singleplayer_prime_backup as adapter
    path = tmp_path / '.mcdr_restore_progress.json'
    world = tmp_path / 'world'
    world.mkdir()
    stages = []
    fail = [False]
    class Create:
        def run(self):
            stages.append(json.loads(path.read_text())['stage'])
    class Export:
        def run(self):
            stages.append(json.loads(path.read_text())['stage'])
            if fail[0]:
                raise RuntimeError('verification failure')
            return []
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
    modules = {
        'prime_backup.mcdr.task.backup.create_backup_task': SimpleNamespace(CreateBackupTask=Backup),
        'prime_backup.mcdr.task.backup.restore_backup_task': SimpleNamespace(RestoreBackupTask=Restore),
        'prime_backup.action.create_backup_action': SimpleNamespace(CreateBackupAction=Create),
        'prime_backup.action.export_backup_action_directory': SimpleNamespace(ExportBackupToDirectoryAction=Export),
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
    # Patch only this adapter's importer, not Python's global importlib module.
    monkeypatch.setattr(adapter, 'importlib', SimpleNamespace(import_module=lambda name: modules[name]))
    monkeypatch.setitem(sys.modules, 'prime_backup.action.get_backup_action', SimpleNamespace(GetBackupAction=lambda *a, **k: SimpleNamespace(run=lambda: None)))
    adapter._install()
    Restore().run()
    assert stages == ['safety_backup', 'restoring']
    assert json.loads(path.read_text())['status'] == 'completed' and current_restore.get() is None
    fail[0] = True
    import pytest
    with pytest.raises(RuntimeError, match='verification failure'):
        Restore().run()
    assert json.loads(path.read_text())['status'] == 'failed' and current_restore.get() is None
    adapter.on_unload(server)
