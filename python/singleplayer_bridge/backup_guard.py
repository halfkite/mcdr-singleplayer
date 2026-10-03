"""Shared save-lock and path checks for optional backup adapters."""
from singleplayer_bridge.i18n import tr
import os
import stat
from pathlib import Path


def check_unlocked(world):
    lock_path = Path(world) / 'session.lock'
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
        raise RuntimeError(tr('error.world_session_lock_is_still_held_save_and_quit_before_restoring')) from exc


def checked_path(root, relative):
    root = Path(root).absolute()
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or '..' in relative.parts:
        raise RuntimeError(tr('error.backup_path_is_outside_its_bound_directory'))
    target = root / relative
    for candidate in (root, *reversed(target.parents), target):
        if candidate.exists() or candidate.is_symlink():
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise RuntimeError(tr('error.backup_paths_cannot_contain_symbolic_links_or_junctions'))
    if not target.resolve().is_relative_to(root.resolve()):
        raise RuntimeError(tr('error.backup_path_is_outside_its_bound_directory'))
    return target


def check_tree(path):
    """Refuse links inside the exact source/target trees before upstream file operations."""
    path = Path(path)
    checked_path(path.parent, path.name)
    if path.is_dir():
        for directory, folders, files in os.walk(path, followlinks=False):
            for name in folders + files:
                checked_path(Path(directory), name)
