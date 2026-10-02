"""Filesystem bounds and the same advisory session lock used by Minecraft's FileChannel."""
import os
import stat
from pathlib import Path


def check_binding(world, config):
    world = Path(world).resolve(strict=True)
    if not world.is_dir() or not (world / 'level.dat').is_file():
        raise RuntimeError('Bound directory is not an existing Minecraft world')
    if Path(config.source_path).resolve() != world.parent or list(config.backup.targets) != [world.name]:
        raise RuntimeError('Prime Backup source_root/targets differ from the bound world; run setup_prime_backup.py')
    storage = Path(config.storage_path).resolve()
    if storage == world or storage.is_relative_to(world):
        raise RuntimeError('Backup storage must be outside the bound world')
    return world


def check_backup(world, backup):
    if backup.targets != [world.name]:
        raise RuntimeError('This backup belongs to a different world; restoration cancelled')
    for file in backup.files:
        relative = Path(file.path)
        destination = (world.parent / relative).resolve()
        if relative.is_absolute() or '..' in relative.parts or not destination.is_relative_to(world):
            raise RuntimeError('Backup file is outside the bound world')
        if stat.S_ISLNK(file.mode):
            raise RuntimeError('Restoring backups containing symbolic links is not supported by this adapter')


def check_unlocked(world):
    lock_path = world / 'session.lock'
    if not lock_path.exists():
        return
    try:
        with lock_path.open('r+b', buffering=0) as stream:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.lockf(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.lockf(stream.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise RuntimeError('World session.lock is still held; save and quit before restoring') from exc
