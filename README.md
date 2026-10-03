# mcdr-singleplayer

[![License](https://img.shields.io/github/license/halfkite/mcdr-singleplayer)](LICENSE)
[![CurseForge](https://img.shields.io/curseforge/dt/1723660?logo=curseforge&label=CurseForge&color=f16436)](https://www.curseforge.com/projects/1723660)
[![Minecraft](https://cf.way2muchnoise.eu/versions/For%20MC_1723660_all.svg)](https://www.curseforge.com/projects/1723660)
[![GitHub downloads](https://img.shields.io/github/downloads/halfkite/mcdr-singleplayer/total?logo=github)](https://github.com/halfkite/mcdr-singleplayer/releases)

**简体中文** | [繁體中文](README_zh_tw.md) | [English](README_en.md)

[GitHub 下载](https://github.com/halfkite/mcdr-singleplayer/releases) · [CurseForge](https://www.curseforge.com/projects/1723660) · [问题反馈](https://github.com/halfkite/mcdr-singleplayer/issues) · [MCDReforged](https://mcdreforged.com/zh-CN/) · [Prime Backup](https://mcdreforged.com/zh-CN/plugin/prime_backup) · [Chunk Backup](https://mcdreforged.com/zh-CN/plugin/chunk_backup)

让 MCDReforged 和已有 Python 插件连接 Minecraft Java 版单人内置服务端。

开发版本 **0.3.10 / Fabric 与 NeoForge**，支持 1.21–1.21.11 与 26.1–26.3，已在 1.21.1、1.21.11、26.3 的两种加载器上通过 PB 备份与回档测试。安装桥接 JAR 后自动准备 MCDR 2.16.0 与运行依赖，在主菜单等待；进入世界后加载对应存档的插件环境，可点击安装 Prime Backup 1.13.1 或 Chunk Backup 2.0.3。实际构建与游戏测试范围见[兼容性记录](docs/0.3.10兼容性与发布.md)。

**本模组处于初步测试阶段，使用备份插件前务必保留一份其他方式制作的完整存档备份。**

## 依赖与版本支持

| 加载器 / 依赖 | 要求 |
| --- | --- |
| [Fabric Loader](https://fabricmc.net/use/installer/) | 0.19.5+，同时安装与游戏版本一致的 [Fabric API](https://modrinth.com/mod/fabric-api) |
| [NeoForge](https://neoforged.net/) | 安装目标 Minecraft 版本的 NeoForge |
| Java | 1.21.x 使用 Java 21+，26.x 使用 Java 25+ |
| MCDR / Python | 模组自动准备，可自定义 Python 和下载镜像 |

每个加载器发行两个系列 JAR，游戏端按实际版本选择包内对应的适配实现。

| 系列 | 明确包含的游戏版本 | 文件命名 |
| --- | --- | --- |
| 1.21.x | 1.21、1.21.1–1.21.11 | `mcdr-singleplayer-<版本>+<fabric/neoforge>+mc1.21.x.jar` |
| 26.x | 26.1、26.1.1、26.1.2、26.2、26.3 | `mcdr-singleplayer-<版本>+<fabric/neoforge>+mc26.x.jar` |

系列包仅声明明确适配的版本，不自动承诺未来版本。

## 安装与使用

将对应加载器、版本系列的 JAR 放进**客户端游戏实例**的 `mods`，安装对应 Fabric API 或 NeoForge，然后进入单人存档。

- [自动启动、存档配置、镜像与配置导入](docs/自动启动与存档配置.md)
- [手动安装流程](docs/安装说明.md)
- [Prime Backup 适配与回档](docs/PrimeBackup适配.md)
- [Chunk Backup 回档等待适配](docs/ChunkBackup适配.md)

所有运行配置集中在游戏实例的 `mcdr-singleplayer/`：共用配置和 `plugins/` 直接位于根目录，运行环境位于 `runtime/`，日志位于 `log/`，各存档配置与数据按存档文件夹名位于 `date/<存档文件夹名>/`，保留插件原生相对路径，PB 使用 `pb_files/`，CB 使用 `cb_files/`。切换存档自动切换工作目录与进程。升级时迁移旧模组配置，并导入旧存档分类和备份。

首次进入世界，聊天提示数据目录、主玩家 MCDR 最高权限（4）、按存档隔离的数据与配置，以及删除存档后的清理位置；测试阶段完整备份警告重复三次。未安装的 PB / CB 显示可点击的安装按钮，CB 同时安装 candy_tools 1.0.2。已有插件跳过其安装推荐。PB 已加载或刚安装后显示 `[开启Prime Backup]`、`[启用4小时定时备份]`、`[启用推荐的自动删除]` 和官方文档链接。清理保留最近 40 份、每日 1 份保留 30 天、每周 1 份保留 30 周。设置按存档保存；`[忽略且不再主动提示]` 对整个游戏实例生效，可用 `/!!spbridge onboarding show` 主动查看。

所有已加载 MCDR 插件的根命令、别名、子指令和参数均注册为客户端斜杠命令，使用 `/!!` 开头输入并按 Tab 补全；加载、卸载和重载插件自动刷新。`/mcdr_setup recommend` 可再次应用推荐配置并显示选项。

配置导入示例：`/!!spbridge profile import "其他存档文件夹名" --replace`。默认只补齐缺少的配置；显式替换会备份当前文件，不复制备份数据库与插件状态。

## 语言与图标

支持简体中文（`zh_cn`）、繁体中文（`zh_tw`）和英文（`en_us`），按单人客户端语言选择，缺少译文时回退英文。首次提示、按钮、命令反馈、模组校验错误和回档界面均从语言文件读取；提示去掉句号，路径和版本号中的点保留。

统一语言源文件位于 `python/singleplayer_bridge/lang/<语言代码>.json`。构建时同时打入 Python 插件和 JAR 的 `assets/mcdr-singleplayer/lang/`，新增语言可添加同键的 JSON 文件。游戏端回档 UI 使用 Minecraft 原生翻译组件。语言文件属于资源，不改变现有配置目录。

模组图标为用户提供的 128×128 PNG，位于 `fabric-bridge/src/main/resources/assets/mcdr-singleplayer/icon.png`，两种加载器元数据均声明图标路径。

## 已有能力

- 转接聊天、玩家加入/退出、世界启动/关闭，让 MCDR 派发原生插件事件。
- 转发游戏命令与反馈；MCDR start/stop/kill 管理代理连接。
- 随机令牌鉴权、回环连接、世界会话与路径校验；断线不重放。
- 保留单人暂停，暂停时拒绝修改世界的命令。
- Prime Backup 确认保存后备份，回档前保存并退出、释放世界锁、验证文件。回档完成后重新进入世界，自动启动对应 MCDR。
- 回档期间在主菜单显示实际阶段，目标存档完成前不能进入；恢复文件后发生失败或进程中断时继续锁定，成功离线重新回档后解除。
- 回档画面复用原版菜单背景、字体、等待动画和灰色按钮，跟随资源包；回档期间隐藏主菜单标志与闪烁标语。
- 控制器等待正在执行的 Prime Backup 任务完成后退出，避免切换进程打断回档。
- 可选 Chunk Backup 2.0.3 适配器接入同一回档界面与存档入口锁，支持回档和撤销回档；控制器等待其任务完成，PB 与 CB 的备份 / 回档互斥。
- Chunk Backup 的 `make` 直接查询单人服务端玩家坐标和维度，兼容中文客户端等不同命令输出，不再依赖英文 NBT 输出正则。

其他插件的固定绝对数据路径、原生 RCON、专用服务端日志格式或进程重启语义仍需适配。MCDR 插件的相对配置与数据路径按存档隔离；自定义绝对路径需要自行修改。


## 构建与自动发布

构建需要 Python 3.10+、JDK 25（Gradle），NeoForge 1.21.x 还使用 JDK 21 工具链。

```text
python scripts/build_matrix.py --loader fabric --family 1.21.x
python scripts/build_matrix.py --loader fabric --family 26.x
python scripts/build_matrix.py --loader neoforge --family 1.21.x
python scripts/build_matrix.py --loader neoforge --family 26.x
```

产物位于 `dist/`，每次成功构建独立归档到 `mod-builds/<时间戳>/` 并记录 SHA-256。

发布结构参考 [RankBoard](https://github.com/halfkite/rankboard)。发布 GitHub Release 后，Fabric 与 NeoForge 独立工作流构建两个系列并上传 GitHub、CurseForge 项目 `1723660`。密钥使用仓库 Secret `CURSEFORGE_TOKEN`，不写入源码；支持手动重新发布已有 Release，详见[发布流程](docs/发布流程.md)。

## 许可证

本项目代码采用 [GNU Lesser General Public License v3.0](LICENSE)，与 [MCDReforged](https://github.com/MCDReforged/MCDReforged) 使用的许可证一致。Copyright (C) 2026 MCDR Singleplayer contributors。

设置 `MCDR_BRIDGE_TEST_PREINSTALLED=1` 可在自动启动测试中预装官方 PB、CB 与 candy_tools，验证跳过安装推荐的分支；不设置则验证首次点击下载安装。测试仍只使用 Gradle 的隔离游戏目录。
