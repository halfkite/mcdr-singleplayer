"""Archive successful CI builds when the local Codex skill is unavailable."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    for key in ('artifact', 'output-root', 'mod-name', 'game-version', 'build-command'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    source = Path(args.artifact).resolve(strict=True)
    root = Path(args.output_root)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    directory = root / stamp
    index = 1
    while directory.exists():
        index += 1
        directory = root / f'{stamp}-{index}'
    directory.mkdir(parents=True)
    shutil.copy2(source, directory / source.name)
    manifest = {'mod': args.mod_name, 'gameVersion': args.game_version,
                'buildCommand': args.build_command, 'createdAt': datetime.now(timezone.utc).isoformat(),
                'artifacts': [{'filename': source.name, 'size': source.stat().st_size,
                               'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}]}
    (directory / 'build-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    print(directory)


if __name__ == '__main__':
    main()
