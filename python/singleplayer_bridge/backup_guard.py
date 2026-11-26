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


# Windows 把下面这些名字当设备，任何目录下都指向设备而不是普通文件；写成 ``NUL``
# 之类的相对路径会绕过目录边界检查（写入被静默丢弃或写到别处）。备份文件名由存档
# 名和备份库决定，正常永远不会用到它们，直接拒绝。
WINDOWS_DEVICE_NAMES = frozenset({
    'con', 'prn', 'aux', 'nul', 'conin$', 'conout$',
    *(f'com{number}' for number in range(1, 10)),
    *(f'lpt{number}' for number in range(1, 10)),
})


def checked_path(root, relative):
    """Resolve one path strictly inside ``root``.

    ``root`` 现在统一走 ``resolve()``：只调用 ``absolute()`` 时，传进来的 root 若自带
    ``..``（例如 ``<base>/real/../outside``），拼出的 target 与 root 都含 ``..``，
    两侧比较会一起通过，实际路径却已经越出 ``real/``。``resolve()`` 会先消除这些
    相对段，比较才有意义。root 不存在时 resolve 不会抛错（strict 默认关闭），
    调用方传尚待创建的目录也安全。
    """
    root = Path(root).resolve()
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or '..' in relative.parts:
        raise RuntimeError(tr('error.backup_path_is_outside_its_bound_directory'))
    if any(_is_windows_hazard(part) for part in relative.parts):
        raise RuntimeError(tr('error.backup_path_is_outside_its_bound_directory'))
    target = root / relative
    for candidate in (root, *reversed(target.parents), target):
        if candidate.exists() or candidate.is_symlink():
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                raise RuntimeError(tr('error.backup_paths_cannot_contain_symbolic_links_or_junctions'))
    if not target.resolve().is_relative_to(root):
        raise RuntimeError(tr('error.backup_path_is_outside_its_bound_directory'))
    return target


def _is_windows_hazard(part):
    """Windows-only names that never denote a file inside the directory.

    备用数据流用 ``名称:流`` 的形式给同一文件挂额外数据；磁盘不允许在文件名里用
    ``:``，所以出现它就一定不是普通备份文件。
    """
    if os.name != 'nt':
        return False
    if ':' in part:
        return True
    # 设备名比较不区分大小写，且带扩展名的 ``NUL.txt`` 同样是设备。
    return part.split('.')[0].lower() in WINDOWS_DEVICE_NAMES


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
