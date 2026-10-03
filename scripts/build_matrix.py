"""Compile explicit game adapters and merge them into one installable JAR per family/loader."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
MATRIX = json.loads((ROOT / 'compat/versions.json').read_text(encoding='utf8'))
VERSION = MATRIX['modVersion']
ARCHIVER = Path(os.environ.get('MCDR_BUILD_ARCHIVER', Path.home() / '.codex/skills/build-game-mods/scripts/archive_mod_build.py'))
if not ARCHIVER.is_file():
    ARCHIVER = ROOT / 'scripts/archive_build.py'


def package(game):
    return 'io.github.mcdrsingleplayer.v' + game.replace('.', '_')


def archive(artifact, label, command):
    subprocess.run([sys.executable, str(ARCHIVER), '--artifact', str(artifact), '--output-root', str(ROOT / 'mod-builds'),
                    '--mod-name', 'mcdr-singleplayer', '--game-version', label, '--build-command', command], check=True)


def compile_variant(loader, row):
    from generate_compat import generate
    project = generate(loader, row)
    gradle = ROOT / 'fabric-bridge' / ('gradlew.bat' if os.name == 'nt' else 'gradlew')
    command = [str(gradle), '-p', str(project), 'build', '--console=plain']
    subprocess.run(command, cwd=ROOT, check=True)
    jars = [p for p in (project / 'build/libs').glob('*.jar') if not p.name.endswith(('-sources.jar', '-dev.jar'))]
    assert len(jars) == 1, jars
    artifact = jars[0]
    archive(artifact, row['minecraft'] + ' ' + loader, ' '.join(command))
    return artifact


def merge(loader, family, rows):
    output = ROOT / 'dist' / f'mcdr-singleplayer-{VERSION}+{loader}+mc{family}.jar'
    output.parent.mkdir(parents=True, exist_ok=True)
    contents = {}
    for row in rows:
        project = ROOT / 'build/matrix' / loader / row['minecraft']
        jars = [p for p in (project / 'build/libs').glob('*.jar') if not p.name.endswith(('-sources.jar', '-dev.jar'))]
        if len(jars) != 1:
            raise RuntimeError('Missing compiled adapter: ' + str(project))
        with ZipFile(jars[0]) as jar:
            for name in jar.namelist():
                if name.endswith('/') or name in ('fabric.mod.json', 'META-INF/neoforge.mods.toml', 'mcdr-variants.json', 'META-INF/MANIFEST.MF', 'mcdr-family.mixins.json'):
                    continue
                if name.startswith('META-INF/') and name.endswith(('.SF', '.RSA', '.DSA')):
                    continue
                data = jar.read(name)
                if name in contents and contents[name] != data:
                    raise RuntimeError('Conflicting shared resource: ' + name)
                contents[name] = data
    contents['mcdr-variants.json'] = json.dumps({row['minecraft']: package(row['minecraft']) for row in rows}).encode()
    contents['mcdr-family.mixins.json'] = json.dumps({'required': True, 'package': 'io.github.mcdrsingleplayer.mixin',
        'plugin': 'io.github.mcdrsingleplayer.bootstrap.VariantMixins', 'compatibilityLevel': 'JAVA_' + str(rows[0]['java']),
        'client': [], 'injectors': {'defaultRequire': 1}}).encode()
    manifest = 'Manifest-Version: 1.0\r\n'
    if loader == 'fabric':
        manifest += 'Fabric-Mapping-Namespace: ' + ('official' if rows[0]['java'] == 25 else 'intermediary') + '\r\n'
    contents['META-INF/MANIFEST.MF'] = (manifest + '\r\n').encode()
    if loader == 'fabric':
        from generate_compat import fabric_metadata
        metadata = fabric_metadata(rows[0])
        metadata['depends']['minecraft'] = [row['minecraft'] for row in rows]
        metadata['depends']['fabric-api'] = '*'
        contents['fabric.mod.json'] = json.dumps(metadata, indent=2).encode()
    else:
        from generate_compat import neo_metadata
        contents['META-INF/neoforge.mods.toml'] = neo_metadata(rows[0], family).encode()
    with ZipFile(output, 'w', ZIP_DEFLATED) as jar:
        for name, data in sorted(contents.items()):
            jar.writestr(name, data)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.sha256').write_text(checksum + '  ' + output.name + '\n')
    archive(output, family + ' ' + loader, f'python scripts/build_matrix.py --loader {loader} --family {family}')
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--loader', choices=['fabric', 'neoforge'], required=True)
    parser.add_argument('--family', choices=['1.21.x', '26.x'])
    parser.add_argument('--game')
    parser.add_argument('--merge-only', action='store_true')
    args = parser.parse_args()
    if not args.family and not args.game:
        parser.error('Specify --family or --game')
    rows = [r for r in MATRIX['versions'] if (not args.family or r['family'] == args.family) and (not args.game or r['minecraft'] == args.game)]
    if not rows:
        parser.error('Unknown game target')
    if not args.merge_only:
        for row in rows:
            compile_variant(args.loader, row)
    if args.family and not args.game:
        print(merge(args.loader, args.family, rows))


if __name__ == '__main__':
    main()
