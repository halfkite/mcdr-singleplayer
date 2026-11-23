"""离线创建 PB / CB / 原版三类备份，供界面上的「立即备份」按钮使用。

游戏正关着存档时不能让备份插件跑在线任务，所以这里按各自存储布局直接写：
PB 用官方 CLI 的 ``make``（配置和数据库都是它自己的格式，不自己造），
CB 按文档的槽位布局自己写（会前移旧槽位，语义与上游一致），
原版由 :mod:`vanilla_restore` 处理。
"""
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .backup_catalog import KINDS, SLOT, _relative, _store, paths
from .backup_guard import checked_path
from .profiles import read_json, write_json

# CB 槽位里各维度的区域子目录；与上游 config 的 region_folder 对应。
CB_REGION_KINDS = ('region', 'entities', 'poi')
DEFAULT_MAX_SLOT = 10


def _world(common, name):
    profile, world = paths(common, name)
    if not world.is_dir() or not checked_path(world, 'level.dat').is_file():
        raise FileNotFoundError('mcdr-singleplayer.catalog.missing_world')
    return profile, world


def prime(common, name, comment=''):
    """用 Prime Backup 自己的 CLI 建备份。

    PB 的存储是它自己的数据库和文件池，自己拼一份会做出它认不出的备份，
    所以这里调官方 CLI 的 make；需要 MCDR 侧解析出的配置和数据库路径。
    """
    profile, world = _world(common, name)
    config, config_path = _store(profile, 'prime_backup')
    relative = _relative(profile, config.get('storage_root', './pb_files'))
    if relative is None:
        raise RuntimeError('mcdr-singleplayer.catalog.prime_outside_profile')
    storage = checked_path(profile, relative)
    database = checked_path(storage, 'prime_backup.db')
    if not database.is_file():
        raise RuntimeError('mcdr-singleplayer.catalog.missing_prime_database')
    pyz = _prime_pyz(profile)
    source = str(world.parent)
    result = _run_prime_cli(pyz, database, config_path, source, comment)
    return dict(path=storage.as_posix(), database=str(database), output=result[-400:])


def _prime_pyz(profile):
    """找到 PB 本体：存档自己的 plugins 与共用 plugins 都看一遍。"""
    plugins = Path(profile).parents[1] / 'plugins'
    if plugins.is_dir():
        for entry in sorted(plugins.iterdir()):
            if entry.is_file() and 'PrimeBackup' in entry.name and entry.suffix in ('.pyz', '.mcdr'):
                return entry
    raise FileNotFoundError('mcdr-singleplayer.catalog.missing_prime_backup')


def _run_prime_cli(pyz, database, config_path, source_root, comment):
    """调用 PB 的 CLI。失败时把它的输出带回去，方便直接看到原因。"""
    command = [sys.executable, str(pyz), '--db', str(database), '--config', str(config_path),
               'make', comment or '', '--source-root', source_root]
    finished = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace',
                              timeout=1800)
    output = (finished.stdout or '') + (finished.stderr or '')
    if finished.returncode != 0:
        raise RuntimeError('mcdr-singleplayer.catalog.prime_backup_failed::' + output.strip()[-400:])
    return output


def chunk(common, name, comment='', dimension=None, bounds=None):
    """按 CB 的槽位布局建一份区域备份：写进 slot1，旧槽位依次后移。

    ``bounds`` 是 ``(x1, z1, x2, z2)`` 的区块坐标范围（与上游 ``pmake`` 的选election一致）；
    给了范围就只备份与该范围重叠的 region 文件，并记为 ``type=chunk`` 的部分备份；
    不给范围则备份全部维度，记为可完整回档的 ``type=region``。
    """
    profile, world = _world(common, name)
    config, _ = _store(profile, 'chunk_backup')
    relative = _relative(profile, config.get('storage_root', './cb_files'))
    if relative is None:
        raise RuntimeError('mcdr-singleplayer.catalog.chunk_outside_profile')
    storage = checked_path(profile, relative)
    if not storage.is_dir():
        storage.mkdir(parents=True, exist_ok=True)
    backup = config.get('backup', {})
    maximum = int(backup.get('max_dynamic_slot') or DEFAULT_MAX_SLOT)
    table = backup.get('dimension', {})
    selected = [dimension] if dimension else list(table)
    for item in selected:
        if item not in table:
            raise ValueError('mcdr-singleplayer.catalog.unknown_dimension')
    region = _normalize(bounds) if bounds else None
    base = checked_path(storage, str(config.get('dynamic_storage') or 'dynamic_storage'))
    base.mkdir(parents=True, exist_ok=True)
    _shift_slots(base, maximum)

    slot = checked_path(base, 'slot1')
    slot.mkdir(parents=True, exist_ok=True)
    root = checked_path(slot, name)
    total = 0
    written = []
    for dimension_name in selected:
        folders = table[dimension_name].get('region_folder') or []
        for relative_folder in folders:
            kind = str(relative_folder).rsplit('/', 1)[-1]
            if kind not in CB_REGION_KINDS:
                continue
            source = checked_path(world, relative_folder)
            if not source.is_dir():
                continue
            target = checked_path(root, relative_folder)
            target.mkdir(parents=True, exist_ok=True)
            kept = 0
            for item in sorted(source.iterdir()):
                if not item.is_file() or item.suffix != '.mca':
                    continue
                # 给了范围就只留与范围重叠的区域文件。
                if region is not None and not _overlaps(item.name, region):
                    continue
                shutil.copy2(item, target / item.name)
                total += item.stat().st_size
                written.append(item.name)
                kept += 1
            if kept:
                # 上游槽位里带一份 index.json 作为区域清单。
                write_json(checked_path(target, 'index.json'), {'type': 'region'})
    if not written:
        shutil.rmtree(slot, ignore_errors=True)
        raise ValueError('mcdr-singleplayer.catalog.empty_chunk_selection')
    players = checked_path(world, 'players')
    if players.is_dir():
        _copy_tree(players, checked_path(root, 'players'))
    info = dict(date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                type='chunk' if region is not None else 'region',
                operator='mcdr-singleplayer.backup.viewer.operator',
                dimension=selected, comment=comment or '', total_size=total,
                version_created='offline', minecraft_version='')
    if region is not None:
        info['name'] = f'{region[0]},{region[1]} -> {region[2]},{region[3]}'
        info['top_left'] = {'x': region[0], 'z': region[1]}
        info['bottom_right'] = {'x': region[2], 'z': region[3]}
    write_json(checked_path(slot, 'info.json'), info)
    return dict(slot=str(slot), files=len(written), size=total,
                dimension=selected[0] if len(selected) == 1 else '', region=region)


def _normalize(bounds):
    """把两个角点规范成 (min_x, min_z, max_x, max_z)，顺序随意。"""
    x1, z1, x2, z2 = (int(value) for value in bounds)
    return min(x1, x2), min(z1, z2), max(x1, x2), max(z1, z2)


REGION_FILE = re.compile(r'r\.(-?\d+)\.(-?\d+)\.mca')


def _overlaps(file_name, region):
    """region 文件覆盖 32x32 个区块，与所选范围有交集就保留。"""
    match = REGION_FILE.fullmatch(file_name)
    if match is None:
        return False
    min_x, min_z = int(match.group(1)) * 32, int(match.group(2)) * 32
    max_x, max_z = min_x + 31, min_z + 31
    return not (max_x < region[0] or min_x > region[2] or max_z < region[1] or min_z > region[3])


def _copy_tree(source, target):
    for item in sorted(Path(source).rglob('*')):
        if not item.is_file():
            continue
        destination = Path(target) / item.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, destination)


def _shift_slots(base, maximum):
    """把现有 slot 整体后移一位，最后一位超出上限时丢弃，语义与上游一致。"""
    slots = sorted((int(entry.name[len('slot'):]), entry) for entry in base.iterdir()
                   if entry.is_dir() and SLOT.fullmatch(entry.name))
    if not slots:
        return
    # 先删掉会越界的最旧槽位，再从大往小改名，避免互相覆盖。
    for number, path in slots:
        if number >= maximum:
            shutil.rmtree(path, ignore_errors=True)
    remaining = [(number, path) for number, path in slots if number < maximum]
    for number, path in sorted(remaining, key=lambda item: item[0], reverse=True):
        target = base / f'slot{number + 1}'
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        path.rename(target)
