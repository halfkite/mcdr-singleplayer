import threading
import json
import uuid
import os
import time
from pathlib import Path
from .protocol import CHECKED_PREFIX, COMPLETION_PREFIX, TREE_PREFIX

from mcdreforged.api.command import Literal, QuotableText

from .handler import BridgeInfo, SingleplayerHandler

_lock = threading.Lock()
_state = {}
_progress_context = {}
_waiters = {}
_closed_sessions = set()
_closed_cv = threading.Condition(_lock)
_retiring = threading.Event()
_publisher_stop = threading.Event()
_prompted_sessions = set()


def prime_busy():
    try:
        from prime_backup.mcdr import mcdr_entrypoint
        manager = mcdr_entrypoint.task_manager
        return manager is not None and any(worker.task_queue.unfinished_size() for worker in (manager.worker_heavy, manager.worker_light))
    except ImportError:
        return False


def retire(source):
    if _retiring.is_set():
        return
    _retiring.set()
    server = source.get_server()
    def finish():
        # In particular, SERVER_STOPPED during PB restore does not mean the restore finished.
        time.sleep(0.5)
        while prime_busy():
            time.sleep(0.1)
        if server.is_server_running():
            server.stop()
            server.wait_until_stop()
        server.exit()
    threading.Thread(target=finish, name='profile-retire', daemon=True).start()


def profile_list(source):
    common = os.environ.get('MCDR_BRIDGE_COMMON')
    if not common:
        source.reply('此功能需要游戏自动启动模式。')
        return
    names = sorted(p.name for p in (Path(common) / 'date').iterdir() if p.is_dir() and not p.name.startswith('.') and (p / 'profile.json').is_file()) if (Path(common) / 'date').is_dir() else []
    source.reply('存档配置：' + '，'.join(names))


def profile_import(source, context, replace=False):
    common = os.environ.get('MCDR_BRIDGE_COMMON')
    if not common:
        source.reply('此功能需要游戏自动启动模式。')
        return
    if prime_busy():
        source.reply('Prime Backup 正在执行任务，请完成后再导入。')
        return
    from .profiles import import_configs
    try:
        copied = import_configs(common, Path.cwd(), context['world'], replace)
        source.reply('已导入 {} 个配置文件；下次进入存档生效。原有文件{}。'.format(len(copied), '已备份后替换' if replace else '保留'))
    except (ValueError, OSError) as exc:
        source.reply('导入失败：' + str(exc))


def recommend_command(source):
    if not os.environ.get('MCDR_BRIDGE_COMMON'):
        source.reply('此功能需要游戏自动启动模式。')
        return
    if prime_busy():
        source.reply('Prime Backup 正在执行任务，请完成后再配置。')
        return
    from .profiles import recommend
    recommend(Path.cwd(), language=os.environ.get('MCDR_BRIDGE_LANGUAGE', 'en_us'))
    source.reply('已启用当前存档的 Prime Backup 推荐配置。正在重新加载插件。')
    source.get_server().reload_plugin('prime_backup')
    prompt_choices(source.get_server(), force=True)


def choose_config(source, key, enabled):
    if not os.environ.get('MCDR_BRIDGE_COMMON'):
        source.reply('此功能需要游戏自动启动模式。')
        return
    if prime_busy():
        source.reply('Prime Backup 正在执行任务，请完成后再次点击选项。')
        return
    from .profiles import recommend
    recommend(Path.cwd(), **{key: enabled})
    source.get_server().reload_plugin('prime_backup')
    source.reply({'auto_backup': '自动备份', 'auto_delete': '自动删除', 'backup_enabled': '备份'}[key] + ('已开启。' if enabled else '已关闭。'))


def prompt_choices(server, force=False):
    from .profiles import read_json
    from mcdreforged.api.rtext import RText, RTextList, RAction, RColor
    host = os.environ.get('MCDR_BRIDGE_HOST') or snapshot().get('host_player')
    session = snapshot().get('session')
    if not host or not session or host not in snapshot().get('players', []) or not os.environ.get('MCDR_BRIDGE_COMMON'):
        return
    if session in _prompted_sessions and not force:
        return
    path = Path('config/singleplayer_bridge/config.json')
    config = read_json(path) if path.exists() else {}
    chinese = os.environ.get('MCDR_BRIDGE_LANGUAGE', 'en_us').lower().startswith('zh_')
    for key, question in [('backup_enabled', '是否开启备份？推荐配置默认已开启 Prime Backup。' if chinese else 'Enable backups? Prime Backup is enabled by default.'),
                          ('auto_backup', '是否开启自动备份？开启后每 4 小时备份一次。' if chinese else 'Enable automatic backup every 4 hours?'),
                          ('auto_delete', '是否开启自动删除？保留最近 40 份、每日 1 份保留 30 天、每周 1 份保留 30 周。' if chinese else 'Enable automatic pruning? Keep last 40, daily 30, weekly 30 backups.')]:
        if key not in config or force:
            command = 'backup' if key == 'backup_enabled' else key
            message = RTextList(question, ' ', RText('[开启]' if chinese else '[Enable]', RColor.green).c(RAction.run_command, f'/!!spbridge config {command} on'),
                ' ', RText('[关闭]' if chinese else '[Disable]', RColor.gray).c(RAction.run_command, f'/!!spbridge config {command} off'))
            server.tell(host, message)
    _prompted_sessions.add(session)


def start_publisher(server):
    from .commands import command_tree
    stop = _publisher_stop
    def publish():
        previous = None
        previous_session = None
        while not stop.wait(0.5):
            session = snapshot().get('session')
            if not session or not server.is_server_running():
                previous = None
                continue
            try:
                tree = command_tree(server)
                if tree != previous or session != previous_session:
                    pieces = [tree[i:i + 6000] for i in range(0, len(tree), 6000)]
                    if len(pieces) > 256:
                        raise ValueError('MCDR command tree exceeds transport limit')
                    revision = uuid.uuid4().hex
                    for index, piece in enumerate(pieces):
                        if stop.is_set():
                            return
                        server.execute(TREE_PREFIX + json.dumps(dict(session=session, revision=revision,
                            index=index, total=len(pieces), payload=piece), ensure_ascii=False))
                    server.logger.info('MCDR command tree synchronized (%s chunks)', len(pieces))
                    previous, previous_session = tree, session
                prompt_choices(server)
            except Exception:
                server.logger.exception('Could not synchronize MCDR commands/settings')
                stop.wait(2)
    threading.Thread(target=publish, name='mcdr-command-tree', daemon=True).start()


def unload():
    _publisher_stop.set()


def reset():
    with _lock:
        _state.clear()
        for waiting in _waiters.values():
            waiting['error'] = 'Bridge connection stopped'
            waiting['done'].set()
        _closed_cv.notify_all()


def snapshot():
    with _lock:
        return dict(_state)


def restore_progress_context():
    with _lock:
        return dict(_progress_context)


def observe(info, server=None):
    if not isinstance(info, BridgeInfo):
        return
    event = info.bridge_event
    if event.get('type') == 'suggest_request' and server is not None:
        # MCDR 2.16 has no public completion API. This narrow adapter uses its actual
        # suggestion engine, including permission checks and plugin-provided suggestions.
        core = server._mcdr_server
        source = server.get_player_command_source(event['player'])
        try:
            suggestions = core.command_manager.suggest_command(event['text'], source)
            values = list(dict.fromkeys(s.command for s in suggestions if s.command.startswith(event['text'])))[:100]
            while len(json.dumps(values, ensure_ascii=False)) > 8000:
                values.pop()
        except Exception:
            values = []
        server.execute(COMPLETION_PREFIX + json.dumps(dict(id=event['id'], session=event['session'], suggestions=values), ensure_ascii=False))
        return
    with _lock:
        if event.get('type') == 'world_info':
            _state.clear()
            _state.update(event)
            _progress_context.clear()
            _progress_context.update(event)
        elif event.get('type') in {'ready', 'pause', 'heartbeat'}:
            _state['paused'] = event['paused']
        elif event.get('type') in {'player_joined', 'player_left'}:
            players = set(_state.get('players', []))
            if event['type'] == 'player_joined':
                players.add(event['player'])
            else:
                players.discard(event['player'])
            _state['players'] = sorted(players)
        elif event.get('type') == 'world_stopped':
            if len(_closed_sessions) >= 64:
                _closed_sessions.clear()
            _closed_sessions.add(event['session'])
            _state.clear()
            _closed_cv.notify_all()
        elif event.get('type') == 'command_result':
            waiting = _waiters.get(event['id'])
            if waiting is not None:
                waiting['result'] = event
                waiting['done'].set()
    if event.get('type') == 'world_info' and server is not None and event.get('host_player'):
        host = event['host_player']
        server.set_permission_level(host, 4)
        preference = server.get_preference(host)
        preference.language = event.get('language', 'en_us')
        server.set_preference(host, preference)


def execute_checked(server, command, timeout=12):
    """For worker threads: return actual game acknowledgment, never infer from log text."""
    request_id = uuid.uuid4().hex
    waiting = {'done': threading.Event()}
    with _lock:
        if not _state.get('session'):
            raise RuntimeError('No singleplayer world connected')
        _waiters[request_id] = waiting
    try:
        server.execute(CHECKED_PREFIX + json.dumps({'id': request_id, 'command': command}, ensure_ascii=False))
        if not waiting['done'].wait(timeout):
            raise RuntimeError('Game command acknowledgment timed out; no automatic replay')
        result = waiting.get('result')
        if result is None:
            raise RuntimeError(waiting.get('error', 'Bridge connection lost'))
        if not result['success']:
            raise RuntimeError(result['text'])
        return result
    finally:
        with _lock:
            _waiters.pop(request_id, None)


def wait_world_closed(session, timeout=60):
    with _closed_cv:
        if not _closed_cv.wait_for(lambda: session in _closed_sessions or _state.get('session') != session, timeout):
            raise RuntimeError('World shutdown timed out; restoration cancelled')
        if session not in _closed_sessions:
            raise RuntimeError('Bridge detached without confirming world shutdown; restoration cancelled')


def status(source):
    with _lock:
        state = dict(_state)
    if not state.get('session'):
        source.reply('单人桥接：尚未连接世界。进入单人世界后连接；!!MCDR server start 可重新连接。')
    else:
        source.reply('单人桥接：{}，Minecraft {}，存档 {}'.format(
            '已暂停' if state.get('paused') else '已连接', state['game_version'], state['world_path']))


def load(server, prev_module):
    global _publisher_stop
    previous = getattr(prev_module, 'plugin', None)
    if previous is not None and hasattr(previous, 'unload'):
        previous.unload()
    _publisher_stop = threading.Event()
    saved = previous.snapshot() if previous is not None and hasattr(previous, 'snapshot') else {}
    progress_context = previous.restore_progress_context() if previous is not None and hasattr(previous, 'restore_progress_context') else {}
    reset()
    with _lock:
        _state.update(saved)
        _progress_context.clear()
        _progress_context.update(progress_context)
    server.register_server_handler(SingleplayerHandler())
    server.register_help_message('!!spbridge', '查看单人世界桥接状态', permission=2)
    server.register_command(
        Literal('!!spbridge').requires(lambda source: source.has_permission(2))
        .runs(status).then(Literal('status').runs(status))
        .then(Literal('profile').requires(lambda source: source.has_permission(3))
            .then(Literal('list').runs(profile_list))
            .then(Literal('import').then(QuotableText('world')
                .runs(profile_import).then(Literal('--replace').runs(lambda source, ctx: profile_import(source, ctx, True))))))
        .then(Literal('config').requires(lambda source: source.has_permission(3))
            .then(Literal('recommend').runs(recommend_command))
            .then(Literal('backup').then(Literal('on').runs(lambda source: choose_config(source, 'backup_enabled', True)))
                .then(Literal('off').runs(lambda source: choose_config(source, 'backup_enabled', False))))
            .then(Literal('auto_backup').then(Literal('on').runs(lambda source: choose_config(source, 'auto_backup', True)))
                .then(Literal('off').runs(lambda source: choose_config(source, 'auto_backup', False))))
            .then(Literal('auto_delete').then(Literal('on').runs(lambda source: choose_config(source, 'auto_delete', True)))
                .then(Literal('off').runs(lambda source: choose_config(source, 'auto_delete', False)))))
        .then(Literal('internal').requires(lambda source: source.is_console)
            .then(Literal('retire').runs(retire)))
    )
    if server.is_server_running():
        server.set_exit_after_stop_flag(False)
    server.logger.info('单人桥接已加载。MCDR 的 start/stop/kill 管理代理连接；不会关闭或重启游戏世界。')
    start_publisher(server)
