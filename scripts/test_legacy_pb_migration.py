"""Read/export a migrated real 0.3.3 PB database in an isolated 0.3.10 game layout."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
sys.path.insert(0, str(ROOT / '.reference/PrimeBackup-v1.13.1.pyz'))
from singleplayer_bridge.layout import migrate_legacy
from singleplayer_bridge.profiles import ensure_profile, read_json, write_json
from prime_backup.config.config import Config, set_config_instance
from prime_backup.db.access import DbAccess
from prime_backup.action.get_backup_action import GetBackupAction
from prime_backup.action.export_backup_action_zip import ExportBackupToZipAction


def main():
    reference = ROOT / '.reference/auto-0.3.3-r2/worlds/New World (4)'
    original_db = reference / 'data/prime_backup/prime_backup.db'
    before = hashlib.sha256(original_db.read_bytes()).hexdigest()
    base = Path(tempfile.mkdtemp(prefix='migration-0.3.10-', dir=ROOT / '.reference'))
    game = base / 'game'
    world = game / 'saves' / reference.name
    world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'isolated-placeholder-not-restored')
    source = base / 'legacy'
    legacy = source / 'worlds' / reference.name
    shutil.copytree(reference, legacy)
    write_json(legacy / 'profile.json', {'world_path': str(world), 'folder': world.name})
    config = read_json(legacy / 'config/prime_backup/config.json')
    config['storage_root'] = str(legacy / 'data/prime_backup')
    config['backup']['source_root'] = str(world.parent)
    write_json(legacy / 'config/prime_backup/config.json', config)
    common = game / 'mcdr-singleplayer'
    write_json(common / 'runtime/.legacy-layout.json', {'source': str(source)})
    migrate_legacy(common)
    profile = ensure_profile(common, world, 'zh_cn')
    assert profile == common / 'date' / world.name
    config = read_json(profile / 'config/prime_backup/config.json')
    os.chdir(profile)
    set_config_instance(Config.deserialize(config))
    DbAccess.init(create=False, migrate=False)
    try:
        backup = GetBackupAction(1, with_files=True).run()
        output = profile / 'pb_files/migrated-test.zip'
        failures = ExportBackupToZipAction(1, output, verify_blob=True).run()
        assert len(failures) == 0
        with zipfile.ZipFile(output) as archive:
            marker = world.name + '/auto-test-marker.txt'
            assert archive.read(marker) == b'before'
            assert world.name + '/level.dat' in archive.namelist()
            files = len(archive.namelist())
        assert (world / 'level.dat').read_bytes() == b'isolated-placeholder-not-restored'
    finally:
        DbAccess.shutdown()
    assert hashlib.sha256(original_db.read_bytes()).hexdigest() == before
    assert not (common / 'worlds').exists()
    result = {'result': 'passed', 'source': str(reference), 'profile': str(profile), 'backup_id': 1,
        'comment': backup.comment, 'exported_entries': files, 'source_database_sha256': before,
        'verified_blob_export': True, 'source_preserved': True}
    (ROOT / 'docs/assets/automatic-0.3.10-migration.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
