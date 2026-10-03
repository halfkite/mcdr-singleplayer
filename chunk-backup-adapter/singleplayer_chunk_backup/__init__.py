"""Task-local adapter for stock Chunk Backup 2.0.3. No upstream files are changed."""
from singleplayer_bridge.i18n import tr
import functools
import importlib
import json
import math
import re
import time
import uuid
from pathlib import Path

from singleplayer_bridge.backup_guard import checked_path, check_tree, check_unlocked
from singleplayer_bridge.restore_progress import RestoreProgress, current_restore, exclusive_backup

_server = None
_world = None
_patches = []


def bridge():
    instance = _server.get_plugin_instance('singleplayer_bridge')
    if instance is None:
        raise RuntimeError(tr('error.singleplayer_bridge_is_not_loaded'))
    return instance.plugin


def binding(config):
    world = Path(_world).resolve(strict=True)
    if not (world / 'level.dat').is_file() or Path(config.server_root).resolve() != world.parent:
        raise RuntimeError(tr('error.chunk_backup_server_root_differs_from_the_bound_world_parent'))
    storage = Path(config.storage_root).absolute()
    if storage.resolve() == world or storage.resolve().is_relative_to(world):
        raise RuntimeError(tr('error.chunk_backup_storage_must_be_outside_the_world'))
    checked_path(storage.parent, storage.name)
    from singleplayer_bridge.profiles import read_json
    profile = Path.cwd()
    if (profile / 'profile.json').is_file():
        if (Path(read_json(profile / 'profile.json')['world_path']).resolve() != world
                or not storage.resolve().is_relative_to(profile.resolve())):
            raise RuntimeError(tr('error.chunk_backup_store_must_stay_inside_the_current_world_profile'))
    marker = storage / '.singleplayer-world.json'
    checked_path(storage, marker.name)
    if not marker.is_file() or Path(read_json(marker)['world_path']).resolve() != world:
        raise RuntimeError(tr('error.chunk_backup_store_is_not_bound_to_this_world_run_setup_chunk_backup_py'))
    roots = [checked_path(storage, getattr(config, key)) for key in ('static_storage', 'dynamic_storage', 'overwrite_storage')]
    if any(a == b or a.is_relative_to(b) or b.is_relative_to(a) for i, a in enumerate(roots) for b in roots[i + 1:]):
        raise RuntimeError(tr('error.chunk_backup_slot_directories_must_not_overlap'))
    for dimension in (config.backup.dimension or {}).values():
        if dimension['world_name'] != world.name:
            raise RuntimeError(tr('error.chunk_backup_dimension_belongs_to_another_world'))
        for folder in dimension['region_folder']:
            checked_path(world, folder)
    for extension, folders in (config.backup.player_data or {}).items():
        if extension not in {'.dat', '.json'}:
            raise RuntimeError(tr('error.unsupported_chunk_backup_player_data_extension'))
        for folder in folders:
            target = checked_path(world.parent, folder)
            if target == world or not target.is_relative_to(world):
                raise RuntimeError(tr('error.chunk_backup_player_data_leaves_the_bound_world'))
    state = bridge().snapshot()
    if state.get('session'):
        if Path(state['world_path']).resolve() != world:
            raise RuntimeError(tr('error.connected_world_differs_from_the_chunk_backup_binding'))
    else:
        check_unlocked(world)
    return world


class ChunkServer:
    def __init__(self, server, world, restoring):
        self.server, self.world, self.restoring = server, world, restoring
        self.closing_session = None

    def __getattr__(self, name):
        return getattr(self.server, name)

    def is_server_running(self):
        return bool(bridge().snapshot().get('session'))

    def execute(self, command):
        bridge().execute_checked(self.server, command)

    def stop(self):
        state = bridge().snapshot()
        if not state.get('session'):
            check_unlocked(self.world)
            return False
        if Path(state['world_path']).resolve() != self.world:
            raise RuntimeError(tr('error.restore_lost_its_world_connection'))
        self.closing_session = state['session']
        current_restore.get().update('saving')
        bridge().execute_checked(self.server, '__bridge_save_and_quit__')
        return True

    def wait_until_stop(self):
        if self.closing_session:
            bridge().wait_world_closed(self.closing_session, timeout=60)
            deadline = time.monotonic() + 10
            while self.server.is_server_running():
                if time.monotonic() >= deadline:
                    raise RuntimeError(tr('error.proxy_did_not_stop_after_world_shutdown'))
                time.sleep(0.05)
        check_unlocked(self.world)

    def start(self):
        progress = current_restore.get()
        if progress is not None and getattr(progress, 'player_error', None):
            raise RuntimeError(progress.player_error)
        self.server.logger.info('Chunk Backup task finished; enter the singleplayer world manually after the restore UI completes')
        return False


def patch(owner, name, make_wrapper):
    original = getattr(owner, name)
    wrapper = make_wrapper(original)
    setattr(owner, name, wrapper)
    _patches.append((owner, name, wrapper, original))


def position_wrapper(original):
    @functools.wraps(original)
    def get_position(getter, name):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_]{3,16}', name):
            raise RuntimeError(tr('error.invalid_chunk_backup_player_name'))
        binding(getter.config)
        result = bridge().execute_checked(_server, '__bridge_player_data__ ' + name)
        data = json.loads(result['text'])
        if (data.get('player') != name or not isinstance(data.get('dimension'), str)
                or not re.fullmatch(r'[a-z0-9_.-]+:[a-z0-9_./-]+', data['dimension'])
                or any(type(data.get(key)) not in (int, float) or not math.isfinite(data[key]) for key in ('x', 'y', 'z'))):
            raise RuntimeError(tr('error.invalid_bridge_player_position'))
        from chunk_backup.types.point import Point3D
        return {'position': Point3D(data['x'], data['y'], data['z']), 'dimension': data['dimension']}
    return get_position


def task_wrapper(original, restoring):
    @functools.wraps(original)
    def run(task):
        with exclusive_backup():
            progress = None
            token = None
            old_server = task.server
            if restoring:
                backup_id = task.ctx.get('backup_id')
                progress = RestoreProgress(bridge().restore_progress_context(), _world, backup_id, _server.logger)
                progress.data['provider'] = 'chunk_backup'
                progress.rolled_back = False
                token = current_restore.set(progress)
                progress.update('checking')
            try:
                world = binding(task.config)
                if not restoring:
                    commands = task.config.server.commands
                    if (not task.config.server.turn_off_auto_save or commands.auto_save_off != 'save-off'
                            or commands.save_all_worlds != 'save-all flush' or commands.auto_save_on != 'save-on'):
                        raise RuntimeError(tr('error.chunk_backup_requires_save_off_save_all_flush_save_on_for_confirmed_singleplayer_backups'))
                if not restoring and bridge().snapshot().get('paused'):
                    raise RuntimeError(tr('error.world_paused_resume_before_creating_a_chunk_backup'))
                task.server = ChunkServer(old_server, world, restoring)
                result = original(task)
                if progress is not None:
                    if progress.rolled_back:
                        progress.update('failed', 'failed', tr('restore.cb_rolled_back'))
                    else:
                        progress.finish()
                return result
            except Exception as exc:
                if progress is not None:
                    progress.update('failed', 'failed', str(exc))
                # Upstream's error callback must not restart the proxy after a failed restore.
                if restoring and hasattr(exc, 'need_start'):
                    exc.need_start = False
                raise
            finally:
                task.server = old_server
                if token is not None:
                    current_restore.reset(token)
    return run


def region_wrapper(original):
    @functools.wraps(original)
    def restore(manager, info):
        progress = current_restore.get()
        if progress is not None:
            progress.region_attempts = getattr(progress, 'region_attempts', 0) + 1
        world = binding(manager.config)
        check_unlocked(world)
        slot = manager.backup_slot
        if slot != manager.config.overwrite_storage and not re.fullmatch(r'slot[1-9][0-9]*', slot):
            raise RuntimeError(tr('error.invalid_chunk_backup_slot'))
        relative = slot if slot == manager.config.overwrite_storage else Path(manager.region_storage) / slot
        check_tree(checked_path(manager.storage_root, relative))
        for dimension in info.dimension:
            for folder in manager.config.backup.dimension[dimension]['region_folder']:
                check_tree(checked_path(world, folder))
        if progress is not None:
            # Set modified before upstream creates/deletes/merges any target files.
            rollback = progress.region_attempts > 1
            progress.data['backup_id'] = int(slot[4:]) if slot.startswith('slot') else None
            progress.update('restoring')
            if rollback:
                progress.rolled_back = True
                progress.update('rolling_back')
        result = original(manager, info)
        if progress is not None:
            progress.exported = True
        return result
    return restore


def player_wrapper(original):
    @functools.wraps(original)
    def restore(manager, *args, **kwargs):
        progress = current_restore.get()
        try:
            world = binding(manager.config)
            check_unlocked(world)
            for value in manager.uuid:
                uuid.UUID(value)
            check_tree(manager.storage_root)
            for folders in (manager.config.backup.player_data or {}).values():
                for folder in folders:
                    check_tree(checked_path(world.parent, folder))
            if progress is not None:
                progress.update('restoring')
                progress.update('player_data')
            return original(manager, *args, **kwargs)
        except Exception as exc:
            if progress is not None:
                progress.player_error = tr('restore.player_failed', str(exc))
            raise
    return restore


def on_load(server, previous):
    global _server, _world
    _server = server
    config = server.load_config_simple(default_config={'world_path': ''})
    _world = config.get('world_path', '')
    if not _world:
        raise RuntimeError(tr('error.no_chunk_backup_world_bound_run_setup_chunk_backup_py'))
    if str(server.get_plugin_metadata('chunk_backup').version) != '2.0.3':
        raise RuntimeError(tr('error.this_adapter_requires_chunk_backup_2_0_3'))
    getter = importlib.import_module('chunk_backup.utils.serverdata_getter').ServerDataGetter
    patch(getter, 'get_position_data', position_wrapper)
    for module, cls, restoring in [('create_backup_task', 'CreateBackupTask', False), ('restore_backup_task', 'RestoreBackupTask', True)]:
        owner = getattr(importlib.import_module('chunk_backup.task.backup.' + module), cls)
        patch(owner, 'run', lambda original, flag=restoring: task_wrapper(original, flag))
    region = importlib.import_module('chunk_backup.utils.region.region').Region
    original = region.restore_regions
    wrapper = region_wrapper(original)
    region.restore_regions = staticmethod(wrapper)
    _patches.append((region, 'restore_regions', wrapper, staticmethod(original)))
    player = importlib.import_module('chunk_backup.utils.backup_utils').PlayerDataFolderManager
    patch(player, 'restore_player_data', player_wrapper)
    action = importlib.import_module('chunk_backup.action.create_backup_action').CreateBackupAction
    def safety(original):
        @functools.wraps(original)
        def run(action):
            progress = current_restore.get()
            if progress is not None:
                progress.update('safety_backup')
            world = binding(action.config)
            check_tree(action.config.storage_root)
            for dimension in action.backup_info.dimension:
                for folder in action.config.backup.dimension[dimension]['region_folder']:
                    check_tree(checked_path(world, folder))
            return original(action)
        return run
    patch(action, 'run', safety)
    server.logger.info('Chunk Backup 2.0.3 singleplayer adapter ready (saved shutdown, restore progress and world lock)')


def on_unload(server):
    for owner, name, wrapper, original in reversed(_patches):
        if getattr(owner, name) is wrapper:
            setattr(owner, name, original)
    _patches.clear()
