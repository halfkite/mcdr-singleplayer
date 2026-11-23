"""New setup dialogs must remain usable by every declared Minecraft adapter."""
import pytest

import build_matrix
from generate_compat import MATRIX, ROOT, adapt_java
from neoforge_compat import write_platform


@pytest.mark.parametrize('loader', ['fabric', 'neoforge'])
@pytest.mark.parametrize('row', MATRIX['versions'], ids=lambda row: row['minecraft'])
def test_setup_dialogs_use_the_target_screen_api(loader, row):
    parts = tuple(map(int, row['minecraft'].split('.')))
    for name in ['SingleplayerBridge.java', 'PythonSetupScreen.java', 'McdrSetupScreen.java']:
        source = (ROOT / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer' / name).read_text(encoding='utf8')
        generated = adapt_java(source, name, row, loader)
        if parts < (26, 2):
            assert '.gui.screen()' not in generated
            assert '.gui.setScreen(' not in generated
            if name == 'SingleplayerBridge.java' and parts < (26, 1):
                assert 'client.player.sendSystemMessage(' not in generated
                assert 'client.gui.getChat().addMessage(' in generated
        if name != 'SingleplayerBridge.java' and parts < (26, 1):
            assert 'GuiGraphicsExtractor' not in generated
            assert 'extractRenderState' not in generated
            assert 'graphics.centeredText' not in generated
            assert 'public void render(GuiGraphics ' in generated
        if name == 'PythonSetupScreen.java' and parts < (26, 1):
            assert 'clickUrlAction' not in generated
            assert 'ConfirmLinkScreen.confirmLinkNow' in generated


@pytest.mark.parametrize('loader', ['fabric', 'neoforge'])
@pytest.mark.parametrize('row', MATRIX['versions'], ids=lambda row: row['minecraft'])
def test_backup_viewer_uses_the_target_screen_api(loader, row):
    parts = tuple(map(int, row['minecraft'].split('.')))
    root = ROOT / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer'
    screen = adapt_java((root / 'BackupViewerScreen.java').read_text(encoding='utf8'),
                        'BackupViewerScreen.java', row, loader)
    mixin = adapt_java((root / 'mixin/BackupViewerMixin.java').read_text(encoding='utf8'),
                       'BackupViewerMixin.java', row, loader)
    if parts < (26, 1):
        # 1.21.x draws through GuiGraphics/render instead of the extractor API, and
        # reaching the screen manager went through Minecraft directly.
        assert 'GuiGraphicsExtractor' not in screen
        assert 'extractRenderState' not in screen
        assert 'graphics.centeredText' not in screen
        assert 'public void render(GuiGraphics ' in screen
        assert '.gui.setScreen(' not in screen
        assert 'Minecraft.getInstance().setScreen(' in screen
    else:
        assert 'extractRenderState(GuiGraphicsExtractor' in screen
        # 26.2+ moved screen switching onto the gui manager.
        assert '.gui.setScreen(' in screen or 'Minecraft.getInstance().setScreen(' in screen
    # Per-variant mixins move into their own package so several can coexist.
    assert 'package io.github.mcdrsingleplayer.mixin.v' in mixin


def test_edit_screen_entry_never_shadows_or_reflects_vanilla_screen_widgets():
    """点「编辑」曾经直接报错：mixin 用 @Shadow 去要泛型的 widget 注册方法。

    EditWorldScreen 自身没有声明 addRenderableWidget（它在 Screen 上，而且是泛型的），
    擦除后在目标类里定位不到，让整个界面类转换失败。这里锁住修法：mixin 只读字段，
    按钮通过 Fabric 的 Screen 事件挂载，且全程不碰反射。
    """
    root = ROOT / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer'
    mixin = (root / 'mixin/BackupViewerMixin.java').read_text(encoding='utf8')
    button = (root / 'BackupViewerButton.java').read_text(encoding='utf8')
    for forbidden in ('addRenderableWidget', 'addWidget', '@Inject', '@At'):
        assert forbidden not in mixin, forbidden
    assert '@Mixin(EditWorldScreen.class)' in mixin
    assert '@Shadow' in mixin and 'levelAccess' in mixin
    assert 'implements BackupViewerAccess' in mixin
    # 反射在运行时会被混淆挡住，入口不允许用它。
    for forbidden in ('getDeclaredField', 'setAccessible', 'java.lang.reflect'):
        assert forbidden not in button, forbidden
        assert forbidden not in mixin, forbidden
    # 按钮走项目里已经验证过的 Screen 事件，而不是给原版界面注入方法。
    assert 'ScreenEvents.AFTER_INIT.register' in button
    assert 'widgets.add(' in button
    assert 'BackupViewerAccess' in button
    # AFTER_INIT 会对同一个界面重复触发（窗口缩放等），必须先查已有入口再添加，
    # 否则编辑界面上会堆出好几个「查看存档」。
    assert 'existing(' in button
    assert 'if (button == null)' in button
    # 编辑界面没有公开的选择器，mixin 必须提供只读访问器。这个接口必须放在 mixin 包
    # 外面：mixin 包是保留包，普通类引用其中类型会让启动直接抛 IllegalClassLoadError。
    access = (root / 'BackupViewerAccess.java').read_text(encoding='utf8')
    assert 'interface BackupViewerAccess' in access
    assert 'package io.github.mcdrsingleplayer;' in access
    assert not (root / 'mixin/BackupViewerAccess.java').exists()
    assert 'io.github.mcdrsingleplayer.mixin.BackupViewerAccess' not in button


def test_backup_viewer_layout_cannot_overlap_text_and_buttons():
    """文字压在按钮上过一次：版面各行必须由同一组 y() 推算，且宽度铺满窗口。

    这里锁住修法：坐标只能来自那一组 y()/x() 方法，渲染和 init 都用它；宽度与行数
    按窗口尺寸算，不写死。
    """
    root = ROOT / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer'
    screen = (root / 'BackupViewerScreen.java').read_text(encoding='utf8')
    # 纵向坐标集中在这些方法里；界面重构后具体名字可以变，但必须有单一来源。
    for method in ('tabsY', 'sectionY', 'listY', 'pagerY', 'statusY', 'toolsY', 'footerY'):
        assert method + '()' in screen, method
    # 不许再出现写死的行号偏移，那正是文字压按钮的来源。
    assert 'top + 144' not in screen
    assert 'top + 200' not in screen
    # 铺满窗口：面板宽高与行数都按窗口尺寸算。
    assert 'private int panelWidth()' in screen
    assert 'private int rows()' in screen
    # 建备份前要收备注 / 选区，并在进行中给出状态提示。
    assert 'BackupCommentScreen.open' in screen
    assert 'ChunkBackupScreen.open' in screen
    assert 'progress' in screen


def test_comment_and_area_dialogs_exist_and_stay_localized():
    root = ROOT / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer'
    comment = (root / 'BackupCommentScreen.java').read_text(encoding='utf8')
    # 备注可以留空直接确认，取消则什么都不做。
    assert 'comment_optional' in comment
    assert 'callback.done(value)' in comment
    assert 'callback.done(null)' in comment
    area = (root / 'ChunkBackupScreen.java').read_text(encoding='utf8')
    # 维度可切换，两个角共四个数字，留空即整维度。
    assert 'dimensionIndex' in area
    assert 'numbers.size() != 4' in area
    assert 'region = null' in area
    assert 'chunk_help' in area


def test_family_build_rejects_old_version_and_ignores_stale_jars(tmp_path, monkeypatch):
    monkeypatch.setattr(build_matrix, 'ROOT', tmp_path)
    monkeypatch.setattr(build_matrix, 'VERSION', '0.4.2')
    monkeypatch.setattr(build_matrix, 'BUILD_VERSION', '0.4.2')
    libs = tmp_path / 'build/matrix/fabric/26.3/build/libs'
    libs.mkdir(parents=True)
    (libs / 'mcdr-singleplayer-0.3.10+fabric+mc26.3.jar').write_bytes(b'old build')
    with pytest.raises(RuntimeError, match='current version'):
        build_matrix.variant_artifact('fabric', '26.3')
    current = libs / 'mcdr-singleplayer-0.4.2+fabric+mc26.3.jar'
    current.write_bytes(b'current build')
    assert build_matrix.variant_artifact('fabric', '26.3') == current


def test_neoforge_bridge_uses_native_server_tick_and_game_directory():
    row = MATRIX['versions'][0]
    source_root = ROOT / 'fabric-bridge/src/main/java/io/github/mcdrsingleplayer'
    bridge = adapt_java((source_root / 'SingleplayerBridge.java').read_text(encoding='utf8'),
                        'SingleplayerBridge.java', row, 'neoforge')
    conflux = adapt_java((source_root / 'mixin/ConfluxNativeCacheMixin.java').read_text(encoding='utf8'),
                         'ConfluxNativeCacheMixin.java', row, 'neoforge')

    assert 'NeoPlatform.serverTick(serverCommands::tick);' in bridge
    assert 'ServerTickEvents' not in bridge
    assert 'net.neoforged.fml.loading.FMLPaths.GAMEDIR.get()' in conflux
    assert 'FabricLoader' not in conflux


def test_neoforge_platform_registers_server_tick_on_the_main_event_bus(tmp_path):
    row = MATRIX['versions'][0]
    write_platform(tmp_path, row)
    package = 'io/github/mcdrsingleplayer/v1_21'
    platform = (tmp_path / package / 'NeoPlatform.java').read_text(encoding='utf8')

    assert 'ServerTickEvent.Post' in platform
    assert 'static void serverTick(Consumer<MinecraftServer> action)' in platform
    assert 'action.accept(event.getServer())' in platform
