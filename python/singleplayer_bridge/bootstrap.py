"""Install the tested MCDR/PB runtime without modifying global Python packages."""
from singleplayer_bridge.i18n import tr
import argparse
import hashlib
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import venv
import zipfile
from pathlib import Path

from .profiles import read_json, write_json

PRIME_VERSION = '1.13.1'
PRIME_HASH = '081c91872ff3f6ab438328b96237e5e8db87ebff28e46b909eca804b6320db2b'
PRIME_URL = 'https://github.com/TISUnion/PrimeBackup/releases/download/v1.13.1/PrimeBackup-v1.13.1.pyz'
PIP_INDEXES = ['https://pypi.org/simple', 'https://pypi.tuna.tsinghua.edu.cn/simple', 'https://mirrors.aliyun.com/pypi/simple/']
DEFAULT_MIRRORS = ['https://gh-proxy.com/']


class InstallationProgress:
    """Atomic, client-scoped stages for the in-game installer UI; never publish pip output."""
    def __init__(self, common, client_id):
        self.path = Path(common) / 'runtime/install-progress.json'
        self.client_id = client_id

    def report(self, stage, attempt=0):
        try:
            write_json(self.path, dict(protocol=1, client_id=self.client_id, stage=stage, attempt=attempt))
        except OSError:
            logging.warning('Could not publish installation progress', exc_info=True)


def download_checked(urls, destination, digest, opener=urllib.request.urlopen):
    destination = Path(destination)
    temporary = destination.with_name(destination.name + '.download')
    for url in urls:
        try:
            started = time.monotonic()
            request = urllib.request.Request(url, headers={'User-Agent': 'MCDR-Singleplayer-Bridge/0.4.2'})
            with opener(request, timeout=15) as response, temporary.open('wb') as output:
                total = 0
                while chunk := response.read(65536):
                    total += len(chunk)
                    if total > 50 * 1024 * 1024 or time.monotonic() - started > 90:
                        raise OSError('Download too large or too slow')
                    output.write(chunk)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
                raise ValueError(tr('error.downloaded_artifact_hash_does_not_match_the_tested_release'))
            temporary.replace(destination)
            logging.info('Verified download succeeded: %s', url)
            return
        except Exception as exc:
            logging.warning('Download failed, trying next source: %s (%s)', url, type(exc).__name__)
            temporary.unlink(missing_ok=True)
    raise RuntimeError(tr('error.all_download_sources_failed_see_log_install_log'))


def install_dependencies(python, requirements, indexes=None, runner=subprocess.run, progress=None):
    for attempt, index in enumerate(indexes or PIP_INDEXES, 1):
        if progress:
            progress('dependencies', attempt)
        logging.info('Installing/updating tested runtime packages using %s', index)
        try:
            result = runner([str(python), '-m', 'pip', 'install', '--upgrade', '--disable-pip-version-check',
                '--timeout', '15', '--retries', '1', '--index-url', index, '-r', str(requirements)],
                stdout=sys.stdout, stderr=sys.stderr, timeout=600,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired:
            continue
        if result.returncode == 0:
            return
    raise RuntimeError(tr('error.dependency_installation_failed_on_all_indexes'))


def pack(source, target):
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for file in source.rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts and file.suffix != '.pyc' and file.name != '.gitignore':
                entry = zipfile.ZipInfo(file.relative_to(source).as_posix())
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, file.read_bytes())


def configure_common(common, python, runtime):
    """Shared config/permissions/plugins; cwd is chosen by the controller per world."""
    from ruamel.yaml import YAML
    yaml = YAML()
    config_dir = common
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / 'config.yml'
    config = yaml.load(path.read_text(encoding='utf-8-sig'))
    desired = dict(working_directory='.', start_command=[str(python), str(runtime / 'bridge_proxy.py'), '--config-env'],
                   plugin_directories=[str(config_dir / 'plugins')], encoding='utf8', decoding='utf8', advanced_console=False)
    if any(config.get(key) != value for key, value in desired.items()):
        config.update(desired)
        config.setdefault('rcon', {})['enable'] = False
        with path.open('w', encoding='utf8') as output:
            yaml.dump(config, output)


def install(common, resources, update=False, progress=None):
    progress = progress or (lambda stage, attempt=0: None)
    common, resources = Path(common).resolve(), Path(resources).resolve()
    common.mkdir(parents=True, exist_ok=True)
    from .layout import migrate_legacy
    migrate_legacy(common)
    runtime_root = common / 'runtime'
    config_dir = common
    environment = runtime_root / '.bridge-venv'
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    progress('environment')
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    marker = runtime_root / 'runtime-install.json'
    requirements = resources / 'requirements-prime-backup.txt'
    signature = hashlib.sha256(requirements.read_bytes()).hexdigest()
    previous = read_json(marker) if marker.exists() else {}
    probe = subprocess.run([str(python), '-c',
        "import apscheduler, sqlalchemy, blake3, mcdreforged, pathspec, psutil, pydantic, pytz, typing_extensions, xxhash, zstandard; "
        "from importlib.metadata import version; assert version('mcdreforged') == '2.16.0'"],
        capture_output=True, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if update or probe.returncode != 0 or previous.get('requirements_sha256') != signature or time.time() - previous.get('checked_at', 0) > 86400:
        install_dependencies(python, requirements, progress=progress)
    progress('files')
    runtime = runtime_root / 'bridge-runtime'
    shutil.copytree(resources / 'runtime', runtime, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    plugins = config_dir / 'plugins'
    plugins.mkdir(exist_ok=True)
    progress('config')
    # MCDR init refuses existing directories; generate defaults separately then copy missing shared files.
    if not (config_dir / 'config.yml').exists() or not (config_dir / 'permission.yml').exists():
        import tempfile
        with tempfile.TemporaryDirectory(prefix='.mcdr-init-', dir=runtime_root) as directory:
            subprocess.run([str(python), '-m', 'mcdreforged', 'init'], cwd=directory, check=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            for name in ('config.yml', 'permission.yml'):
                if not (config_dir / name).exists():
                    shutil.copy2(Path(directory) / name, config_dir / name)
    configure = [str(python), str(resources / 'bridge_bootstrap.py'), '--configure-only', '--common', str(common), '--resources', str(resources)]
    subprocess.run(configure, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    progress('plugins')
    # Backup plugins are opt-in. Keep bundled adapters outside the live plugin directory
    # until their upstream plugin is present; first-run chat provides install buttons.
    from .onboarding import archives
    bundled_plugins = [('bridge-plugin', 'singleplayer_bridge.mcdr')]
    adapter_store = runtime_root / 'backup-adapters'
    adapter_store.mkdir(exist_ok=True)
    for folder, plugin_id, upstream in [('adapter-plugin', 'singleplayer_prime_backup', 'prime_backup'),
                                        ('chunk-adapter-plugin', 'singleplayer_chunk_backup', 'chunk_backup')]:
        pack(resources / folder, adapter_store / (plugin_id + '.mcdr'))
        tested = '1.13.1' if upstream == 'prime_backup' else '2.0.3'
        existing = archives(common, upstream)
        if len(existing) == 1 and existing[0][1] == tested:
            bundled_plugins.append((folder, plugin_id + '.mcdr'))
    for folder, name in bundled_plugins:
        plugin_id = name.removesuffix('.mcdr')
        prepared = runtime_root / (name + '.prepared')
        pack(resources / folder, prepared)
        target = plugins / name
        if target.exists() and target.read_bytes() == prepared.read_bytes():
            prepared.unlink()
            continue
        for file, _ in archives(common, plugin_id):
            history = runtime_root / 'install-history' / str(time.time_ns())
            history.mkdir(parents=True, exist_ok=True)
            shutil.move(str(file), str(history / file.name))
        prepared.replace(target)
    write_json(marker, dict(mcdr='2.16.0', backup_plugins_opt_in=True, requirements_sha256=signature, checked_at=time.time(), python=str(python)))
    return python


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--common', required=True, type=Path)
    parser.add_argument('--resources', required=True, type=Path)
    parser.add_argument('--update', action='store_true')
    parser.add_argument('--configure-only', action='store_true')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--client-id')
    parser.add_argument('--parent-pid')
    args = parser.parse_args()
    args.common.mkdir(parents=True, exist_ok=True)
    log_dir = args.common / 'log'
    log_dir.mkdir(parents=True, exist_ok=True)
    (args.common / 'runtime').mkdir(exist_ok=True)
    logging.basicConfig(filename=log_dir / 'install.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf8')
    if args.configure_only:
        configure_common(args.common.resolve(), Path(sys.executable), args.common.resolve() / 'runtime/bridge-runtime')
        return 0
    progress = InstallationProgress(args.common, args.client_id)
    progress.report('preparing')
    try:
        from .supervisor import lock_common
        installation_lock = lock_common(args.common, '.installation.lock')
        try:
            active_controller_lock = lock_common(args.common)
            active_controller_lock.close()
            python = install(args.common, args.resources, args.update, progress=progress.report)
        finally:
            installation_lock.close()
        if args.state:
            progress.report('starting')
            process = subprocess.Popen([str(python), str(args.common / 'runtime/bridge-runtime/bridge_supervisor.py'),
                '--common', str(args.common), '--config', str(args.config), '--state', str(args.state),
                '--client-id', args.client_id, '--parent-pid', args.parent_pid],
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return process.wait()
        return 0
    except Exception:
        progress.report('failed')
        logging.exception('Automatic installation failed')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
