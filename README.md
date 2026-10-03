# mcdr-singleplayer

[![License](https://img.shields.io/github/license/halfkite/mcdr-singleplayer)](LICENSE)
[![CurseForge downloads](https://img.shields.io/curseforge/dt/1723660?logo=curseforge&label=CurseForge&color=f16436)](https://www.curseforge.com/projects/1723660)
[![Minecraft versions](https://cf.way2muchnoise.eu/versions/For%20MC_1723660_all.svg)](https://www.curseforge.com/projects/1723660)
[![GitHub downloads](https://img.shields.io/github/downloads/halfkite/mcdr-singleplayer/total?logo=github)](https://github.com/halfkite/mcdr-singleplayer/releases)

**简体中文** | [繁體中文](README_zh_tw.md) | [English](README_en.md)

[问题反馈](https://github.com/halfkite/mcdr-singleplayer/issues) | [MCDReforged](https://mcdreforged.com/zh-CN/) | [Prime Backup](https://mcdreforged.com/zh-CN/plugin/prime_backup) | [Chunk Backup](https://mcdreforged.com/zh-CN/plugin/chunk_backup)

MCDR是用于控制 Minecraft 服务器的一个 Python 工具 [MCDReforged](https://mcdreforged.com/zh-CN/) <br>

**本模组处于初步测试阶段，使用备份插件前务必保留一份其他方式制作的完整存档备份！！！！！**<br>
**本模组处于初步测试阶段，使用备份插件前务必保留一份其他方式制作的完整存档备份！！！！！**<br>
**本模组处于初步测试阶段，使用备份插件前务必保留一份其他方式制作的完整存档备份！！！！！**<br>

## 依赖与版本支持

支持 1.21–26.3 Fabric 与 NeoForge

| 加载器 / 依赖 | 要求 |
| --- | --- |
| [Fabric Loader](https://fabricmc.net/use/installer/) | 0.19.5+，同时安装与游戏版本一致的  [Fabric API](https://modrinth.com/mod/fabric-api) |
| [NeoForge](https://neoforged.net/) | 安装目标 Minecraft 版本的 NeoForge |
| [MCDR](https://mcdreforged.com/zh-CN/)  | python下载后模组自动安装MCDR |
| python| 需要 Python 3.10 或更新版本及 pip|

模组不会自动下载或安装 Python；如果未检测到 Python，进入单人世界后会显示安装提示。安装并检测到 Python 后，模组会继续准备 MCDR。


## 安装与首次启动

将对应加载器和版本系列的 JAR 放入**客户端游戏实例**的 `mods/` 文件夹，然后启动游戏并进入单人存档。Fabric 还需要 Fabric API。

- [自动启动、存档配置与配置导入](docs/自动启动与存档配置.md)
- [手动安装说明](docs/安装说明.md)
- [Prime Backup 适配](docs/PrimeBackup适配.md)
- [Chunk Backup 适配](docs/ChunkBackup适配.md)

MCDR 启动后，聊天栏会提示主玩家的四级权限和可选备份插件。可以按提示安装 Prime Backup 或 Chunk Backup；安装 Prime Backup 后，还可以选择是否启用备份、每 4 小时自动备份以及推荐的自动清理策略。

## 功能

- 将游戏聊天、玩家加入与退出、世界启动与关闭转发给 MCDR 插件，并传递命令和反馈
- 将已加载 MCDR 插件的根命令、别名、子命令、参数和补全注册为客户端 `/!!` 命令；插件加载、卸载或重载后同步更新
- 按存档文件夹名隔离插件配置、插件数据和备份，切换存档时启动对应的 MCDR 环境
- 为 Prime Backup 与 Chunk Backup 提供单人世界适配；回档时显示处理阶段，并在回档完成前阻止打开目标存档
- 支持简体中文、繁體中文与 English，界面语言跟随客户端

## 数据目录

模组和 MCDR 的共用文件放在游戏实例的 `mcdr-singleplayer/`；每个存档的数据放在 `date/<存档文件夹名>/`

```text
mcdr-singleplayer/
├─ mcdr-singleplayer-config.yml  本模组配置，包含字段备注
├─ config.yml                    共用 MCDR 配置
├─ permission.yml                共用玩家权限
├─ plugins/                      共用 MCDR 插件
├─ date/
│  └─ <存档文件夹名>/
│     ├─ config/<插件 ID>/       插件配置及部分插件数据
│     ├─ pb_files/               Prime Backup 数据与备份
│     └─ cb_files/               Chunk Backup 区域备份
├─ log/                          安装、控制器及 MCDR 日志
└─ runtime/                      Python、MCDR 与桥接运行环境
```

彻底删除存档后，如需清理其插件数据，可删除对应的 `mcdr-singleplayer/date/<存档文件夹名>/`。使用固定绝对路径的第三方插件可能需要单独调整配置

## 许可证

本项目采用 [GNU Lesser General Public License v3.0](LICENSE)
