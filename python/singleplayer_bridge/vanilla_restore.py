"""原版备份的创建与恢复，复用原版自己的 zip 格式和命名。

原版把存档压成 ``<gameDir>/backups/<时间>_<存档名>.zip``，zip 内以存档文件夹名为根。
这里照同样的格式读写，所以备份与游戏原生的「备份此存档」互相通用，也无需任何插件。
"""
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from .backup_catalog import VANILLA, vanilla_dir, vanilla_folders
from .backup_guard import checked_path
MARKER = 'level.dat'
# 原版备份会跳过这几个目录，同名的缓存重建即可，没必要占备份体积。
SKIPPED = ('session.lock',)


def create(common, name):
    """把当前存档压成一份原版格式的备份，返回新文件路径。"""
    from .backup_catalog import paths
    _, world = paths(common, name)
    if not world.is_dir():
        raise FileNotFoundError('mcdr-singleplayer.catalog.missing_world')
    if not checked_path(world, MARKER).is_file():
        raise ValueError('mcdr-singleplayer.error.world_has_no_level_dat')
    folder = vanilla_dir(common, name)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    target = checked_path(folder, f'{stamp}_{name}.zip')
    # 同一秒重复点击会撞名：先算好基础名，再找第一个没被占用的。
    base = f'{stamp}_{name}'
    target = checked_path(folder, base + '.zip')
    index = 1
    while target.exists():
        target = checked_path(folder, f'{base} ({index}).zip')
        index += 1
    partial = target.with_name(target.name + '.partial')
    with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for item in sorted(world.rglob('*')):
            if not item.is_file() or item.name in SKIPPED:
                continue
            archive.write(item, f'{name}/{item.relative_to(world).as_posix()}')
    partial.replace(target)
    return dict(path=str(target), size=target.stat().st_size)


def locate(common, name, ref):
    """把 ``vanilla:<文件名>`` 解析回真实备份文件，拒绝跨存档或越界引用。"""
    if not ref.startswith('vanilla:'):
        raise ValueError('mcdr-singleplayer.error.invalid_vanilla_backup')
    file_name = ref.removeprefix('vanilla:')
    if Path(file_name).name != file_name:
        raise ValueError('mcdr-singleplayer.error.invalid_vanilla_backup')
    match = VANILLA.fullmatch(file_name)
    if match is None or match.group(2) != name:
        raise ValueError('mcdr-singleplayer.error.invalid_vanilla_backup')
    # 备份可能在新旧两个位置，逐个找。
    for folder in vanilla_folders(common, name):
        candidate = folder / file_name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError('mcdr-singleplayer.catalog.missing_vanilla_backup')


def _members(archive, name):
    """zip 内这个存档的条目；root 只能是存档文件夹本身，防止解到别处。"""
    root = name + '/'
    for info in archive.infolist():
        member = info.filename
        if not member.startswith(root) or member == root:
            continue
        relative = member[len(root):]
        # 绝对路径、上跳和空段都不合法，直接拒绝整份备份。
        if not relative or relative.startswith('/') or '..' in relative.split('/') or ':' in relative:
            raise ValueError('mcdr-singleplayer.error.invalid_vanilla_backup')
        yield info, relative


def restore(common, name, ref, logger=None):
    """用原版备份替换存档内容。

    原版的行为是把所选备份解回存档目录、覆盖同名文件；这里保持一致，但明确拒绝
    zip 内出现存档目录之外的条目，避免恶意或损坏的备份写到别处。
    """
    from .backup_catalog import paths
    _, world = paths(common, name)
    if not world.is_dir():
        raise FileNotFoundError('mcdr-singleplayer.catalog.missing_world')
    backup = locate(common, name, ref)
    written = 0
    with zipfile.ZipFile(backup) as archive:
        members = list(_members(archive, name))
        if not members:
            raise ValueError('mcdr-singleplayer.error.invalid_vanilla_backup')
        if not any(relative == MARKER for _, relative in members):
            raise ValueError('mcdr-singleplayer.error.vanilla_backup_has_no_level_dat')
        for info, relative in members:
            if info.is_dir():
                continue
            destination = checked_path(world, relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, open(destination, 'wb') as output:
                shutil.copyfileobj(source, output)
            written += 1
    return dict(world=str(world), backup=str(backup), files=written)
