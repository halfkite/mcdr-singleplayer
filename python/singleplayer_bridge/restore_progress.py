"""Atomic, token-free restore status that survives the world socket closing."""
from singleplayer_bridge.i18n import tr
import contextvars
import contextlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

current_restore = contextvars.ContextVar('singleplayer_restore_progress', default=None)
_backup_lock = threading.Lock()


@contextlib.contextmanager
def exclusive_backup():
    if not _backup_lock.acquire(blocking=False):
        raise RuntimeError(tr('error.another_backup_or_restore_task_is_running_retry_after_it_completes'))
    try:
        yield
    finally:
        _backup_lock.release()


class RestoreProgress:
    def __init__(self, context, world, backup_id, logger):
        raw = context.get('progress_path')
        if not raw and os.environ.get('MCDR_BRIDGE_CONFIG'):
            raw = str(Path(os.environ['MCDR_BRIDGE_RUNTIME']) / '.mcdr_restore_progress.json') if os.environ.get('MCDR_BRIDGE_RUNTIME') else str(Path(os.environ['MCDR_BRIDGE_CONFIG']).with_name('.mcdr_restore_progress.json'))
        self.path = Path(raw) if raw else None
        if self.path and (not self.path.is_absolute() or self.path.name != '.mcdr_restore_progress.json'):
            self.path = None
        self.logger = logger
        self.lock = threading.RLock()
        self.exported = False
        session = context.get('session', '')
        if not session and self.path:
            try:
                if self.path.stat().st_size <= 16384:
                    previous = json.loads(self.path.read_text(encoding='utf8'))
                    if previous.get('world_name') == Path(world).name:
                        session = previous.get('session', '')
            except (OSError, ValueError):
                pass
        self.data = dict(protocol=1, operation=uuid.uuid4().hex, session=session,
            world_name=Path(world).name, backup_id=backup_id, backend_pid=os.getpid(),
            started_at=int(time.time() * 1000), status='running', stage='checking', detail='', modified=False)

    def update(self, stage, status='running', detail=''):
        with self.lock:
            self.data.update(stage=stage, status=status, detail=str(detail).replace('\x00', '')[:512],
                updated_at=int(time.time() * 1000))
            if stage == 'restoring':
                self.data['modified'] = True
            if self.path is None:
                return
            temporary = self.path.with_name(self.path.name + '.' + self.data['operation'] + '.tmp')
            try:
                if self.path.is_symlink() or (hasattr(self.path, 'is_junction') and self.path.is_junction()):
                    raise OSError('Restore status cannot be a link')
                temporary.write_text(json.dumps(self.data, ensure_ascii=False), encoding='utf8')
                for attempt in range(10):
                    try:
                        temporary.replace(self.path)
                        break
                    except PermissionError:
                        # Windows readers briefly prevent atomic replacement. In particular,
                        # retry the terminal update so a completed restore cannot stay running.
                        if attempt == 9:
                            raise
                        time.sleep(min(0.01 * (attempt + 1), 0.05))
            except OSError as exc:
                # A UI reporting error must never interrupt a real restore.
                self.logger.warning('Could not update restore status: %s', exc)
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def finish(self):
        if self.exported:
            self.update('completed', 'completed')
        else:
            self.update('cancelled', 'cancelled')
