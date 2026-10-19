"""Install the mod loaders into the workspace runtime.

Fabric and NeoForge both ship installers that write into a game directory, so pointing them at
.client-tests/shared/mc-home keeps the player's launcher untouched. The loader builds are the ones
that were verified to satisfy the control mod's minimum versions.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TEST_ROOT = Path(r'D:\ai\MCDR\.client-tests')
HOME = TEST_ROOT / 'shared' / 'mc-home'
CACHE = TEST_ROOT / 'cache'
JAVA = Path(r'D:\我的世界\java\zulu21\zulu21.28.85-ca-jdk21.0.0-win_x64\bin\java.exe')
PROXY_ARGS = ['-Dhttp.proxyHost=127.0.0.1', '-Dhttp.proxyPort=7897',
              '-Dhttps.proxyHost=127.0.0.1', '-Dhttps.proxyPort=7897']
FABRIC_LOADER = '0.19.5'

NEOFORGE = {
    '1.21': '21.0.167',
    '1.21.1': '21.1.263',
    '1.21.2': '21.2.1-beta',
    '1.21.3': '21.3.100',
    '1.21.4': '21.4.161',
    '1.21.5': '21.5.101',
    '1.21.6': '21.6.20-beta',
    '1.21.7': '21.7.25-beta',
    '1.21.8': '21.8.57',
    '1.21.9': '21.9.16-beta',
    '1.21.10': '21.10.64',
    '1.21.11': '21.11.48',
    '26.1': '26.1.0.19-beta',
    '26.1.1': '26.1.1.15-beta',
    '26.1.2': '26.1.2.122',
    '26.2': '26.2.0.93',
    '26.3': '26.3.0.92',
}


def run(args: list[str]) -> tuple[int, str]:
    result = subprocess.run([str(JAVA), *PROXY_ARGS, *args], capture_output=True, text=True,
                            encoding='utf8', errors='replace', timeout=3600)
    return result.returncode, (result.stdout or '') + (result.stderr or '')


def install_fabric(minecraft: str) -> bool:
    target = HOME / 'versions' / f'fabric-loader-{FABRIC_LOADER}-{minecraft}'
    if (target / f'{target.name}.json').is_file():
        return True
    code, output = run(['-jar', str(CACHE / 'fabric-installer-1.0.1.jar'), 'client',
                        '-dir', str(HOME), '-mcversion', minecraft, '-loader', FABRIC_LOADER])
    if not (target / f'{target.name}.json').is_file():
        print(f'    fabric {minecraft} 失败: {output.strip().splitlines()[-1:]}', flush=True)
        return False
    return True


def install_neoforge(minecraft: str, version: str) -> bool:
    target = HOME / 'versions' / f'neoforge-{version}'
    if (target / f'{target.name}.json').is_file():
        return True
    installer = CACHE / f'neoforge-{version}-installer.jar'
    if not installer.is_file():
        print(f'    neoforge {version} 缺少安装器', flush=True)
        return False
    code, output = run(['-jar', str(installer), '--install-client', str(HOME)])
    if not (target / f'{target.name}.json').is_file():
        print(f'    neoforge {version} 失败: {output.strip().splitlines()[-1:]}', flush=True)
        return False
    return True


def main() -> int:
    matrix = json.loads((Path(r'D:\ai\MCDR') / 'compat' / 'versions.json').read_text(encoding='utf8'))
    versions = [row['minecraft'] for row in matrix['versions']]
    # NeoForge's installer refuses to run unless a launcher profile file sits beside the game.
    (HOME / 'launcher_profiles.json').write_text(
        json.dumps({'profiles': {}, 'settings': {}, 'version': 3}), encoding='utf8')
    failures = 0
    for minecraft in versions:
        fabric_ok = install_fabric(minecraft)
        neoforge_ok = install_neoforge(minecraft, NEOFORGE[minecraft])
        failures += (0 if fabric_ok else 1) + (0 if neoforge_ok else 1)
        print(f'  {minecraft:8} fabric={fabric_ok} neoforge={neoforge_ok}', flush=True)
    print(f'完成，失败 {failures} 项', flush=True)
    return 0 if failures == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
