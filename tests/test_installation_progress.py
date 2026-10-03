import json
import sys
from types import SimpleNamespace

import pytest

from singleplayer_bridge import bootstrap, supervisor


def test_dependency_mirror_fallback_reports_actual_attempts(tmp_path):
    progress = bootstrap.InstallationProgress(tmp_path, 'this-client')
    attempts = []

    def runner(command, **kwargs):
        attempts.append(json.loads(progress.path.read_text()))
        return SimpleNamespace(returncode=1 if len(attempts) == 1 else 0)

    bootstrap.install_dependencies('python', 'requirements.txt', indexes=['first', 'fallback'],
                                   runner=runner, progress=progress.report)
    assert [(value['stage'], value['attempt']) for value in attempts] == [('dependencies', 1), ('dependencies', 2)]
    assert all(value['client_id'] == 'this-client' for value in attempts)
    assert not progress.path.with_suffix('.json.tmp').exists()


@pytest.mark.parametrize('fails', [False, True])
def test_installer_reports_failure_or_waits_for_connection_without_claiming_ready(tmp_path, monkeypatch, fails):
    monkeypatch.setattr(sys, 'argv', ['bridge_bootstrap.py', '--common', str(tmp_path), '--resources', str(tmp_path),
                                    '--state', str(tmp_path / 'state.json'), '--config', str(tmp_path / 'config.yml'),
                                    '--client-id', 'this-client', '--parent-pid', '123'])
    monkeypatch.setattr(supervisor, 'lock_common', lambda *args: SimpleNamespace(close=lambda: None))

    def install(*args, progress, **kwargs):
        progress('dependencies', 1)
        if fails:
            raise OSError('test dependency download failure')
        return sys.executable

    monkeypatch.setattr(bootstrap, 'install', install)
    monkeypatch.setattr(bootstrap.subprocess, 'Popen', lambda *args, **kwargs: SimpleNamespace(wait=lambda: 0))
    assert bootstrap.main() == (1 if fails else 0)
    status = json.loads((tmp_path / 'runtime/install-progress.json').read_text())
    assert status == dict(protocol=1, client_id='this-client', stage='failed' if fails else 'starting', attempt=0)
