"""Local first-run chat and explicit, verified installation of backup plugins."""
import os
import threading
from pathlib import Path

from mcdreforged.api.rtext import RAction, RColor, RText, RTextList

from .backup_guard import checked_path
from .config_file import read as read_bridge_config, write as write_bridge_config
from .plugin_archives import archives
from .profiles import read_json, write_json
from .i18n import tr, locale

PB_PAGE = 'https://mcdreforged.com/zh-CN/plugin/prime_backup'
CB_PAGE = 'https://mcdreforged.com/zh-CN/plugin/chunk_backup'
PB_DOC = 'https://tisunion.github.io/PrimeBackup/'
WARNING = tr('onboarding.warning', language='zh_cn')
_shown = set()
_settings_shown = set()
_install_lock = threading.Lock()
_preferences_lock = threading.Lock()


def common_preferences(**changes):
    path = checked_path(Path(os.environ['MCDR_BRIDGE_COMMON']), 'mcdr-singleplayer-config.yml')
    with _preferences_lock:
        config = read_bridge_config(path)
        if changes:
            config.update(changes)
            write_bridge_config(path, config)
        return config


def button(label, command):
    return RText(label, RColor.green).c(RAction.run_command, '/!!spbridge ' + command)


def link(label, url):
    return RText(label, RColor.aqua).c(RAction.open_url, url)


def prime_options(server, host):
    labels = [tr('prime.' + name) for name in ('enable', 'schedule', 'prune', 'docs')]
    server.tell(host, RTextList(button(labels[0], 'config backup on'), ' ', button(labels[1], 'config auto_backup on'),
        ' ', button(labels[2], 'config auto_delete on'), ' ', link(labels[3], PB_DOC + ('zh/' if locale().startswith('zh_') else ''))))
    server.tell(host, tr('prime.policy'))


def prompt(server, force=False):
    from .plugin import snapshot
    state = snapshot()
    host = os.environ.get('MCDR_BRIDGE_HOST') or state.get('host_player')
    session = state.get('session')
    common = os.environ.get('MCDR_BRIDGE_COMMON')
    if not common or not session or not host or host not in state.get('players', []):
        return
    if session in _shown and not force:
        return
    _shown.add(session)
    config = common_preferences()
    if config.get('onboardingDismissed') and not force:
        return
    client = os.environ.get('MCDR_BRIDGE_CLIENT_ID', session)
    if force or config.get('onboardingLastClientId') != client:
        server.tell(host, tr('onboarding.intro'))
        missing = []
        for plugin_id, label, page in [('prime_backup', tr('onboarding.prime'), PB_PAGE),
                                        ('chunk_backup', tr('onboarding.chunk'), CB_PAGE)]:
            if not archives(common, plugin_id) and server.get_plugin_instance(plugin_id) is None:
                missing.append(RTextList(tr('onboarding.recommend'), link(label, page), ' ',
                    button(tr('onboarding.install'), 'install ' + plugin_id)))
        for message in missing:
            server.tell(host, message)
        server.tell(host, button(tr('onboarding.dismiss'), 'onboarding dismiss'))
        for _ in range(3):
            server.tell(host, RText(tr('onboarding.warning'), RColor.red))
        server.tell(host, tr('onboarding.chat_hint'))
        common_preferences(onboardingLastClientId=client)
    if server.get_plugin_instance('prime_backup') is not None and (force or session not in _settings_shown):
        prime_options(server, host)
        _settings_shown.add(session)


def dismiss(source):
    if not os.environ.get('MCDR_BRIDGE_COMMON'):
        source.reply(tr('command.auto_required'))
        return
    common_preferences(onboardingDismissed=True)
    source.reply(tr('onboarding.dismissed'))


def installing():
    return _install_lock.locked()


def prepare_install(common, profile, plugin_id):
    """Stage downloads outside plugins; preserve installed versions and activate as a batch."""
    from .bootstrap import PRIME_HASH, PRIME_URL, DEFAULT_MIRRORS, download_checked
    specs = {
        'prime_backup': ('1.13.1', 'PrimeBackup-v1.13.1.pyz', PRIME_URL, PRIME_HASH),
        'candy_tools': ('1.0.2', 'Candy_Tools-v1.0.2.mcdr', 'https://github.com/Passion-Never-Dissipate/candy_tools/releases/download/1.0.2/Candy_Tools-v1.0.2.mcdr', 'd1cd50a22b6bee05cbd9b0aed89afb13e8ff6d44d058dcb9d1276c2282eab048'),
        'chunk_backup': ('2.0.3', 'Chunk_BackUp-v2.0.3.mcdr', 'https://github.com/Passion-Never-Dissipate/Chunk_BackUp/releases/download/v2.0.3/Chunk_BackUp-v2.0.3.mcdr', 'b6f66c9dd621104176d6b2e656353f932d9088a7621c84ab67f204cd8ee0374d'),
    }
    ids = [plugin_id] if plugin_id == 'prime_backup' else ['candy_tools', 'chunk_backup']
    # Check the whole dependency set before any network or plugin-directory writes.
    for item in ids:
        existing = archives(common, item)
        if existing and (len(existing) != 1 or existing[0][1] != specs[item][0]):
            raise RuntimeError(tr('install.incompatible', item))
    pending = []
    for item in ids:
        version, filename, url, digest = specs[item]
        existing = archives(common, item)
        if existing:
            if len(existing) != 1 or existing[0][1] != version:
                raise RuntimeError(tr('install.incompatible', item))
            pending.append(existing[0][0])
            continue
        stage = checked_path(common, 'runtime/plugin-downloads/' + filename)
        stage.parent.mkdir(parents=True, exist_ok=True)
        mirrors_path = Path(common) / 'download-sources.json'
        mirrors = read_json(mirrors_path).get('github_mirrors', DEFAULT_MIRRORS) if mirrors_path.exists() else DEFAULT_MIRRORS
        download_checked([url, *(base + url for base in mirrors)], stage, digest)
        pending.append(stage)
    if plugin_id == 'chunk_backup':
        from .chunk_backup_config import prepare
        prepare(profile, Path(read_json(Path(profile) / 'profile.json')['world_path']))
    else:
        from .profiles import validate_prime_binding
        validate_prime_binding(profile)
    adapter_id = 'singleplayer_' + plugin_id
    adapter = checked_path(common, 'runtime/backup-adapters/' + adapter_id + '.mcdr')
    if not adapter.is_file():
        raise RuntimeError(tr('install.adapter_missing'))
    import shutil
    result = []
    for path in [*pending, adapter]:
        target = checked_path(common, 'plugins/' + path.name)
        if path != target:
            if target.exists() and target.read_bytes() != path.read_bytes():
                raise RuntimeError(tr('install.file_conflict'))
            shutil.copy2(path, target)
        result.append(target)
    return result


def install(source, plugin_id):
    from .plugin import prime_busy, snapshot
    common = os.environ.get('MCDR_BRIDGE_COMMON')
    if not common:
        source.reply(tr('command.auto_required'))
        return
    if prime_busy() or not _install_lock.acquire(blocking=False):
        source.reply(tr('install.busy'))
        return
    server = source.get_server()
    session = snapshot().get('session')
    profile = Path.cwd()
    source.reply(tr('install.starting', plugin_id))
    def worker():
        newly_loaded = []
        try:
            paths = prepare_install(Path(common), profile, plugin_id)
            # Do not load a new backup scheduler after the world has closed.
            if snapshot().get('session') != session or not session:
                source.reply(tr('install.next_visit'))
                return
            ids = ['prime_backup', 'singleplayer_prime_backup'] if plugin_id == 'prime_backup' else ['candy_tools', 'chunk_backup', 'singleplayer_chunk_backup']
            newly_loaded = [item for item in ids if server.get_plugin_instance(item) is None]
            to_load = [str(path) for path, item in zip(paths, ids) if server.get_plugin_instance(item) is None]
            if to_load and not server.manipulate_plugins(load=to_load):
                raise RuntimeError(tr('install.load_failed'))
            if any(server.get_plugin_instance(item) is None for item in ids):
                raise RuntimeError(tr('install.incomplete'))
            source.reply(tr('install.loaded', plugin_id))
            if plugin_id == 'prime_backup':
                host = os.environ.get('MCDR_BRIDGE_HOST') or snapshot().get('host_player')
                if host:
                    prime_options(server, host)
                    _settings_shown.add(session)
        except Exception as exc:
            # A partially loaded upstream backup plugin must not expose unadapted restores.
            if plugin_id in newly_loaded and server.get_plugin_instance(plugin_id) is not None:
                server.unload_plugin(plugin_id)
            server.logger.exception('Backup plugin installation failed')
            source.reply(tr('install.failed', str(exc)))
        finally:
            _install_lock.release()
    threading.Thread(target=worker, name='backup-plugin-install', daemon=True).start()
