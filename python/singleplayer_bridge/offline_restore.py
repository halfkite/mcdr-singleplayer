"""List and restore one world's PB backups while its integrated server is closed."""
import argparse
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from .backup_guard import checked_path, check_tree, wait_restore_ready
from .plugin_archives import archives
from .profiles import child, read_json, write_json
from .restore_progress import RestoreProgress
from .supervisor import lock_common


def locations(common, name):
    common = Path(common).resolve(strict=True)
    if common.name != 'mcdr-singleplayer':
        raise ValueError('Invalid MCDR Singleplayer directory')
    saves = checked_path(common.parent, 'saves')
    profile = child(common / 'plugindata', name)
    world = child(saves, name)
    if not profile.is_dir():
        raise FileNotFoundError('This world has no MCDR plugin data')
    config_path = checked_path(profile, 'config/prime_backup/config.json')
    if not config_path.is_file():
        raise FileNotFoundError('This world has no Prime Backup configuration')
    config = read_json(config_path)
    raw_storage = Path(config.get('storage_root', './pb_files'))
    storage = raw_storage if raw_storage.is_absolute() else profile / raw_storage
    try:
        relative_storage = storage.relative_to(profile)
    except ValueError:
        raise ValueError('Prime Backup storage is outside this world profile')
    storage = checked_path(profile, relative_storage)
    database = checked_path(storage, 'prime_backup.db')
    if not database.is_file():
        raise FileNotFoundError('This world has no Prime Backup database')
    return common, saves, profile, world, storage, database


def backup_rows(database, name):
    """Read only the selected world's records, including temporary safety backups."""
    with sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True) as connection:
        rows = connection.execute(
            'SELECT id, timestamp, comment, targets, tags, file_raw_size_sum '
            'FROM backup ORDER BY id DESC').fetchall()
    result = []
    for backup_id, timestamp, comment, targets, tags, size in rows:
        if json.loads(targets) != [name]:
            continue
        result.append(dict(id=backup_id, timestamp=timestamp, comment=comment,
                           temporary=bool(json.loads(tags).get('temporary')), size=size))
    return result


def prime_archive(common):
    found = archives(common, 'prime_backup')
    if len(found) != 1 or found[0][1] != '1.13.1' or found[0][0].suffix != '.pyz':
        raise RuntimeError('Prime Backup 1.13.1 must be installed for offline restore')
    return found[0][0]


def validate_profile_binding(profile, world):
    metadata = read_json(checked_path(profile, 'profile.json'))
    if metadata.get('folder') != world.name or Path(metadata.get('world_path', '')).name != world.name:
        raise ValueError('World profile does not match the selected save folder')
    old = Path(metadata['world_path'])
    if old.resolve() != world.resolve() and old.exists():
        raise ValueError('Original world still exists at the profile binding')
    config = read_json(checked_path(profile, 'config/prime_backup/config.json'))
    backup = config.get('backup', {})
    if backup.get('targets') != [world.name] or backup.get('source_root_use_mcdr_working_directory') is not False:
        raise ValueError('Prime Backup config does not target this save folder')
    marker = checked_path(profile, 'cb_files/.singleplayer-world.json')
    if marker.is_file():
        bound = Path(read_json(marker).get('world_path', ''))
        if bound.name != world.name or bound.resolve() != world.resolve() and bound.exists():
            raise ValueError('Chunk Backup store is bound to another existing world')


def rebind_moved_profile(profile, world):
    """A selected backup from this profile authorizes rebinding a moved instance."""
    metadata = checked_path(profile, 'profile.json')
    record = read_json(metadata)
    if record.get('folder') != world.name or Path(record['world_path']).name != world.name:
        raise ValueError('World profile does not match the selected save folder')
    old = Path(record['world_path'])
    if old.resolve() == world.resolve():
        return
    if old.exists():
        raise ValueError('Original world still exists at the profile binding')
    prime_path = checked_path(profile, 'config/prime_backup/config.json')
    config = read_json(prime_path)
    backup = config.get('backup', {})
    if backup.get('targets') != [world.name] or backup.get('source_root_use_mcdr_working_directory') is not False:
        raise ValueError('Prime Backup config does not target this save folder')
    history = profile / 'recovery-config-history' / str(time.time_ns())
    history.mkdir(parents=True, exist_ok=False)
    shutil.copy2(metadata, history / 'profile.json')
    shutil.copy2(prime_path, history / 'prime_backup.json')
    record['world_path'] = str(world)
    write_json(metadata, record)
    backup['source_root'] = str(world.parent)
    write_json(prime_path, config)
    adapter = checked_path(profile, 'config/singleplayer_prime_backup/config.json')
    if adapter.is_file():
        shutil.copy2(adapter, history / 'singleplayer_prime_backup.json')
        adapter_config = read_json(adapter)
        adapter_config['world_path'] = str(world)
        write_json(adapter, adapter_config)
    # CB is a separate store. Rebind only when its marker names this same save.
    cb_marker = checked_path(profile, 'cb_files/.singleplayer-world.json')
    if cb_marker.is_file():
        cb_record = read_json(cb_marker)
        if Path(cb_record.get('world_path', '')).name == world.name and not Path(cb_record['world_path']).exists():
            shutil.copy2(cb_marker, history / 'chunk_backup_world.json')
            write_json(cb_marker, {'world_path': str(world)})
            cb_config_path = checked_path(profile, 'config/chunk_backup/config.json')
            if cb_config_path.is_file():
                from .chunk_backup_config import rebind
                shutil.copy2(cb_config_path, history / 'chunk_backup.json')
                write_json(cb_config_path, rebind(read_json(cb_config_path), profile, world))
            cb_adapter = checked_path(profile, 'config/singleplayer_chunk_backup/config.json')
            if cb_adapter.is_file():
                shutil.copy2(cb_adapter, history / 'singleplayer_chunk_backup.json')
                adapter_config = read_json(cb_adapter)
                adapter_config['world_path'] = str(world)
                write_json(cb_adapter, adapter_config)


def restore(common, name, backup_id, runner=subprocess.run):
    common, saves, profile, world, storage, database = locations(common, name)
    if backup_id <= 0:
        raise ValueError('Invalid backup ID')
    installation = lock_common(common, '.installation.lock')
    try:
        controller = lock_common(common)
    except BaseException:
        installation.close()
        raise RuntimeError('Another Minecraft client is using MCDR; close it before retrying')
    progress = None
    try:
        progress = RestoreProgress({'progress_path': str(common / 'runtime/.mcdr_restore_progress.json')},
                                   world, backup_id, logging.getLogger('offline_restore'))
        progress.update('checking')
        matches = [row for row in backup_rows(database, name) if row['id'] == backup_id]
        if len(matches) != 1:
            raise ValueError('Selected backup does not belong to this world')
        validate_profile_binding(profile, world)
        archive = prime_archive(common)
        wait_restore_ready(world, progress=progress)
        if shutil.disk_usage(saves).free < matches[0]['size'] + 256 * 1024 * 1024:
            raise OSError('Not enough free space to stage the selected backup')
        operation = progress.data['operation']
        staging = checked_path(common, f'runtime/recovery-staging/{operation}')
        history = checked_path(common, f'runtime/recovery-history/{operation}')
        if staging.exists() or history.exists():
            raise FileExistsError('Recovery operation directory already exists')
        staging.mkdir(parents=True)
        history.mkdir(parents=True)
        log_path = common / 'log/recovery.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        progress.update('checking', detail='mcdr-singleplayer.restore.detail.exporting_backup')
        with log_path.open('a', encoding='utf8') as output:
            result = runner([sys.executable, str(archive), '--db', str(storage), 'extract',
                             str(backup_id), '.', '--recursively', '--output', str(staging)],
                            cwd=profile, stdout=output, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode != 0:
            raise RuntimeError('Prime Backup could not verify and export the selected backup; see log/recovery.log')
        staged_world = checked_path(staging, name)
        if not (staged_world / 'level.dat').is_file():
            raise ValueError('Selected backup has no level.dat')
        check_tree(staged_world)
        wait_restore_ready(world, progress=progress)
        progress.update('restoring')  # The entry lock survives a crash during either rename.
        moved_original = False
        if world.exists():
            os.rename(world, history / name)
            moved_original = True
        try:
            os.rename(staged_world, world)
        except BaseException:
            if moved_original and not world.exists():
                os.rename(history / name, world)
            raise
        (history / 'restore.json').write_text(json.dumps(
            {'world': name, 'backup_id': backup_id, 'operation': operation,
             'previous_world': str(history / name) if moved_original else None}, ensure_ascii=False, indent=2),
            encoding='utf8')
        rebind_moved_profile(profile, world)
        progress.exported = True
        progress.finish()
        return history
    except Exception as exc:
        if progress is not None:
            progress.update('failed', 'failed', str(exc))
        raise
    finally:
        controller.close()
        installation.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--common', type=Path, required=True)
    parser.add_argument('--world', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--list', action='store_true')
    group.add_argument('--restore', type=int)
    args = parser.parse_args(argv)
    try:
        if args.list:
            _, _, _, _, _, database = locations(args.common, args.world)
            print(json.dumps({'backups': backup_rows(database, args.world)}, ensure_ascii=False))
        else:
            history = restore(args.common, args.world, args.restore)
            print(json.dumps({'completed': True, 'history': str(history)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 1
