# mcdr-singleplayer

让 MCDReforged 和已有 Python 插件连接 Minecraft Java 版单人内置服务端。

当前版本 **0.3.5 / Minecraft 26.3 正式版 / Fabric**。游戏端需要 Fabric Loader 0.19.5、Fabric API 0.161.0+26.3 和 Java 25。安装桥接 JAR 后自动准备 MCDR 2.16.0、Prime Backup 1.13.1 与依赖，在主菜单等待，进入世界后加载对应存档的插件环境。

## 安装与使用

使用完整安装包，或单独将 `mcdr-singleplayer-0.3.5.jar` 放进游戏实例的 `mods`，并安装对应 Fabric API。

- [自动启动、存档配置、镜像与配置导入](docs/自动启动与存档配置.md)
- [手动安装流程](docs/安装说明.md)
- [Prime Backup 适配与回档](docs/PrimeBackup适配.md)

所有运行配置集中在游戏实例的 `mcdr-singleplayer/`：共用配置、插件和运行时文件位于 `runtime/`，日志位于 `log/`，各存档配置与数据按存档文件夹名位于 `date/<存档文件夹名>/`。切换存档自动切换工作目录与进程。升级时迁移旧模组配置，并导入旧存档分类和备份。

进入世界后，单人主玩家自动获得 MCDR `owner`，PB 默认启用，语言跟随客户端。左下角聊天分别提示是否开启备份、自动备份、自动删除，可点击开启或关闭：备份间隔 4 小时；清理保留最近 40 份、每日 1 份保留 30 天、每周 1 份保留 30 周。选择按存档保存。

所有已加载 MCDR 插件的根命令、别名、子指令和参数均注册为客户端斜杠命令，使用 `/!!` 开头输入并按 Tab 补全；加载、卸载和重载插件自动刷新。`/mcdr_setup recommend` 可再次应用推荐配置并显示选项。

配置导入示例：`/!!spbridge profile import "其他存档文件夹名" --replace`。默认只补齐缺少的配置；显式替换会备份当前文件，不复制备份数据库与插件状态。

## 已有能力

- 转接聊天、玩家加入/退出、世界启动/关闭，让 MCDR 派发原生插件事件。
- 转发游戏命令与反馈；MCDR start/stop/kill 管理代理连接。
- 随机令牌鉴权、回环连接、世界会话与路径校验；断线不重放。
- 保留单人暂停，暂停时拒绝修改世界的命令。
- Prime Backup 确认保存后备份，回档前保存并退出、释放世界锁、验证文件。回档完成后重新进入世界，自动启动对应 MCDR。
- 回档期间在主菜单显示实际阶段，目标存档完成前不能进入；恢复文件后发生失败或进程中断时继续锁定，成功离线重新回档后解除。
- 回档画面复用原版菜单背景、字体、等待动画和灰色按钮，跟随资源包；回档期间隐藏主菜单标志与闪烁标语。
- 控制器等待正在执行的 Prime Backup 任务完成后退出，避免切换进程打断回档。

其他插件的固定绝对数据路径、原生 RCON、专用服务端日志格式或进程重启语义仍需适配。MCDR 插件的相对配置与数据路径按存档隔离；自定义绝对路径需要自行修改。

## 构建与验证

源码位于 `fabric-bridge/`、`python/singleplayer_bridge/` 与 `prime-backup-adapter/`。

构建命令：`scripts/build.ps1`。它执行 Python 测试、真实 Gradle 构建、MCDR 打包并归档到独立时间戳的 `mod-builds/`。

真实客户端测试命令：`fabric-bridge/gradlew.bat -p fabric-bridge runClientGameTest --console=plain`。设置 `MCDR_BRIDGE_TEST_PYTHON`、`MCDR_BRIDGE_TEST_ROOT`、`MCDR_BRIDGE_TEST_PRIME_BACKUP` 与 `MCDR_BRIDGE_TEST_AUTO_COMMON`，可验证真实 MCDR、官方备份插件及自动启动流程。自动安装测试使用 Gradle 的隔离游戏目录，`MCDR_BRIDGE_TEST_AUTO_COMMON` 作为启用标记；实际测试数据写入该游戏目录的 `mcdr-singleplayer/`。

MCDR 原生补全目前使用 2.16 的内部建议接口，因此兼容通道固定这一版本。仅实现并验证 26.3 Fabric。

## 许可证

本项目代码采用 [GNU Lesser General Public License v3.0](LICENSE)，与 [MCDReforged](https://github.com/MCDReforged/MCDReforged) 使用的许可证一致。Copyright (C) 2026 MCDR Singleplayer contributors。
