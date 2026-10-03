"""Test-only launcher: stock Prime Backup release + the real singleplayer bridge."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from ruamel.yaml import YAML

from game_mcdr_harness import pack_bridge


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-dir', type=Path, required=True)
    parser.add_argument('--world-dir', type=Path, required=True)
    parser.add_argument('--player', required=True)
    parser.add_argument('--prime-backup', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = Path(tempfile.mkdtemp(prefix='prime-backup-game-', dir=root / 'fabric-bridge/build'))
    config_dir = work / '.'
    config_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-m', 'mcdreforged', 'init'], cwd=config_dir, check=True)
    (config_dir / 'plugins').mkdir(exist_ok=True)
    pack_bridge(root, config_dir / 'plugins/singleplayer_bridge.mcdr')
    shutil.copy2(args.prime_backup, config_dir / 'plugins' / args.prime_backup.name)
    pb = work / 'date' / args.world_dir.name / 'config/prime_backup/config.json'
    pb.parent.mkdir(parents=True)
    config = dict(enabled=True, storage_root=str(work / 'date' / args.world_dir.name / 'pb_files'),
                  backup=dict(source_root=str(args.world_dir.parent), source_root_use_mcdr_working_directory=False,
                              targets=[args.world_dir.name]),
                  server=dict(save_world_max_wait='3s'),
                  command=dict(restore_countdown_sec=1),
                  scheduled_backup=dict(enabled=False))
    pb.write_text(json.dumps(config), encoding='utf8')
    if not args.baseline:
        from setup_prime_backup import configure
        configure(root, work, args.world_dir, copy_adapter=True, profile_dir=work / 'date' / args.world_dir.name)
    yaml = YAML()
    settings = yaml.load((work / 'config.yml').read_text(encoding='utf8'))
    settings.update(language='en_us', advanced_console=False, working_directory='.', encoding='utf8', decoding='utf8',
                    plugin_directories=[str(config_dir / 'plugins')])
    settings['start_command'] = [sys.executable, str(root / 'python/bridge_proxy.py'), '--config',
                                str(args.game_dir / 'mcdr-singleplayer/mcdr-singleplayer-config.yml')]
    with (work / 'config.yml').open('w', encoding='utf8') as out:
        yaml.dump(settings, out)
    permissions = yaml.load((work / 'permission.yml').read_text(encoding='utf8'))
    permissions['owner'] = [args.player]
    with (work / 'permission.yml').open('w', encoding='utf8') as out:
        yaml.dump(permissions, out)
    (args.game_dir / 'prime-backup-test-work.txt').write_text(str(work), encoding='utf8')
    profile_log = work / 'log' / args.world_dir.name
    profile_log.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONUTF8='1', MCDR_BRIDGE_LOG_DIR=str(profile_log), MCDR_BRIDGE_RUNTIME=str(work / 'runtime'))
    entrypoint = ('import os; from mcdreforged.constants import core_constant; core_constant.LOGGING_FILE=os.path.join(os.environ["MCDR_BRIDGE_LOG_DIR"], "MCDR.log"); '
        'from mcdreforged import mcdr_entrypoint; mcdr_entrypoint.entrypoint()')
    return subprocess.run([sys.executable, '-c', entrypoint, 'start', '--config', str(config_dir / 'config.yml'),
                           '--permission', str(config_dir / 'permission.yml')], cwd=work / 'date' / args.world_dir.name,
                          env=env).returncode


if __name__ == '__main__':
    raise SystemExit(main())
