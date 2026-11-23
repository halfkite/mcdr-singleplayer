"""备份查看界面的版面必须随窗口尺寸保持自洽。

界面重构的方向是「左侧列表 + 右侧详情」的铺满式布局，行距从面板两端向中间推算。
窗口很矮时如果算错，文字就会压在按钮上或列表区被压成负数——这正是之前出现过
的问题。这里按 BackupViewerScreen 的公式复算各种 GUI 尺寸，锁住不变量。
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCREEN = ROOT / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer/BackupViewerScreen.java'


def constants():
    """从源码里读出行距常量，避免测试和实现各写一份。"""
    text = SCREEN.read_text(encoding='utf8')
    def value(name):
        match = re.search(rf'{name}\s*=\s*(\d+)', text)
        assert match, name
        return int(match.group(1))
    return dict(row_step=value('ROW_STEP'), max_rows=value('MAX_ROWS'),
                panel_max=value('PANEL_MAX_WIDTH'))


def layout(width, height):
    c = constants()
    panel_width = max(160, min(c['panel_max'], width - 16))
    panel_height = max(190, min(450, height - 14))
    panel_y = max(4, (height - panel_height) // 2)
    panel_bottom = panel_y + panel_height
    content_width = panel_width - 24
    # 分栏条件与界面一致：面板够宽够高才左右分栏。
    split = panel_width >= 600 and panel_height >= 315
    compact = panel_height < 315
    tiny = panel_height < 240
    tabs = panel_y + (27 if tiny else 37 if compact else 47)
    section = tabs + (23 if tiny else 27)
    listing = section + (12 if tiny else 16)
    footer = panel_bottom - (27 if tiny else 30)
    tools = footer - (24 if tiny else 29)
    status = tools - (12 if tiny else 16)
    pager = status - (24 if tiny else 27)
    reserved = 0 if (split or tiny) else 27
    rows = max(1, min(c['max_rows'], (pager - listing - reserved - 4) // c['row_step']))
    list_width = (content_width * 55 // 100) - 6 if split else content_width
    return dict(rows=rows, listing=listing, pager=pager, status=status, tools=tools,
                footer=footer, panel_bottom=panel_bottom, split=split, tiny=tiny,
                content_width=content_width, list_width=list_width)


SIZES = [(320, 240), (427, 240), (500, 300), (600, 260), (640, 360), (854, 480),
         (854, 498), (900, 320), (1000, 300), (1200, 260), (1280, 720), (1600, 900),
         (1920, 1080), (2560, 1440), (3840, 2160)]


@pytest.mark.parametrize('width,height', SIZES, ids=lambda v: str(v))
def test_layout_rows_are_consistent(width, height):
    v = layout(width, height)
    assert v['rows'] >= 1
    # 列表区必须有实际高度，否则列表行会被压到分页按钮上。
    assert v['pager'] > v['listing']


@pytest.mark.parametrize('width,height', SIZES, ids=lambda v: str(v))
def test_layout_rows_never_overlap(width, height):
    v = layout(width, height)
    order = ['listing', 'pager', 'status', 'tools', 'footer']
    for upper, lower in zip(order, order[1:]):
        # 自下而上的各行必须严格递增。
        assert v[upper] < v[lower], f'{upper} >= {lower}'


@pytest.mark.parametrize('width,height', SIZES, ids=lambda v: str(v))
def test_footer_stays_inside_the_panel(width, height):
    v = layout(width, height)
    assert v['footer'] + 20 <= v['panel_bottom']


def test_split_columns_both_have_room():
    for width, height in SIZES:
        v = layout(width, height)
        if not v['split']:
            continue
        detail = v['content_width'] - v['list_width'] - 12
        # 详情栏要有地方放「字段名 + 值」两列。
        assert detail >= 80, (width, height, detail)


def test_the_screen_keeps_a_single_source_of_coordinates():
    """渲染与布局必须共用同一组坐标方法，不能再出现写死的行号偏移。"""
    text = SCREEN.read_text(encoding='utf8')
    for method in ('panelWidth()', 'panelHeight()', 'panelX()', 'panelY()',
                   'tabsY()', 'sectionY()', 'listY()', 'pagerY()', 'statusY()',
                   'toolsY()', 'footerY()', 'rows()'):
        assert method in text, method
    # 旧实现里写死的偏移，正是文字压按钮的来源。
    assert 'top + 144' not in text
    assert 'top + 200' not in text
    # 三个标签页都要有：PB、CB、原版。
    assert '"prime", "chunk", "vanilla"' in text or "'prime', 'chunk', 'vanilla'" in text
    # 建备份前的备注与选区、处理中状态都要保留。
    assert 'BackupCommentScreen.open' in text
    assert 'ChunkBackupScreen.open' in text
