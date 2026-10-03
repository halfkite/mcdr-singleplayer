"""Filesystem bounds and the same advisory session lock used by Minecraft's FileChannel."""
from singleplayer_bridge.i18n import tr
import stat
from pathlib import Path
from singleplayer_bridge.backup_guard import check_unlocked


def check_binding(world, config):
    world = Path(world).resolve(strict=True)
    if not world.is_dir() or not (world / 'level.dat').is_file():
        raise RuntimeError(tr('error.bound_directory_is_not_an_existing_minecraft_world'))
    if Path(config.source_path).resolve() != world.parent or list(config.backup.targets) != [world.name]:
        raise RuntimeError(tr('error.prime_backup_source_root_targets_differ_from_the_bound_world_run_setup_prime_backup_py'))
    storage = Path(config.storage_path).resolve()
    if storage == world or storage.is_relative_to(world):
        raise RuntimeError(tr('error.backup_storage_must_be_outside_the_bound_world'))
    return world


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
