# mcdr-singleplayer

[![License](https://img.shields.io/github/license/halfkite/mcdr-singleplayer)](LICENSE)
[![CurseForge downloads](https://img.shields.io/curseforge/dt/1723660?logo=curseforge&label=CurseForge&color=f16436)](https://www.curseforge.com/projects/1723660)
[![Minecraft versions](https://cf.way2muchnoise.eu/versions/For%20MC_1723660_all.svg)](https://www.curseforge.com/projects/1723660)
[![GitHub downloads](https://img.shields.io/github/downloads/halfkite/mcdr-singleplayer/total?logo=github)](https://github.com/halfkite/mcdr-singleplayer/releases)

**简体中文** | [繁體中文](https://github.com/halfkite/mcdr-singleplayer/blob/main/README_zh_tw.md) | [English](https://github.com/halfkite/mcdr-singleplayer/blob/main/README_en.md)

[问题反馈](https://github.com/halfkite/mcdr-singleplayer/issues) | [MCDReforged](https://mcdreforged.com/zh-CN/) | [Prime Backup](https://mcdreforged.com/zh-CN/plugin/prime_backup) | [Chunk Backup](https://mcdreforged.com/zh-CN/plugin/chunk_backup)

MCDR是用于控制 Minecraft 服务器的一个 Python 工具 [MCDReforged](https://mcdreforged.com/zh-CN/) <br>

**本模组处于初步测试阶段，使用备份插件前务必保留一份其他方式制作的完整存档备份！！！！！**<br>
**本模组处于初步测试阶段，使用备份插件前务必保留一份其他方式制作的完整存档备份！！！！！**<br>
**本模组处于初步测试阶段，使用备份插件前务必保留一份其他方式制作的完整存档备份！！！！！**<br>

## 依赖与版本支持

支持 1.21–26.3 Fabric 与 NeoForge

| 加载器 / 依赖 | 要求 |
| --- | --- |
| [Fabric Loader](https://fabricmc.net/use/installer/) | 本模组最低要求 0.15.11+，同时安装与游戏版本一致的 [Fabric API](https://modrinth.com/mod/fabric-api)，如果 Fabric API 要求更高版本则以其要求为准 |
| [NeoForge](https://neoforged.net/) | 1.21.x 声明最低 21.0+，26.x 声明最低 26.1+，需安装与目标 Minecraft 版本匹配的 NeoForge |
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

进入存档时，若 MCDR 尚未准备完成，会显示带模组名称的进度窗口，可用关闭按钮或 Esc 关闭，安装仍在后台继续。聊天栏同步提示实际安装阶段、下载源切换、就绪或失败状态，长时间等待时每 20 秒提醒一次。

## 功能

- 将游戏聊天、玩家加入与退出、世界启动与关闭转发给 MCDR 插件，并传递命令和反馈
- 兼容 `1`、`ab` 等一至两个字符的 Carpet 假人名称，避免短名称中断整个桥接连接
- 将已加载 MCDR 插件的根命令、别名、子命令、参数和补全注册为客户端 `/!!` 命令；插件加载、卸载或重载后同步更新
- 按存档文件夹名隔离插件配置、插件数据和备份，切换存档时启动对应的 MCDR 环境
- 为 Prime Backup 与 Chunk Backup 提供单人世界适配；回档时显示处理阶段，并在回档完成前阻止打开目标存档
- 回档前检查 Windows 文件占用，持续占用时显示具体文件并停止；修复 Syncmatica 0.3.20 配置读取后未关闭文件的问题
- 适配 Conflux Map 0.1.6，将原生库缓存存放到存档外并按游戏进程隔离，避免多开时 DLL 阻止回档
- 支持简体中文、繁體中文与 English，界面语言跟随客户端
- 同目录多开时，各客户端的临时会话独立保存，局域网访客不会中断主机的 MCDR；访客也可使用主机提供的 `/!!` 指令及 Tab 补全，按各自的 MCDR 权限执行

共用目录同一时刻只控制一个单人世界；同时打开其他单人存档时会等待共用目录释放，切换期间也会等待备份或回档任务完成。单纯加入局域网世界不会占用该控制器

## 数据目录

模组和 MCDR 的共用文件放在游戏实例的 `mcdr-singleplayer/`；每个存档的数据放在 `plugindata/<存档文件夹名>/`。从旧版本升级时，旧 `date/` 会自动迁移到 `plugindata/`

```text
mcdr-singleplayer/
├─ mcdr-singleplayer-config.yml  本模组配置，包含字段备注
├─ config.yml                    共用 MCDR 配置
├─ permission.yml                共用玩家权限
├─ plugins/                      共用 MCDR 插件
├─ plugindata/
│  └─ <存档文件夹名>/
│     ├─ config/<插件 ID>/       插件配置及部分插件数据
│     ├─ pb_files/               Prime Backup 数据与备份
│     └─ cb_files/               Chunk Backup 区域备份
├─ log/                          安装、控制器及 MCDR 日志
└─ runtime/                      Python、MCDR 与桥接运行环境
```

彻底删除存档后，如需清理其插件数据，可删除对应的 `mcdr-singleplayer/plugindata/<存档文件夹名>/`。使用固定绝对路径的第三方插件可能需要单独调整配置

## 许可证

本项目采用 [GNU Lesser General Public License v3.0](LICENSE)
