"""Build a self-contained Minecraft runtime inside the workspace.

The tests must not read or write the player's launcher directory, so every file the client needs -
version manifests, client jars, libraries, and assets - is downloaded here instead. Files already
present with the expected size are skipped, which makes the script safe to re-run.
"""
from __future__ import annotations

import json
import sys
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(r'D:\ai\MCDR\.client-tests')
HOME = ROOT / 'shared' / 'mc-home'
VERSIONS = HOME / 'versions'
LIBRARIES = HOME / 'libraries'
ASSETS = HOME / 'assets'
MANIFEST_URL = 'https://launchermeta.mojang.com/mc/game/version_manifest_v2.json'
PROXY = 'http://127.0.0.1:7897'
WORKERS = 64

_lock = threading.Lock()
_stats = {'files': 0, 'bytes': 0, 'skipped': 0, 'failed': 0}
_local = threading.local()


def session():
    """One keep-alive session per worker.

    The asset store holds tens of thousands of tiny objects, so a fresh TLS handshake per file was
    the bottleneck; connections are reused across requests instead.
    """
    current = getattr(_local, 'session', None)
    if current is None:
        import requests
        current = requests.Session()
        current.trust_env = False
        current.proxies = {'http': PROXY, 'https': PROXY}
        current.headers['User-Agent'] = 'mcdr-singleplayer-test-harness'
        adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=8)
        current.mount('https://', adapter)
        current.mount('http://', adapter)
        _local.session = current
    return current


def fetch(url: str, attempts: int = 4) -> bytes:
    last: Exception | None = None
    for _ in range(attempts):
        try:
            response = session().get(url, timeout=180)
            response.raise_for_status()
            return response.content
        except Exception as error:  # noqa: BLE001 - retry a flaky transfer
            last = error
    raise RuntimeError(f'download failed: {url}: {last}')


def download(url: str, target: Path, size: int | None = None) -> None:
    """Write one file, skipping it when an identical size is already on disk."""
    if target.is_file() and (size is None or target.stat().st_size == size):
        with _lock:
            _stats['skipped'] += 1
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    data = fetch(url)
    temporary = target.with_suffix(target.suffix + '.part')
    temporary.write_bytes(data)
    temporary.replace(target)
    with _lock:
        _stats['files'] += 1
        _stats['bytes'] += len(data)


def allowed(entry: dict) -> bool:
    """Evaluate the library's rule list for a Windows client."""
    rules = entry.get('rules')
    if not rules:
        return True
    result = False
    for rule in rules:
        os_name = (rule.get('os') or {}).get('name')
        matches = os_name in (None, 'windows')
        if matches:
            result = rule.get('action') == 'allow'
    return result


def plan_version(version_id: str, manifest: dict) -> tuple[dict, list[tuple[str, Path, int | None]]]:
    entry = next(v for v in manifest['versions'] if v['id'] == version_id)
    details = json.loads(fetch(entry['url']).decode('utf8'))
    jobs: list[tuple[str, Path, int | None]] = []

    client = details.get('downloads', {}).get('client')
    if client:
        jobs.append((client['url'], VERSIONS / version_id / f'{version_id}.jar', client.get('size')))

    for library in details.get('libraries', []):
        if not allowed(library):
            continue
        artifact = (library.get('downloads') or {}).get('artifact')
        if artifact and artifact.get('url'):
            jobs.append((artifact['url'], LIBRARIES / artifact['path'], artifact.get('size')))

    index = details.get('assetIndex')
    if index:
        jobs.append((index['url'], ASSETS / 'indexes' / f'{index["id"]}.json', index.get('size')))
    return details, jobs


def main() -> int:
    matrix = json.loads((Path(r'D:\ai\MCDR') / 'compat' / 'versions.json').read_text(encoding='utf8'))
    targets = sys.argv[1:] or [row['minecraft'] for row in matrix['versions']]
    for folder in (VERSIONS, LIBRARIES, ASSETS):
        folder.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(fetch(MANIFEST_URL).decode('utf8'))
    (HOME / 'version_manifest_v2.json').write_text(json.dumps(manifest), encoding='utf8')

    index_ids: set[str] = set()
    jobs: list[tuple[str, Path, int | None]] = []
    for version_id in targets:
        details, version_jobs = plan_version(version_id, manifest)
        (VERSIONS / version_id).mkdir(parents=True, exist_ok=True)
        (VERSIONS / version_id / f'{version_id}.json').write_text(
            json.dumps(details, indent=2), encoding='utf8')
        jobs.extend(version_jobs)
        if details.get('assetIndex'):
            index_ids.add(details['assetIndex']['id'])
        print(f'  {version_id}: {len(version_jobs)} 个文件', flush=True)

    # Asset indexes are content addressed, so the objects they list can be fetched once for all
    # versions that share them.
    object_jobs: list[tuple[str, Path, int | None]] = []
    for index_id in sorted(index_ids):
        path = ASSETS / 'indexes' / f'{index_id}.json'
        if not path.is_file():
            continue
        index = json.loads(path.read_text(encoding='utf8'))
        for name, item in index['objects'].items():
            # Newer indexes are keyed by resource name and carry the digest in the entry.
            digest = item.get('hash') or name
            if len(digest) < 3:
                continue
            object_jobs.append((
                f'https://resources.download.minecraft.net/{digest[:2]}/{digest}',
                ASSETS / 'objects' / digest[:2] / digest,
                item.get('size'),
            ))
    print(f'  资源索引 {sorted(index_ids)}，共 {len(object_jobs)} 个对象', flush=True)

    def run(job: tuple[str, Path, int | None]) -> None:
        url, target, size = job
        try:
            download(url, target, size)
        except Exception as error:  # noqa: BLE001 - one bad file must not stop the sweep
            with _lock:
                _stats['failed'] += 1
            print(f'    FAILED {target.name}: {error}', flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        list(pool.map(run, jobs))
        print(f'  基础文件完成：{_stats["files"]} 下载 / {_stats["skipped"]} 跳过 / '
              f'{_stats["failed"]} 失败', flush=True)
        list(pool.map(run, object_jobs))

    print(f'完成：{_stats["files"]} 下载 / {_stats["skipped"]} 跳过 / '
          f'{_stats["failed"]} 失败，共 {_stats["bytes"] / 1024 / 1024:.0f} MB', flush=True)
    print(f'位置：{HOME}', flush=True)
    return 0 if _stats['failed'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
