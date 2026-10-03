"""Configure manual MCDR operation inside the game's mcdr-singleplayer folder."""
import argparse
import json
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', required=True, type=Path)
    parser.add_argument('--world-dir', required=True, type=Path)
    parser.add_argument('--mcdr-dir', type=Path, help='Optional; must equal game-dir/mcdr-singleplayer')
    parser.add_argument('--player')
    parser.add_argument('--bundle', type=Path)
    args = parser.parse_args()
    game = args.game_dir.expanduser().resolve(strict=True)
    world = args.world_dir.expanduser().resolve(strict=True)
    common = game / 'mcdr-singleplayer'
    if args.mcdr_dir and args.mcdr_dir.resolve() != common:
        parser.error('--mcdr-dir must be game-dir/mcdr-singleplayer')
    if world.parent != game / 'saves' or not (world / 'level.dat').is_file():
        parser.error('--world-dir must be an existing save in game-dir/saves')
    if args.player and not re.fullmatch(r'[A-Za-z0-9_]{3,16}', args.player):
        parser.error('invalid player name')
    script_dir = Path(__file__).resolve().parent
    bundle = (args.bundle or script_dir).resolve()
    runtime = bundle / 'runtime'
    plugins = list((bundle / 'plugins').glob('singleplayer_bridge-*.mcdr'))
    if len(plugins) != 1 or not (runtime / 'bridge_proxy.py').is_file():
        parser.error('extract the complete release zip; from source, supply --bundle')
    try:
        from ruamel.yaml import YAML
        import mcdreforged
    except ImportError:
        parser.error('install MCDR first: python -m pip install mcdreforged==2.16.0')
    sys.path.insert(0, str(runtime))
    from singleplayer_bridge.profiles import ensure_profile
    from singleplayer_bridge.bootstrap import configure_common
    from singleplayer_bridge.config_file import read as read_bridge_config, write as write_bridge_config
    from singleplayer_bridge.layout import migrate_legacy
    common.mkdir(parents=True, exist_ok=True)
    migrate_legacy(common)
    config_dir, data_dir, log_dir, runtime_root = common, common / 'date', common / 'log', common / 'runtime'
    for directory in (config_dir, data_dir, log_dir, runtime_root):
        directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.mcdr-init-', dir=runtime_root) as temporary:
        subprocess.run([sys.executable, '-m', 'mcdreforged', 'init'], cwd=temporary, check=True)
        for name in ('config.yml', 'permission.yml'):
            if not (config_dir / name).exists():
                shutil.copy2(Path(temporary) / name, config_dir / name)
    plugin_dir = config_dir / 'plugins'
    plugin_dir.mkdir(exist_ok=True)
    for plugin in plugin_dir.iterdir():
        if not zipfile.is_zipfile(plugin):
            continue
        with zipfile.ZipFile(plugin) as archive:
            try:
                metadata = json.loads(archive.read('mcdreforged.plugin.json'))
            except (KeyError, ValueError):
                continue
        if metadata.get('id') == 'singleplayer_bridge':
            history = runtime_root / 'install-history' / str(time.time_ns())
            history.mkdir(parents=True)
            plugin.rename(history / plugin.name)
    shutil.copy2(plugins[0], plugin_dir / 'singleplayer_bridge.mcdr')
    shutil.copytree(runtime, runtime_root / 'bridge-runtime', dirs_exist_ok=True)
    configure_common(common, Path(sys.executable), runtime_root / 'bridge-runtime')
    config_path = config_dir / 'mcdr-singleplayer-config.yml'
    old_config_path = config_dir / 'config.json'
    if not config_path.exists() and old_config_path.is_file():
        bridge = read_bridge_config(old_config_path)
        write_bridge_config(config_path, bridge)
        history = runtime_root / 'migration-history'
        history.mkdir(parents=True, exist_ok=True)
        old_config_path.replace(history / f'config-json-before-yaml-{time.time_ns()}.json')
    else:
        bridge = read_bridge_config(config_path) if config_path.exists() else dict(enabled=True, port=25585, token=secrets.token_hex(32))
    bridge.pop('mcdrDirectory', None)
    if not isinstance(bridge.get('token'), str) or len(bridge['token']) < 32:
        bridge['token'] = secrets.token_hex(32)
    bridge['autoStartMcdr'] = False
    write_bridge_config(config_path, bridge)
    profile = ensure_profile(common, world)
    if args.player:
        yaml = YAML()
        permission = config_dir / 'permission.yml'
        permissions = yaml.load(permission.read_text(encoding='utf8'))
        owners = permissions.get('owner') or []
        permissions['owner'] = owners
        if args.player not in owners:
            history = runtime_root / 'history' / f'permission.yml.before-owner-{time.time_ns()}'
            history.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(permission, history)
            owners.append(args.player)
            with permission.open('w', encoding='utf8') as output:
                yaml.dump(permissions, output)
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    launcher = '\n'.join([
        '$env:MCDR_BRIDGE_CONFIG = ' + quote(config_path),
        '$env:MCDR_BRIDGE_COMMON = ' + quote(common),
        '$env:MCDR_BRIDGE_RUNTIME = ' + quote(runtime_root),
        '$env:MCDR_BRIDGE_LOG_DIR = ' + quote(log_dir / world.name),
        'Set-Location -LiteralPath ' + quote(profile),
        '& ' + quote(sys.executable) + ' -c ' + quote('import os; from mcdreforged.constants import core_constant; core_constant.LOGGING_FILE=os.path.join(os.environ["MCDR_BRIDGE_LOG_DIR"], "MCDR.log"); from mcdreforged import mcdr_entrypoint; mcdr_entrypoint.entrypoint()') + ' start --config ' + quote(config_dir / 'config.yml') + ' --permission ' + quote(config_dir / 'permission.yml'), ''])
    (runtime_root / 'start_mcdr.ps1').write_text(launcher, encoding='utf-8-sig')
    print(f'MCDR shared directory: {common}\nWorld profile: {profile}\nManual launcher: {runtime_root / "start_mcdr.ps1"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
