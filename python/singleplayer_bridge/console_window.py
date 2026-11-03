"""Console window front-end for the running MCDR.

The controller owns MCDR's real stdin, so this window cannot attach to it. Instead it mirrors the
console the controller records and forwards every line the player types, which keeps the window
interactive without giving a second process control over the server.

Usage:
    python console_window.py --console <console.log> --commands <console-command.txt>
                             [--watch <latest.log>] [--title <text>]
"""
from __future__ import annotations

import argparse
import codecs
import os
import sys
import threading
import time
from pathlib import Path

POLL_SECONDS = 0.2
INITIAL_TAIL_BYTES = 64 * 1024


class Tail:
    """Print a file's first tail, then everything appended after it."""

    def __init__(self, path: Path, prefix: str = ''):
        self.path = Path(path)
        self.prefix = prefix
        self.offset = 0
        self.pending = b''
        self._open()

    def _open(self):
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        start = max(0, size - INITIAL_TAIL_BYTES)
        try:
            with self.path.open('rb') as handle:
                handle.seek(start)
                data = handle.read()
        except OSError:
            return
        self.offset = size
        if start > 0:
            # Drop the half line at the cut so the first printed line is complete.
            cut = data.find(b'\n')
            data = data[cut + 1:] if cut >= 0 else b''
        self._emit(data)

    def poll(self):
        try:
            size = self.path.stat().st_size
        except OSError:
            return
        if size < self.offset:
            # The file was rotated or truncated.
            self.offset = 0
            self._open()
            return
        if size == self.offset:
            return
        try:
            with self.path.open('rb') as handle:
                handle.seek(self.offset)
                data = handle.read()
        except OSError:
            return
        self.offset += len(data)
        self._emit(data)

    def _emit(self, data: bytes):
        if not data:
            return
        self.pending += data
        *lines, self.pending = self.pending.split(b'\n')
        for raw in lines:
            text = raw.decode('utf8', 'replace').rstrip('\r')
            if text:
                print(f'{self.prefix}{text}', flush=True)


def forward_input(commands: Path):
    """Every typed line becomes a command for the controller, which writes it to MCDR."""
    for line in sys.stdin:
        command = line.rstrip('\r\n')
        if not command.strip():
            continue
        try:
            commands.parent.mkdir(parents=True, exist_ok=True)
            with commands.open('a', encoding='utf8') as handle:
                handle.write(command + '\n')
        except OSError as error:
            print(f'  无法发送命令: {error}', flush=True)
            continue
        print(f'> {command}', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description='Interactive MCDR console window')
    parser.add_argument('--console', required=True, type=Path)
    parser.add_argument('--commands', required=True, type=Path)
    parser.add_argument('--watch', action='append', default=[], type=Path)
    parser.add_argument('--title', default='')
    args = parser.parse_args()

    # A Windows console defaults to the legacy code page, which mangles Chinese output.
    if os.name == 'nt':
        try:
            os.system('chcp 65001 > nul')
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
        except (OSError, AttributeError):
            pass

    if args.title:
        print(f'== {args.title} ==', flush=True)
    print('输入 MCDR 命令后回车即可执行（例如 !!MCDR）；窗口只显示输出时不影响游戏', flush=True)
    print('', flush=True)

    tailers = [Tail(args.console)]
    tailers += [Tail(path, prefix=f'[game] ') for path in args.watch]

    threading.Thread(target=forward_input, args=(args.commands,), daemon=True).start()
    while True:
        for tailer in tailers:
            tailer.poll()
        time.sleep(POLL_SECONDS)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
