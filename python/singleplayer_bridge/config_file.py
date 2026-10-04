"""Read and write the small, comment-friendly YAML configuration shared by the bridge."""
import json
from pathlib import Path


COMMENTS = {
    'enabled': '启用单人游戏与 MCDR 的桥接',
    'port': '本机回环连接端口；发生冲突时可修改',
    'token': '随机身份验证令牌，请勿分享或公开',
    'autoStartMcdr': '进入单人存档时自动启动 MCDR',
    'pythonExecutable': '可选的 Python 可执行文件路径；留空时自动检测',
    'autoInstall': '自动准备 MCDR、桥接插件及运行依赖',
    'onboardingDismissed': '是否隐藏首次使用提示',
    'onboardingLastClientId': '上次显示提示的客户端标识，由模组维护',
}
DEFAULTS = {
    'enabled': True,
    'port': 25585,
    'token': '',
    'autoStartMcdr': True,
    'pythonExecutable': '',
    'autoInstall': True,
    'onboardingDismissed': False,
    'onboardingLastClientId': '',
}


def _parse_yaml(text):
    result = {}
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        key, separator, raw = stripped.partition(':')
        if not separator or not key.strip():
            raise ValueError(f'invalid bridge YAML at line {number}')
        key, raw = key.strip(), _strip_comment(raw.strip())
        if not raw:
            value = None
        elif raw.startswith(('"', '[', '{')):
            value = json.loads(raw)
        elif raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
            value = raw[1:-1].replace("''", "'")
        elif raw.lower() in {'true', 'false'}:
            value = raw.lower() == 'true'
        elif raw.lower() in {'null', '~'}:
            value = None
        else:
            try:
                value = int(raw, 10)
            except ValueError:
                value = raw.split(' #', 1)[0].strip()
        result[key] = value
    return result


def _strip_comment(raw):
    quote = None
    escaped = False
    for index, char in enumerate(raw):
        if escaped:
            escaped = False
        elif char == '\\' and quote == '"':
            escaped = True
        elif quote and char == quote:
            quote = None
        elif not quote and char in {'"', "'"}:
            quote = char
        elif not quote and char == '#' and (index == 0 or raw[index - 1].isspace()):
            return raw[:index].rstrip()
    return raw


def read(path):
    path = Path(path)
    if not path.exists():
        return {}
    text = path.read_text(encoding='utf-8-sig')
    if text.lstrip().startswith('{') or path.suffix.lower() == '.json':
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError('invalid bridge configuration')
        return value
    return _parse_yaml(text)


def write(path, config):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == '.json':
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        return
    values = dict(DEFAULTS)
    values.update(config)
    lines = [
        '# MCDR Singleplayer bridge settings / 单人游戏 MCDR 桥接设置',
        '# These settings apply to this game instance; plugin data remains separated by save.',
        '# 本设置作用于当前游戏实例；各存档的插件配置和数据仍分别保存在 plugindata/<存档文件夹名>。',
        '# Edit values below, then restart the game to apply changes.',
        '# 修改下列数值后重启游戏生效。',
    ]
    for key, default in DEFAULTS.items():
        if key not in values:
            continue
        lines.extend((f'# {COMMENTS[key]}', f'{key}: {json.dumps(values.pop(key), ensure_ascii=False)}'))
    for key, value in values.items():
        lines.append(f'{key}: {json.dumps(value, ensure_ascii=False)}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf8')
