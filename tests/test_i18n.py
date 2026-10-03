import ast
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from singleplayer_bridge import onboarding, plugin
from singleplayer_bridge.config_file import write as write_bridge_config
from singleplayer_bridge.i18n import catalog, locale, tr
from singleplayer_bridge.profiles import write_json

ROOT = Path(__file__).resolve().parents[1]


def test_all_three_catalogs_cover_same_keys_and_arguments_without_full_stops():
    english = catalog('en_us')
    assert len(english) >= 100
    for language in ['zh_cn', 'zh_tw', 'en_us']:
        values = catalog(language)
        assert values.keys() == english.keys()
        for key, text in values.items():
            assert text and '。' not in text
            assert text.count('%s') == english[key].count('%s'), key
        assert '\n' in values['mcdr-singleplayer.onboarding.intro']
        assert not values['mcdr-singleplayer.onboarding.intro'].endswith('.')
    assert '權限' in catalog('zh_tw')['mcdr-singleplayer.onboarding.intro']


@pytest.mark.parametrize('language,word,button', [
    ('zh_cn', '存档', '[开启Prime Backup]'),
    ('zh_tw', '存檔', '[開啟Prime Backup]'),
    ('en_us', 'singleplayer', '[Enable Prime Backup]')])
def test_chat_and_configuration_use_selected_catalog(tmp_path, monkeypatch, language, word, button):
    common = tmp_path / 'common'
    (common / 'plugins').mkdir(parents=True)
    write_bridge_config(common / 'mcdr-singleplayer-config.yml', {'token': 'preserved'})
    monkeypatch.setenv('MCDR_BRIDGE_COMMON', str(common))
    monkeypatch.setenv('MCDR_BRIDGE_LANGUAGE', language)
    monkeypatch.setenv('MCDR_BRIDGE_CLIENT_ID', 'test-' + language)
    monkeypatch.setenv('MCDR_BRIDGE_HOST', 'Host')
    monkeypatch.setattr(plugin, 'snapshot', lambda: dict(session=language, players=['Host']))
    monkeypatch.setattr(onboarding, '_shown', set())
    monkeypatch.setattr(onboarding, '_settings_shown', set())
    messages = []
    server = SimpleNamespace(tell=lambda player, value: messages.append(value), get_plugin_instance=lambda item: object() if item == 'prime_backup' else None)
    onboarding.prompt(server)
    text = '\n'.join(str(m) for m in messages)
    assert word in text and button in text
    assert text.count(tr('onboarding.warning')) == 3
    assert '。' not in text and 'mcdr-singleplayer.onboarding' not in text
    clicks = json.dumps([m.to_json_object() for m in messages if hasattr(m, 'to_json_object')])
    assert '/!!spbridge config auto_backup on' in clicks
    assert '/!!spbridge config auto_delete on' in clicks
    assert '/!!spbridge onboarding dismiss' in clicks


def test_unsupported_locale_and_missing_key_fall_back_to_english(monkeypatch):
    assert locale('zh-HK') == 'zh_tw'
    assert locale('../private') == 'en_us'
    assert tr('prime.enable', language='fr_fr') == '[Enable Prime Backup]'
    monkeypatch.setitem(catalog('zh_tw'), 'mcdr-singleplayer.command.enabled', '%s已啟用')
    assert tr('command.enabled', 'PB', language='zh_tw') == 'PB已啟用'
    assert tr('unknown.key', language='fr_fr') == 'mcdr-singleplayer.unknown.key'


def test_python_translation_references_exist_in_catalog_and_replies_are_not_literal():
    for folder in ['python/singleplayer_bridge', 'prime-backup-adapter', 'chunk-backup-adapter']:
        for path in (ROOT / folder).rglob('*.py'):
            source = path.read_text(encoding='utf-8')
            for key in re.findall(r"\btr\(['\"]([a-z_]+\.[a-z0-9_]+)['\"]", source):
                assert 'mcdr-singleplayer.' + key in catalog('en_us'), (path, key)
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {'reply', 'tell'}:
                    assert not any(isinstance(arg, ast.Constant) and isinstance(arg.value, str) and re.search('[\u4e00-\u9fff]', arg.value) for arg in node.args), path


def test_mod_metadata_points_to_packaged_png_icon():
    import struct
    resources = ROOT / 'fabric-bridge/src/main/resources'
    metadata = json.loads((resources / 'fabric.mod.json').read_text(encoding='utf-8'))
    image = (resources / metadata['icon']).read_bytes()
    assert image[:8] == b'\x89PNG\r\n\x1a\n'
    assert struct.unpack('>II', image[16:24]) == (128, 128)
