import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manual_setup_keeps_all_settings_in_game_root_and_upgrades_bridge(tmp_path):
    game = tmp_path / 'game'
    world = game / 'saves/测试存档'; world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'keep-world')
    bundle = tmp_path / 'bundle'; (bundle / 'plugins').mkdir(parents=True)
    runtime = bundle / 'runtime'
    shutil.copytree(ROOT / 'python', runtime, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    with zipfile.ZipFile(bundle / 'plugins/singleplayer_bridge-0.3.5.mcdr', 'w') as archive:
        archive.writestr('mcdreforged.plugin.json', json.dumps({'id': 'singleplayer_bridge', 'version': '0.3.5'}))
    command = [sys.executable, str(ROOT / 'scripts/setup_mcdr.py'), '--game-dir', str(game), '--world-dir', str(world),
               '--bundle', str(bundle), '--player', 'TestOwner']
    environment = dict(os.environ, PYTHONUTF8='1')
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf8', env=environment)
    assert result.returncode == 0, result.stderr
    common = game / 'mcdr-singleplayer'
    config = json.loads((common / 'runtime/config/config.json').read_text(encoding='utf8'))
    assert config['autoStartMcdr'] is False
    assert len(config['token']) == 64
    assert not (game / 'config').exists()
    assert (common / 'date').is_dir() and not (common / 'worlds').exists()
    profile = common / 'date' / world.name
    assert (profile / 'config/prime_backup/config.json').is_file()
    assert (common / 'runtime/config').is_dir()
    launch = (common / 'runtime/start_mcdr.ps1').read_text(encoding='utf-8-sig')
    assert str(profile) in launch and str(common / 'runtime/config/config.yml') in launch
    assert 'TestOwner' in (common / 'runtime/config/permission.yml').read_text(encoding='utf8')
    with zipfile.ZipFile(common / 'runtime/config/plugins/singleplayer_bridge.mcdr', 'w') as archive:
        archive.writestr('mcdreforged.plugin.json', '{"id":"singleplayer_bridge","version":"0.3.3"}')
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf8', env=environment)
    assert result.returncode == 0, result.stderr
    with zipfile.ZipFile(common / 'runtime/config/plugins/singleplayer_bridge.mcdr') as archive:
        assert json.loads(archive.read('mcdreforged.plugin.json'))['version'] == '0.3.5'
    assert list((common / 'runtime/install-history').glob('*/singleplayer_bridge.mcdr'))
    assert json.loads((common / 'runtime/config/config.json').read_text(encoding='utf8'))['token'] == config['token']
    assert (world / 'level.dat').read_bytes() == b'keep-world'


def test_manual_setup_rejects_external_configuration_directory(tmp_path):
    game = tmp_path / 'game'
    world = game / 'saves/world'; world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'world')
    external = tmp_path / 'external'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/setup_mcdr.py'), '--game-dir', str(game),
        '--world-dir', str(world), '--mcdr-dir', str(external)], capture_output=True, text=True)
    assert result.returncode != 0
    assert not external.exists()
    assert not (game / 'mcdr-singleplayer').exists()
