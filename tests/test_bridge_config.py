import json

from singleplayer_bridge.config_file import read, write


def test_yaml_settings_have_comments_and_round_trip_values(tmp_path):
    path = tmp_path / 'mcdr-singleplayer-config.yml'
    settings = {
        'enabled': True,
        'port': 25591,
        'token': '秘密-token: #value',
        'autoStartMcdr': False,
        'pythonExecutable': 'D:/Python 3.14/python.exe',
        'autoInstall': True,
        'onboardingDismissed': True,
        'onboardingLastClientId': 'client-a',
    }

    write(path, settings)

    text = path.read_text(encoding='utf8')
    assert '# MCDR Singleplayer bridge settings' in text
    assert '# 随机身份验证令牌，请勿分享或公开' in text
    assert read(path) == settings | {'enabled': True}


def test_json_is_still_readable_for_upgrade_migration(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'enabled': True, 'token': 'a' * 64, 'port': 25590}), encoding='utf8')

    assert read(path) == {'enabled': True, 'token': 'a' * 64, 'port': 25590}


def test_yaml_inline_comments_do_not_change_types_or_quoted_values(tmp_path):
    path = tmp_path / 'mcdr-singleplayer-config.yml'
    path.write_text('enabled: true # comment\nport: 25591 # comment\ntoken: "secret # text" # trailing\n', encoding='utf8')

    assert read(path) == {'enabled': True, 'port': 25591, 'token': 'secret # text'}
