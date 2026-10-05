"""Shared save-lock and path checks for optional backup adapters."""
from singleplayer_bridge.i18n import tr
import os
import stat
import time
import functools
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


@functools.lru_cache(maxsize=1)
def _windows_file_api():
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    return kernel


def _check_replaceable(path):
    """Probe delete/write sharing without renaming, writing or deleting anything."""
    if os.name != 'nt':
        return
    import ctypes
    kernel = _windows_file_api()
    directory = path.is_dir()
    access = 0x00010000 | (0 if directory else 0x40000000)  # DELETE, GENERIC_WRITE
    handle = kernel.CreateFileW(str(path.absolute()), access, 7, None, 3,
                                0x02000000 if directory else 0, None)
    if handle == ctypes.c_void_p(-1).value:
        error = ctypes.WinError(ctypes.get_last_error())
        error.filename = str(path)
        raise error
    kernel.CloseHandle(handle)


def wait_restore_ready(world, paths=None, timeout=10, progress=None):
    """Wait off the game thread, and fail before upstream can modify a locked tree."""
    world = Path(world)
    roots = [Path(path) for path in paths] if paths is not None else [world]
    for root in roots:
        check_tree(root)
    if progress is not None:
        progress.update('waiting_files')
    deadline = time.monotonic() + timeout
    while True:
        try:
            check_unlocked(world)
            for root in roots:
                if not root.exists():
                    continue
                _check_replaceable(root)
                if root.is_dir():
                    for directory, folders, files in os.walk(root, followlinks=False):
                        for name in folders + files:
                            _check_replaceable(checked_path(Path(directory), name))
            return
        except (OSError, RuntimeError) as exc:
            filename = getattr(exc, 'filename', None)
            if filename:
                try:
                    filename = Path(filename).relative_to(world).as_posix()
                except ValueError:
                    filename = Path(filename).name
                key = 'error.restore_native_library_in_use' if filename.lower().endswith('.dll') else 'error.restore_file_still_in_use'
                detail = tr(key, filename)
            else:
                detail = str(exc)
            if progress is not None:
                progress.update('waiting_files', detail=detail)
            if time.monotonic() >= deadline:
                raise RuntimeError(detail) from exc
            time.sleep(0.1)
