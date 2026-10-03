"""Package already-built installable artifacts. Called after the Gradle build."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    metadata = json.loads((ROOT / 'python' / 'mcdreforged.plugin.json').read_text(encoding='utf8'))
    version = metadata['version']
    plugin_name = f'singleplayer_bridge-{version}.mcdr'
    subprocess.run([sys.executable, '-m', 'mcdreforged', 'pack', '-i', str(ROOT / 'python'),
                    '-o', str(dist), '-n', plugin_name], check=True)
    plugin = dist / plugin_name
    if not plugin.is_file():
        raise SystemExit('MCDR plugin packing failed')
    jar = ROOT / 'fabric-bridge' / 'build' / 'libs' / f'mcdr-singleplayer-{version}.jar'
    if not jar.is_file():
        raise SystemExit('Run the real Gradle build first')
    adapter_name = f'singleplayer_prime_backup-{version}.mcdr'
    subprocess.run([sys.executable, '-m', 'mcdreforged', 'pack', '-i', str(ROOT / 'prime-backup-adapter'),
                    '-o', str(dist), '-n', adapter_name], check=True)
    chunk_adapter = f'singleplayer_chunk_backup-{version}.mcdr'
    subprocess.run([sys.executable, '-m', 'mcdreforged', 'pack', '-i', str(ROOT / 'chunk-backup-adapter'),
                    '-o', str(dist), '-n', chunk_adapter], check=True)
    bundle = Path(tempfile.mkdtemp(prefix=f'bundle-{version}-', dir=dist))
    for folder in ('mods', 'plugins', 'runtime', 'adapters'):
        (bundle / folder).mkdir(parents=True, exist_ok=True)
    shutil.copy2(jar, bundle / 'mods' / jar.name)
    shutil.copy2(plugin, bundle / 'plugins' / plugin.name)
    shutil.copy2(dist / adapter_name, bundle / 'adapters' / adapter_name)
    shutil.copy2(dist / chunk_adapter, bundle / 'adapters' / chunk_adapter)
    for name in ('bridge_proxy.py', 'bridge_supervisor.py', 'bridge_bootstrap.py'):
        shutil.copy2(ROOT / 'python' / name, bundle / 'runtime' / name)
    shutil.copytree(ROOT / 'python' / 'singleplayer_bridge', bundle / 'runtime' / 'singleplayer_bridge',
                    dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(ROOT / 'scripts' / 'setup_mcdr.py', bundle / 'setup_mcdr.py')
    shutil.copy2(ROOT / 'scripts' / 'setup_prime_backup.py', bundle / 'setup_prime_backup.py')
    shutil.copy2(ROOT / 'scripts' / 'setup_chunk_backup.py', bundle / 'setup_chunk_backup.py')
    shutil.copy2(ROOT / 'requirements-prime-backup.txt', bundle / 'requirements-prime-backup.txt')
    shutil.copy2(ROOT / 'docs' / '安装说明.md', bundle / '安装说明.md')
    shutil.copy2(ROOT / 'docs' / 'PrimeBackup适配.md', bundle / 'PrimeBackup适配.md')
    shutil.copy2(ROOT / 'docs' / 'ChunkBackup适配.md', bundle / 'ChunkBackup适配.md')
    shutil.copy2(ROOT / 'docs' / 'PrimeBackup测试记录.md', bundle / 'PrimeBackup测试记录.md')
    shutil.copy2(ROOT / 'docs' / '自动启动与存档配置.md', bundle / '自动启动与存档配置.md')
    shutil.copy2(ROOT / 'docs' / '自动启动测试记录.md', bundle / '自动启动测试记录.md')
    for record in sorted((ROOT / 'docs').glob('0.*.md')):
        shutil.copy2(record, bundle / record.name)
    (bundle / 'assets').mkdir()
    for name in ('prime-backup-baseline.png', 'prime-backup-online.png', 'prime-backup-restored.png',
                 'prime-backup-baseline.log', 'prime-backup-adapted.log'):
        shutil.copy2(ROOT / 'docs/assets' / name, bundle / 'assets' / name)
    for file in (ROOT / 'docs/assets').glob('automatic-*'):
        shutil.copy2(file, bundle / 'assets' / file.name)
    for file in (ROOT / 'docs/assets').glob('chunk-backup-*'):
        shutil.copy2(file, bundle / 'assets' / file.name)
    shutil.copy2(ROOT / 'LICENSE', bundle / 'LICENSE')
    archive = shutil.make_archive(str(dist / f'mcdr-singleplayer-{version}-mc26.3-fabric'), 'zip', bundle)
    print(archive)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
