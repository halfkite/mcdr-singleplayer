"""Resident controller: wait at menu, start a fresh MCDR process per save session."""
import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from .profiles import ensure_profile, read_json, recommend


def configure_host(common, player, language):
    """Only the local client's authenticated account is promoted, never LAN guests."""
    import re
    from ruamel.yaml import YAML
    yaml = YAML()
    for filename in ('permission.yml', 'config.yml'):
        path = Path(common) / filename
        with path.open(encoding='utf8') as stream:
            config = yaml.load(stream)
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
        self.output = None
        self.setup_requests = set()
        self.lease = None
        self.progress = progress or (lambda stage: None)

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
            self.process.wait()  # Keep the lease until outstanding restore tasks finish.
            self.process.stdin.close()
            self.output.close()
            self.process = None
        if self.lease:
            self.lease.close()
            self.lease = None

    def retire(self):
        if self.process and self.process.poll() is None and not self.retiring:
            try:
                self.process.stdin.write('!!spbridge internal retire\n')
                self.process.stdin.flush()
                self.retiring = True
                logging.info('Waiting for plugin tasks before retiring profile')
            except (OSError, BrokenPipeError):
                pass

    def tick(self, state):
        if self.process and self.process.poll() is not None:
            self.process.stdin.close()
            self.output.close()
            self.process = None
            # Keep the session marker after user-issued MCDR exit: do not auto-loop restart.
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
                self.output = (world_log / 'controller-child.log').open('a', encoding='utf8')
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
                    cwd=profile, env=environment, stdin=subprocess.PIPE, stdout=self.output,
                    stderr=subprocess.STDOUT, text=True, encoding='utf8',
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
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
