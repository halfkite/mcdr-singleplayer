import errno
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from singleplayer_prime_backup.guards import check_backup, check_binding, check_unlocked, retry_temp_cleanup


@pytest.fixture
def world(tmp_path):
    save = tmp_path / 'saves' / '测试世界'
    save.mkdir(parents=True)
    (save / 'level.dat').write_bytes(b'test')
    (save / 'session.lock').write_bytes(b'\xe2\x98\x83')
    return save


def test_binding_requires_exact_world_target_and_external_backup_storage(world):
    config = SimpleNamespace(source_path=world.parent, storage_path=world.parents[1] / 'backups',
                             backup=SimpleNamespace(targets=[world.name]))
    assert check_binding(str(world), config) == world
    config.backup.targets = ['another-world']
    with pytest.raises(RuntimeError, match='differ'):
        check_binding(world, config)
    config.backup.targets = [world.name]
    config.storage_path = world / 'backups'
    with pytest.raises(RuntimeError, match='outside'):
        check_binding(world, config)


@pytest.mark.parametrize('path,mode', [('other/level.dat', stat.S_IFREG),
    ('测试世界/../other/level.dat', stat.S_IFREG), ('测试世界/link', stat.S_IFLNK)])
def test_restore_rejects_files_outside_binding_and_symlinks(world, path, mode):
    backup = SimpleNamespace(targets=[world.name], files=[SimpleNamespace(path=path, mode=mode)])
    with pytest.raises(RuntimeError):
        check_backup(world, backup)


def test_restore_rejects_another_world_backup(world):
    with pytest.raises(RuntimeError, match='different world'):
        check_backup(world, SimpleNamespace(targets=['other'], files=[]))
    check_backup(world, SimpleNamespace(targets=[world.name], files=[SimpleNamespace(path=f'{world.name}/level.dat', mode=stat.S_IFREG)]))


def test_real_separate_process_file_lock_blocks_detached_world_restore(world):
    # OS locks are per-process on POSIX, so a real child process is required.
    child = '''import os,sys
f=open(sys.argv[1],'r+b',buffering=0)
if os.name=='nt':
 import msvcrt; msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
else:
 import fcntl; fcntl.lockf(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
print('locked',flush=True)
sys.stdin.readline()
'''
    process = subprocess.Popen([sys.executable, '-c', child, str(world / 'session.lock')],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert process.stdout.readline().strip() == 'locked'
        with pytest.raises(RuntimeError, match='still held'):
            check_unlocked(world)
    finally:
        process.communicate('\n', timeout=5)
    check_unlocked(world)


def test_partial_world_can_only_be_used_as_a_restore_target(world):
    config = SimpleNamespace(source_path=world.parent, storage_path=world.parents[1] / 'backups',
                             backup=SimpleNamespace(targets=[world.name]))
    (world / 'level.dat').unlink()
    with pytest.raises(RuntimeError, match='existing Minecraft world'):
        check_binding(world, config)
    assert check_binding(world, config, allow_incomplete=True) == world


def test_restore_rejects_a_partial_backup_without_level_dat(world):
    backup = SimpleNamespace(targets=[world.name], files=[SimpleNamespace(path=f'{world.name}/syncmatica/config.json', mode=stat.S_IFREG)])
    with pytest.raises(RuntimeError, match='level.dat'):
        check_backup(world, backup)


def test_temp_cleanup_retries_directory_not_empty(tmp_path):
    temp = tmp_path / 'export_temp'
    graveyard = temp / 'trash_bin/world/config/carpet-org-addition/player_data/graveyard'
    graveyard.mkdir(parents=True)
    (graveyard / 'old.json').write_text('old')
    attempts = []

    def erase():
        attempts.append(1)
        if len(attempts) == 1:
            (graveyard / 'late.json').write_text('late')
            raise OSError(errno.ENOTEMPTY, 'Directory not empty', str(graveyard))
        shutil.rmtree(temp)

    retry_temp_cleanup(erase, timeout=1)
    assert len(attempts) == 2 and not temp.exists()


def test_temp_cleanup_preserves_persistent_or_unrelated_errors():
    for error, expected_calls in [(OSError(errno.ENOTEMPTY, 'Directory not empty'), 1),
                                  (OSError(errno.EIO, 'I/O error'), 1)]:
        calls = []
        def erase():
            calls.append(1)
            raise error
        with pytest.raises(OSError) as raised:
            retry_temp_cleanup(erase, timeout=0)
        assert raised.value is error and len(calls) == expected_calls
