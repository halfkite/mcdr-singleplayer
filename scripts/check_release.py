"""Validate the published release against the checked-out compatibility manifest."""
import json
import re
from pathlib import Path

# The guards read the checkout itself, never the caller's working directory.
ROOT = Path(__file__).resolve().parents[1]


def declared_bridge_version(root=ROOT):
    """The materials folder and the release bundle must agree with the declared bridge version."""
    root = Path(root)
    gradle = (root / 'fabric-bridge/gradle.properties').read_text(encoding='utf8')
    version = re.search(r'^version=(.+)$', gradle, re.MULTILINE).group(1).strip()
    bridge = (root / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer/SingleplayerBridge.java').read_text(encoding='utf8')
    fallback = re.search(r'BUNDLED_VERSION = "([^"]+)"', bridge).group(1)
    if fallback != version:
        raise SystemExit(f'SingleplayerBridge.java BUNDLED_VERSION {fallback} does not match gradle.properties {version}')
    for name in ('python', 'prime-backup-adapter', 'chunk-backup-adapter'):
        metadata = json.loads((root / name / 'mcdreforged.plugin.json').read_text(encoding='utf8'))
        if metadata['version'] != version:
            raise SystemExit(f'{name} declares {metadata["version"]}, expected {version}')
    return version


def installed_mcdr_version(root=ROOT):
    """The probe, the installer and the pinned requirements must all target one MCDR release."""
    root = Path(root)
    bootstrap = (root / 'python/singleplayer_bridge/bootstrap.py').read_text(encoding='utf8')
    python = re.search(r"^MCDR_VERSION = '([^']+)'", bootstrap, re.MULTILINE).group(1)
    runtime = (root / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer/AutoRuntime.java').read_text(encoding='utf8')
    probe = re.search(r'EXPECTED_MCDR = "([^"]+)"', runtime).group(1)
    pinned = re.search(r'^mcdreforged==(.+)$', (root / 'requirements-prime-backup.txt').read_text(encoding='utf8'), re.MULTILINE).group(1).strip()
    if len({python, probe, pinned}) != 1:
        raise SystemExit(f'MCDR versions disagree: bootstrap={python} bridge={probe} requirements={pinned}')
    return python


def main():
    matrix = json.loads(Path('compat/versions.json').read_text(encoding='utf8'))
    release = json.loads(Path('release-metadata.json').read_text(encoding='utf8'))
    if release['isDraft'] or release['tagName'].removeprefix('v') != matrix['modVersion']:
        raise SystemExit('Publish requires a published Release tag matching compat/versions.json')
    version = declared_bridge_version()
    if matrix['modVersion'] != version:
        raise SystemExit(f'compat/versions.json declares {matrix["modVersion"]}, expected {version}')
    print('Publishing', release['tagName'], 'beta' if release['isPrerelease'] else 'release',
          'with MCDR', installed_mcdr_version())

if __name__ == '__main__':
    main()
