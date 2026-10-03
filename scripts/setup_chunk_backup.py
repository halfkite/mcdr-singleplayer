"""Bind an existing 26.3 world and install the optional Chunk Backup adapter."""
import argparse
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'runtime'))
from singleplayer_bridge.chunk_backup_config import prepare
from singleplayer_bridge.profiles import ensure_profile


def configure(root, common, world):
    root, common, world = Path(root), Path(common), Path(world)
    profile = ensure_profile(common, world)
    prepare(profile, world)
    target = common / 'plugins/singleplayer_chunk_backup.mcdr'
    source = root / 'chunk-backup-adapter'
    if source.is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in source.rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                    archive.write(path, path.relative_to(source).as_posix())
    else:
        artifacts = list((root / 'adapters').glob('singleplayer_chunk_backup-*.mcdr'))
        if len(artifacts) != 1:
            raise ValueError('Extract the complete release bundle before configuring Chunk Backup')
        shutil.copy2(artifacts[0], target)
    return profile


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcdr-dir', type=Path, required=True)
    parser.add_argument('--world-dir', type=Path, required=True)
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    root = directory if (directory / 'adapters').is_dir() else directory.parent
    configure(root, args.mcdr_dir.resolve(), args.world_dir.resolve())
