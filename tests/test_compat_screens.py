"""New setup dialogs must remain usable by every declared Minecraft adapter."""
import pytest

import build_matrix
from generate_compat import MATRIX, ROOT, adapt_java


@pytest.mark.parametrize('loader', ['fabric', 'neoforge'])
@pytest.mark.parametrize('row', MATRIX['versions'], ids=lambda row: row['minecraft'])
def test_setup_dialogs_use_the_target_screen_api(loader, row):
    parts = tuple(map(int, row['minecraft'].split('.')))
    for name in ['SingleplayerBridge.java', 'PythonSetupScreen.java', 'McdrInstallNoticeScreen.java']:
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


def test_family_build_rejects_old_version_and_ignores_stale_jars(tmp_path, monkeypatch):
    monkeypatch.setattr(build_matrix, 'ROOT', tmp_path)
    monkeypatch.setattr(build_matrix, 'VERSION', '0.4.2')
    libs = tmp_path / 'build/matrix/fabric/26.3/build/libs'
    libs.mkdir(parents=True)
    (libs / 'mcdr-singleplayer-0.3.10+fabric+mc26.3.jar').write_bytes(b'old build')
    with pytest.raises(RuntimeError, match='current version'):
        build_matrix.variant_artifact('fabric', '26.3')
    current = libs / 'mcdr-singleplayer-0.4.2+fabric+mc26.3.jar'
    current.write_bytes(b'current build')
    assert build_matrix.variant_artifact('fabric', '26.3') == current
