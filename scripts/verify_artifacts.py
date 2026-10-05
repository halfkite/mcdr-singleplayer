"""Check distribution metadata and every explicitly selected variant before publishing."""
import argparse
import hashlib
import io
import json
import re
import struct
import tomllib
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def verify_checksum(path, release_assets=None):
    if release_assets is None:
        expected_hash = path.with_suffix('.sha256').read_text().split()[0]
    else:
        assets = json.loads(Path(release_assets).read_text(encoding='utf8'))['assets']
        matches = [asset for asset in assets if asset['name'] == path.name]
        assert len(matches) == 1, 'Missing or ambiguous Release artifact'
        digest = matches[0].get('digest') or ''
        assert digest.startswith('sha256:') and len(digest) == 71, 'Missing GitHub artifact SHA-256 digest'
        expected_hash = digest.removeprefix('sha256:')
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash, 'Artifact checksum mismatch'


def verify(loader, family, release_assets=None, timestamp=None):
    matrix = json.loads((ROOT / 'compat/versions.json').read_text(encoding='utf8'))
    rows = [r for r in matrix['versions'] if r['family'] == family]
    version = matrix['modVersion']
    if timestamp:
        if not re.fullmatch(r'\d{8}-\d{4}', timestamp):
            raise ValueError('Development timestamp must use UTC YYYYMMDD-HHMM format')
        version += '-dev.' + timestamp.replace('-', '.')
    path = ROOT / 'dist' / f"mcdr-singleplayer-{version}+{loader}+mc{family}.jar"
    with ZipFile(path) as jar:
        names = jar.namelist()
        assert len(names) == len(set(names)), 'Duplicate ZIP entries'
        variants = json.loads(jar.read('mcdr-variants.json'))
        assert set(variants) == {r['minecraft'] for r in rows}
        for row in rows:
            prefix = variants[row['minecraft']].replace('.', '/')
            variant = 'v' + row['minecraft'].replace('.', '_')
            for name in (prefix + '/SingleplayerBridge.class', 'io/github/mcdrsingleplayer/mixin/' + variant + '/RestoreWorldOpenMixin.class',
                         'io/github/mcdrsingleplayer/mixin/' + variant + '/RestoreTitleScreenMixin.class'):
                binary = jar.read(name)
                assert binary[:4] == b'\xca\xfe\xba\xbe'
                assert struct.unpack('>H', binary[6:8])[0] == row['java'] + 44
        assert not any('smoke/' in name or 'GameTest.class' in name for name in names), 'Test fixture included'
        mixins = json.loads(jar.read('mcdr-family.mixins.json'))
        assert mixins['plugin'] == 'io.github.mcdrsingleplayer.bootstrap.VariantMixins'
        assert mixins['compatibilityLevel'] == 'JAVA_' + str(rows[0]['java'])
        for language in ('en_us', 'zh_cn', 'zh_tw'):
            expected = (ROOT / 'python/singleplayer_bridge/lang' / (language + '.json')).read_bytes()
            assert jar.read('assets/mcdr-singleplayer/lang/' + language + '.json') == expected
        assert jar.read('assets/mcdr-singleplayer/icon.png') == (ROOT / 'fabric-bridge/src/main/resources/assets/mcdr-singleplayer/icon.png').read_bytes()
        with ZipFile(io.BytesIO(jar.read('mcdr-install.zip'))) as installer:
            assert installer.read('runtime/singleplayer_bridge/__init__.py') == (ROOT / 'python/singleplayer_bridge/__init__.py').read_bytes()
            assert 'adapter-plugin/singleplayer_prime_backup/__init__.py' in installer.namelist()
            assert 'chunk-adapter-plugin/singleplayer_chunk_backup/__init__.py' in installer.namelist()
        if loader == 'fabric':
            metadata = json.loads(jar.read('fabric.mod.json'))
            assert set(metadata['depends']['minecraft']) == set(variants)
            assert metadata['version'] == version
            assert metadata['environment'] == 'client'
            assert metadata['depends']['fabricloader'] == '>=' + matrix['fabricLoaderMinimum']
        else:
            metadata = tomllib.loads(jar.read('META-INF/neoforge.mods.toml').decode())
            assert metadata['mods'][0]['version'] == version
            loader_dep = next(d for d in metadata['dependencies']['mcdr_singleplayer'] if d['modId'] == 'neoforge')
            assert loader_dep['versionRange'] == ('[21.0,)' if family == '1.21.x' else '[26.1,)')
            dep = next(d for d in metadata['dependencies']['mcdr_singleplayer'] if d['modId'] == 'minecraft')
            assert dep['versionRange'] == ','.join('[' + r['minecraft'] + ']' for r in rows)
    verify_checksum(path, release_assets)
    print('Verified', path.name, len(rows), 'game adapters')


def main():
    global ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument('--loader', choices=['fabric', 'neoforge'])
    parser.add_argument('--family', choices=['1.21.x', '26.x'])
    parser.add_argument('--release-assets', type=Path)
    parser.add_argument('--timestamp', help='Verify a development artifact with UTC YYYYMMDD-HHMM version suffix')
    parser.add_argument('--source-root', type=Path)
    args = parser.parse_args()
    if args.source_root:
        ROOT = args.source_root.resolve()
    for loader in ([args.loader] if args.loader else ['fabric', 'neoforge']):
        for family in ([args.family] if args.family else ['1.21.x', '26.x']):
            verify(loader, family, args.release_assets, args.timestamp)


if __name__ == '__main__':
    main()
