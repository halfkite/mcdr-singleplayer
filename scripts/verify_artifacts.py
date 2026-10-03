"""Check distribution metadata and every explicitly selected variant before publishing."""
import argparse
import hashlib
import io
import json
import struct
import tomllib
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def verify(loader, family):
    matrix = json.loads((ROOT / 'compat/versions.json').read_text(encoding='utf8'))
    rows = [r for r in matrix['versions'] if r['family'] == family]
    path = ROOT / 'dist' / f"mcdr-singleplayer-{matrix['modVersion']}+{loader}+mc{family}.jar"
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
            assert metadata['version'] == matrix['modVersion']
            assert metadata['environment'] == 'client'
            assert metadata['depends']['fabricloader'] == '>=' + matrix['fabricLoaderMinimum']
        else:
            metadata = tomllib.loads(jar.read('META-INF/neoforge.mods.toml').decode())
            assert metadata['mods'][0]['version'] == matrix['modVersion']
            loader_dep = next(d for d in metadata['dependencies']['mcdr_singleplayer'] if d['modId'] == 'neoforge')
            assert loader_dep['versionRange'] == ('[21.0,)' if family == '1.21.x' else '[26.1,)')
            dep = next(d for d in metadata['dependencies']['mcdr_singleplayer'] if d['modId'] == 'minecraft')
            assert dep['versionRange'] == ','.join('[' + r['minecraft'] + ']' for r in rows)
    expected_hash = path.with_suffix('.sha256').read_text().split()[0]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
    print('Verified', path.name, len(rows), 'game adapters')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--loader', choices=['fabric', 'neoforge'])
    parser.add_argument('--family', choices=['1.21.x', '26.x'])
    args = parser.parse_args()
    for loader in ([args.loader] if args.loader else ['fabric', 'neoforge']):
        for family in ([args.family] if args.family else ['1.21.x', '26.x']):
            verify(loader, family)


if __name__ == '__main__':
    main()
