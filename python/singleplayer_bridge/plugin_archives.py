"""Read installed plugin metadata without importing the MCDR runtime."""
import json
import zipfile
from pathlib import Path

from .profiles import read_json


def archives(common, plugin_id):
    result = []
    for path in (Path(common) / 'plugins').iterdir():
        if path.name.endswith('.disabled'):
            continue
        if path.is_dir() and (path / 'mcdreforged.plugin.json').is_file():
            try:
                metadata = read_json(path / 'mcdreforged.plugin.json')
            except ValueError:
                continue
        elif path.is_file() and zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                try:
                    metadata = json.loads(archive.read('mcdreforged.plugin.json'))
                except (KeyError, ValueError):
                    continue
        else:
            continue
        if metadata.get('id') == plugin_id:
            result.append((path, metadata.get('version')))
    return result
