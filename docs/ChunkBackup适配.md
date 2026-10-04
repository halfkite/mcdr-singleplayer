# Chunk Backup 单人回档等待适配

适用于 mcdr-singleplayer 0.3.9、Minecraft 26.3 Fabric、MCDR 2.16.0、官方 [Chunk_BackUp 2.0.3](https://github.com/Passion-Never-Dissipate/Chunk_BackUp/releases/tag/v2.0.3) 和其前置 [candy_tools 1.0.2](https://github.com/Passion-Never-Dissipate/candy_tools/releases/tag/1.0.2)。不修改或重新分发这两个上游插件。

## 安装与绑定

首次进入世界时点击区域备份推荐后的 `[安装]`，或执行 `/!!spbridge install chunk_backup`，自动下载并校验官方 Chunk Backup 2.0.3、candy_tools 1.0.2 与单人适配器，当前存档立即加载。也可手动放入共用插件目录 `mcdr-singleplayer/plugins/`。升级到本模组 0.3.9 并重启客户端后，安装器识别 Chunk Backup 2.0.3，自动安装随模组提供的 `singleplayer_chunk_backup.mcdr`；进入存档时准备独立配置和备份目录。安装其他 Chunk Backup 版本时不会自动启用此适配器。

完整安装包的 `adapters/` 中也提供适配器，手动模式或需要提前绑定时，在退出游戏世界并停止该 MCDR 环境后执行：

```powershell
python ./setup_chunk_backup.py --mcdr-dir 'D:/Minecraft/游戏实例/mcdr-singleplayer' --world-dir 'D:/Minecraft/游戏实例/saves/存档文件夹名'
```

脚本创建独立存档配置并安装适配器，已有 Chunk Backup 配置保留；旧配置的路径需要按照下述绑定要求调整。不要在备份或回档任务执行中修改配置、运行脚本或移走插件。

- 配置：`plugindata/<存档文件夹名>/config/chunk_backup/config.json`。
- 适配器绑定：`plugindata/<存档文件夹名>/config/singleplayer_chunk_backup/config.json`。
- 备份槽位与回档前备份：`plugindata/<存档文件夹名>/cb_files/`。
- 任务日志：`log/<存档文件夹名>/chunk_backup/`；MCDR 日志仍在相同存档的日志分类下。

`server_root` 必须指向实际存档父目录，所有维度的 `world_name` 必须等于当前存档文件夹名；26.3 默认区域路径使用 `dimensions/minecraft/<维度>/region`、`entities` 和 `poi`。玩家数据路径也必须位于当前存档内。

存储目录通过 `.singleplayer-world.json` 绑定实际世界路径。已有、非空而没有绑定记录的备份目录不会自动接管，也不能通过复制其他存档的绑定文件来混用备份。配置导入会重新绑定当前存档和独立存储目录，不导入备份槽位。

## 回档与等待界面

`/!!cb make <半径> [备注]` 的位置和维度查询由适配器直接读取单人服务端的同一时刻玩家数据，保留上游区块选区算法，不再匹配 `data get entity` 的英文输出、NBT 文本或显示名称。26.3 的输出与客户端语言变化不会影响这个查询；玩家离开、暂停或连接中断时拒绝执行，不沿用旧坐标。

保留上游命令前缀、参数、权限、确认和倒计时。默认前缀下可使用：

```text
/!!cb back 1
/!!cb confirm
/!!cb abort
/!!cb restore
```

`back` 恢复指定槽位，`restore` 撤销上次回档。静态槽位和上游的 `-s`、`-c` 参数仍由 Chunk Backup 处理；`-d` 玩家数据恢复仍依赖其原有功能及游戏环境，本适配器不会自动安装 Carpet。

确认后，适配器把回档任务内的 MCDR `stop` 转为保存并退出单人世界。等待真实世界关闭、代理停止及 `session.lock` 释放，才允许回档前备份和恢复文件。普通 MCDR `stop` 仍只断开桥接。

主菜单显示检查 / 等待确认、保存退出、安全备份、恢复区域文件、玩家数据或失败后的自动恢复阶段。目标存档回档完成前不能进入，完成后手动重新打开原存档。适配器不使用“代理停止”或“开始恢复”日志作为完成信号，也不会把上游 `start()` 解释为自动重新进入游戏。

控制器退出或切换存档时等待 Chunk Backup 的任务队列完成。Prime Backup 与 Chunk Backup 的备份 / 回档任务互斥，冲突时拒绝新任务并要求稍后重试。

未确认、确认超时或倒计时中取消不显示成功。文件恢复失败、玩家数据恢复错误或进程中断时保留目标存档入口锁。上游自动恢复回档前状态后仍显示失败，不把它当作用户请求的目标回档成功；检查日志后，在主菜单下用原存档环境离线重新回档，成功后解除入口锁。

## 范围与验证边界

适配器固定 Chunk Backup 2.0.3 的任务与区域操作接口；依赖版本不符合时 MCDR 禁用适配器。没有加载此适配器时，不能对仍在运行的单人世界使用 Chunk Backup 原生回档。

支持沿用上游的区块选区、维度和静态 / 动态槽位恢复，恢复对象必须位于绑定世界内，拒绝越界路径、符号链接、Windows 目录联接和跨存档数据。在线备份要求 `save-off / save-all flush / save-on`，暂停时拒绝在线备份；断开桥接但世界仍运行时，存档锁阻止离线回档。

本页描述当前适配行为与使用边界。可在本地运行仓库中的自动化测试；测试日志、截图和历史记录不随安装包分发。
