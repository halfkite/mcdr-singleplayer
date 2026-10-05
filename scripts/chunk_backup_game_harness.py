"""GameTest-only launcher: official CB and candy_tools archives, actual MCDR and adapter."""
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
from setup_chunk_backup import configure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-dir', type=Path, required=True)
    parser.add_argument('--world-dir', type=Path, required=True)
    parser.add_argument('--player', required=True)
    parser.add_argument('--chunk-backup', type=Path, required=True)
    parser.add_argument('--candy-tools', type=Path, required=True)
    parser.add_argument('--reuse-work', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = args.reuse_work or Path(tempfile.mkdtemp(prefix='chunk-backup-game-', dir=root / 'fabric-bridge/build'))
    config_dir = work / '.'
    if not args.reuse_work:
        config_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, '-m', 'mcdreforged', 'init'], cwd=config_dir, check=True)
        pack_bridge(root, config_dir / 'plugins/singleplayer_bridge.mcdr')
        for archive in (args.chunk_backup, args.candy_tools):
            shutil.copy2(archive, config_dir / 'plugins' / archive.name)
        profile = configure(root, work, args.world_dir)
        cb_path = profile / 'config/chunk_backup/config.json'
        cb = json.loads(cb_path.read_text(encoding='utf8'))
        cb['command'] = dict(restore_countdown_sec=1, confirm_time_wait='30s')
        cb_path.write_text(json.dumps(cb), encoding='utf8')
        # Pause at the real region-action boundary so the UI and retirement wait can be inspected.
        probe = '''import time
from pathlib import Path
from mcdreforged.api.command import Literal
from mcdreforged.api.command import Text
from mcdreforged.api.decorator import new_thread
PLUGIN_METADATA = {'id': 'chunk_test_gate', 'version': '1.0.0', 'dependencies': {'singleplayer_chunk_backup': '==0.5.1'}}
def on_load(server, prev):
    @new_thread('cb-original-output-probe')
    def probe(source, ctx):
        from chunk_backup.utils.serverdata_getter import ServerDataGetter
        from singleplayer_bridge import plugin
        name = ctx['player']
        for path in ('Pos', 'Dimension'):
            result = plugin.execute_checked(server, 'data get entity ' + name + ' ' + path)
            server.logger.info('CB_ORIGINAL_OUTPUT_%s %r', path, result['text'])
        original_getter = ServerDataGetter.get_position_data.__wrapped__
        server.logger.info('CB_ORIGINAL_GETTER_RESULT %r', original_getter(ServerDataGetter(), name))
    server.register_command(Literal('!!chunk_test_probe').then(Text('player').runs(probe)))
    from chunk_backup.utils.region.region import Region
    from singleplayer_bridge.restore_progress import current_restore
    original = Region.restore_regions
    def gated(manager, info):
        progress = current_restore.get()
        if progress is not None:
            progress.update('restoring')
        server.logger.info('CB_TEST_RESTORE_GATE')
        deadline = time.monotonic() + 30
        while not Path('release-restore-gate').exists():
            if time.monotonic() > deadline: raise RuntimeError('Test restore gate timed out')
            time.sleep(0.025)
        return original(manager, info)
    Region.restore_regions = staticmethod(gated)
'''
        (config_dir / 'plugins/chunk_test_gate.py').write_text(probe, encoding='utf8')
        yaml = YAML()
        settings = yaml.load((config_dir / 'config.yml').read_text(encoding='utf8'))
        settings.update(language='en_us', advanced_console=False, working_directory='.', encoding='utf8', decoding='utf8',
                        plugin_directories=[str(config_dir / 'plugins')])
        settings['start_command'] = [sys.executable, str(root / 'python/bridge_proxy.py'), '--config',
            str(args.game_dir / 'mcdr-singleplayer/mcdr-singleplayer-config.yml')]
        with (config_dir / 'config.yml').open('w', encoding='utf8') as stream:
            yaml.dump(settings, stream)
        permissions = yaml.load((config_dir / 'permission.yml').read_text(encoding='utf8'))
        permissions['owner'] = [args.player]
        with (config_dir / 'permission.yml').open('w', encoding='utf8') as stream:
            yaml.dump(permissions, stream)
    (args.game_dir / 'chunk-backup-test-work.txt').write_text(str(work), encoding='utf8')
    log = work / 'log' / args.world_dir.name
    log.mkdir(parents=True, exist_ok=True)
    entry = ('import os; from mcdreforged.constants import core_constant; '
        'core_constant.LOGGING_FILE=os.path.join(os.environ["MCDR_BRIDGE_LOG_DIR"], "MCDR.log"); '
        'from mcdreforged import mcdr_entrypoint; mcdr_entrypoint.entrypoint()')
    return subprocess.run([sys.executable, '-c', entry, 'start', '--config', str(config_dir / 'config.yml'),
        '--permission', str(config_dir / 'permission.yml')], cwd=work / 'plugindata' / args.world_dir.name,
        env=dict(os.environ, PYTHONUTF8='1', MCDR_BRIDGE_LOG_DIR=str(log), MCDR_BRIDGE_RUNTIME=str(work / 'runtime'))).returncode


if __name__ == '__main__':
    raise SystemExit(main())
