"""Filesystem bounds and the same advisory session lock used by Minecraft's FileChannel."""
from singleplayer_bridge.i18n import tr
import stat
import os
import time
from pathlib import Path
from singleplayer_bridge.backup_guard import check_unlocked, checked_path


def check_binding(world, config, allow_incomplete=False):
    original = Path(world).absolute()
    checked_path(original.parent, original.name)
    world = Path(world).resolve(strict=True)
    if not world.is_dir() or (not allow_incomplete and not (world / 'level.dat').is_file()):
        raise RuntimeError(tr('error.bound_directory_is_not_an_existing_minecraft_world'))
    if Path(config.source_path).resolve() != world.parent or list(config.backup.targets) != [world.name]:
        raise RuntimeError(tr('error.prime_backup_source_root_targets_differ_from_the_bound_world_run_setup_prime_backup_py'))
    storage = Path(config.storage_path).resolve()
    if storage == world or storage.is_relative_to(world):
        raise RuntimeError(tr('error.backup_storage_must_be_outside_the_bound_world'))
    return world


def move_world_to_trash(world, target, progress=None, timeout=10):
    """Only rename: open child directories can deny a move despite sharing DELETE.

    Publish a conservative modified flag before the atomic operation, so a crash
    cannot expose a moved world. A failed rename leaves the source unchanged and
    can safely restore the previous flag before waiting or reporting failure.
    """
    deadline = time.monotonic() + timeout
    was_modified = bool(progress and progress.data['modified'])
    while True:
        if progress is not None:
            progress.update('restoring')
        try:
            os.rename(world, target)
            return
        except OSError as exc:
            retryable = getattr(exc, 'winerror', None) in (5, 32, 33)
            detail = tr('error.restore_directory_still_in_use', Path(world).name) if retryable else str(exc)
            if progress is not None:
                progress.data['modified'] = was_modified
                progress.update('waiting_files', detail=detail)
            if not retryable:
                raise
            if time.monotonic() >= deadline:
                raise RuntimeError(detail) from exc
            time.sleep(0.2)


def check_backup(world, backup):
    if backup.targets != [world.name]:
        raise RuntimeError(tr('error.this_backup_belongs_to_a_different_world_restoration_cancelled'))
    for file in backup.files:
        relative = Path(file.path)
        destination = (world.parent / relative).resolve()
        if relative.is_absolute() or '..' in relative.parts or not destination.is_relative_to(world):
            raise RuntimeError(tr('error.backup_file_is_outside_the_bound_world'))
        if stat.S_ISLNK(file.mode):
            raise RuntimeError(tr('error.restoring_backups_containing_symbolic_links_is_not_supported_by_this_adapter'))
    if not any(Path(file.path) == Path(world.name) / 'level.dat' and stat.S_ISREG(file.mode) for file in backup.files):
        raise RuntimeError(tr('error.restore_backup_has_no_level_dat'))
