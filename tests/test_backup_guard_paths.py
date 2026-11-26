"""路径校验必须真正把路径限制在给定目录内。

``checked_path`` 是所有备份文件操作的唯一入口；它曾经用 ``Path.absolute()`` 取 root，
root 自带 ``..`` 时 target 和 root 会一起带着 ``..`` 通过比较，实际路径却已经越界。
这里同时锁住 Windows 上不属于普通文件的两种名字：备用数据流与设备名。
"""
import os
from pathlib import Path

import pytest

from singleplayer_bridge.backup_guard import checked_path

WINDOWS = os.name == 'nt'


def workspace(tmp_path):
    (tmp_path / 'inside').mkdir()
    (tmp_path / 'outside').mkdir()
    return tmp_path


def test_a_relative_path_stays_inside_the_directory(tmp_path):
    root = workspace(tmp_path)
    target = checked_path(root / 'inside', 'nested/file.txt')
    assert target.is_relative_to((root / 'inside').resolve())


def test_a_parent_segment_is_refused(tmp_path):
    root = workspace(tmp_path)
    for relative in ('../outside/x', 'a/../../outside/x', '..'):
        with pytest.raises(RuntimeError):
            checked_path(root / 'inside', relative)


def test_an_absolute_path_is_refused(tmp_path):
    root = workspace(tmp_path)
    with pytest.raises(RuntimeError):
        checked_path(root / 'inside', str(root / 'outside' / 'x'))


def test_a_root_containing_dotdot_cannot_be_used_to_escape(tmp_path):
    """root 自带 ``..`` 时，边界必须按解析后的真实目录算。

    旧实现两侧都保留 ``..``，比较一起通过；现在 root 先 resolve，
    所以走 ``inside/../outside`` 拿到的 root 就是 ``outside`` 本身。
    """
    root = workspace(tmp_path)
    messy = root / 'inside' / '..' / 'outside'
    target = checked_path(messy, 'file.txt')
    # 落在解析后的 outside 里，而不是通过 `..` 逃到别处。
    assert target == (root / 'outside').resolve() / 'file.txt'
    assert target.is_relative_to((root / 'outside').resolve())
    # 上跳一级仍然会被拒。
    with pytest.raises(RuntimeError):
        checked_path(messy, '../x')


def test_a_symlinked_leaf_is_refused(tmp_path):
    root = workspace(tmp_path)
    link = root / 'inside' / 'link'
    try:
        link.symlink_to(root / 'outside', target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('symlinks are not available here')
    with pytest.raises(RuntimeError):
        checked_path(root / 'inside', 'link/file.txt')


@pytest.mark.skipif(not WINDOWS, reason='Windows-only path forms')
def test_a_windows_alternate_data_stream_is_refused(tmp_path):
    """``name:stream`` 给同一文件挂额外数据，磁盘不允许文件名字符里有 ``:``。"""
    root = workspace(tmp_path)
    with pytest.raises(RuntimeError):
        checked_path(root / 'inside', 'backup.zip:hidden')


@pytest.mark.skipif(not WINDOWS, reason='Windows-only path forms')
def test_a_windows_device_name_is_refused(tmp_path):
    """设备名在任何目录下都指向设备，不是普通文件。"""
    root = workspace(tmp_path)
    for relative in ('NUL', 'nul', 'CON', 'aux.txt', 'com1', 'LPT9.log'):
        with pytest.raises(RuntimeError):
            checked_path(root / 'inside', relative)


def test_a_missing_directory_is_still_usable(tmp_path):
    """root 还不存在时必须能算（备份库目录是逐步创建的）。"""
    root = workspace(tmp_path)
    target = checked_path(root / 'not-yet', 'x.txt')
    assert target == (root / 'not-yet' / 'x.txt')
