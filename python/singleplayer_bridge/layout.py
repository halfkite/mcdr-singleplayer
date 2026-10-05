"""Migrate older bridge layouts, then import legacy MCDR world profiles."""
from singleplayer_bridge.i18n import tr
import logging
import shutil
import time
import uuid
from pathlib import Path

from .profiles import linked, profile_path, read_json, write_json


def checked_copy(source, target):
    source, target = Path(source), Path(target)
    if linked(source) or linked(target) or any(linked(parent) for parent in target.parents):
        raise ValueError(tr('error.migration_paths_cannot_be_links'))
    if source.is_dir():
        for item in source.rglob('*'):
            if linked(item):
                raise ValueError(tr('error.legacy_data_contains_a_link_migration_stopped'))
        shutil.copytree(source, target)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _relocate(source, target, common):
    if linked(source) or linked(target) or any(linked(parent) for parent in target.parents):
        raise ValueError(tr('error.migration_source_link', source.name))
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
    conflict = common / 'runtime/migration-history' / f'{time.time_ns()}-{uuid.uuid4().hex}-{source.name}'
    conflict.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(conflict))


def _check_tree_has_no_links(path):
    path = Path(path)
    if linked(path):
        raise ValueError(tr('error.migration_source_link', path.name))
    if path.is_dir():
        for item in path.rglob('*'):
            if linked(item):
                raise ValueError(tr('error.migration_source_link', item.name))


def organize_layout(common):
    """Shared MCDR files stay at root; each save keeps plugins' native relative layout."""
    common = Path(common).resolve()
    for name in ('log', 'runtime'):
        directory = common / name
        if linked(directory):
            raise ValueError(tr('error.directory_link', name))
        directory.mkdir(exist_ok=True)

    # 0.4.2 renames the per-save plugin-data directory. Merge safely if both
    # layouts exist, preserving differing files in migration-history.
    old_profiles, profiles = common / 'date', common / 'plugindata'
    if old_profiles.exists():
        _check_tree_has_no_links(old_profiles)
        if profiles.exists():
            _check_tree_has_no_links(profiles)
        _relocate(old_profiles, profiles, common)
    if linked(profiles):
        raise ValueError(tr('error.directory_link', profiles.name))
    profiles.mkdir(exist_ok=True)

    for old_config in (common / 'config', common / 'runtime/config'):
        if old_config.exists():
            if linked(old_config):
                raise ValueError(tr('error.legacy_shared_config_cannot_be_a_link'))
            for item in list(old_config.iterdir()):
                if item.name in {'config.json', 'config.yml', 'permission.yml', 'download-sources.json', 'plugins'}:
                    _relocate(item, common / item.name, common)
                elif item.name.startswith('config.yml.before-'):
                    item.unlink()
                else:
                    _relocate(item, common / 'runtime/legacy-files/shared-config' / item.name, common)
            old_config.rmdir()
    old_data = common / 'data'
    if old_data.exists():
        _relocate(old_data, profiles, common)

    # Older releases kept the mod settings beside MCDR's shared files as JSON.
    # Convert that file to the named YAML settings file while retaining a copy
    # in migration-history; MCDR's own configuration remains config.yml.
    old_bridge_config = common / 'config.json'
    bridge_config = common / 'mcdr-singleplayer-config.yml'
    if linked(bridge_config):
        raise ValueError(tr('error.migration_source_link', bridge_config.name))
    if old_bridge_config.exists():
        if linked(old_bridge_config):
            raise ValueError(tr('error.migration_source_link', old_bridge_config.name))
        history = common / 'runtime/migration-history'
        if linked(history):
            raise ValueError(tr('error.migration_source_link', history.name))
        history.mkdir(parents=True, exist_ok=True)
        if not bridge_config.exists():
            from .config_file import read as read_bridge_config, write as write_bridge_config
            write_bridge_config(bridge_config, read_bridge_config(old_bridge_config))
        old_bridge_config.replace(history / f'config-json-before-yaml-{time.time_ns()}.json')

    folder_targets = {
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
        '.migration-staging': 'plugindata/.migration-staging',
    }
    for name, relative in folder_targets.items():
        source = common / name
        if source.exists():
            _relocate(source, common / relative, common)
    for source in list(common.glob('bootstrap-resources-*')):
        _relocate(source, common / 'runtime' / source.name, common)
    for name in ('bootstrap.log', 'install.log', 'controller.log', 'python-install.log'):
        source = common / name
        if source.exists():
            _relocate(source, common / 'log' / name, common)

    for source in list(common.iterdir()):
        if source.name in {'date', 'plugindata', 'log', 'runtime', 'plugins', 'config.json', 'mcdr-singleplayer-config.yml', 'config.yml', 'permission.yml', 'download-sources.json'}:
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
    for profile in profiles.iterdir():
        if profile.is_dir() and (profile / 'profile.json').is_file():
            migrate_profile_data(profile)


def migrate_profile_data(profile):
    """Only undo paths introduced by the bridge; never merge databases or change custom paths."""
    from .backup_guard import checked_path, check_tree
    profile = Path(profile).resolve()
    plans = []
    for plugin, native in (('prime_backup', 'pb_files'), ('chunk_backup', 'cb_files')):
        previous = checked_path(profile, 'data/' + plugin)
        target = checked_path(profile, native)
        config_path = checked_path(profile, 'config/' + plugin + '/config.json')
        config = read_json(config_path) if config_path.exists() else None
        if previous.exists():
            check_tree(previous)
            if target.exists() and any(target.iterdir()):
                raise ValueError(tr('error.store_conflict', plugin, native))
        plans.append((previous, target, config_path, config, native))
    for previous, target, config_path, config, native in plans:
        if previous.exists():
            if target.exists():
                target.rmdir()  # Only the preflight-confirmed empty directory.
            previous.rename(target)
        if config is not None:
            configured = Path(config.get('storage_root', './' + native))
            if not configured.is_absolute():
                configured = profile / configured
            if configured.resolve() == previous:
                config['storage_root'] = './' + native
                write_json(config_path, config)
    data = profile / 'data'
    if data.is_dir() and not any(data.iterdir()):
        data.rmdir()


def migrate_legacy(common, *, controller_locked=False):
    from .supervisor import lock_common
    common = Path(common).resolve()
    common.mkdir(parents=True, exist_ok=True)
    # Automatic installation holds this lease throughout its file/config updates.
    lease = None if controller_locked else lock_common(common)
    try:
        _migrate_legacy(common)
    finally:
        if lease:
            lease.close()


def _migrate_legacy(common):
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
        raise ValueError(tr('error.legacy_mcdr_directory_is_missing_preserve_the_migration_marker_and_restore_that_directory_first'))
    if source != common and (source.is_relative_to(common) or common.is_relative_to(source)):
        raise ValueError(tr('error.legacy_and_destination_directories_cannot_be_nested'))
    from .supervisor import lock_common
    lock = lock_common(source) if source != common else None
    try:
        config_dir = common
        for name in ('config.yml', 'permission.yml', 'download-sources.json'):
            target = config_dir / name
            if (source / name).is_file() and not target.exists():
                checked_copy(source / name, target)
        plugins = source / 'plugins'
        target_plugins = config_dir / 'plugins'
        if plugins.exists() and source != common:
            if linked(plugins) or linked(target_plugins):
                raise ValueError(tr('error.plugin_directories_cannot_be_links'))
            target_plugins.mkdir(exist_ok=True)
            for plugin in plugins.iterdir():
                target = target_plugins / plugin.name
                if not target.exists():
                    checked_copy(plugin, target)
        worlds = source / 'worlds'
        if linked(worlds):
            raise ValueError(tr('error.legacy_profiles_cannot_be_a_link'))
        for profile in sorted(worlds.iterdir()) if worlds.exists() else []:
            if not profile.is_dir() or not (profile / 'profile.json').is_file():
                continue
            target = profile_path(common, profile.name)
            metadata = read_json(profile / 'profile.json')
            if metadata.get('folder') != profile.name or Path(metadata['world_path']).name != profile.name:
                raise ValueError(tr('error.legacy_profile_name_does_not_match_its_world_binding'))
            if target.exists():
                if not (target / '.legacy-import.json').is_file() or read_json(target / '.legacy-import.json').get('source') != str(profile):
                    raise ValueError(tr('error.destination_profile_already_exists_migration_will_not_overwrite_it'))
                continue
            staging = common / 'plugindata/.migration-staging' / uuid.uuid4().hex
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
            migrate_profile_data(target)
            logging.info('Imported legacy world profile: %s', profile.name)
        record['completed'] = True
        write_json(marker, record)
    finally:
        if lock is not None:
            lock.close()
