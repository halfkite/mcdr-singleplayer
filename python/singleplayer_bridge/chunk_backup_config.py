"""Prepare a separate Chunk Backup store; never adopt another world's backup slots."""
from singleplayer_bridge.i18n import tr
from pathlib import Path

from .backup_guard import checked_path
from .profiles import read_json, write_json


def installed(common):
    from .plugin_archives import archives
    if not (Path(common) / 'plugins').is_dir():
        return False
    return any(version == '2.0.3' for _, version in archives(common, 'chunk_backup'))


def rebind(config, profile, world):
    config['server_root'] = str(world.parent)
    config['storage_root'] = './cb_files'
    config['log_storage'] = str(profile.parent.parent / 'log' / world.name / 'chunk_backup')
    backup = config.setdefault('backup', {})
    if not backup.get('dimension'):
        backup['dimension'] = {name: dict(integer_id=value, world_name=world.name, description=name,
            region_folder=[f'dimensions/minecraft/{name.split(":")[1]}/{kind}' for kind in ('poi', 'entities', 'region')])
            for name, value in [('minecraft:overworld', 0), ('minecraft:the_nether', -1), ('minecraft:the_end', 1)]}
    for dimension in backup['dimension'].values():
        dimension['world_name'] = world.name
    backup['player_data'] = {'.json': [f'{world.name}/players/advancements', f'{world.name}/players/stats'],
                             '.dat': [f'{world.name}/players/playerdata']}
    config['minecraft_version'] = '26.3'
    return config


def prepare(profile, world):
    profile, world = Path(profile).resolve(), Path(world).resolve(strict=True)
    if not (world / 'level.dat').is_file():
        raise ValueError(tr('error.world_has_no_level_dat'))
    store = profile / 'cb_files'
    checked_path(profile, 'cb_files')
    marker = store / '.singleplayer-world.json'
    if marker.exists():
        if Path(read_json(marker)['world_path']).resolve() != world:
            raise ValueError(tr('error.chunk_backup_store_belongs_to_another_world'))
    elif store.exists() and any(store.iterdir()):
        raise ValueError(tr('error.existing_chunk_backup_store_has_no_world_binding_cannot_adopt_its_backups_automatically'))
    else:
        write_json(marker, {'world_path': str(world)})
    config_path = profile / 'config/chunk_backup/config.json'
    if not config_path.exists():
        write_json(config_path, rebind({}, profile, world))
    write_json(profile / 'config/singleplayer_chunk_backup/config.json', {'world_path': str(world)})
