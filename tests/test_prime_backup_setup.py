import json
from pathlib import Path

import pytest

from setup_prime_backup import configure

ROOT = Path(__file__).resolve().parents[1]


def test_binding_preserves_prior_config_and_storage_without_touching_save(tmp_path):
    mcdr = tmp_path / 'mcdr'; mcdr.mkdir()
    (mcdr / 'runtime/config').mkdir(parents=True)
    (mcdr / 'runtime/config/config.yml').write_text('test')
    (mcdr / 'runtime/config/plugins').mkdir()
    world = tmp_path / 'saves' / '测试世界'; world.mkdir(parents=True)
    (world / 'level.dat').write_bytes(b'world-do-not-change')
    pb = mcdr / 'date' / world.name / 'config/prime_backup/config.json'; pb.parent.mkdir(parents=True)
    original = dict(storage_root='./my_existing_backups', debug=True, command=dict(prefix='!!backup'),
                    scheduled_backup=dict(enabled=True, interval='2h'), backup=dict(compress_method='zstd'))
    pb.write_text(json.dumps(original), encoding='utf8')
    configure(ROOT, mcdr, world, copy_adapter=True)
    result = json.loads(pb.read_text(encoding='utf8'))
    assert result['storage_root'] == original['storage_root']
    assert result['command'] == original['command']
    assert result['scheduled_backup'] == original['scheduled_backup']
    assert result['backup']['targets'] == [world.name]
    assert result['backup']['source_root'] == str(world.parent)
    assert result['backup']['compress_method'] == 'zstd'
    prior = list(pb.parent.glob('config.before-singleplayer-*.json'))
    assert len(prior) == 1 and json.loads(prior[0].read_text()) == original
    assert (world / 'level.dat').read_bytes() == b'world-do-not-change'
    assert (mcdr / 'runtime/config/plugins/singleplayer_prime_backup.mcdr').is_file()


def test_missing_adapter_release_is_rejected_before_config_is_changed(tmp_path):
    mcdr = tmp_path / 'mcdr'; mcdr.mkdir()
    (mcdr / 'runtime/config').mkdir(parents=True)
    (mcdr / 'runtime/config/config.yml').write_text('test')
    world = tmp_path / 'world'; world.mkdir()
    (world / 'level.dat').write_bytes(b'test')
    # No bundled artifacts and no release in this intentionally empty source root.
    with pytest.raises(ValueError, match='complete 0.3.5 release'):
        configure(tmp_path / 'empty-source', mcdr, world)
    assert not (mcdr / 'date/prime_backup/config.json').exists()
