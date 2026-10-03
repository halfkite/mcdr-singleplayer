"""Test-only MCDR process harness used by Fabric's real client game test."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from ruamel.yaml import YAML


def pack_bridge(root, target):
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in (root / 'python').rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts and file.suffix != '.pyc' and not file.name.startswith('bridge_'):
                archive.write(file, file.relative_to(root / 'python').as_posix())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-dir', type=Path, required=True)
    parser.add_argument('--player', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = Path(tempfile.mkdtemp(prefix='mcdr-game-test-', dir=root / 'fabric-bridge' / 'build'))
    subprocess.run([sys.executable, '-m', 'mcdreforged', 'init'], cwd=work, check=True)
    pack_bridge(root, work / 'plugins' / 'singleplayer_bridge.mcdr')
    probe = '''from mcdreforged.api.command import Literal
PLUGIN_METADATA = {'id': 'full_path_probe', 'version': '1.0.0'}
def on_load(server, prev):
    server.register_command(Literal('!!fullbridge').runs(lambda source: source.reply('full-path-ok')))
'''
    (work / 'plugins' / 'full_path_probe.py').write_text(probe, encoding='utf8')
    yaml = YAML()
    config = yaml.load((work / 'config.yml').read_text(encoding='utf8'))
    config.update(language='en_us', advanced_console=False, working_directory=str(work), encoding='utf8', decoding='utf8')
    config['start_command'] = [sys.executable, str(root / 'python' / 'bridge_proxy.py'), '--config',
                               str(args.game_dir / 'mcdr-singleplayer' / 'mcdr-singleplayer-config.yml')]
    with (work / 'config.yml').open('w', encoding='utf8') as output:
        yaml.dump(config, output)
    permissions = yaml.load((work / 'permission.yml').read_text(encoding='utf8'))
    permissions['owner'] = [args.player]
    with (work / 'permission.yml').open('w', encoding='utf8') as output:
        yaml.dump(permissions, output)
    return subprocess.run([sys.executable, '-m', 'mcdreforged', 'start'], cwd=work,
                          env=dict(os.environ, PYTHONUTF8='1')).returncode


if __name__ == '__main__':
    raise SystemExit(main())
