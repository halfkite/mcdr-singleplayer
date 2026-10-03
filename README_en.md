# mcdr-singleplayer

[![License](https://img.shields.io/github/license/halfkite/mcdr-singleplayer)](LICENSE)
[![CurseForge downloads](https://img.shields.io/curseforge/dt/1723660?logo=curseforge&label=CurseForge&color=f16436)](https://www.curseforge.com/projects/1723660)
[![Minecraft versions](https://cf.way2muchnoise.eu/versions/For%20MC_1723660_all.svg)](https://www.curseforge.com/projects/1723660)
[![GitHub downloads](https://img.shields.io/github/downloads/halfkite/mcdr-singleplayer/total?logo=github)](https://github.com/halfkite/mcdr-singleplayer/releases)

[简体中文](README.md) | [繁體中文](README_zh_tw.md) | **English**

[Issues](https://github.com/halfkite/mcdr-singleplayer/issues) | [MCDReforged](https://mcdreforged.com/) | [Prime Backup](https://mcdreforged.com/en/plugin/prime_backup) | [Chunk Backup](https://mcdreforged.com/en/plugin/chunk_backup)

MCDR is a Python tool for controlling Minecraft servers. See [MCDReforged](https://mcdreforged.com/).<br>

**This mod is in early testing. Before using backup plugins, make a complete backup of your save using another method!!!!!**<br>
**This mod is in early testing. Before using backup plugins, make a complete backup of your save using another method!!!!!**<br>
**This mod is in early testing. Before using backup plugins, make a complete backup of your save using another method!!!!!**<br>

## Requirements and Version Support

Supports Fabric and NeoForge on Minecraft 1.21–26.3.

| Loader / dependency | Requirement |
| --- | --- |
| [Fabric Loader](https://fabricmc.net/use/installer/) | This mod requires 0.15.11 or later; also install the [Fabric API](https://modrinth.com/mod/fabric-api) matching your Minecraft version and meet its higher Loader requirement if applicable |
| [NeoForge](https://neoforged.net/) | Declared minimum: 21.0+ for 1.21.x, 26.1+ for 26.x; install NeoForge matching your Minecraft version |
| [MCDR](https://mcdreforged.com/) | After Python is installed, the mod installs MCDR automatically |
| Python | Python 3.10 or later and pip |

The mod does not download or install Python. If Python is not detected, an installation prompt appears after you enter a singleplayer world. Once Python is installed and detected, the mod continues setting up MCDR.

## Installation and First Launch

Place the JAR for your loader and Minecraft version series in the `mods/` folder of your **client game instance**, then launch the game and enter a singleplayer world. Fabric also requires Fabric API.

- [Automatic startup, save profiles, and configuration import](docs/自动启动与存档配置.md)
- [Manual installation](docs/安装说明.md)
- [Prime Backup compatibility](docs/PrimeBackup适配.md)
- [Chunk Backup compatibility](docs/ChunkBackup适配.md)

After MCDR starts, chat explains that the main player has MCDR permission level 4 and offers optional backup plugins. Follow the prompts to install Prime Backup or Chunk Backup. After installing Prime Backup, you can choose whether to enable backups, schedule one every 4 hours, and apply the recommended automatic cleanup settings.

## Features

- Forward in-game chat, player join and leave events, and world start and stop events to MCDR plugins; relay commands and their responses
- Register loaded MCDR plugin root commands, aliases, subcommands, arguments, and suggestions as client-side `/!!` commands; update them when plugins are loaded, unloaded, or reloaded
- Isolate plugin configuration, plugin data, and backups by save-folder name, and start the matching MCDR environment when switching saves
- Adapt Prime Backup and Chunk Backup for singleplayer; show restore progress and prevent opening the target save until restoration is complete
- Support Simplified Chinese, Traditional Chinese, and English, following the client language

## Data Directory

Shared mod and MCDR files are stored in the game instance's `mcdr-singleplayer/` directory. Each save's data is stored under `date/<save folder name>/`.

```text
mcdr-singleplayer/
├─ mcdr-singleplayer-config.yml  Mod configuration with field comments
├─ config.yml                    Shared MCDR configuration
├─ permission.yml                Shared player permissions
├─ plugins/                      Shared MCDR plugins
├─ date/
│  └─ <save folder name>/
│     ├─ config/<plugin ID>/     Plugin configuration and some plugin data
│     ├─ pb_files/               Prime Backup data and backups
│     └─ cb_files/               Chunk Backup region backups
├─ log/                          Installer, controller, and MCDR logs
└─ runtime/                      Python, MCDR, and bridge runtime
```

After permanently deleting a save, you can remove its `mcdr-singleplayer/date/<save folder name>/` directory to delete its plugin data as well. Third-party plugins that use fixed absolute paths may need their configuration adjusted.

## License

This project is licensed under the [GNU Lesser General Public License v3.0](LICENSE).
