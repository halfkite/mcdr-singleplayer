"""Fetch the verified upstream fixtures needed by the existing integration tests."""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
from singleplayer_bridge.bootstrap import download_checked, PRIME_URL, PRIME_HASH


def main():
    plugins = [
        ('PrimeBackup-v1.13.1.pyz', PRIME_URL, PRIME_HASH),
        ('Candy_Tools-v1.0.2.mcdr', 'https://github.com/Passion-Never-Dissipate/candy_tools/releases/download/1.0.2/Candy_Tools-v1.0.2.mcdr', 'd1cd50a22b6bee05cbd9b0aed89afb13e8ff6d44d058dcb9d1276c2282eab048'),
        ('Chunk_BackUp-v2.0.3.mcdr', 'https://github.com/Passion-Never-Dissipate/Chunk_BackUp/releases/download/v2.0.3/Chunk_BackUp-v2.0.3.mcdr', 'b6f66c9dd621104176d6b2e656353f932d9088a7621c84ab67f204cd8ee0374d'),
    ]
    destination = ROOT / '.reference'
    destination.mkdir(exist_ok=True)
    for name, url, digest in plugins:
        target = destination / name
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            download_checked([url], target, digest)
        print('Verified test dependency', name)


if __name__ == '__main__':
    main()
