"""Shared Minecraft/Python language catalog with an English fallback."""
import json
import os
import re
from functools import lru_cache
from importlib.resources import files

PREFIX = 'mcdr-singleplayer.'


@lru_cache(maxsize=None)
def catalog(language):
    path = files(__package__).joinpath('lang', language + '.json')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}


def locale(language=None):
    value = (language or os.environ.get('MCDR_BRIDGE_LANGUAGE', 'en_us')).lower().replace('-', '_')
    if not re.fullmatch(r'[a-z][a-z0-9_]{1,31}', value):
        return 'en_us'
    return {'zh_hk': 'zh_tw', 'zh_mo': 'zh_tw', 'zh_sg': 'zh_cn'}.get(value, value)


def tr(key, *args, language=None):
    key = key if key.startswith(PREFIX) else PREFIX + key
    template = catalog(locale(language)).get(key, catalog('en_us').get(key, key))
    return template % args if args else template
