# MCDR Singleplayer Bridge

让 MCDReforged 和已有的 Python 插件连接 Minecraft Java 版单人世界的内置服务端。

本文保存初始调研与设计。当前已经实现 26.3 Fabric 首版，实际能力、产物和验证状态以根目录 README、安装说明及测试记录为准；以下待实现要求属于原始设计，不能全部视为首版已交付功能。

## 设计目标

- 保持用户在客户端的“单人游戏”中进入、游玩和退出世界。
- 保留 MCDR 的插件加载、权限和命令系统。
- 尽量复用已有插件的 `server.execute`、`tell`、`say`、聊天和玩家事件。
- MCDR 插件与代理进程使用通用协议，不为每个 Minecraft 版本复制 Python 实现。
- 若需要客户端 Mod，把它限制为内置服务端的接口桥接；实际业务仍由 MCDR 插件完成。

## 调研依据

本地参考源码：`.reference/MCDReforged`，上游 master 提交 `53e1917a331e66a3358f88e265e0b461936c15b4`，源码版本标记为 2.16.0。

关键事实：

1. MCDR 创建子进程，从进程输出读取事件，向进程输入发送游戏命令。
2. `ServerInterface.execute` 最终调用进程输入发送逻辑；注册一个日志 handler 本身不会提供新的命令传输接口。
3. `register_server_handler` 是公开的插件扩展点，自 MCDR 2.13.0 起提供。
4. `ServerInterface.dispatch_event` 明确禁止用它派发同名的 MCDR 内置事件。因此直接从网络监听器补发内置聊天、加入和启动事件不是公开 API 支持的做法。
5. 单人内置服务端可以执行 Minecraft 命令，但没有独立服务端的终端命令输入和原生 RCON 接口。开放局域网提供游戏连接，不能直接替代控制台。

参考来源：

- [MCDReforged 上游说明](https://github.com/MCDReforged/MCDReforged)
- [ServerInterface API](https://docs.mcdreforged.com/en/latest/code_references/ServerInterface.html)
- [PluginServerInterface API](https://docs.mcdreforged.com/en/latest/code_references/PluginServerInterface.html)
- [自定义 Server Handler](https://docs.mcdreforged.com/en/latest/customize/handler.html)
- [MinecraftServer 的集成服务端与独立服务端说明](https://maven.fabricmc.net/docs/yarn-1.21.11%2Bbuild.3/net/minecraft/server/MinecraftServer.html)

上述 Minecraft 文档用于说明接口边界，不代表本项目已经选择或支持该游戏版本。

## 接入方式评估

| 接入方式 | 能力 | 限制 | 判断 |
| --- | --- | --- | --- |
| 只读取客户端日志 | 观察部分聊天和世界事件 | 无法可靠执行命令；日志格式和输出行为会变化 | 可作为受限观察模式，不能满足完整控制 |
| 自动向游戏聊天框输入命令 | 可在允许命令时执行部分操作 | 依赖窗口焦点、菜单状态和玩家权限，游戏内反馈难以与请求对应 | 不作为默认控制通道 |
| 开放局域网并接入机器人 | 作为另一名玩家聊天和操作 | 不等于控制台权限；另有游戏协议版本和登录要求 | 不作为默认控制通道 |
| 把存档改用本地独立服务端运行 | 可直接使用 MCDR 现有控制方式 | 游玩入口和运行方式改变，模组环境还需匹配 | 适合愿意改用多人入口的用户，不是本项目目标 |
| 最小客户端桥接 Mod | 提供命令执行、反馈和结构化事件 | 游戏端需要按加载器和 Minecraft API 适配 | 完整单人控制的推荐方案 |
| Java Agent / JVM 注入 | 可研究在不安装加载器 Mod 时提供接口 | 仍需进入 JVM、识别游戏对象和处理版本差异；不能据此承诺免适配 | 暂不作为首个实现 |

判断来自当前已核查的接口与源码，不宣称不存在任何第三方可用桥接工具。

## 推荐架构

```text
已有 MCDR 插件
      ↕ MCDR 的公开 API、命令树与事件
MCDReforged + singleplayer_bridge 插件 / handler
      ↕ 代理进程的标准输入与标准输出
Python 代理进程（由 MCDR 启动和管理）
      ↕ 本机 TCP，鉴权，UTF-8 JSON 消息
最小桥接 Mod（安装在 Minecraft 客户端）
      ↕ 在内置服务端线程执行命令、监听事件
当前单人世界
```

MCDR 管理代理进程，Minecraft 客户端仍由用户正常启动。桥接 Mod 只提供接口，不承担其他 MCDR 插件的业务逻辑。

代理进程把结构化事件写入 stdout，插件提供的 handler 把它们转换成 MCDR 的 `Info` 和服务端状态识别结果。随后由 MCDR 自身的 reactor 派发内置事件，避免修改 MCDR 核心或替换其他插件的 API。

MCDR 写入代理 stdin 的游戏命令转发给 Mod。Mod 必须在内置服务端线程执行命令，执行结果通过协议返回。网络读取不能阻塞游戏线程。

## 协议与生命周期要求

以下为待实现的协议约束：

- 协议版本与 Minecraft 版本分别表示，并在连接握手时报告。
- 仅绑定本机回环地址，使用随机令牌鉴权；日志不输出令牌。
- 每次进入世界生成新的会话标识。所有请求绑定会话，切换世界后不执行旧请求。
- 握手报告真实游戏版本、世界标识、存档路径、在线玩家和支持能力。
- 区分 `world_ready`、`player_joined`、`player_left`、`chat`、`command_result`、`log`、`world_stopped` 事件。
- 聊天事件的玩家来源由游戏端取得，普通日志和命令反馈不能伪装成玩家指令。
- 连接发生在世界加载后时，通过快照初始化版本与在线玩家；实际加入事件与快照需要去重。
- 每条命令包含请求标识和会话标识。断线后不自动重放可能产生副作用的命令。
- 对消息长度、排队数量和超时做明确限制。代理诊断信息写入 stderr，stdout 保留给结构化事件。
- 单人暂停时报告暂停状态。首版不擅自改变暂停行为，也不把暂时没有命令反馈误判为世界已退出。
- 世界完整关闭后代理结束本次会话，使 MCDR 清除启动状态并产生停止事件；MCDR 插件需要使 MCDR 保留运行，以便下次重新连接。
- 代理等待连接期间，MCDR 的“进程运行”仅表示代理存在；“服务端已启动”必须等待 `world_ready`。状态命令要区分这两个状态。
- 首版的停止代理表示断开控制连接，不能静默转成退出游戏或关闭世界。世界关闭和重启需要单独定义并验证。

## 已有插件的兼容边界

| 插件行为 | 预期处理 |
| --- | --- |
| 注册 `!!` 命令、处理聊天、管理权限 | 通过结构化聊天转成 MCDR 原生处理流程，首轮重点验证 |
| `execute`、`tell`、`say`、计分板操作 | 通过代理转发；游戏命令仍受所用 Minecraft 版本和桥接授权能力影响 |
| 玩家加入和退出 | 转成 handler 可识别的事件，并验证快照与事件不重复 |
| 读取特定原始服务端日志 | 可能需要适配，结构化输出不能保证与独立服务端原始日志完全相同 |
| `rcon_query` / 原生 RCON | 首版不承诺支持，仅有通用命令桥接不能等价替代 RCON |
| 依赖 Paper、Carpet、Forge 等额外游戏命令 | 对应游戏环境必须实际提供这些命令 |
| 读取固定的 `server/world` 路径 | 必须匹配真实单人存档路径；首版不自动移动存档或创建路径替身 |
| 在线备份和回档 | 需要确认保存完成、文件写入、存档锁和世界退出状态，不能直接承诺兼容 |
| `start` / `stop` / `restart` / `kill` | 默认管理代理生命周期，与 Minecraft 世界生命周期有区别；需单独适配 |

## 首个可验证里程碑

1. 选定一个 Minecraft Java 版版本及加载器作为游戏端验证基线。
2. 实现通用 Python 代理、MCDR 插件、结构化 handler，以及协议层的模拟游戏端。
3. 使用真实 MCDR 验证命令路由、权限、内置聊天与加入事件，验证断线和会话切换不重放命令。
4. 实现所选基线的最小 Mod，实际构建可安装 jar。
5. 用单人世界验证 `!!help`、简单插件回复、游戏命令、暂停、退出与再次进入。
6. 报告自动测试与游戏内验证的区别，并归档安装产物。基线验证后再扩展其他游戏版本和加载器。

项目的 Python 部分以统一协议复用。需要选择游戏版本的是游戏端编译和实测，不能把 MCDR 本身的跨版本能力误解为桥接 Mod 无需适配。
