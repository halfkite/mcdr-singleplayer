# mcdr-singleplayer

[![License](https://img.shields.io/github/license/halfkite/mcdr-singleplayer)](LICENSE)
[![CurseForge](https://img.shields.io/curseforge/dt/1723660?logo=curseforge&label=CurseForge&color=f16436)](https://www.curseforge.com/projects/1723660)
[![Minecraft](https://cf.way2muchnoise.eu/versions/For%20MC_1723660_all.svg)](https://www.curseforge.com/projects/1723660)
[![GitHub downloads](https://img.shields.io/github/downloads/halfkite/mcdr-singleplayer/total?logo=github)](https://github.com/halfkite/mcdr-singleplayer/releases)

[简体中文](README.md) | [繁體中文](README_zh_tw.md) | **English**

[Downloads](https://github.com/halfkite/mcdr-singleplayer/releases) · [CurseForge](https://www.curseforge.com/projects/1723660) · [Issues](https://github.com/halfkite/mcdr-singleplayer/issues) · [MCDReforged](https://mcdreforged.com/) · [Prime Backup](https://mcdreforged.com/en/plugin/prime_backup) · [Chunk Backup](https://mcdreforged.com/en/plugin/chunk_backup)

Connect MCDReforged (MCDR) and existing Python plugins to the integrated server of a Minecraft Java Edition singleplayer world.

Development version: **0.3.10 / Fabric and NeoForge**, supporting 1.21–1.21.11 and 26.1–26.3. Both loaders passed real-client PB backup and restore tests on 1.21.1, 1.21.11 and 26.3. Installing the JAR prepares MCDR 2.16.0 and dependencies in the background, waits at the title screen, and starts the selected world's plugin environment after entering a save. Click to install Prime Backup 1.13.1 or Chunk Backup 2.0.3. See the [compatibility record](docs/0.3.10兼容性与发布.md) for actual builds and gameplay coverage.

**This mod is in early testing. Keep an independent, complete world backup before using backup plugins through it.**

## Dependencies and versions

| Dependency | Requirement |
| --- | --- |
| [Fabric Loader](https://fabricmc.net/use/installer/) | 0.19.5+, with [Fabric API](https://modrinth.com/mod/fabric-api) matching Minecraft |
| [NeoForge](https://neoforged.net/) | Match the Minecraft version |
| Java | Java 21+ for 1.21.x, Java 25+ for 26.x |
| MCDR / Python | Automatically prepared; Python and download mirrors are configurable |

One JAR per loader and family, selecting the explicitly compiled adapter for the running game.

| Family | Included Minecraft versions | Filename |
| --- | --- | --- |
| 1.21.x | 1.21, 1.21.1–1.21.11 | `mcdr-singleplayer-<version>+<fabric/neoforge>+mc1.21.x.jar` |
| 26.x | 26.1, 26.1.1, 26.1.2, 26.2, 26.3 | `mcdr-singleplayer-<version>+<fabric/neoforge>+mc26.x.jar` |

Future versions are not automatically supported.

## Installation and onboarding

Put the JAR for your loader and family into the **client game instance's** `mods/` directory, install Fabric API or NeoForge, and enter a singleplayer save.

- [Startup, profiles, mirrors and configuration imports](docs/自动启动与存档配置.md)
- [Manual installation](docs/安装说明.md) · [Prime Backup integration](docs/PrimeBackup适配.md) · [Chunk Backup integration](docs/ChunkBackup适配.md)

Onboarding explains the data directory, main player level-4 MCDR permission, per-world isolation and cleanup after deleting a save. The full-backup warning appears three times. Missing plugins offer clickable installation buttons; installed plugins skip their installation recommendation. CB also installs candy_tools 1.0.2.

Once PB loads, click to enable PB, enable backups every four hours, enable recommended pruning, or open its official documentation. Automatic backups and pruning require the player's choice and are saved per world. Pruning combines the latest 40 backups, one per day for 30 days, and one per week for 30 weeks; 40 is not a total backup cap. Dismissal applies to the whole instance; `/!!spbridge onboarding show` displays onboarding again.

## Commands and features

Use `/!!` for loaded MCDR plugins' commands, aliases, subcommands, arguments and Tab completion. Plugin loading, unloading and reloading refresh the command tree. `/mcdr_setup recommend` applies recommended configuration and shows options.

```text
/!!MCDR                                      MCDR administration
/!!pb make                                   Incremental full-world backup
/!!cb make                                   Region backup at the player's position
/!!spbridge onboarding show                  Show onboarding and clickable options
/!!spbridge profile list                     List world profiles
/!!spbridge profile import "another folder"   Import missing configuration
```

Add `--replace` to replace imported configuration while preserving previous files; other saves' backup databases and plugin runtime state are not imported.

- Forward chat, joins/leaves, world lifecycle, commands and feedback; use loopback-only connections, random-token authentication and session/path checks, without replaying side-effecting commands after disconnection.
- The main player receives MCDR level 4 (`owner`); individual plugins retain their own permission checks. Preserve singleplayer pause behavior and reject world-changing commands while paused.
- PB confirms saving before backup; restoration saves and exits first, releases the world lock and verifies files. The title screen shows actual stages and blocks the target save until success. Failure or interruption after modifying files retains the entry lock.
- CB supports position backups, restoration and undo using the same progress UI and entry lock. Positions come directly from the integrated server rather than localized command output.
- PB / CB backup and restore tasks are mutually exclusive; the controller waits for active tasks when switching saves.
- Restore UI uses vanilla backgrounds, fonts, buttons and loading animation, following resource packs without fabricated percentages.

Plugins depending on dedicated-server logs, native RCON, standalone-process restart or fixed absolute paths may require additional adaptation.

## Configuration, language and icon

All active configuration lives in the game instance's `mcdr-singleplayer/`, separated by **save folder name**, preserving native relative plugin paths.

```text
mcdr-singleplayer/
├─ config.json               Mod settings and onboarding preference
├─ config.yml                Shared MCDR configuration
├─ permission.yml            Shared permissions
├─ plugins/                  Shared plugins
├─ date/<save folder>/
│  ├─ config/                World-specific plugin configuration
│  ├─ pb_files/              Native PB database and backup files
│  └─ cb_files/              Native CB backups
├─ log/                      Installer, controller and world logs
└─ runtime/                  Python, MCDR, bridge and restore state
```

Switching saves changes the working directory and process; upgrades migrate the old layout and preserve backups. After permanently deleting a save, manually remove its matching `date/` profile if desired. Custom absolute paths require manual adjustment and are not automatically isolated.

Simplified Chinese (`zh_cn`), Traditional Chinese (`zh_tw`) and English (`en_us`) follow the client language, with English fallback. Mod prompts, buttons, command feedback, checks and restore UI use language files. Sentence full stops are removed from prompts; paths and version-number dots remain. Canonical JSON lives in `python/singleplayer_bridge/lang/` and is packaged in both Python and Minecraft resources. The mod uses the provided 128×128 PNG icon. See [language and icon tests](docs/0.3.9语言与图标测试记录.md).

## Building and publishing

Build with Python 3.10+ and JDK 25 for Gradle; NeoForge 1.21.x also uses a JDK 21 toolchain.

```text
python scripts/build_matrix.py --loader fabric --family 1.21.x
python scripts/build_matrix.py --loader fabric --family 26.x
python scripts/build_matrix.py --loader neoforge --family 1.21.x
python scripts/build_matrix.py --loader neoforge --family 26.x
```

Outputs go to `dist/`; every successful build is archived under `mod-builds/<timestamp>/` with SHA-256 metadata.

Publishing follows the [RankBoard](https://github.com/halfkite/rankboard) structure. After publishing a GitHub Release, separate Fabric and NeoForge workflows build both families and upload to GitHub and CurseForge project `1723660`. Store the token as repository Secret `CURSEFORGE_TOKEN`, never in source code. Manual re-publication of an existing Release is supported; see the [publishing guide](docs/发布流程.md).

## License

[LGPL-3.0-only](LICENSE), Copyright (C) 2026 MCDR Singleplayer contributors.
