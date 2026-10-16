"""Publication must reject a mismatched tag and advertise only compiled game versions."""
import io
import json
import shutil
import sys
from urllib.error import HTTPError
from pathlib import Path

import pytest

import check_release
import publish_curseforge
import verify_artifacts


def test_release_jar_checksum_uses_github_asset_digest_without_sidecar(tmp_path):
    import hashlib
    artifact = tmp_path / 'mod.jar'
    artifact.write_bytes(b'test jar')
    assets = tmp_path / 'release-assets.json'
    assets.write_text(json.dumps({'assets': [{'name': artifact.name, 'digest':
                                            'sha256:' + hashlib.sha256(artifact.read_bytes()).hexdigest()}]}))
    verify_artifacts.verify_checksum(artifact, assets)
    artifact.write_bytes(b'tampered jar')
    with pytest.raises(AssertionError, match='checksum mismatch'):
        verify_artifacts.verify_checksum(artifact, assets)
    assets.write_text(json.dumps({'assets': [{'name': artifact.name, 'digest': None}]}))
    with pytest.raises(AssertionError, match='Missing GitHub'):
        verify_artifacts.verify_checksum(artifact, assets)


@pytest.mark.parametrize('body', [b'not JSON', b'{"headers":{"X-Api-Token":"test-only-token"}}',
                                b'{"message":"Invalid dependency test-only-token"}'])
def test_curseforge_error_diagnostics_do_not_expose_credentials(body):
    error = HTTPError('https://example.invalid/upload', 400, 'Bad request', {}, io.BytesIO(body))
    detail = publish_curseforge.upload_error_detail(error, 'test-only-token')
    assert 'test-only-token' not in detail
    if b'message' in body:
        assert 'Invalid dependency' in detail


@pytest.mark.parametrize('tag,draft,allowed', [('v0.4.1', False, True), ('0.4.1', False, True),
                                               ('v0.3.9', False, False), ('v0.3.10', True, False)])
def test_release_tag_guard(tmp_path, monkeypatch, tag, draft, allowed):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'compat').mkdir()
    (tmp_path / 'compat/versions.json').write_text(json.dumps({'modVersion': '0.4.1'}))
    (tmp_path / 'release-metadata.json').write_text(json.dumps({'tagName': tag, 'isDraft': draft, 'isPrerelease': True}))
    # The version guards read the checkout, not the caller's working directory.
    monkeypatch.setattr(check_release, 'declared_bridge_version', lambda root=None: '0.4.1')
    monkeypatch.setattr(check_release, 'installed_mcdr_version', lambda root=None: '2.16.0')
    if allowed:
        check_release.main()
    else:
        with pytest.raises(SystemExit):
            check_release.main()


def test_loader_versions_stay_aligned_with_the_release():
    bridge = check_release.declared_bridge_version()
    matrix = json.loads((check_release.ROOT / 'compat/versions.json').read_text(encoding='utf8'))
    assert bridge == matrix['modVersion']
    # The probe, the installer and the pinned requirements must never drift apart.
    pinned = (check_release.ROOT / 'requirements-prime-backup.txt').read_text(encoding='utf8')
    assert f'mcdreforged=={check_release.installed_mcdr_version()}' in pinned


def test_loader_version_guards_reject_a_stale_declaration(tmp_path):
    for name in ('fabric-bridge', 'python', 'prime-backup-adapter', 'chunk-backup-adapter'):
        shutil.copytree(check_release.ROOT / name, tmp_path / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', 'build', 'logs', 'run'))
    shutil.copy2(check_release.ROOT / 'requirements-prime-backup.txt', tmp_path / 'requirements-prime-backup.txt')
    assert check_release.declared_bridge_version(tmp_path) == check_release.declared_bridge_version()
    properties = tmp_path / 'fabric-bridge/gradle.properties'
    properties.write_text(properties.read_text(encoding='utf8').replace('version=0.6.0', 'version=0.5.2'), encoding='utf8')
    with pytest.raises(SystemExit, match='BUNDLED_VERSION'):
        check_release.declared_bridge_version(tmp_path)
    plugin = tmp_path / 'python/mcdreforged.plugin.json'
    plugin.write_text(plugin.read_text(encoding='utf8').replace('"0.6.0"', '"0.5.0"'), encoding='utf8')
    properties.write_text(properties.read_text(encoding='utf8').replace('version=0.5.2', 'version=0.6.0'), encoding='utf8')
    with pytest.raises(SystemExit, match='expected 0.6.0'):
        check_release.declared_bridge_version(tmp_path)


@pytest.mark.parametrize('loader', ['fabric', 'neoforge'])
def test_curseforge_upload_metadata(tmp_path, monkeypatch, loader):
    matrix = json.loads((publish_curseforge.ROOT / 'compat/versions.json').read_text(encoding='utf8'))
    (tmp_path / 'compat').mkdir()
    (tmp_path / 'dist').mkdir()
    (tmp_path / 'compat/versions.json').write_text(json.dumps(matrix))
    (tmp_path / 'release-metadata.json').write_text(json.dumps({'body': 'test release', 'isPrerelease': True}))
    artifact = tmp_path / 'dist' / f"mcdr-singleplayer-{matrix['modVersion']}+{loader}+mc1.21.x.jar"
    artifact.write_bytes(b'test-only-jar')
    monkeypatch.setattr(publish_curseforge, 'ROOT', tmp_path)
    monkeypatch.setenv('CURSEFORGE_TOKEN', 'test-only-token')
    monkeypatch.setattr(sys, 'argv', ['publish_curseforge.py', '--loader', loader, '--family', '1.21.x'])
    requests = []

    def fake_upload(request, timeout):
        requests.append(request)
        return io.BytesIO(b'{"id":123}')

    monkeypatch.setattr(publish_curseforge, 'urlopen', fake_upload)
    publish_curseforge.main()
    request = requests[0]
    assert request.full_url.endswith('/api/projects/1723660/upload-file')
    body = request.data
    raw = body.split(b'\r\n\r\n', 1)[1].split(b'\r\n--', 1)[0]
    metadata = json.loads(raw)
    assert metadata['releaseType'] == 'beta'
    expected = [r['minecraft'] for r in matrix['versions'] if r['family'] == '1.21.x']
    assert metadata['gameVersionNames'] == expected + ['Fabric' if loader == 'fabric' else 'NeoForge', 'Client']
    assert b'test-only-token' not in body
    assert ('relations' in metadata) == (loader == 'fabric')
    if loader == 'fabric':
        dependency = metadata['relations']['projects'][0]
        assert type(dependency['projectID']) is int
        assert dependency['projectID'] == 306612
        assert dependency['slug'] == 'fabric-api'
        assert dependency['type'] == 'requiredDependency'
