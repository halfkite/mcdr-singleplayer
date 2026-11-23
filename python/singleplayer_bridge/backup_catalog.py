"""Read-only catalog of one world's Prime Backup and Chunk Backup snapshots.

The edit-screen viewer lists both stores at once, so each store reports its own
failure instead of hiding the other one. Nothing here imports MCDR or an upstream
backup plugin, which is what lets the catalog run while the game is closed.
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from .backup_guard import checked_path
from .i18n import tr
from .profiles import child, read_json

SLOT = re.compile(r'slot[1-9]\d*')
INFO_LIMIT = 262144
KINDS = (('dynamic', 'dynamic_storage'), ('static', 'static_storage'))


def _error(key):
    return 'mcdr-singleplayer.catalog.' + key


# 上游翻译标记的兜底文案：语言文件比模块旧时 tr() 会退回键名，这里仍有可读文字。
FALLBACK = {
    'prime.pre_restore_comment': 'Automatic backup before restoring to #%s',
    'prime.pre_restore_comment_latest': 'Automatic backup before restore',
}


def _label(key, *args):
    """本地化的界面文案，并在语言文件偏旧时仍给出可读结果。"""
    name = 'mcdr-singleplayer.' + key
    template = tr(name)
    if template == name:
        template = FALLBACK.get(key, name)
    if not args:
        return template
    try:
        return template % args
    except (TypeError, ValueError):
        return FALLBACK.get(key, name) % args


def _json(value, fallback):
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if isinstance(parsed, type(fallback)) else fallback


def _relative(profile, raw):
    """Resolve a configured store so it can never leave the world profile."""
    raw = Path(str(raw))
    storage = raw if raw.is_absolute() else Path(profile) / raw
    try:
        # ``..`` survives relative_to, so both sides must be resolved first.
        return storage.resolve().relative_to(Path(profile).resolve())
    except (ValueError, OSError):
        return None


def _store(profile, plugin):
    path = checked_path(profile, f'config/{plugin}/config.json')
    if not path.is_file():
        raise RuntimeError(_error('missing_' + plugin))
    return read_json(path), path


# 上游把「回档前保护备份」之类的备注存成 __pb_translated__:<键>[:参数]，
# 由它自己的语言文件渲染。这里不引入上游，只按它的键给出等价文案。
TRANSLATED = re.compile(r'__pb_translated__:(\w+)(?::(.*))?')
COMMENT_KEYS = {'pre_restore': 'prime.pre_restore_comment'}


def _comment(raw, backup_id):
    """Turn an upstream translated comment marker into readable text."""
    text = str(raw or '')
    match = TRANSLATED.fullmatch(text)
    if match is None:
        return text
    key = COMMENT_KEYS.get(match.group(1))
    if key is None:
        return text
    if match.group(2):
        return _label(key, match.group(2))
    return _label(key + '_latest')


def _error(key, *args):
    """返回给界面的失败原因；界面按语言键翻译，所以这里只拼键名。"""
    text = 'mcdr-singleplayer.catalog.' + key
    return text.format(*args) if args else text


def prime_rows(profile, world):
    """Read only this world's records, including temporary safety backups."""
    name = Path(world).name
    config, _ = _store(profile, 'prime_backup')
    relative = _relative(profile, config.get('storage_root', './pb_files'))
    if relative is None:
        raise RuntimeError(_error('prime_outside_profile'))
    database = checked_path(checked_path(profile, relative), 'prime_backup.db')
    if not database.is_file():
        raise RuntimeError(_error('missing_prime_database'))
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute(
            'SELECT id, timestamp, creator, comment, targets, tags, file_raw_size_sum '
            'FROM backup ORDER BY id DESC').fetchall()
    result = []
    for backup_id, timestamp, creator, comment, targets, tags, size in rows:
        # 只列属于这个存档的备份，避免同一数据库里的其它存档混进来。
        if _json(targets, []) != [name]:
            continue
        result.append(dict(ref='prime:' + str(backup_id), id=backup_id, kind='prime',
                           date=datetime.fromtimestamp(int(timestamp or 0)).strftime('%Y-%m-%d %H:%M'),
                           comment=_comment(comment, backup_id), operator=str(creator or ''),
                           dimensions=[], size=int(size or 0),
                           temporary=bool(_json(tags, {}).get('temporary')),
                           restorable=True, reason=''))
    return dict(backups=result, error='')


def _info(slot):
    """One slot descriptor; anything unreadable or oversized is treated as absent."""
    try:
        path = checked_path(slot, 'info.json')
        if path.stat().st_size > INFO_LIMIT:
            return None
        value = read_json(path)
    except (OSError, ValueError, RuntimeError):
        return None
    return value if isinstance(value, dict) else None


def _reason(config, world, dimensions, backup_type):
    """Why a slot cannot be restored, or '' when it can.

    ``type=chunk``（按选区备份）同样可以离线回档：上游恢复时就是把槽位里的区域
    文件复制回世界，选区备份只是少了几个文件，复制已有的部分即可，不需要上游的
    合并逻辑。真正不能处理的是 ``custom``（组合备份），它由上游把多份子备份拼在
    一起，离线路径不猜测这种结构。
    """
    if backup_type == 'custom':
        return _error('custom_type')
    if backup_type not in ('region', 'chunk', ''):
        return _error('unknown_type')
    if not dimensions:
        return _error('no_dimension')
    bound = Path(str(config.get('server_root') or ''))
    if not bound.is_absolute() or not Path(world).is_dir():
        return _error('store_moved')
    try:
        if bound.resolve() != Path(world).parent.resolve():
            return _error('store_moved')
    except OSError:
        return _error('store_moved')
    table = (config.get('backup') or {}).get('dimension') or {}
    for item in dimensions:
        entry = table.get(item)
        if not isinstance(entry, dict) or not entry.get('region_folder'):
            return _error('unknown_dimension')
        if str(entry.get('world_name') or '') != Path(world).name:
            return _error('store_moved')
    return ''


def _entry(ref, info, config, world):
    dimensions = [str(item) for item in (info.get('dimension') or [])]
    backup_type = str(info.get('type') or '')
    reason = _reason(config, world, dimensions, backup_type)
    return dict(ref=ref, id=0, kind='chunk', date=str(info.get('date') or ''),
                comment=str(info.get('comment') or ''), operator=str(info.get('operator') or ''),
                dimensions=dimensions, size=int(info.get('total_size') or 0),
                temporary=ref == 'chunk:overwrite', restorable=not reason, reason=reason)


def chunk_rows(profile, world):
    config, _ = _store(profile, 'chunk_backup')
    relative = _relative(profile, config.get('storage_root', './cb_files'))
    if relative is None:
        raise RuntimeError(_error('chunk_outside_profile'))
    storage = checked_path(profile, relative)
    if not storage.is_dir():
        raise RuntimeError(_error('missing_chunk_store'))
    rows = []
    for kind, key in KINDS:
        base = checked_path(storage, str(config.get(key) or key))
        if not base.is_dir():
            continue
        for slot in sorted(base.iterdir(), key=lambda item: item.name):
            if not slot.is_dir() or not SLOT.fullmatch(slot.name):
                continue
            info = _info(slot)
            if info is not None:
                rows.append(_entry('chunk:' + kind + '/' + slot.name, info, config, world))
    overwrite = checked_path(storage, str(config.get('overwrite_storage') or 'overwrite'))
    info = _info(overwrite) if overwrite.is_dir() else None
    if info is not None:
        rows.append(_entry('chunk:overwrite', info, config, world))
    # 最新的排在最前面；同一天按槽位名倒序，顺序始终稳定。
    rows.sort(key=lambda row: (row['date'], row['ref']), reverse=True)
    return dict(backups=rows, error='')


def paths(common, name):
    """解析存档的插件目录与存档目录。

    存档目录优先取 profile.json 里记录的真实路径：像 halfmasa 这类模组会把存档根
    重定向到游戏目录之外，只按 ``<gameDir>/saves`` 拼路径会找不到存档。
    """
    common = Path(common).resolve(strict=True)
    if common.name != 'mcdr-singleplayer':
        raise ValueError('Invalid MCDR Singleplayer directory')
    profile = child(common / 'plugindata', name)
    metadata = profile / 'profile.json'
    if metadata.is_file():
        recorded = str(read_json(metadata).get('world_path') or '')
        if recorded:
            world = Path(recorded)
            if world.is_dir():
                return profile, world
    saves = checked_path(common.parent, 'saves')
    return profile, child(saves, name)


# 原版备份是 <存档根>/_Backups（1.20.5 起）或 <游戏目录>/backups（更早），
# 文件名 <年-月-日_时-分-秒>_<存档名>.zip，zip 内以存档文件夹名为根。
# 存档根可能被模组重定向到游戏目录之外，所以两个候选位置都要看。
VANILLA = re.compile(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})_(.+?)(?: \(\d+\))?\.zip')
VANILLA_FOLDERS = ('_Backups',)


def vanilla_folders(common, name):
    """原版备份可能存在的目录，按新到旧排列；只返回真实存在的。"""
    folder = None
    try:
        _, world = paths(common, name)
        folder = world.parent
    except Exception:  # noqa: BLE001 - 存档缺失时仍要能列出 gameDir 下的旧备份
        folder = None
    candidates = []
    if folder is not None:
        for child_name in VANILLA_FOLDERS:
            candidates.append(checked_path(folder, child_name))
    # 旧版把备份放在游戏目录的 backups 下。
    candidates.append(checked_path(Path(common).resolve(strict=True).parent, 'backups'))
    seen = []
    for candidate in candidates:
        if candidate not in seen:
            seen.append(candidate)
    return seen


def vanilla_dir(common, name):
    """创建原版备份时用的目录：优先这个存档根下的 _Backups，退到游戏目录的 backups。"""
    folders = vanilla_folders(common, name)
    for candidate in folders:
        if candidate.is_dir():
            return candidate
    return folders[0]


def vanilla_rows(common, name):
    """列出这个存档的原版备份；只按文件名归属，不读 zip 内容。"""
    rows = []
    for folder in vanilla_folders(common, name):
        if not folder.is_dir():
            continue
        for entry in sorted(folder.iterdir(), key=lambda item: item.name, reverse=True):
            if not entry.is_file():
                continue
            match = VANILLA.fullmatch(entry.name)
            if match is None or match.group(2) != name:
                continue
            stamp = datetime.strptime(match.group(1), '%Y-%m-%d_%H-%M-%S')
            rows.append(dict(ref='vanilla:' + entry.name, id=0, kind='vanilla',
                             date=stamp.strftime('%Y-%m-%d %H:%M'), comment='', operator='',
                             dimensions=[], size=entry.stat().st_size, temporary=False,
                             restorable=True, reason='', path=str(entry)))
    # 同一个文件名可能同时出现在新旧两个位置，保留最新的那一份。
    unique = {}
    for row in rows:
        unique.setdefault(row['ref'], row)
    return dict(backups=sorted(unique.values(), key=lambda row: (row['date'], row['ref']), reverse=True),
                error='')


def catalog(common, name):
    """Both stores, each carrying its own failure instead of one shared one."""
    profile, world = paths(common, name)
    result = dict(world=name, world_path=str(world), prime=dict(backups=[], error=''),
                  chunk=dict(backups=[], error=''), vanilla=dict(backups=[], error=''))
    for key, loader in (('prime', prime_rows), ('chunk', chunk_rows)):
        try:
            if not profile.is_dir():
                raise RuntimeError(_error('missing_profile'))
            result[key] = loader(profile, world)
        except Exception as exc:  # noqa: BLE001 - the viewer shows any store failure verbatim
            text = str(exc)
            result[key]['error'] = text if text.startswith('mcdr-singleplayer.') else _error('unreadable')
    # 原版备份不依赖插件配置，独立于前两个备份库读取。
    try:
        result['vanilla'] = vanilla_rows(common, name)
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        result['vanilla']['error'] = text if text.startswith('mcdr-singleplayer.') else _error('unreadable_vanilla')
    return result
