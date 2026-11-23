"""Restore one Chunk Backup slot while the world is closed, without upstream imports.

Plugins are replaced when the mod is upgraded, so the offline path cannot rely on
Chunk Backup 2.0.3 being installed. It reproduces the documented slot layout and
the documented restore semantics instead: the region folders of the selected slot
are copied over the world, extra world files survive, and the pre-restore state is
written to the ``overwrite`` slot exactly like the plugin's own safety snapshot.
"""
import logging
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .backup_catalog import chunk_rows, paths
from .backup_guard import checked_path, check_tree, wait_restore_ready
from .profiles import read_json, write_json
from .restore_progress import RestoreProgress
from .supervisor import lock_common

MARKER = 'index.json'
SLOT_PREFIX = ('dynamic/', 'static/')


class UnsupportedSlot(Exception):
    """The slot exists but its layout is not a full region backup."""


def _store_config(profile):
    path = checked_path(profile, 'config/chunk_backup/config.json')
    if not path.is_file():
        raise RuntimeError('mcdr-singleplayer.catalog.missing_chunk_backup')
    return read_json(path), path


def _storage(profile, config):
    raw = Path(str(config.get('storage_root') or './cb_files'))
    storage = raw if raw.is_absolute() else Path(profile) / raw
    try:
        # ``..`` survives relative_to, so both sides must be resolved first.
        relative = storage.resolve().relative_to(Path(profile).resolve())
    except (ValueError, OSError):
        raise RuntimeError('mcdr-singleplayer.catalog.chunk_outside_profile')
    return checked_path(profile, relative)


def locate(profile, world, ref):
    """Resolve one catalog reference back to its slot directory and descriptor."""
    config, config_path = _store_config(profile)
    storage = _storage(profile, config)
    if ref == 'chunk:overwrite':
        slot = checked_path(storage, str(config.get('overwrite_storage') or 'overwrite'))
    else:
        name = ref.removeprefix('chunk:')
        prefix, _, folder = name.partition('/')
        if prefix + '/' not in SLOT_PREFIX or not folder:
            raise ValueError('mcdr-singleplayer.error.invalid_chunk_backup_slot')
        key = 'dynamic_storage' if prefix == 'dynamic' else 'static_storage'
        slot = checked_path(storage, str(config.get(key) or key) + '/' + folder)
    info_path = checked_path(slot, 'info.json')
    if not slot.is_dir() or not info_path.is_file():
        raise ValueError('mcdr-singleplayer.catalog.missing_chunk_slot')
    info = read_json(info_path)
    rows = [row for row in chunk_rows(profile, world)['backups'] if row['ref'] == ref]
    if len(rows) != 1:
        raise ValueError('mcdr-singleplayer.catalog.missing_chunk_slot')
    if not rows[0]['restorable']:
        raise UnsupportedSlot(rows[0]['reason'])
    return dict(config=config, config_path=config_path, storage=storage, slot=slot,
                info=info, row=rows[0])


def _copy_tree(source, target):
    """Copy one region folder's files; the plugin's own marker is never restored."""
    copied = 0
    for directory, folders, files in os.walk(source, followlinks=False):
        relative = Path(directory).relative_to(source)
        (target / relative).mkdir(parents=True, exist_ok=True)
        for name in folders:
            (target / relative / name).mkdir(parents=True, exist_ok=True)
        for name in files:
            if name == MARKER:
                continue
            destination = target / relative / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(directory) / name, destination)
            copied += 1
    return copied


def _targets(located, world):
    """Every region folder this slot restores, as (source, target) pairs.

    按选区备份的槽位只包含选区覆盖到的目录，所以缺某个子目录是正常的：跳过即可。
    但至少要有一个目录，否则说明这个槽位没有可恢复的内容。
    """
    config = located['config']
    table = (config.get('backup') or {}).get('dimension') or {}
    pairs = []
    for dimension in located['row']['dimensions']:
        folder = str((table.get(dimension) or {}).get('world_name') or '')
        if folder != Path(world).name:
            raise ValueError('mcdr-singleplayer.catalog.store_moved')
        for relative in table[dimension]['region_folder']:
            source = checked_path(located['slot'], f'{folder}/{relative}')
            if not source.is_dir():
                continue
            pairs.append((source, checked_path(world, relative)))
    if not pairs:
        raise ValueError('mcdr-singleplayer.catalog.missing_chunk_slot')
    return pairs


def _snapshot(located, world, pairs):
    """Write the pre-restore state into the overwrite slot, like the plugin does."""
    config = located['config']
    overwrite = checked_path(located['storage'], str(config.get('overwrite_storage') or 'overwrite'))
    if overwrite.exists():
        shutil.rmtree(overwrite)
    overwrite.mkdir(parents=True)
    # Slots keep the world folder as their first level, so the snapshot does too.
    for _, target in pairs:
        destination = checked_path(overwrite, f'{Path(world).name}/{target.relative_to(world).as_posix()}')
        destination.mkdir(parents=True, exist_ok=True)
        _copy_tree(target, destination)
        write_json(checked_path(destination, MARKER), {'type': 'region'})
    players = Path(world) / 'players'
    if players.is_dir():
        _copy_tree(players, checked_path(overwrite, f'{Path(world).name}/players'))
    info = dict(located['info'])
    info.update(type='region', comment='mcdr-singleplayer.chunk.overwrite_comment',
                date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                operator='mcdr-singleplayer.chunk.overwrite_operator',
                dimension=list(located['row']['dimensions']))
    for key in ('name', 'player_position', 'top_left', 'top_right', 'bottom_left', 'bottom_right',
                'sub_backup', 'command', 'uuid_dict'):
        info.pop(key, None)
    write_json(checked_path(overwrite, 'info.json'), info)
    return overwrite


def restore(common, name, ref, logger=None):
    """Two-phase restore: snapshot the world, then copy the slot over it."""
    common = Path(common).resolve(strict=True)
    profile, world = paths(common, name)
    if not profile.is_dir():
        raise FileNotFoundError('mcdr-singleplayer.catalog.missing_profile')
    logger = logger or logging.getLogger('chunk_restore')
    installation = lock_common(common, '.installation.lock')
    try:
        controller = lock_common(common)
    except BaseException:
        installation.close()
        raise RuntimeError('mcdr-singleplayer.error.another_minecraft_client_is_using_mcdr')
    progress = RestoreProgress({'progress_path': str(common / 'runtime/.mcdr_restore_progress.json')},
                               world, 0, logger)
    try:
        progress.update('checking')
        located = locate(profile, world, ref)
        pairs = _targets(located, world)
        check_tree(located['slot'])
        wait_restore_ready(world, [target for _, target in pairs], progress=progress)
        progress.update('safety_backup')
        _snapshot(located, world, pairs)
        progress.update('restoring')
        copied = 0
        for source, target in pairs:
            target.mkdir(parents=True, exist_ok=True)
            copied += _copy_tree(source, target)
        if not copied:
            raise RuntimeError('mcdr-singleplayer.catalog.empty_chunk_slot')
        players = checked_path(located['slot'], 'players')
        if players.is_dir():
            progress.update('player_data')
            _copy_tree(players, Path(world) / 'players')
        progress.exported = True
        progress.finish()
        return dict(common=str(common), world=str(world), ref=ref, files=copied)
    except Exception as exc:
        progress.update('failed', 'failed', str(exc))
        raise
    finally:
        controller.close()
        installation.close()


def main(argv=None):
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--common', type=Path, required=True)
    parser.add_argument('--world', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--list', action='store_true')
    group.add_argument('--restore')
    args = parser.parse_args(argv)
    try:
        from .backup_catalog import catalog
        if args.list:
            print(json.dumps(catalog(args.common, args.world), ensure_ascii=False))
        else:
            print(json.dumps(restore(args.common, args.world, args.restore), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False))
        return 1
