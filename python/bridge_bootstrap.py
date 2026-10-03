import sys
from pathlib import Path

runtime = Path(__file__).resolve().parent / 'runtime'
if runtime.is_dir():
    sys.path.insert(0, str(runtime))
from singleplayer_bridge.bootstrap import main

if __name__ == '__main__':
    raise SystemExit(main())
