> 0.3.9 首次进入存档后可点击安装 Prime Backup 1.13.1；已有 PB 跳过安装推荐。安装成功或 PB 已加载时，显示备份总开关、4 小时自动备份、自动清理和官方文档按钮，主玩家自动获得 owner 权限。主菜单显示回档阶段，完成前不能进入目标存档；重新进入时自动连接。详情见 [自动启动与存档配置](自动启动与存档配置.md)。下文的手工绑定步骤用于关闭自动启动后的手动模式。

# Prime Backup 1.13.1：26.3 Fabric 单人适配

使用桥接 0.3.9 和独立的 `singleplayer_prime_backup` 适配插件。Prime Backup 使用官方原版 **1.13.1**，无需改动其 `.pyz`。适配插件严格绑定一个存档，并接管 Prime Backup 的备份创建和回档任务；其他插件的 MCDR `stop` 仍只断开桥接。

官方插件：[Prime Backup](https://mcdreforged.com/zh-CN/plugin/prime_backup)。官方配置说明：[快速上手](https://tisunion.github.io/PrimeBackup/zh/quick_start/)。

## 安装

1. 按本包的《安装说明》升级游戏端 JAR、MCDR 插件和 `bridge-runtime`，三者都使用 **0.3.9**。旧版 JAR/桥接插件应移出 mods/plugins，避免重复 ID。
2. 从 [官方发布页](https://github.com/TISUnion/PrimeBackup/releases/tag/v1.13.1) 下载 `PrimeBackup-v1.13.1.pyz`，放入 MCDR 的 `plugins`。本包不重新分发 Prime Backup。
3. 关闭 MCDR，使用运行 MCDR 的同一个 Python 安装依赖，并绑定现有单人存档：

```powershell
python -m pip install -r .\requirements-prime-backup.txt
python .\setup_prime_backup.py --mcdr-dir 'D:\Minecraft\实例目录\mcdr-singleplayer' --world-dir 'D:\Minecraft\实例目录\saves\你的存档目录'
```

在解压完整安装包的目录执行以上命令。存档目录需包含 `level.dat`。脚本复制适配插件到 MCDR 的 `plugins`，配置 Prime Backup 的 `source_root` 和 `targets`，并启用 `save-off / save-all flush / save-on`；已有 Prime Backup 配置会先按时间保存副本。配置保存在 `mcdr-singleplayer/plugindata/<存档文件夹名>/config/prime_backup/config.json`，备份存储必须在该分类目录中。MCDR 共用设置与插件位于 `mcdr-singleplayer/`。其他配置项保持原值；升级时旧 `date/` 会自动合并迁移到 `plugindata/`。

共用 MCDR 目录必须是所属游戏实例的 `mcdr-singleplayer/`；手动启动使用《安装说明》生成的脚本，工作目录是 `plugindata/<存档文件夹名>/`。

不要给同一个备份数据库混入不同存档。已有数据库如果来自其他世界，建议先保留原数据库，给本世界设置独立的 `storage_root`。适配器会拒绝 `targets` 不同的回档，但相同目录名本身不能证明两个历史存档是同一个世界。

启动 MCDR 并进入绑定的单人世界。日志应出现 `Prime Backup 1.13.1 singleplayer adapter ready` 和 `Singleplayer world ready`。聊天中的备份管理权限沿用 Prime Backup 和 MCDR 的权限设置。

## 使用

| 操作 | 指令或步骤 |
| --- | --- |
| 创建在线备份 | 游戏聊天 `!!pb make 测试备份`，先恢复游戏，保持世界运行直到完成 |
| 查看备份 | `!!pb list`、`!!pb show 1` |
| 导出备份 | `!!pb export 1 zip`，输出在备份存储目录的 `export` |
| 回档 | `!!pb back 1`，然后按 Prime Backup 提示用 `!!pb confirm` 确认 |
| 回档后继续玩 | 等 MCDR 控制台显示回档完成，再从单人列表进入同一世界，执行 `!!MCDR server start` 重新连接 |

在线创建备份会等待游戏确认保存并完成 flush，再由原版 Prime Backup 创建备份。保存失败或暂停时不会创建备份。桥接断开后会恢复由桥接禁用的自动保存设置。

在线回档沿用 Prime Backup 的确认、倒计时、回档前临时备份和完整性校验。倒计时后游戏自动执行“保存并退出”，回到标题画面；适配器等待世界关闭事件、代理结束，并确认 `session.lock` 已释放，再让 Prime Backup 恢复文件。标题画面显示真实回档阶段，并阻止提前进入目标存档。显示完成后点击“返回主菜单”，手动进入原世界。文件恢复中途失败时保持目标入口锁定，成功离线重新回档后才解除；详见《自动启动与存档配置》。

世界已经关闭时，可在 MCDR 控制台执行回档。仅断开桥接但仍在游戏世界内时，`session.lock` 检查会阻止离线备份和回档。原版 Prime Backup 未配合适配插件时，不可直接对运行中的单人存档执行 `!!pb back`。

0.5.0 在恢复文件前额外检查 Windows 文件是否可以替换，最多等待 10 秒，并在回档界面显示等待阶段。占用未解除时显示具体文件，停止回档，不改写原存档；Prime Backup 移走原世界时只允许原子重命名，避免重命名失败后退回复制并删除而留下不完整存档。文件恢复开始后的失败仍会锁定目标入口。

针对 Syncmatica 0.3.20，模组会关闭其读取配置时遗留的文件流。升级前已经打开的流需要完全退出所有 Minecraft 客户端后才能可靠释放。其他程序的占用仍需自行解除。

Windows 资源管理器打开存档内的子文件夹时，即使文件检查通过，也可能阻止移动整个存档。适配器会重试目录重命名最多 10 秒，并提示关闭查看该存档及其子文件夹的资源管理器窗口和其他占用程序。如果目录始终未能移动，原存档不变，失败状态不会永久锁定它；如果移动已经成功，后续失败仍按已改写存档处理。

Conflux Map 0.1.6 会从存档目录加载原生预测库，Windows 下已加载的 DLL 可能直到游戏进程退出才释放。0.5.0 将它的原生库提取目录转接到 `mcdr-singleplayer/runtime/native-cache/confluxmap/<游戏进程会话>/`，不同客户端使用不同目录，地图缓存、路径点和世界数据的原有路径不变。首次换用该修复包前，需完全退出已运行的 Minecraft 客户端，以释放旧存档内已经加载的 DLL；不删除已有地图数据。显式设置的 `-Dconfluxmap.nativeLib` 仍沿用原模组行为。

回档等待文件释放时显示等待阶段，超时后显示失败，并启用“返回主菜单”按钮。关闭失败提示不会解除已改写存档的安全锁，成功重新回档后才能解除。

在 Fabric 26.3 的回档失败画面或被回档锁拦截时，可点“重新回档”，选择**同一存档**的 Prime Backup 备份编号（包括回档前保护备份），再点确认。模组在后台将所选备份完整导出并校验到独立暂存目录；只有成功后才将当前存档原样移到 `mcdr-singleplayer/runtime/recovery-history/<操作编号>/<存档名>/`，再把已验证的备份移入 `saves/`。成功后才解除入口锁。导出、文件占用检查或替换失败时继续锁定，原存档或保留目录不会被自动删除。恢复前请确认已退出目标单人存档；若其他客户端或程序仍占用文件，应先关闭它们。此入口当前使用 Prime Backup 1.13.1 的备份库，不列出其他存档或 Chunk Backup 槽位。

如果旧版失败已经导致绑定存档缺少 `level.dat`，请先保留原存档和 PB 数据库，退出所有占用文件的客户端，再从 MCDR 控制台对同一绑定目录执行离线回档。适配器只允许从目标匹配、包含正常 `level.dat` 且通过完整性校验的备份恢复；普通备份和首次绑定仍要求现有存档完整。这不代表旧版失败后的存档已经修复，进入游戏前应确认回档成功。

## 范围

- 本版仅适配 Minecraft 26.3 / Fabric、MCDR 2.16.0、Prime Backup 1.13.1。
- 自动模式按世界选择独立绑定；手动模式仅绑定所选世界，进入其他世界会拒绝备份和回档，换绑定需退出 MCDR 并重新运行配置脚本。
- 回档只支持当前绑定目录下的常规文件，拒绝跨存档目标、越界路径和符号链接。
- 回档要求空 `retain_patterns`、完整性校验开启，不支持 `--fail-soft` 或 `--no-verify`。
- 未适配其他备份插件、LAN 多人世界、原生 RCON、自动重进世界或其他加载器。
- 定时备份仍使用 Prime Backup 原机制；暂停或桥接未连接时不会执行在线备份。没有连接时只有确认存档未被锁定，才允许离线备份。

本页描述当前适配行为与使用边界。可在本地运行仓库中的自动化测试；测试日志、截图和历史记录不随安装包分发。
