"""Generate isolated source sets from the tested bridge plus explicit API compatibility edits.

Generated projects live below build/matrix; canonical sources are never rewritten by a port.
"""
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = json.loads((ROOT / 'compat/versions.json').read_text(encoding='utf8'))
BASE = 'io.github.mcdrsingleplayer'


def fabric_metadata(row):
    metadata = json.loads((ROOT / 'fabric-bridge/src/main/resources/fabric.mod.json').read_text())
    metadata['version'] = MATRIX['modVersion']
    metadata['entrypoints'] = {'main': [BASE + '.bootstrap.FabricEntry']}
    metadata['mixins'] = ['mcdr-family.mixins.json']
    metadata['depends'] = {'fabricloader': '>=' + MATRIX['fabricLoaderMinimum'], 'minecraft': row['minecraft'],
                           'java': '>=' + str(row['java']), 'fabric-api': '*'}
    metadata['contact'] = {'homepage': 'https://github.com/halfkite/mcdr-singleplayer',
                           'sources': 'https://github.com/halfkite/mcdr-singleplayer',
                           'issues': 'https://github.com/halfkite/mcdr-singleplayer/issues'}
    return metadata


def neo_metadata(row, family=None):
    targets = [r['minecraft'] for r in MATRIX['versions'] if r['family'] == family] if family else [row['minecraft']]
    game_range = ','.join('[' + game + ']' for game in targets)
    return f'''modLoader="javafml"
loaderVersion="[1,)"
license="LGPL-3.0-only"
issueTrackerURL="https://github.com/halfkite/mcdr-singleplayer/issues"
[[mods]]
modId="mcdr_singleplayer"
version="{MATRIX['modVersion']}"
displayName="mcdr-singleplayer"
displayURL="https://github.com/halfkite/mcdr-singleplayer"
{'iconFile' if row['java'] == 25 else 'logoFile'}="assets/mcdr-singleplayer/icon.png"
description="Connect MCDReforged and Python plugins to the integrated singleplayer server"
[[mixins]]
config="mcdr-family.mixins.json"
[[dependencies.mcdr_singleplayer]]
modId="neoforge"
type="required"
versionRange="[{'21.0' if row['java'] == 21 else '26.1'},)"
ordering="NONE"
side="CLIENT"
[[dependencies.mcdr_singleplayer]]
modId="minecraft"
type="required"
versionRange="{game_range}"
ordering="NONE"
side="CLIENT"
'''


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf8')


def legacy_overlay(text, game):
    text = text.replace('beforeExtract', 'beforeRender').replace('afterExtract', 'afterRender')
    if tuple(map(int, game.split('.'))) < (1, 21, 11):
        text = text.replace('background.init(width, height)', 'background.init(client, width, height)')
    text = text.replace('graphics.nextStratum();', '')
    text = text.replace('background.extractBackground', 'background.renderBackground')
    text = text.replace('screen.getFont()', 'client.font')
    text = text.replace('graphics.centeredText', 'graphics.drawCenteredString')
    text = text.replace('dismiss.extractRenderState', 'dismiss.render')
    return text


def adapt_java(text, name, row, loader):
    game = row['minecraft']
    parts = tuple(map(int, game.split('.')))
    late = parts >= (1, 21, 11)
    extracted = parts >= (26, 1)
    text = text.replace('getPlainTextName()', 'getName().getString()')
    if parts < (26, 2):
        text = text.replace('client.gui.setScreen(', 'client.setScreen(')
        text = text.replace('getInstance().gui.setScreen(', 'getInstance().setScreen(')
        text = text.replace('.gui.screen()', '.screen')
    if not late:
        text = text.replace('.dimension().identifier()', '.dimension().location()')
    if not extracted:
        if not late:
            text = text.replace('net.minecraft.util.Util', 'net.minecraft.Util')
        text = text.replace('client.gui.setScreen(', 'client.setScreen(')
        text = text.replace('getInstance().gui.setScreen(', 'getInstance().setScreen(')
        if name in ('RestoreTitleScreenMixin.java', 'PythonSetupScreen.java', 'McdrInstallNoticeScreen.java'):
            text = text.replace('GuiGraphicsExtractor', 'GuiGraphics').replace('extractRenderState', 'render')
            text = text.replace('graphics.centeredText', 'graphics.drawCenteredString')
        if name == 'PythonSetupScreen.java':
            # Older Screen APIs do not expose clickUrlAction; keep vanilla link confirmation.
            text = text.replace('clickUrlAction(Minecraft.getInstance(), Minecraft.getInstance().screen, URI.create(url))',
                                'net.minecraft.client.gui.screens.ConfirmLinkScreen.confirmLinkNow(Minecraft.getInstance().screen, URI.create(url))')
        if name == 'RestoreTitleOverlay.java':
            text = legacy_overlay(text, game)
    if name == 'SingleplayerBridge.java':
        text = text.replace('server.isPaused()', 'Minecraft.getInstance().isPaused()')
        if parts < (26, 1):
            if parts < (1, 21, 6):
                text = text.replace('client.disconnectFromWorld(Component.translatable("mcdr-singleplayer.restore.disconnect"));',
                                    'client.level.disconnect();\n                client.disconnect();')
            elif parts < (1, 21, 9):
                text = text.replace('client.disconnectFromWorld(Component.translatable("mcdr-singleplayer.restore.disconnect"));',
                                    'client.level.disconnect(Component.translatable("mcdr-singleplayer.restore.disconnect"));\n                client.disconnect(new net.minecraft.client.gui.screens.TitleScreen(), false);')
            text = text.replace('server.setAutoSave(false);', 'for (ServerLevel level : server.getAllLevels()) level.noSave = true;')
            text = text.replace('server.setAutoSave(true);', 'restoreAutoSave(server);')
        text = text.replace('FabricClientCommandSource::attended', 'source -> source.getPlayer() != null')
    if loader == 'fabric' and parts < (26, 1):
        text = text.replace('ClientCommands', 'ClientCommandManager')
        text = text.replace('Screens.getWidgets', 'Screens.getButtons')
        if name == 'ClientCommandTree.java':
            text = text.replace('ClientCommandManager.refreshCommandCompletions();', 'refreshLegacyCompletions();')
            text = text.replace('bridge.suggest(command.getSource().getPlayer().getName().getString(),',
                                'bridge.suggest(net.minecraft.client.Minecraft.getInstance().player.getName().getString(),')
            # Legacy Fabric has no refresh API: mirror only owned roots into the suggestion dispatcher.
            marker = '    @SuppressWarnings("unchecked")\n    private void removeOwned()'
            text = text.replace(marker, '''    @SuppressWarnings({"rawtypes", "unchecked"})
    private void refreshLegacyCompletions() {
        var connection = net.minecraft.client.Minecraft.getInstance().getConnection();
        if (connection == null) return;
        for (String name : owned) connection.getCommands().getRoot().addChild((CommandNode) dispatcher.getRoot().getChild(name));
    }

''' + marker)
            # Remove previous suggestion roots along with actual client roots.
            text = text.replace('owned.forEach(nodes::remove);', '''owned.forEach(nodes::remove);
                var connection = net.minecraft.client.Minecraft.getInstance().getConnection();
                if (connection != null) {
                    Map<String, ?> suggestions = (Map<String, ?>) field.get(connection.getCommands().getRoot());
                    owned.forEach(suggestions::remove);
                }''')
    if loader == 'neoforge':
        from neoforge_compat import adapt
        text = adapt(text, name, row)
    package = BASE + '.v' + game.replace('.', '_')
    text = text.replace(BASE, package)
    if name in ('RestoreWorldOpenMixin.java', 'RestoreTitleScreenMixin.java'):
        text = text.replace('package ' + package + '.mixin;', 'package ' + BASE + '.mixin.v' + game.replace('.', '_') + ';')
    return text


def generate(loader, row):
    game = row['minecraft']
    project = ROOT / 'build/matrix' / loader / game
    project.mkdir(parents=True, exist_ok=True)
    source_root = project / 'src/main/java'
    # Prevent stale generated files after changes to a version adapter.
    if source_root.exists():
        assert source_root.resolve().is_relative_to((ROOT / 'build/matrix').resolve())
        shutil.rmtree(source_root)
    for source in (ROOT / 'fabric-bridge/src/main/java').rglob('*.java'):
        relative = source.relative_to(ROOT / 'fabric-bridge/src/main/java')
        relative = Path(str(relative).replace('mcdrsingleplayer', 'mcdrsingleplayer/v' + game.replace('.', '_')))
        if source.name in ('RestoreWorldOpenMixin.java', 'RestoreTitleScreenMixin.java'):
            relative = Path('io/github/mcdrsingleplayer/mixin/v' + game.replace('.', '_')) / source.name
        write(source_root / relative, adapt_java(source.read_text(encoding='utf8'), source.name, row, loader))
    for source in (ROOT / 'compat/bootstrap').glob('*.java'):
        if (loader == 'fabric' and source.name == 'NeoForgeEntry.java') or (loader == 'neoforge' and source.name == 'FabricEntry.java'):
            continue
        write(source_root / 'io/github/mcdrsingleplayer/bootstrap' / source.name, source.read_text(encoding='utf8'))
    if loader == 'neoforge':
        from neoforge_compat import write_platform
        write_platform(source_root, row)
    resources = project / 'src/main/resources'
    resources.mkdir(parents=True, exist_ok=True)
    write(resources / 'mcdr-variants.json', json.dumps({game: BASE + '.v' + game.replace('.', '_')}))
    mixins = {'required': True, 'package': BASE + '.mixin', 'plugin': BASE + '.bootstrap.VariantMixins',
              'compatibilityLevel': 'JAVA_' + str(row['java']), 'client': [], 'injectors': {'defaultRequire': 1}}
    write(resources / 'mcdr-family.mixins.json', json.dumps(mixins))
    if loader == 'fabric':
        if row['java'] == 21:
            mixins['refmap'] = 'mcdr-' + game + '.refmap.json'
            write(resources / 'mcdr-family.mixins.json', json.dumps(mixins))
        write(resources / 'fabric.mod.json', json.dumps(fabric_metadata(row), indent=2))
    else:
        write(resources / 'META-INF/neoforge.mods.toml', neo_metadata(row))
    write(project / 'settings.gradle', '''pluginManagement {
    repositories { maven { url = 'https://maven.fabricmc.net/' }; gradlePluginPortal(); mavenCentral() }
}
plugins { id 'org.gradle.toolchains.foojay-resolver-convention' version '1.0.0' }
rootProject.name = 'mcdr-singleplayer'
''')
    properties = 'org.gradle.jvmargs=-Xmx2G\norg.gradle.parallel=false\n'
    if os.environ.get('MCDR_JAVA_INSTALLATIONS'):
        properties += 'org.gradle.java.installations.paths=' + os.environ['MCDR_JAVA_INSTALLATIONS'].replace('\\', '/') + '\n'
    write(project / 'gradle.properties', properties)
    gradle = (ROOT / 'compat' / (loader + '.gradle')).read_text(encoding='utf8')
    values = {'GAME': game, 'VERSION': MATRIX['modVersion'], 'JAVA': row['java'], 'ROOT': ROOT.as_posix(),
              'FABRIC_API': row['fabricApi'], 'LOADER': MATRIX['fabricLoader'], 'NEOFORGE': row['neoforge'],
              'LOOM_PLUGIN': 'net.fabricmc.fabric-loom' if row['java'] == 25 else 'fabric-loom',
              'MOD_DEPENDENCY': 'implementation' if row['java'] == 25 else 'modImplementation',
              'MAPPINGS': '' if row['java'] == 25 else 'mappings loom.officialMojangMappings()',
              'MIXIN_AP': '' if row['java'] == 25 else "loom { mixin { useLegacyMixinAp = true; defaultRefmapName = 'mcdr-" + game + ".refmap.json' } }"}
    for key, value in values.items():
        gradle = gradle.replace('@' + key + '@', str(value))
    write(project / 'build.gradle', gradle)
    return project
