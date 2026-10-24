"""Resident controller: wait at menu, start a fresh MCDR process per save session."""
import argparse
import collections
import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from .profiles import ensure_profile, read_json, recommend

# One session's console log is capped so a runaway child cannot fill the disk; the flood guard below
# normally stops the cause long before this.
CHILD_LOG_LIMIT = 32 * 1024 * 1024
CHILD_LOG_KEEP = 2
# A closed stdin makes MCDR's console thread read an empty line forever and echo it into its log.
REPEAT_LIMIT = 2000
# How long a retired child may take to leave before the controller stops waiting by itself. The
# plugin finishes any backup or restore it still runs before it stops, so this only applies when the
# game is already gone; while the player is there the menu offers to terminate instead.
RETIRE_TIMEOUT = 300.0
# Waiting this long without the child leaving is reported to the player together with a way out.
RETIRE_NOTICE_AFTER = 30.0


class ChildLog:
    """Append-only console log that rotates instead of growing without bound."""

    def __init__(self, path, limit=CHILD_LOG_LIMIT, keep=CHILD_LOG_KEEP):
        self.path = Path(path)
        self.limit = limit
        self.keep = keep
        self.size = self.path.stat().st_size if self.path.is_file() else 0
        self.stream = self.path.open('a', encoding='utf8')

    def write(self, text):
        if self.stream is None:
            return
        try:
            self.stream.write(text)
            self.stream.flush()
        except (OSError, ValueError):
            return
        self.size += len(text.encode('utf8', 'ignore'))
        if self.size >= self.limit:
            self.rotate()

    def rotate(self):
        try:
            self.stream.close()
        except (OSError, ValueError):
            pass
        for index in range(self.keep, 1, -1):
            newer = self.path.with_suffix(self.path.suffix + f'.{index - 1}')
            older = self.path.with_suffix(self.path.suffix + f'.{index}')
            try:
                if newer.is_file():
                    newer.replace(older)
            except OSError:
                pass
        try:
            if self.path.is_file():
                self.path.replace(self.path.with_suffix(self.path.suffix + '.1'))
        except OSError:
            pass
        self.size = 0
        try:
            self.stream = self.path.open('a', encoding='utf8')
        except OSError:
            self.stream = None

    def close(self):
        if self.stream is not None:
            try:
                self.stream.close()
            except OSError:
                pass
            self.stream = None


class ChildReader(threading.Thread):
    """Drain the child's console into ChildLog and stop a repeating flood.

    MCDR answers a closed stdin with an endless echo of an empty command. That loop alternates
    between two messages, so counting only *consecutive* identical lines never sees it: the same
    line has to be counted inside a sliding window instead. Logging stops and the child is
    terminated once one message fills the window.
    """

    def __init__(self, stream, log, on_flood):
        super().__init__(name='mcdr-console', daemon=True)
        self.stream = stream
        self.log = log
        self.on_flood = on_flood
        # Enough room for the alternating pair to reach the limit twice per window.
        self.window = collections.deque(maxlen=max(REPEAT_LIMIT * 2, 64))
        self.counts = collections.Counter()
        self.flooded = False

    def run(self):
        try:
            for line in self.stream:
                if not self.flooded:
                    self.log.write(line)
                self._count(line.strip())
        except (OSError, ValueError):
            pass
        finally:
            try:
                self.stream.close()
            except OSError:
                pass

    def _count(self, text):
        if self.flooded:
            return
        if len(self.window) == self.window.maxlen:
            oldest = self.window[0]
            self.counts[oldest] -= 1
            if self.counts[oldest] <= 0:
                del self.counts[oldest]
        self.window.append(text)
        self.counts[text] += 1
        if self.counts[text] >= REPEAT_LIMIT:
            self.flooded = True
            try:
                self.on_flood(text)
            except Exception:  # noqa: BLE001 - the guard must never break the reader
                pass


def configure_host(common, player, language):
    """Only the local client's authenticated account is promoted, never LAN guests."""
    import re
    from ruamel.yaml import YAML
    yaml = YAML()
    for filename in ('permission.yml', 'config.yml'):
        path = Path(common) / filename
        config = _load_or_default(path, filename, yaml)
        if config is None:
            # config.yml is MCDR's own file: a damaged copy is moved aside and MCDR rewrites the
            # defaults on the next start, which is safer than guessing at its contents.
            continue
        changed = False
        if filename == 'permission.yml' and re.fullmatch(r'[A-Za-z0-9_]{1,16}', player):
            for key in ('guest', 'user', 'helper', 'admin', 'owner'):
                names = config.get(key) or []
                updated = [name for name in names if name != player]
                if key == 'owner':
                    updated.append(player)
                if names != updated:
                    config[key] = updated
                    changed = True
        if filename == 'config.yml' and language:
            # Retain the client's locale; MCDR's translation engine supplies fallbacks.
            locale = language.lower()
            if config.get('language') != locale:
                config['language'] = locale
                changed = True
        if changed:
            if filename == 'permission.yml':
                history = Path(common) / 'runtime/history' / f'permission.yml.before-host-update-{time.time_ns()}'
                history.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(path, history)
            temporary = path.with_suffix(path.suffix + '.tmp')
            with temporary.open('w', encoding='utf8') as stream:
                yaml.dump(config, stream)
            temporary.replace(path)
            if filename == 'permission.yml':
                # Keep the version that just parsed and wrote cleanly, so a later corruption can be
                # repaired from real data instead of falling back to an empty permission list.
                _remember_good(path)


def _write_yaml(path, data, yaml):
    """Replace the file atomically so a reader never sees a half-written document."""
    temporary = Path(path).with_suffix(Path(path).suffix + '.tmp')
    with temporary.open('w', encoding='utf8') as stream:
        yaml.dump(data, stream)
    temporary.replace(Path(path))


def _good_copy(path):
    return Path(path).parent / 'runtime/history' / 'permission.yml.last-good'


def _remember_good(path):
    import shutil
    try:
        target = _good_copy(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    except OSError:
        pass


def _load_or_default(path, filename, yaml):
    """Load a YAML file, replacing one that cannot be parsed.

    A zero-filled or truncated file (an interrupted write, a crash, a full disk) used to raise out
    of the controller's tick and stop MCDR for the whole session. The damaged copy is kept under
    runtime/history for diagnosis, and the caller continues with a usable document. MCDR's own
    config.yml is removed so it writes fresh defaults; permission.yml is rebuilt from scratch here
    because MCDR would otherwise keep failing on the same file.
    """
    import shutil
    try:
        with path.open(encoding='utf8') as stream:
            data = yaml.load(stream)
    except FileNotFoundError:
        return None
    except Exception as error:  # noqa: BLE001 - any unreadable file must not stop the controller
        return _rebuild(path, filename, yaml, error.__class__.__name__)
    if isinstance(data, dict):
        if filename == 'permission.yml':
            # Remember what parsed cleanly; that copy is what a later corruption is repaired from.
            good = _good_copy(path)
            try:
                if not good.is_file() or good.stat().st_size != Path(path).stat().st_size:
                    shutil.copy2(path, good)
            except OSError:
                pass
        return data
    try:
        empty = Path(path).stat().st_size == 0
    except OSError:
        empty = False
    if empty:
        # Zero bytes is the other shape of an interrupted write: it parses as "no document" instead
        # of raising, and MCDR would then run with an empty permission list without any complaint.
        return _rebuild(path, filename, yaml, '空文件')
    return None


def _rebuild(path, filename, yaml, problem):
    """Back a damaged file up, then restore what is still known about it."""
    import shutil
    history = Path(path).parent / 'runtime/history' / f'{Path(path).name}.corrupt-{time.time_ns()}'
    history.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(path, history)
    except OSError:
        pass
    logging.getLogger('singleplayer_bridge').warning(
        '%s 无法解析（%s），已备份到 %s', Path(path).name, problem, history)
    if filename != 'permission.yml':
        try:
            Path(path).unlink()
        except OSError:
            pass
        return None
    # Repair from the last file that parsed, so owners and helpers survive the damage; only fall
    # back to an empty document when no usable copy was ever recorded.
    restored = _restore_good(path, yaml)
    if restored is not None:
        # The damaged file is still on disk and MCDR reads it too, so it has to be replaced now
        # rather than only being used in memory.
        try:
            _write_yaml(path, restored, yaml)
            _remember_good(path)
        except OSError:
            pass
        logging.getLogger('singleplayer_bridge').warning(
            '%s 已从上一次可用的副本恢复', Path(path).name)
        return restored
    # The owner is added by the caller, so the document starts empty and gets written back.
    return {'guest': [], 'user': [], 'helper': [], 'admin': [], 'owner': []}


def _restore_good(path, yaml):
    """Return the last document that parsed, or None when there is no usable copy."""
    good = _good_copy(path)
    try:
        with good.open(encoding='utf8') as stream:
            data = yaml.load(stream)
    except Exception:  # noqa: BLE001 - a missing or equally damaged copy just means "no repair"
        return None
    return data if isinstance(data, dict) else None


class Controller:
    def __init__(self, common, game_config, state_file, client_id, python=None, progress=None):
        self.common = Path(common).resolve()
        self.game_config = Path(game_config).resolve()
        self.state_file = Path(state_file).resolve()
        self.client_id = client_id
        self.python = str(python or sys.executable)
        self.process = None
        self.session = None
        self.retiring = False
        self.retired_at = 0.0
        self.output = None
        self.reader = None
        self.setup_requests = set()
        self.lease = None
        self.progress = progress or (lambda stage: None)
        self.published_retire = ''
        self.terminate_handled = False

    def acquire(self):
        if self.lease is not None:
            return True
        try:
            installation = lock_common(self.common, '.installation.lock')
        except OSError:
            self.progress('waiting_instance')
            return False
        try:
            self.lease = lock_common(self.common)
        except OSError:
            self.progress('waiting_instance')
            return False
        finally:
            installation.close()
        return True

    def close(self):
        self.retire()
        if self.process:
            self._wait_or_kill(RETIRE_TIMEOUT)
        # Also drop the log handle when the child never started: Popen can fail after the file is open.
        self._close_output()
        self.process = None
        if self.lease:
            self.lease.close()
            self.lease = None

    def _wait_or_kill(self, timeout):
        """A retired child that ignores the request must not keep the controller alive."""
        try:
            self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logging.warning('MCDR did not exit within %.0fs; terminating it', timeout)
            try:
                self.process.kill()
                self.process.wait(timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _close_output(self):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        if self.reader is not None:
            self.reader.join(timeout=5)
            self.reader = None
        if self.output is not None:
            self.output.close()
            self.output = None

    def _retire_status_path(self):
        return Path(self.state_file).parent / 'retire-status.json'

    def _publish_retire_state(self):
        """Tell the game how long the retired child has been finishing its work."""
        active = bool(self.process and self.retiring and self.process.poll() is None)
        seconds = int(time.monotonic() - self.retired_at) if active and self.retired_at else 0
        data = json.dumps({'protocol': 1, 'stalled': active and seconds >= RETIRE_NOTICE_AFTER,
                           'seconds': seconds})
        if data == self.published_retire:
            return
        path = self._retire_status_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix('.json.tmp')
            temporary.write_text(data, encoding='utf8')
            temporary.replace(path)
            self.published_retire = data
        except OSError:
            pass

    def _apply_terminate_request(self):
        """The player asked to stop MCDR while it still had tasks to finish."""
        request = Path(self.state_file).parent / 'terminate.request'
        if not request.exists():
            return
        try:
            request.unlink()
        except OSError:
            pass
        if self.process and self.process.poll() is None:
            logging.warning('The player asked to stop MCDR before its tasks finished; terminating it')
            self._wait_or_kill(0)

    def _flood_detected(self, text):
        """The child is looping on an empty command; stop it instead of filling the disk."""
        logging.error('MCDR console repeated one line %d times (%s); terminating it',
                      REPEAT_LIMIT, text[:80])
        try:
            if self.process and self.process.poll() is None:
                self.process.kill()
        except OSError:
            pass

    def retire(self):
        if self.process and self.process.poll() is None and not self.retiring:
            try:
                self.process.stdin.write('!!spbridge internal retire\n')
                self.process.stdin.flush()
                self.retiring = True
                self.retired_at = time.monotonic()
                logging.info('Waiting for plugin tasks before retiring profile')
            except (OSError, BrokenPipeError):
                pass

    def tick(self, state):
        if self.process and self.process.poll() is not None:
            self._close_output()
            self.process = None
            # Keep the session marker after user-issued MCDR exit: do not auto-loop restart.
        # While the game is still there, a long retire is reported to the player with an offer to
        # stop it; the controller never ends a backup or restore on its own.
        self._publish_retire_state()
        self._apply_terminate_request()
        desired = state.get('session') if state.get('world_path') else None
        if self.process and desired != self.session:
            self.retire()
            return
        if self.process is None and desired != self.session:
            if desired and not self.acquire():
                return
            self.session = desired
            self.retiring = False
            if desired:
                self.progress('starting')
                language = state.get('language', 'en_us')
                player = state.get('host_player', '')
                configure_host(self.common, player, language)
                profile = ensure_profile(self.common, state['world_path'], language)
                (self.common / 'runtime').mkdir(parents=True, exist_ok=True)
                environment = dict(os.environ, PYTHONUTF8='1', MCDR_BRIDGE_COMMON=str(self.common),
                                   MCDR_BRIDGE_CONFIG=str(self.game_config), MCDR_BRIDGE_WORLD_PATH=state['world_path'],
                                   MCDR_BRIDGE_SESSION=desired, MCDR_BRIDGE_HOST=player,
                                   MCDR_BRIDGE_LANGUAGE=language, MCDR_BRIDGE_CLIENT_ID=self.client_id)
                world_log = self.common / 'log' / profile.name
                world_log.mkdir(parents=True, exist_ok=True)
                self.output = ChildLog(world_log / 'controller-child.log')
                environment['MCDR_BRIDGE_RUNTIME'] = str(self.common / 'runtime')
                environment['MCDR_BRIDGE_LOG_DIR'] = str(world_log)
                if 'bridge_port' in state:
                    port = state['bridge_port']
                    if type(port) is not int or not 1 <= port <= 65535:
                        raise ValueError('Invalid client bridge port')
                    environment['MCDR_BRIDGE_PORT'] = str(port)
                mcdr_entrypoint = ('import os; from mcdreforged.constants import core_constant; '
                    'core_constant.LOGGING_FILE=os.path.join(os.environ["MCDR_BRIDGE_LOG_DIR"], "MCDR.log"); '
                    'from mcdreforged import mcdr_entrypoint; mcdr_entrypoint.entrypoint()')
                self.process = subprocess.Popen([self.python, '-c', mcdr_entrypoint, 'start',
                    '--config', str(self.common / 'config.yml'), '--permission', str(self.common / 'permission.yml')],
                    cwd=profile, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, encoding='utf8',
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                # The console is drained on a thread so the log can be capped and a runaway child
                # can be stopped, which a direct file handle could not do.
                self.reader = ChildReader(self.process.stdout, self.output, self._flood_detected)
                self.reader.start()
                logging.info('MCDR profile started: %s', profile.name)
            elif self.lease:
                self.lease.close()
                self.lease = None
        for request in state.get('setup_requests', [])[:64]:
            if not (self.process and not self.retiring and self.process.poll() is None
                    and request.get('id') not in self.setup_requests and request.get('session') == self.session):
                continue
            # A local attended Fabric command created this request; it is never accepted from server chat.
            action = request.get('action')
            if action == 'recommend':
                self.process.stdin.write('!!spbridge config recommend\n')
            elif action == 'owner':
                import re
                player = request.get('player', '')
                if re.fullmatch('[A-Za-z0-9_]{1,16}', player):
                    self.process.stdin.write(f'!!MCDR permission set {player} owner\n')
            self.process.stdin.flush()
            self.setup_requests.add(request.get('id'))


def lock_common(common, name='.controller.lock'):
    runtime = Path(common) / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    handle = (runtime / name).open('a+b')
    try:
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            # Reading the locked byte fails on Windows even before try-lock.
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        handle.close()
        raise
    return handle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--common', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--client-id', required=True)
    parser.add_argument('--parent-pid', type=int, required=True)
    args = parser.parse_args()
    import psutil
    parent = psutil.Process(args.parent_pid)
    born = parent.create_time()
    args.common.mkdir(parents=True, exist_ok=True)
    (args.common / 'log').mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=args.common / 'log/controller.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf8')
    from .installation_progress import InstallationProgress
    controller = Controller(args.common, args.config, args.state, args.client_id,
                            progress=InstallationProgress(args.common, args.client_id).report)
    logging.info('Controller ready; waiting for a singleplayer world')
    try:
        while True:
            try:
                alive = parent.is_running() and parent.create_time() == born
            except psutil.NoSuchProcess:
                alive = False
            try:
                state = read_json(args.state)
                if state.get('client_id') != args.client_id:
                    alive = False
            except (OSError, ValueError):
                state = {}
            if not alive:
                state = {}
            controller.tick(state)
            if (not alive or state.get('closing')) and not controller.process:
                break
            time.sleep(0.25)
    except Exception:
        logging.exception('Controller failed; waiting for safe shutdown')
    finally:
        controller.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
