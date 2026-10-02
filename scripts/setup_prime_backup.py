"""Bind the optional adapter and stock Prime Backup to one existing singleplayer save."""
import argparse
import json
import shutil
import zipfile
from pathlib import Path


def pack_adapter(root, target):
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in (root / 'prime-backup-adapter').rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts and file.suffix != '.pyc':
                archive.write(file, file.relative_to(root / 'prime-backup-adapter').as_posix())


def configure(root, mcdr, world, copy_adapter=False, *, profile_dir=None):
    mcdr, world = mcdr.resolve(strict=True), world.resolve(strict=True)
    if not (mcdr / 'runtime/config/config.yml').is_file():
        raise ValueError('MCDR config.yml not found')
    if not (world / 'level.dat').is_file():
        raise ValueError('Select an existing world folder containing level.dat')
    if mcdr == world or mcdr.is_relative_to(world):
        raise ValueError('MCDR directory must be outside the world')
    artifacts = []
    if not copy_adapter:
        bundle = Path(__file__).resolve().parent
        artifacts = list((bundle / 'adapters').glob('singleplayer_prime_backup-*.mcdr'))
        if not artifacts:
            artifacts = list((root / 'dist').glob('singleplayer_prime_backup-0.3.5.mcdr'))
        if len(artifacts) != 1:
            raise ValueError('Extract the complete 0.3.5 release bundle before running this script')
    # profile_dir is used by the isolated integration harness, whose cwd is already a profile.
    profile = profile_dir.resolve() if profile_dir is not None else mcdr / 'date' / world.name
    if profile_dir is None:
        import sys
        runtime = mcdr / 'runtime/bridge-runtime'
        source = root / 'python'
        sys.path.insert(0, str(runtime if runtime.is_dir() else source))
        from singleplayer_bridge.profiles import profile_path, read_json, write_json
        profile = profile_path(mcdr, world.name)
        metadata = profile / 'profile.json'
        if metadata.exists() and Path(read_json(metadata)['world_path']).resolve() != world:
            raise ValueError('Profile already belongs to a different world')
        write_json(metadata, {'world_path': str(world), 'folder': world.name})
    pb_path = profile / 'config/prime_backup/config.json'
    pb_path.parent.mkdir(parents=True, exist_ok=True)
    config = json.loads(pb_path.read_text(encoding='utf-8-sig')) if pb_path.exists() else {}
    config['enabled'] = True
    backup = config.setdefault('backup', {})
    backup.update(source_root=str(world.parent), source_root_use_mcdr_working_directory=False, targets=[world.name])
    commands = config.setdefault('server', {})
    commands['turn_off_auto_save'] = True
    commands['commands'] = dict(auto_save_off='save-off', save_all_worlds='save-all flush', auto_save_on='save-on')
    commands['saved_world_regex'] = ['Saved the game']
    config.setdefault('storage_root', str(profile / 'data/prime_backup'))
    storage = Path(config['storage_root'])
    if not storage.is_absolute():
        storage = profile / storage
    if not storage.resolve().is_relative_to(profile) or storage.resolve().is_relative_to(world):
        raise ValueError('Prime Backup storage must be inside the current profile and outside the selected world')
    if pb_path.exists():
        # Keep every prior config intact for inspection/recovery.
        from datetime import datetime
        saved = pb_path.with_name('config.before-singleplayer-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.json')
        shutil.copy2(pb_path, saved)
    pb_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    adapter_config = profile / 'config/singleplayer_prime_backup/config.json'
    adapter_config.parent.mkdir(parents=True, exist_ok=True)
    adapter_config.write_text(json.dumps({'world_path': str(world)}, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    if copy_adapter:
        pack_adapter(root, mcdr / 'runtime/config/plugins/singleplayer_prime_backup.mcdr')
    else:
        shutil.copy2(artifacts[0], mcdr / 'runtime/config/plugins/singleplayer_prime_backup.mcdr')
    return pb_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcdr-dir', required=True, type=Path)
    parser.add_argument('--world-dir', required=True, type=Path)
    args = parser.parse_args()
    if args.mcdr_dir.resolve() != args.world_dir.resolve().parent.parent / 'mcdr-singleplayer':
        parser.error('--mcdr-dir must be the game instance mcdr-singleplayer folder')
    try:
        result = configure(Path(__file__).resolve().parents[1], args.mcdr_dir, args.world_dir)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f'Prime Backup bound: {args.world_dir.resolve()}')
    print(f'Configuration: {result}')
    print('Install stock PrimeBackup-v1.13.1.pyz and its Python dependencies, then restart MCDR.')


if __name__ == '__main__':
    main()
