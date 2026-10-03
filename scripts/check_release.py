"""Validate the published release against the checked-out compatibility manifest."""
import json
from pathlib import Path


def main():
    matrix = json.loads(Path('compat/versions.json').read_text(encoding='utf8'))
    release = json.loads(Path('release-metadata.json').read_text(encoding='utf8'))
    if release['isDraft'] or release['tagName'].removeprefix('v') != matrix['modVersion']:
        raise SystemExit('Publish requires a published Release tag matching compat/versions.json')
    print('Publishing', release['tagName'], 'beta' if release['isPrerelease'] else 'release')


if __name__ == '__main__':
    main()
