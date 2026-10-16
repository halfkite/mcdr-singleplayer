"""The startup probe must report the same MCDR release the installer prepares."""
import json
from pathlib import Path

import pytest

from singleplayer_bridge import bootstrap


class _Probe:
    def __init__(self, version=None, returncode=0):
        self.returncode = returncode
        self.stdout = (version + '\n') if version else ''
        self.stderr = ''


def _probe(monkeypatch, version=None, returncode=0):
    monkeypatch.setattr(bootstrap.subprocess, 'run', lambda *a, **k: _Probe(version, returncode))


def _environment(common: Path) -> Path:
    if bootstrap.os.name == 'nt':
        python = common / 'runtime/.bridge-venv/Scripts/python.exe'
    else:
        python = common / 'runtime/.bridge-venv/bin/python'
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_bytes(b'')
    return python


def test_missing_environment_asks_for_the_download(tmp_path, monkeypatch):
    _probe(monkeypatch, version=bootstrap.MCDR_VERSION)
    assert bootstrap.install_state(tmp_path) == ('missing', 'the isolated environment is absent')


def test_installed_environment_reports_ready(tmp_path, monkeypatch):
    _probe(monkeypatch, version=bootstrap.MCDR_VERSION)
    _environment(tmp_path)
    bootstrap.write_json(tmp_path / 'runtime/runtime-install.json', dict(mcdr=bootstrap.MCDR_VERSION))
    assert bootstrap.install_state(tmp_path) == ('ready', f'MCDR {bootstrap.MCDR_VERSION} is installed')


def test_other_versions_are_reported_as_outdated(tmp_path, monkeypatch):
    _probe(monkeypatch, version='2.15.0')
    _environment(tmp_path)
    bootstrap.write_json(tmp_path / 'runtime/runtime-install.json', dict(mcdr=bootstrap.MCDR_VERSION))
    status, detail = bootstrap.install_state(tmp_path)
    assert status == 'outdated' and '2.15.0' in detail

    # A marker from an older bridge build is enough on its own.
    _probe(monkeypatch, version=bootstrap.MCDR_VERSION)
    bootstrap.write_json(tmp_path / 'runtime/runtime-install.json', dict(mcdr='2.15.0'))
    status, detail = bootstrap.install_state(tmp_path)
    assert status == 'outdated' and '2.15.0' in detail


def test_environment_that_cannot_import_mcdr_is_broken(tmp_path, monkeypatch):
    _environment(tmp_path)
    _probe(monkeypatch, returncode=1)
    assert bootstrap.install_state(tmp_path) == ('broken', 'the isolated environment cannot load MCDR')


def test_check_only_never_installs_and_reports_its_status(tmp_path, monkeypatch, capsys):
    _probe(monkeypatch, version=bootstrap.MCDR_VERSION)
    monkeypatch.setattr(bootstrap, 'install', lambda *a, **k: pytest.fail('check-only must not install'))
    monkeypatch.setattr('sys.argv', ['bootstrap.py', '--common', str(tmp_path), '--resources', str(tmp_path),
                                     '--check-only'])
    assert bootstrap.main() == 3
    assert json.loads(capsys.readouterr().out.strip())['status'] == 'missing'


def test_an_expected_version_mismatch_stops_before_installing(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, 'install', lambda *a, **k: pytest.fail('a mismatched bundle must not install'))
    monkeypatch.setattr('sys.argv', ['bootstrap.py', '--common', str(tmp_path), '--resources', str(tmp_path),
                                     '--expected-mcdr', '0.0.1'])
    assert bootstrap.main() == 3
