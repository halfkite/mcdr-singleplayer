"""Migrate older bridge layouts, then import legacy MCDR world profiles."""
import logging
import shutil
import time
import uuid
from pathlib import Path

from .profiles import linked, profile_path, read_json, write_json


def checked_copy(source, target):
    source, target = Path(source), Path(target)
    if linked(source) or linked(target) or any(linked(parent) for parent in target.parents):
        raise ValueError('Migration paths cannot be links')
    if source.is_dir():
        for item in source.rglob('*'):
            if linked(item):
                raise ValueError('Legacy data contains a link; migration stopped')
        shutil.copytree(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _relocate(source, target, common):
    if linked(source):
        raise ValueError(f'Migration source cannot be a link: {source.name}')
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.move(str(source), str(target))
        return
    if source.is_dir() and target.is_dir():
        for item in list(source.iterdir()):
            _relocate(item, target / item.name, common)
        source.rmdir()
        return
    if source.is_file() and target.is_file() and source.read_bytes() == target.read_bytes():
        source.unlink()
        return
    conflict = common / 'runtime/migration-history' / f'{time.time_ns()}-{source.name}'
    conflict.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(conflict))


def organize_layout(common):
    """Keep only date/log/runtime at the shared root; shared config lives in runtime/config."""
    common = Path(common).resolve()
    for name in ('date', 'log', 'runtime'):
        directory = common / name
        if linked(directory):
            raise ValueError(f'{name} directory cannot be a link')
        directory.mkdir(exist_ok=True)

    old_config = common / 'config'
    if old_config.exists():
        _relocate(old_config, common / 'runtime/config', common)
    old_data = common / 'data'
    if old_data.exists():
        _relocate(old_data, common / 'date', common)

    for filename in ('config.json', 'config.yml', 'permission.yml', 'download-sources.json'):
        source = common / filename
        if source.exists():
            _relocate(source, common / 'runtime/config' / filename, common)
    folder_targets = {
        'plugins': 'runtime/config/plugins',
        'logs': 'log/mcdr',
        '.bridge-venv': 'runtime/.bridge-venv',
        'bridge-runtime': 'runtime/bridge-runtime',
        'python-runtime': 'runtime/python-runtime',
        'install-history': 'runtime/install-history',
        'migration-history': 'runtime/migration-history',
        'start_mcdr.ps1': 'runtime/start_mcdr.ps1',
        'runtime-install.json': 'runtime/runtime-install.json',
        '.legacy-layout.json': 'runtime/.legacy-layout.json',
        '.mcdr_restore_progress.json': 'runtime/.mcdr_restore_progress.json',
        '.mcdr_restore_locks.json': 'runtime/.mcdr_restore_locks.json',
        '.mcdr_bridge_session.json': 'runtime/.mcdr_bridge_session.json',
        '.controller.lock': 'runtime/.controller.lock',
        '.installation.lock': 'runtime/.installation.lock',
        '.migration-staging': 'date/.migration-staging',
    }
    for name, relative in folder_targets.items():
        source = common / name
        if source.exists():
            _relocate(source, common / relative, common)
    for source in list(common.glob('bootstrap-resources-*')):
        _relocate(source, common / 'runtime' / source.name, common)
    for source in list((common / 'runtime/config').glob('config.yml.before-*')):
        source.unlink()
    for name in ('bootstrap.log', 'install.log', 'controller.log', 'python-install.log'):
        source = common / name
        if source.exists():
            _relocate(source, common / 'log' / name, common)

    for source in list(common.iterdir()):
        if source.name in {'date', 'log', 'runtime'}:
            continue
        if source.is_dir() and (source / 'profile.json').is_file():
            world_name = source.name
            target = profile_path(common, world_name)
            world_log = common / 'log' / world_name
            for item in list(source.iterdir()):
                if item.is_file() and item.suffix.lower() == '.log':
                    _relocate(item, world_log / item.name, common)
            if (source / 'logs').exists():
                _relocate(source / 'logs', world_log / 'mcdr', common)
            _relocate(source, target, common)
        elif source.name.startswith('config.yml.before-'):
            # These are generated copies of MCDR defaults, not user plugin data.
            source.unlink()
        elif source.is_file() and source.suffix.lower() == '.log':
            _relocate(source, common / 'log' / source.name, common)
        else:
            _relocate(source, common / 'runtime/legacy-files' / source.name, common)


def migrate_legacy(common):
    common = Path(common).resolve()
    organize_layout(common)
    marker = common / 'runtime/.legacy-layout.json'
    if not marker.exists():
        return
    record = read_json(marker)
    if record.get('completed'):
        return
    source = Path(record['source']).resolve()
    if not source.is_dir():
        raise ValueError('Legacy MCDR directory is missing; preserve the migration marker and restore that directory first')
    if source != common and (source.is_relative_to(common) or common.is_relative_to(source)):
        raise ValueError('Legacy and destination directories cannot be nested')
    from .supervisor import lock_common
    lock = lock_common(source)
    try:
        config_dir = common / 'runtime/config'
        for name in ('config.yml', 'permission.yml', 'download-sources.json'):
            target = config_dir / name
            if (source / name).is_file() and not target.exists():
                checked_copy(source / name, target)
        plugins = source / 'plugins'
        target_plugins = config_dir / 'plugins'
        if plugins.exists() and source != common:
            if linked(plugins) or linked(target_plugins):
                raise ValueError('Plugin directories cannot be links')
            target_plugins.mkdir(exist_ok=True)
            for plugin in plugins.iterdir():
                target = target_plugins / plugin.name
                if not target.exists():
                    checked_copy(plugin, target)
        worlds = source / 'worlds'
        if linked(worlds):
            raise ValueError('Legacy profiles cannot be a link')
        for profile in sorted(worlds.iterdir()) if worlds.exists() else []:
            if not profile.is_dir() or not (profile / 'profile.json').is_file():
                continue
            target = profile_path(common, profile.name)
            metadata = read_json(profile / 'profile.json')
            if metadata.get('folder') != profile.name or Path(metadata['world_path']).name != profile.name:
                raise ValueError('Legacy profile name does not match its world binding')
            if target.exists():
                if not (target / '.legacy-import.json').is_file() or read_json(target / '.legacy-import.json').get('source') != str(profile):
                    raise ValueError('Destination profile already exists; migration will not overwrite it')
                continue
            staging = common / 'date/.migration-staging' / uuid.uuid4().hex
            checked_copy(profile, staging)
            pb = staging / 'config/prime_backup/config.json'
            if pb.exists():
                config = read_json(pb)
                storage = Path(config.get('storage_root', './pb_files'))
                if not storage.is_absolute():
                    storage = profile / storage
                relative = storage.resolve().relative_to(profile.resolve())
                config['storage_root'] = str(target / relative)
                write_json(pb, config)
            write_json(staging / '.legacy-import.json', {'source': str(profile)})
            staging.rename(target)
            logging.info('Imported legacy world profile: %s', profile.name)
        record['completed'] = True
        write_json(marker, record)
    finally:
        lock.close()
