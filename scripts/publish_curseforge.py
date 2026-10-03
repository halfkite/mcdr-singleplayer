"""Upload one explicit-version family artifact through the official CurseForge API."""
import argparse
import json
import os
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def upload_error_detail(error, token):
    """Expose API validation messages without logging credentials or response headers."""
    try:
        payload = json.loads(error.read(8192))
    except (ValueError, OSError):
        return ''
    if not isinstance(payload, dict):
        return ''
    details = [payload[key] for key in ('message', 'Message', 'errorMessage', 'ErrorMessage', 'error', 'errors')
               if payload.get(key)]
    if not details:
        return ''
    message = json.dumps(details, ensure_ascii=True).replace(token, '[redacted]')
    return ' '.join(message.split())[:1000]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--loader', choices=['fabric', 'neoforge'], required=True)
    parser.add_argument('--family', choices=['1.21.x', '26.x'], required=True)
    args = parser.parse_args()
    token = os.environ.get('CURSEFORGE_TOKEN')
    if not token:
        raise SystemExit('Set the repository Actions Secret CURSEFORGE_TOKEN before uploading')
    matrix = json.loads((ROOT / 'compat/versions.json').read_text(encoding='utf8'))
    release = json.loads((ROOT / 'release-metadata.json').read_text(encoding='utf8'))
    versions = [r['minecraft'] for r in matrix['versions'] if r['family'] == args.family]
    filename = f"mcdr-singleplayer-{matrix['modVersion']}+{args.loader}+mc{args.family}.jar"
    artifact = ROOT / 'dist' / filename
    metadata = {'changelog': release.get('body') or f"mcdr-singleplayer {matrix['modVersion']}",
                'changelogType': 'markdown', 'displayName': filename.removesuffix('.jar'),
                'releaseType': 'beta' if release['isPrerelease'] else 'release',
                'gameVersionNames': versions + ['Fabric' if args.loader == 'fabric' else 'NeoForge', 'Client']}
    if args.loader == 'fabric':
        metadata['relations'] = {'projects': [{'slug': 'fabric-api', 'projectID': 306612, 'type': 'requiredDependency'}]}
    boundary = 'mcdr-upload-' + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n'.encode()
            + json.dumps(metadata).encode() + b'\r\n'
            + f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: application/java-archive\r\n\r\n'.encode()
            + artifact.read_bytes() + f'\r\n--{boundary}--\r\n'.encode())
    request = Request(f"https://minecraft.curseforge.com/api/projects/{matrix['curseforgeProjectId']}/upload-file",
                      data=body, headers={'X-Api-Token': token, 'Content-Type': 'multipart/form-data; boundary=' + boundary})
    try:
        with urlopen(request, timeout=180) as response:
            result = json.load(response)
    except HTTPError as error:
        detail = upload_error_detail(error, token)
        suffix = ': ' + detail if detail else '; inspect project upload permissions'
        raise SystemExit(f'CurseForge upload rejected (HTTP {error.code})' + suffix) from None
    print('CurseForge uploaded file', result.get('id'), filename)


if __name__ == '__main__':
    main()
