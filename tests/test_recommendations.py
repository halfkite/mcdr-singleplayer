import json
from pathlib import Path
from types import SimpleNamespace
from ruamel.yaml import YAML

from singleplayer_bridge.profiles import ensure_profile, recommend, read_json
from singleplayer_bridge.supervisor import configure_host
from singleplayer_bridge.commands import command_tree
from mcdreforged.api.command import Literal, QuotableText


def test_recommendation_consent_is_independent_and_survives_reentry(tmp_path):
    world = tmp_path / 'saves/world'
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'test')
    common = tmp_path / 'common'
    profile = ensure_profile(common, world, 'zh_cn')
    path = profile / 'config/prime_backup/config.json'
    initial = read_json(path)
    assert initial['enabled'] and not initial['scheduled_backup']['enabled'] and not initial['prune']['enabled']
    assert read_json(profile / 'config/singleplayer_bridge/config.json') == {'language': 'zh_cn', 'recommendation_version': '0.3.2'}
    recommend(profile, auto_backup=True)
    configured = read_json(path)
    assert configured['scheduled_backup']['enabled'] and configured['scheduled_backup']['interval'] == '4h'
    assert not configured['prune']['enabled']
    recommend(profile, auto_delete=True)
    configured = read_json(path)
    assert configured['prune']['regular_backup'] == dict(enabled=True, max_amount=0, max_lifetime='0s', last=40, hour=0, day=30, week=30, month=0, year=0)
    assert not configured['prune']['scheduled_backup']['enabled']  # Included in the regular pool.
    assert configured['scheduled_backup']['enabled'] and configured['prune']['enabled']
    ensure_profile(common, world, 'en_us')
    assert read_json(path) == configured
    recommend(profile, auto_backup=False)
    assert not read_json(path)['scheduled_backup']['enabled'] and read_json(path)['prune']['enabled']
    recommend(profile, backup_enabled=False)
    ensure_profile(common, world)
    assert not read_json(path)['enabled']
    recommend(profile, backup_enabled=True)
    assert read_json(path)['enabled']


def test_only_main_player_gets_owner_and_language_follows_client(tmp_path):
    config_dir = tmp_path / 'runtime/config'; config_dir.mkdir(parents=True)
    (config_dir / 'config.yml').write_text('language: en_us\n', encoding='utf8')
    (config_dir / 'permission.yml').write_text('default_level: user\nowner: [Existing]\nuser: [Main, Guest]\n', encoding='utf8')
    configure_host(tmp_path, 'Main', 'zh_cn')
    yaml = YAML()
    permission = yaml.load((config_dir / 'permission.yml').read_text(encoding='utf8'))
    assert permission['owner'] == ['Existing', 'Main'] and permission['user'] == ['Guest']
    assert yaml.load((config_dir / 'config.yml').read_text(encoding='utf8'))['language'] == 'zh_cn'
    before = (config_dir / 'permission.yml').read_bytes()
    configure_host(tmp_path, 'Main', 'zh_cn')
    assert before == (config_dir / 'permission.yml').read_bytes()
    configure_host(tmp_path, 'not valid', 'de_de')
    assert before == (config_dir / 'permission.yml').read_bytes()
    assert yaml.load((config_dir / 'config.yml').read_text(encoding='utf8'))['language'] == 'de_de'


def test_all_roots_aliases_arguments_and_recursive_redirects_are_exported():
    leaf = Literal('leaf').runs(lambda source: None)
    recursive = Literal('again')
    root = Literal(('!!custom', '!!alias')).then(QuotableText('world').then(leaf)).then(recursive)
    recursive.redirects(root)
    manager = SimpleNamespace(root_nodes={name: [SimpleNamespace(node=root)] for name in root.literals})
    tree = json.loads(command_tree(SimpleNamespace(_mcdr_server=SimpleNamespace(command_manager=manager))))
    assert {tree['nodes'][i]['name'] for i in tree['roots']} == {'!!custom', '!!alias'}
    for i in tree['roots']:
        value = tree['nodes'][i]
        arg = next(tree['nodes'][child] for child in value['children'] if tree['nodes'][child]['kind'] == 'argument')
        assert arg['name'] == 'world' and tree['nodes'][arg['children'][0]]['name'] == 'leaf'
    assert len(tree['nodes']) == 5


def test_upgrade_enables_recommendation_once_without_resetting_future_choices(tmp_path):
    world = tmp_path / 'saves/world'
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'test')
    common = tmp_path / 'common'
    profile = ensure_profile(common, world)
    preferences = profile / 'config/singleplayer_bridge/config.json'
    preferences.write_text('{}', encoding='utf8')
    prime = profile / 'config/prime_backup/config.json'
    old = read_json(prime)
    old['enabled'] = False
    prime.write_text(json.dumps(old), encoding='utf8')
    ensure_profile(common, world, 'zh_cn')
    assert read_json(prime)['enabled']
    recommend(profile, auto_backup=True, auto_delete=False)
    ensure_profile(common, world, 'en_us')
    assert read_json(prime)['scheduled_backup']['enabled'] and not read_json(prime)['prune']['enabled']
    assert read_json(preferences)['language'] == 'en_us'


def test_actual_prime_backup_retention_keeps_last_daily_and_weekly_buckets():
    import sys
    import datetime
    from contextlib import contextmanager
    archive = Path(__file__).resolve().parents[1] / '.reference/PrimeBackup-v1.13.1.pyz'
    sys.path.insert(0, str(archive))
    try:
        from prime_backup.config.prune_config import PruneSetting
        from prime_backup.mcdr.task.backup.prune_backup_task import PruneBackupTask
        from prime_backup.types.timestamp import Timestamp
        backups = []
        start = datetime.datetime(2026, 10, 2, 12, tzinfo=datetime.timezone.utc)
        for index in range(2400):
            backups.append(SimpleNamespace(id=index + 1, timestamp=Timestamp.from_datetime(start - datetime.timedelta(hours=index * 4)),
                tags=SimpleNamespace(is_protected=lambda: False)))
        plan = PruneBackupTask.calc_prune_backups(backups, PruneSetting(enabled=True, last=40, day=30, week=30), timezone=datetime.timezone.utc)
        kept = [item for item in plan if item.mark.keep]
        assert all(plan.id_to_mark[index].keep for index in range(1, 41))
        assert sum(item.mark.reason.startswith('keep day ') for item in kept) == 30
        assert sum(item.mark.reason.startswith('keep week ') for item in kept) == 30
        assert not plan.id_to_mark[2400].keep
        assert any(item.mark.keep and item.backup.id > 1000 for item in plan)
    finally:
        sys.path.remove(str(archive))
