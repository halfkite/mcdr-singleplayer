"""Optional, version-pinned adapter. The upstream Prime Backup archive remains unchanged."""
from singleplayer_bridge.i18n import tr
import functools
import importlib
import time
from pathlib import Path

from .guards import check_backup, check_binding, check_unlocked

_server = None
_world_path = ''
_patches = []
_prime_instance = None


def bridge():
    module = _server.get_plugin_instance('singleplayer_bridge')
    if module is None:
        raise RuntimeError(tr('error.singleplayer_bridge_plugin_is_not_loaded'))
    return module.plugin


def preflight(task, restore=False):
    if not _world_path:
        raise RuntimeError(tr('error.no_world_bound_to_the_prime_backup_adapter_run_setup_prime_backup_py'))
    world = check_binding(_world_path, task.config)
    if restore and task.config.backup.retain_patterns:
        raise RuntimeError(tr('error.this_adapter_requires_empty_retain_patterns_to_keep_restoration_inside_the_bound_world'))
    commands = task.config.server.commands
    if (not task.config.server.turn_off_auto_save or commands.auto_save_off != 'save-off'
            or commands.save_all_worlds != 'save-all flush' or commands.auto_save_on != 'save-on'):
        raise RuntimeError(tr('error.singleplayer_backups_require_the_adapter_save_off_save_all_flush_save_on_configuration'))
    state = bridge().snapshot()
    if state.get('session'):
        if Path(state['world_path']).resolve() != world:
            raise RuntimeError(tr('error.connected_world_differs_from_the_bound_backup_world'))
        if not restore and state.get('paused'):
            raise RuntimeError(tr('error.world_paused_resume_the_game_before_creating_a_backup'))
    else:
        check_unlocked(world)
    return world


class PrimeServer:
    """Only task-local server calls change; normal MCDR stop continues to detach."""
    def __init__(self, server, world):
        self.server = server
        self.world = world
        self.closing_session = None

    def __getattr__(self, name):
        return getattr(self.server, name)

    def is_server_running(self):
        return bool(bridge().snapshot().get('session'))

    def execute(self, command):
        bridge().execute_checked(self.server, command)

    def stop(self):
        state = bridge().snapshot()
        if not state.get('session') or Path(state['world_path']).resolve() != self.world:
            raise RuntimeError(tr('error.restore_lost_its_world_connection_restoration_cancelled'))
        self.closing_session = state['session']
        from singleplayer_bridge.restore_progress import current_restore
        progress = current_restore.get()
        if progress is not None:
            progress.update('saving')
        bridge().execute_checked(self.server, '__bridge_save_and_quit__')
        return True

    def wait_until_stop(self):
        if self.closing_session is None:
            raise RuntimeError(tr('error.restore_did_not_request_world_shutdown'))
        bridge().wait_world_closed(self.closing_session, timeout=60)
        deadline = time.monotonic() + 10
        while self.server.is_server_running():
            if time.monotonic() >= deadline:
                raise RuntimeError(tr('error.proxy_did_not_stop_after_world_shutdown_restoration_cancelled'))
            time.sleep(0.05)
        check_unlocked(self.world)

    def start(self):
        import os
        if os.environ.get('MCDR_BRIDGE_COMMON'):
            self.server.logger.info(tr('restore.reenter_auto'))
        else:
            self.server.logger.info(tr('restore.reenter_manual'))
        return False


def _install():
    global _prime_instance
    instance = _server.get_plugin_instance('prime_backup')
    if instance is None or instance is _prime_instance:
        return
    metadata = _server.get_plugin_metadata('prime_backup')
    if str(metadata.version) != '1.13.1':
        raise RuntimeError(tr('error.the_adapter_only_supports_prime_backup_1_13_1'))
    for module_name, class_name, restore in [
        ('prime_backup.mcdr.task.backup.create_backup_task', 'CreateBackupTask', False),
        ('prime_backup.mcdr.task.backup.restore_backup_task', 'RestoreBackupTask', True),
    ]:
        cls = getattr(importlib.import_module(module_name), class_name)
        original = getattr(cls.run, '_spbridge_original', cls.run)

        def make_wrapper(original_run, restoring):
            @functools.wraps(original_run)
            def run(task):
                from singleplayer_bridge.restore_progress import exclusive_backup
                with exclusive_backup():
                    return run_exclusive(task)

            def run_exclusive(task):
                if restoring:
                    from singleplayer_bridge.restore_progress import RestoreProgress, current_restore
                    context = bridge().restore_progress_context()
                    if not context.get('progress_path'):
                        command = _server.get_mcdr_config().get('start_command', [])
                        if isinstance(command, list) and '--config' in command:
                            index = command.index('--config') + 1
                            if index < len(command):
                                context['progress_path'] = str(Path(command[index]).with_name('.mcdr_restore_progress.json'))
                    progress = RestoreProgress(context, _world_path, task.backup_id, _server.logger)
                    progress.update('checking')
                    token = current_restore.set(progress)
                    try:
                        result = run_bound(task)
                        progress.finish()
                        return result
                    except Exception as exc:
                        progress.update('failed', 'failed', str(exc))
                        raise
                    finally:
                        current_restore.reset(token)
                return run_bound(task)

            def run_bound(task):
                world = preflight(task, restore=restoring)
                if restoring:
                    from prime_backup.action.get_backup_action import GetBackupAction
                    if task.backup_id is None:
                        from prime_backup.action.list_backup_action import ListBackupAction
                        from prime_backup.types.backup_filter import BackupFilter
                        backup_filter = BackupFilter()
                        backup_filter.requires_non_temporary_backup()
                        candidates = ListBackupAction(backup_filter=backup_filter, limit=1).run()
                        if not candidates:
                            return original_run(task)
                        task.backup_id = candidates[0].id
                    check_backup(world, GetBackupAction(task.backup_id, with_files=True).run())
                    from singleplayer_bridge.restore_progress import current_restore
                    progress = current_restore.get()
                    if progress is not None:
                        progress.data['backup_id'] = task.backup_id
                    # A restore must verify all files; partial restoration is not offered here.
                    if task.fail_soft or not task.verify_blob:
                        raise RuntimeError(tr('error.singleplayer_restore_requires_blob_verification_and_fail_soft_false'))
                original_server = task.server
                task.server = PrimeServer(original_server, world)
                try:
                    return original_run(task)
                finally:
                    task.server = original_server
            run._spbridge_original = original_run
            return run

        wrapper = make_wrapper(original, restore)
        cls.run = wrapper
        _patches.append((cls, wrapper, original))
    # Observe real action boundaries, without parsing translated PB log messages.
    for module_name, class_name, stage in [
        ('prime_backup.action.create_backup_action', 'CreateBackupAction', 'safety_backup'),
        ('prime_backup.action.export_backup_action_directory', 'ExportBackupToDirectoryAction', 'restoring'),
    ]:
        cls = getattr(importlib.import_module(module_name), class_name)
        original = getattr(cls.run, '_spbridge_original', cls.run)
        def action_wrapper(original_run, action_stage):
            @functools.wraps(original_run)
            def run(action):
                from singleplayer_bridge.restore_progress import current_restore
                progress = current_restore.get()
                if progress is not None:
                    progress.update(action_stage)
                result = original_run(action)
                if progress is not None and action_stage == 'restoring':
                    if len(result) != 0:
                        raise RuntimeError(tr('error.restore_finished_with_file_verification_failures'))
                    progress.exported = True
                return result
            run._spbridge_original = original_run
            return run
        wrapper = action_wrapper(original, stage)
        cls.run = wrapper
        _patches.append((cls, wrapper, original))
    _prime_instance = instance
    _server.logger.info('Prime Backup 1.13.1 singleplayer adapter ready (one bound world, confirmed saves and shutdown)')


def on_load(server, previous):
    global _server, _world_path
    _server = server
    config = server.load_config_simple(default_config={'world_path': ''})
    _world_path = config.get('world_path', '')
    _install()


def on_unload(server):
    for cls, wrapper, original in reversed(_patches):
        if cls.run is wrapper:
            cls.run = original
    _patches.clear()
