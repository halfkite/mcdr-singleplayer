"""控制台窗口的启动命令必须能在含空格的路径下工作。

点「打开控制台」曾经只弹出游戏内面板，而不是真正的命令行窗口：启动命令拆成了
参数数组交给 cmd.exe，而 `start` 还要再解析一次引号，两层解析叠加把含空格的
路径拆断，新窗口刚出现就退出。这里锁住修法：命令必须拼成单个字符串，且 `start`
的第一个引号参数（窗口标题）不能省。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer/AutoRuntime.java'


def source():
    return RUNTIME.read_text(encoding='utf8')


def test_console_window_uses_a_single_start_string():
    text = source()
    # 命令必须作为整串传给 /c，而不是拆成 "start", "MCDR console", "cmd.exe", "/k", ...
    assert '"start \\"MCDR console\\" cmd.exe /k \\"" + launcher + "\\""' in text
    assert '"cmd.exe", "/c",\n' in text or '"cmd.exe", "/c",' in text


def test_start_never_passes_the_title_as_a_separate_argument():
    text = source()
    # 这种写法会被 cmd 二次解析引号，含空格的实例路径因此打不开窗口。
    assert '"start", "MCDR console", "cmd.exe", "/k"' not in text


def test_the_launcher_is_quoted_inside_the_command():
    text = source()
    assert 'cmd.exe /k \\"" + launcher + "\\""' in text


def test_console_falls_back_to_the_panel_only_when_the_window_fails():
    """Windows 上先开真窗口；非 Windows 或失败时才用游戏内面板。"""
    bridge = (ROOT / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer/SingleplayerBridge.java'
              ).read_text(encoding='utf8')
    assert 'if (runtime.openConsoleWindow()) return;' in bridge
    assert 'new McdrConsoleScreen(' in bridge


def test_the_window_only_opens_on_windows():
    text = source()
    assert 'os.name' in text
    assert 'contains("windows")' in text
