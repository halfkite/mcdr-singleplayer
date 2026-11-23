"""按需为当前存档创建备份插件的配置，供「创建配置」按钮使用。

这里只补配置，不安装插件、不启动 MCDR：界面在游戏里，装插件属于 MCDR 的职责。
创建后的配置与进入存档时自动写的那份一致，所以之后进游戏即可正常备份。
"""
from .backup_catalog import _relative, _store, paths
from .backup_guard import checked_path
from .profiles import ensure_profile, read_json, recommend, write_json


def _world(common, name):
    """只接受真实存在的存档，避免给人手改名后的目录凭空写配置。"""
    profile, world = paths(common, name)
    if not world.is_dir() or not checked_path(world, 'level.dat').is_file():
        raise FileNotFoundError('mcdr-singleplayer.catalog.missing_world')
    return profile, world


def prime(common, name, language='zh_cn'):
    """创建或修复 Prime Backup 配置，并返回它现在的位置。"""
    profile, world = _world(common, name)
    ensure_profile(common, world, language=language)
    recommend(profile, language=language)
    config, path = _store(profile, 'prime_backup')
    relative = _relative(profile, config.get('storage_root', './pb_files'))
    if relative is None:
        raise RuntimeError('mcdr-singleplayer.catalog.prime_outside_profile')
    return dict(config=str(path), storage=str(checked_path(profile, relative)))


def chunk(common, name):
    """创建 Chunk Backup 配置；已有配置时只做绑定校正。"""
    profile, world = _world(common, name)
    from .chunk_backup_config import rebind
    profile.mkdir(parents=True, exist_ok=True)
    write_json(profile / 'profile.json', {'world_path': str(world), 'folder': world.name})
    path = checked_path(profile, 'config/chunk_backup/config.json')
    if path.is_file():
        # 已有配置只校正存档绑定，保留用户设置的存储位置和保留策略。
        config = read_json(path)
        keep = config.get('storage_root')
        config = rebind(config, profile, world)
        if keep:
            config['storage_root'] = keep
        write_json(path, config)
    else:
        config = rebind({}, profile, world)
        write_json(path, config)
    config, _ = _store(profile, 'chunk_backup')
    relative = _relative(profile, config.get('storage_root', './cb_files'))
    if relative is None:
        raise RuntimeError('mcdr-singleplayer.catalog.chunk_outside_profile')
    storage = checked_path(profile, relative)
    storage.mkdir(parents=True, exist_ok=True)
    return dict(config=str(path), storage=str(storage))
