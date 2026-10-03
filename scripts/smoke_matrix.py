"""Launch an isolated client using the merged family JAR and a test-only PB fixture."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import secrets
from datetime import datetime
from pathlib import Path
from generate_compat import ROOT, MATRIX, generate, write


def prepare(loader, row):
    game = row['minecraft']
    generated = generate(loader, row)
    project = ROOT / 'build/smoke' / loader / game
    project.mkdir(parents=True, exist_ok=True)
    run = project / ('run-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    run.mkdir(exist_ok=True)
    config = run / 'mcdr-singleplayer/config.json'
    config.parent.mkdir(exist_ok=True)
    write(config, json.dumps({'enabled': True, 'autoStartMcdr': False, 'autoInstall': False, 'token': secrets.token_hex(32), 'port': 25585}))
    write(run / 'options.txt', 'pauseOnLostFocus:false\nrenderDistance:2\nsimulationDistance:2\nmaxFps:30\nlang:en_us\nskipMultiplayerWarning:true\n')
    for name in ('settings.gradle', 'gradle.properties'):
        shutil.copy2(generated / name, project / name)
    artifact = ROOT / 'dist' / f"mcdr-singleplayer-{MATRIX['modVersion']}+{loader}+mc{row['family']}.jar"
    if not artifact.is_file():
        raise FileNotFoundError(artifact)
    text = (ROOT / 'compat/SmokeFixture.java').read_text(encoding='utf8')
    if loader == 'fabric':
        values = {'IMPORTS': 'import net.fabricmc.api.ModInitializer;\nimport net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;',
                  'ANNOTATION': '', 'INTERFACE': 'implements ModInitializer',
                  'REGISTRATION': 'public void onInitialize() { ClientTickEvents.END_CLIENT_TICK.register(this::tick); }'}
        metadata = {'schemaVersion': 1, 'id': 'singleplayer_bridge_gametest', 'version': '1.0.0', 'environment': 'client',
                    'entrypoints': {'main': ['io.github.mcdrsingleplayer.smoke.SmokeFixture']}}
        write(project / 'src/main/resources/fabric.mod.json', json.dumps(metadata))
    else:
        values = {'IMPORTS': 'import net.neoforged.fml.common.Mod;\nimport net.neoforged.api.distmarker.Dist;\nimport net.neoforged.neoforge.common.NeoForge;\nimport net.neoforged.neoforge.client.event.ClientTickEvent;',
                  'ANNOTATION': '@Mod(value="singleplayer_bridge_gametest", dist=Dist.CLIENT)', 'INTERFACE': '',
                  'REGISTRATION': 'public SmokeFixture() { NeoForge.EVENT_BUS.addListener((ClientTickEvent.Post event) -> tick(Minecraft.getInstance())); }'}
        write(project / 'src/main/resources/META-INF/neoforge.mods.toml', 'modLoader="javafml"\nloaderVersion="[1,)"\nlicense="LGPL-3.0-only"\n[[mods]]\nmodId="singleplayer_bridge_gametest"\nversion="1.0.0"\ndisplayName="Isolated smoke fixture"\n')
        mods = run / 'mods'
        mods.mkdir(exist_ok=True)
        shutil.copy2(artifact, mods / artifact.name)
    values.update(GAME=game, LOADER=loader, SCREEN='client.gui.screen()' if game == '26.3' else 'client.screen',
                  OVERLAY='client.gui.overlay()' if game == '26.3' else 'client.getOverlay()')
    if game == '26.3':
        settings = 'new LevelSettings("matrix-smoke", GameType.CREATIVE, new LevelSettings.DifficultySettings(Difficulty.PEACEFUL, false, false), true, WorldDataConfiguration.DEFAULT)'
    else:
        rules = 'new GameRules()' if game == '1.21.1' else 'new net.minecraft.world.level.gamerules.GameRules(net.minecraft.world.flag.FeatureFlags.DEFAULT_FLAGS)'
        settings = f'new LevelSettings("matrix-smoke", GameType.CREATIVE, false, Difficulty.PEACEFUL, true, {rules}, WorldDataConfiguration.DEFAULT)'
    values['SETTINGS'] = settings
    for key, value in values.items():
        text = text.replace('@' + key + '@', value)
    write(project / 'src/main/java/io/github/mcdrsingleplayer/smoke/SmokeFixture.java', text)
    gradle = (generated / 'build.gradle').read_text(encoding='utf8').split("tasks.register('bundleInstaller'")[0]
    if loader == 'fabric':
        gradle += f"\ndependencies {{ {'modImplementation' if row['java'] == 21 else 'implementation'} files('{artifact.as_posix()}') }}\nloom {{ runs {{ client {{ client(); runDir = '{run.as_posix()}' }} }} }}\n"
    else:
        gradle = gradle.replace("layout.buildDirectory.dir('run-client').get().asFile", "file('" + run.as_posix() + "')")
        gradle = gradle.replace('mcdr_singleplayer {', 'singleplayer_bridge_gametest {')
    properties = {'game': run.as_posix(), 'python': Path(sys.executable).as_posix(), 'root': ROOT.as_posix(), 'pb': (ROOT / '.reference/PrimeBackup-v1.13.1.pyz').as_posix()}
    arguments = ', '.join("'-Dmcdr.smoke." + key + '=' + value + "'" for key, value in properties.items())
    if loader == 'fabric':
        gradle += f"loom {{ runs {{ client {{ vmArgs {arguments} }} }} }}\n"
    else:
        for key, value in properties.items():
            gradle += f"neoForge.runs.client.systemProperty('mcdr.smoke.{key}', '{value}')\n"
    write(project / 'build.gradle', gradle)
    return project, run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--loader', choices=['fabric', 'neoforge'], required=True)
    parser.add_argument('--game', choices=['1.21.1', '1.21.11', '26.3'], required=True)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    row = next(r for r in MATRIX['versions'] if r['minecraft'] == args.game)
    project, run = prepare(args.loader, row)
    if args.prepare_only:
        print(project)
        return
    wrapper = ROOT / 'fabric-bridge' / ('gradlew.bat' if os.name == 'nt' else 'gradlew')
    subprocess.run([str(wrapper), '-p', str(project), 'runClient', '--console=plain'], check=True, timeout=1500)
    result = json.loads((run / 'smoke-result.json').read_text())
    if not result['success']:
        raise SystemExit('Smoke test failed: ' + str(result))
    print(result)


if __name__ == '__main__':
    main()
