"""备份查看器的滚轮与键盘操作。

界面本身要靠游戏才能跑起来，但翻页与选中的边界逻辑是纯计算，可以直接验证：
滚轮必须只在列表区域内生效，翻页不能越界，上下键跨页时要跟着换页。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREEN = ROOT / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer/BackupViewerScreen.java'


def source():
    return SCREEN.read_text(encoding='utf8')


def test_the_viewer_handles_scrolling_and_keys():
    text = source()
    assert 'boolean mouseScrolled(' in text
    assert 'boolean keyPressed(KeyEvent event)' in text


def test_key_handling_uses_the_26x_event_object():
    """26.1 起原版把按键改成 KeyEvent；用旧的三参数签名会编译失败。"""
    text = source()
    assert 'import net.minecraft.client.input.KeyEvent;' in text
    assert 'event.key()' in text
    assert 'keyPressed(int keyCode, int scanCode, int modifiers)' not in text


def test_scrolling_only_acts_inside_the_list():
    """标签页和底部按钮上滚动不应该翻页。"""
    text = source()
    assert 'listRegionContains(' in text
    assert 'if (!listRegionContains(mouseX, mouseY) || working)' in text


def test_paging_clamps_at_both_ends():
    """越界翻页必须什么都不做，不能把页码推成负数或超出末页。"""
    text = source()
    body = text.split('private void movePage(int delta) {', 1)[1].split('\n    }', 1)[0]
    assert 'if (target < 0) return;' in body
    assert 'target * rows() >= entries().size()' in body


def test_selection_moves_within_the_list_and_follows_the_page():
    text = source()
    body = text.split('private void moveSelection(int delta) {', 1)[1].split('\n    }', 1)[0]
    # 空列表直接返回，避免对空集合取下标。
    assert 'if (items.isEmpty()) return;' in body
    # 越界时夹到两端，不越出列表。
    assert 'index = 0;' in body
    assert 'index = items.size() - 1;' in body
    # 选中项可能落在别的页，页码要跟着它走。
    assert 'index / rows()' in body


def test_enter_restores_only_when_something_is_selected():
    text = source()
    assert 'if (chosen() != null) { restore(); return true; }' in text


def test_the_page_is_rebuilt_so_details_refresh():
    """移动选中项要整页重建，详情面板和确认按钮才会跟着刷新。"""
    text = source()
    body = text.split('private void moveSelection(int delta) {', 1)[1].split('\n    }', 1)[0]
    assert 'with(tab, index / rows(), next, false)' in body


def test_the_compat_generator_rewrites_keys_for_older_targets():
    """按键分界是 1.21.9：之前是三参数签名，兼容生成必须把按键改回去。"""
    generator = (ROOT / 'scripts/generate_compat.py').read_text(encoding='utf8')
    assert "if name == 'BackupViewerScreen.java':" in generator
    assert 'if parts < (1, 21, 9):' in generator
    assert 'keyPressed(int keyCode, int scanCode, int modifiers)' in generator
    assert 'switch (event.key()) {' in generator
    assert "'switch (keyCode) {'" in generator


def test_the_shared_painter_is_adapted_for_older_targets():
    """VanillaConfluxUi 是参考包新加的绘制工具，老版本没有 render state API。"""
    generator = (ROOT / 'scripts/generate_compat.py').read_text(encoding='utf8')
    block = generator.split("if name in ('RestoreTitleScreenMixin.java'", 1)[1].split('):', 1)[0]
    for name in ('VanillaConfluxUi.java', 'BackupCommentScreen.java', 'ChunkBackupScreen.java'):
        assert name in block, name
