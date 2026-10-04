"""World profiles. Relative plugin paths inherit the profile process cwd."""
from singleplayer_bridge.i18n import tr
import json
import re
import shutil
from datetime import datetime
from pathlib import Path


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def child(root, name):
    root = Path(root).resolve()
    if not name or name in {'.', '..'} or re.search(r'[\\/:*?"<>|\x00-\x1f]', name) or name.endswith((' ', '.')):
        raise ValueError(tr('error.invalid_world_folder_name'))
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        raise ValueError(tr('error.reserved_folder_name'))
    path = root / name
    if linked(path) or path.resolve().parent != root:
        raise ValueError(tr('error.profile_must_be_a_direct_folder_without_links'))
    return path


def profile_path(common, name):
    return child(Path(common) / 'plugindata', name)


def linked(path):
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def ensure_profile(common, world, language='en_us'):
    world = Path(world).resolve(strict=True)
    common = Path(common).resolve()
    if common.is_relative_to(world):
        raise ValueError(tr('error.shared_mcdr_directory_must_be_outside_the_world'))
    if not (world / 'level.dat').is_file():
        raise ValueError(tr('error.world_has_no_level_dat'))
    profile = profile_path(common, world.name)
    profile.mkdir(parents=True, exist_ok=True)
    metadata = profile / 'profile.json'
    if metadata.exists() and Path(read_json(metadata)['world_path']).resolve() != world:
        raise ValueError(tr('error.this_folder_name_already_belongs_to_a_different_world_rename_the_save_folder'))
    write_json(metadata, {'world_path': str(world), 'folder': world.name})
    (profile / 'config').mkdir(exist_ok=True)
    from .layout import migrate_profile_data
    migrate_profile_data(profile)
    prime = profile / 'config/prime_backup/config.json'
    if not prime.exists():
        write_json(prime, {'enabled': True, 'storage_root': './pb_files',
            'backup': {'source_root': str(world.parent), 'source_root_use_mcdr_working_directory': False, 'targets': [world.name]}})
        recommend(profile, language=language)
    preferences_path = profile / 'config/singleplayer_bridge/config.json'
    preferences = read_json(preferences_path) if preferences_path.exists() else {}
    if preferences.get('recommendation_version') != '0.3.2':
        recommend(profile, language=language)
    elif preferences.get('language') != language:
        preferences['language'] = language
        write_json(preferences_path, preferences)
    validate_prime_binding(profile)
    from .chunk_backup_config import installed, prepare
    if installed(common):
        prepare(profile, world)
    return profile


def recommend(profile, language=None, auto_backup=None, auto_delete=None, backup_enabled=None):
    """Enable PB; consent and policy are saved separately for each world."""
    profile = Path(profile).resolve()
    world = Path(read_json(profile / 'profile.json')['world_path']).resolve()
    path = profile / 'config/prime_backup/config.json'
    config = read_json(path) if path.exists() else {}
    if path.exists():
        backup_file(path)
    config['enabled'] = True
    config.setdefault('storage_root', './pb_files')
    config.setdefault('backup', {}).update(source_root=str(world.parent), source_root_use_mcdr_working_directory=False, targets=[world.name])
    preferences_path = profile / 'config/singleplayer_bridge/config.json'
    preferences = read_json(preferences_path) if preferences_path.exists() else {}
    preferences['recommendation_version'] = '0.3.2'
    for key, value in [('auto_backup', auto_backup), ('auto_delete', auto_delete), ('backup_enabled', backup_enabled)]:
        if value is not None:
            preferences[key] = bool(value)
    if language is not None:
        preferences['language'] = language
    config['enabled'] = preferences.get('backup_enabled', True)
    config.setdefault('scheduled_backup', {}).update(enabled=preferences.get('auto_backup') is True,
        interval='4h', crontab=None, jitter='0s', reset_timer_on_backup=False)
    prune = config.setdefault('prune', {})
    prune.update(enabled=preferences.get('auto_delete') is True, interval='6h', crontab=None)
    for kind in ('regular_backup',):
        prune[kind] = dict(enabled=True, max_amount=0, max_lifetime='0s',
            last=40, hour=0, day=30, week=30, month=0, year=0)
    # Regular PB backups already include scheduled backups: one shared retention pool.
    prune['scheduled_backup'] = dict(enabled=False)
    prune['temporary_backup'] = dict(enabled=False)
    settings = config.setdefault('server', {})
    settings.update(turn_off_auto_save=True, saved_world_regex=['Saved the game'])
    settings['commands'] = dict(auto_save_off='save-off', save_all_worlds='save-all flush', auto_save_on='save-on')
    write_json(path, config)
    write_json(preferences_path, preferences)
    write_json(profile / 'config/singleplayer_prime_backup/config.json', {'world_path': str(world)})
    return path


def backup_file(path):
    path = Path(path)
    target = path.with_name(path.name + '.before-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    shutil.copy2(path, target)
    return target


def validate_prime_binding(profile):
    """Block external stores or imported world bindings before PB is loaded."""
    profile = Path(profile).resolve()
    path = profile / 'config/prime_backup/config.json'
    if not path.exists():
        return False
    config = read_json(path)
    world = Path(read_json(profile / 'profile.json')['world_path']).resolve()
    backup = config.get('backup', {})
    storage = Path(config.get('storage_root', './pb_files'))
    if not storage.is_absolute():
        storage = profile / storage
    if not storage.resolve().is_relative_to(profile):
        raise ValueError(tr('error.prime_backup_storage_root_must_be_inside_the_current_profile'))
    if (backup.get('source_root_use_mcdr_working_directory') is not False
            or Path(backup.get('source_root', '')).resolve() != world.parent
            or backup.get('targets') != [world.name]):
        raise ValueError(tr('error.prime_backup_configuration_is_not_bound_to_this_world_use_recommended_configuration'))
    write_json(profile / 'config/singleplayer_prime_backup/config.json', {'world_path': str(world)})
    return True


def import_configs(common, destination, source_name, replace=False):
    """Copy standard config files, never plugin data/DBs or backup files."""
    destination = Path(destination).resolve()
    source = profile_path(common, source_name)
    if source.resolve() == destination or not (source / 'profile.json').is_file():
        raise ValueError(tr('error.select_another_existing_world_profile'))
    copied = []
    source_config = source / 'config'
    if linked(source_config) or source_config.resolve().parent != source.resolve():
        raise ValueError(tr('error.configuration_directory_cannot_be_a_link'))
    if not source_config.exists():
        return copied
    for file in source_config.rglob('*'):
        relative = file.relative_to(source_config)
        # config.json is the standard MCDR plugin configuration convention.
        extension = file.suffix.lower()
        permitted = extension in {'.json', '.yml', '.yaml', '.toml', '.ini', '.cfg', '.conf', '.properties'} and (
            file.stem.lower() in {'config', 'settings', 'options'} or file.stem.lower().endswith(('.config', '.settings')))
        if not file.is_file() or not permitted or any(p.lower() in {'data', 'cache', 'backups', 'database'} for p in relative.parts[:-1]):
            continue
        if any(linked(source_config / Path(*relative.parts[:i])) for i in range(1, len(relative.parts) + 1)):
            raise ValueError(tr('error.configuration_links_cannot_be_imported'))
        if relative.parts[0] in {'singleplayer_bridge', 'singleplayer_prime_backup', 'singleplayer_chunk_backup'}:
            continue
        target = destination / 'config' / relative
        if not target.resolve().is_relative_to(destination) or target.is_symlink():
            raise ValueError(tr('error.configuration_target_leaves_the_profile'))
        if target.exists() and not replace:
            continue
        if target.exists():
            backup_file(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative.as_posix() == 'prime_backup/config.json':
            # Import policy/settings, excluding world and backup database location.
            config = read_json(file)
            world = Path(read_json(destination / 'profile.json')['world_path'])
            config['storage_root'] = './pb_files'
            config.setdefault('backup', {}).update(source_root=str(world.parent), source_root_use_mcdr_working_directory=False, targets=[world.name])
            write_json(target, config)
        elif relative.as_posix() == 'chunk_backup/config.json':
            from .chunk_backup_config import rebind, prepare
            world = Path(read_json(destination / 'profile.json')['world_path'])
            prepare(destination, world)
            write_json(target, rebind(read_json(file), destination, world))
        else:
            shutil.copy2(file, target)
        copied.append(relative.as_posix())
    return copied
