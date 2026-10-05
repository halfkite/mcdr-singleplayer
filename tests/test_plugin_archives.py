import json
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_can_scan_plugins_without_site_packages(tmp_path):
    plugins = tmp_path / 'plugins'
    plugins.mkdir()
    with zipfile.ZipFile(plugins / 'PrimeBackup.pyz', 'w') as archive:
        archive.writestr('mcdreforged.plugin.json', json.dumps({'id': 'prime_backup', 'version': '1.13.1'}))
    script = (f'import sys; sys.path.insert(0, {str(ROOT / "python")!r}); '
              f'from singleplayer_bridge.bootstrap import install; '
              f'from singleplayer_bridge.plugin_archives import archives; '
              f'assert archives({str(tmp_path)!r}, "prime_backup")[0][1] == "1.13.1"')
    result = subprocess.run([sys.executable, '-S', '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
