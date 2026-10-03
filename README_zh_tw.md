# mcdr-singleplayer

[![License](https://img.shields.io/github/license/halfkite/mcdr-singleplayer)](LICENSE)
[![CurseForge](https://img.shields.io/curseforge/dt/1723660?logo=curseforge&label=CurseForge&color=f16436)](https://www.curseforge.com/projects/1723660)
[![Minecraft](https://cf.way2muchnoise.eu/versions/For%20MC_1723660_all.svg)](https://www.curseforge.com/projects/1723660)
[![GitHub downloads](https://img.shields.io/github/downloads/halfkite/mcdr-singleplayer/total?logo=github)](https://github.com/halfkite/mcdr-singleplayer/releases)

[简体中文](README.md) | **繁體中文** | [English](README_en.md)

[GitHub 下載](https://github.com/halfkite/mcdr-singleplayer/releases) · [CurseForge](https://www.curseforge.com/projects/1723660) · [問題反饋](https://github.com/halfkite/mcdr-singleplayer/issues) · [MCDReforged](https://mcdreforged.com/zh-CN/) · [Prime Backup](https://mcdreforged.com/zh-CN/plugin/prime_backup) · [Chunk Backup](https://mcdreforged.com/zh-CN/plugin/chunk_backup)

讓 MCDReforged 和已有 Python 外掛連線 Minecraft Java 版單人內建服務端。

開發版本 **0.3.10 / Fabric 與 NeoForge**，支援 1.21–1.21.11 與 26.1–26.3，已在 1.21.1、1.21.11、26.3 的兩種載入器上透過 PB 備份與回檔測試。安裝橋接 JAR 後自動準備 MCDR 2.16.0 與執行依賴，在主選單等待；進入世界後載入對應存檔的外掛環境，可點選安裝 Prime Backup 1.13.1 或 Chunk Backup 2.0.3。實際構建與遊戲測試範圍見[相容性記錄](docs/0.3.10兼容性与发布.md)。

**本模組處於初步測試階段，使用備份外掛前務必保留一份其他方式製作的完整存檔備份。**

## 依賴與版本支援

| 載入器 / 依賴 | 要求 |
| --- | --- |
| [Fabric Loader](https://fabricmc.net/use/installer/) | 0.19.5+，同時安裝與遊戲版本一致的 [Fabric API](https://modrinth.com/mod/fabric-api) |
| [NeoForge](https://neoforged.net/) | 安裝目標 Minecraft 版本的 NeoForge |
| Java | 1.21.x 使用 Java 21+，26.x 使用 Java 25+ |
| MCDR / Python | 模組自動準備，可自定義 Python 和下載映象 |

每個載入器發行兩個系列 JAR，遊戲端按實際版本選擇包內對應的適配實現。

| 系列 | 明確包含的遊戲版本 | 檔案命名 |
| --- | --- | --- |
| 1.21.x | 1.21、1.21.1–1.21.11 | `mcdr-singleplayer-<版本>+<fabric/neoforge>+mc1.21.x.jar` |
| 26.x | 26.1、26.1.1、26.1.2、26.2、26.3 | `mcdr-singleplayer-<版本>+<fabric/neoforge>+mc26.x.jar` |

系列包僅宣告明確適配的版本，不自動承諾未來版本。

## 安裝與使用

將對應載入器、版本系列的 JAR 放進**客戶端遊戲例項**的 `mods`，安裝對應 Fabric API 或 NeoForge，然後進入單人存檔。

- [自動啟動、存檔配置、映象與配置匯入](docs/自动启动与存档配置.md)
- [手動安裝流程](docs/安装说明.md)
- [Prime Backup 適配與回檔](docs/PrimeBackup适配.md)
- [Chunk Backup 回檔等待適配](docs/ChunkBackup适配.md)

所有執行配置集中在遊戲例項的 `mcdr-singleplayer/`：共用配置和 `plugins/` 直接位於根目錄，執行環境位於 `runtime/`，日誌位於 `log/`，各存檔配置與資料按存檔資料夾名位於 `date/<存檔資料夾名>/`，保留外掛原生相對路徑，PB 使用 `pb_files/`，CB 使用 `cb_files/`。切換存檔自動切換工作目錄與程序。升級時遷移舊模組配置，並匯入舊存檔分類和備份。

首次進入世界，聊天提示資料目錄、主玩家 MCDR 最高權限（4）、按存檔隔離的資料與配置，以及刪除存檔後的清理位置；測試階段完整備份警告重複三次。未安裝的 PB / CB 顯示可點選的安裝按鈕，CB 同時安裝 candy_tools 1.0.2。已有外掛跳過其安裝推薦。PB 已載入或剛安裝後顯示 `[開啟Prime Backup]`、`[啟用4小時定時備份]`、`[啟用推薦的自動刪除]` 和官方文件連結。清理保留最近 40 份、每日 1 份保留 30 天、每週 1 份保留 30 週。設定按存檔儲存；`[忽略且不再主動提示]` 對整個遊戲例項生效，可用 `/!!spbridge onboarding show` 主動檢視。

所有已載入 MCDR 外掛的根命令、別名、子指令和引數均註冊為客戶端斜槓命令，使用 `/!!` 開頭輸入並按 Tab 補全；載入、解除安裝和過載外掛自動重新整理。`/mcdr_setup recommend` 可再次應用推薦配置並顯示選項。

配置匯入示例：`/!!spbridge profile import "其他存檔資料夾名" --replace`。預設只補齊缺少的配置；顯式替換會備份當前檔案，不復製備份資料庫與外掛狀態。

## 語言與圖示

支援簡體中文（`zh_cn`）、繁體中文（`zh_tw`）和英文（`en_us`），按單人客戶端語言選擇，缺少譯文時回退英文。首次提示、按鈕、命令反饋、模組校驗錯誤和回檔介面均從語言檔案讀取；提示去掉句號，路徑和版本號中的點保留。

統一語言原始檔位於 `python/singleplayer_bridge/lang/<語言程式碼>.json`。構建時同時打入 Python 外掛和 JAR 的 `assets/mcdr-singleplayer/lang/`，新增語言可新增同鍵的 JSON 檔案。遊戲端回檔 UI 使用 Minecraft 原生翻譯元件。語言檔案屬於資源，不改變現有配置目錄。

模組圖示為使用者提供的 128×128 PNG，位於 `fabric-bridge/src/main/resources/assets/mcdr-singleplayer/icon.png`，兩種載入器後設資料均宣告圖示路徑。

## 已有能力

- 轉接聊天、玩家加入/退出、世界啟動/關閉，讓 MCDR 派發原生外掛事件。
- 轉發遊戲命令與反饋；MCDR start/stop/kill 管理代理連線。
- 隨機令牌鑑權、迴環連線、世界會話與路徑校驗；斷線不重放。
- 保留單人暫停，暫停時拒絕修改世界的命令。
- Prime Backup 確認儲存後備份，回檔前儲存並退出、釋放世界鎖、驗證檔案。回檔完成後重新進入世界，自動啟動對應 MCDR。
- 回檔期間在主選單顯示實際階段，目標存檔完成前不能進入；恢復檔案後發生失敗或程序中斷時繼續鎖定，成功離線重新回檔後解除。
- 回檔畫面複用原版選單背景、字型、等待動畫和灰色按鈕，跟隨資源包；回檔期間隱藏主選單標誌與閃爍標語。
- 控制器等待正在執行的 Prime Backup 任務完成後退出，避免切換程序打斷回檔。
- 可選 Chunk Backup 2.0.3 介面卡接入同一回檔介面與存檔入口鎖，支援回檔和撤銷回檔；控制器等待其任務完成，PB 與 CB 的備份 / 回檔互斥。
- Chunk Backup 的 `make` 直接查詢單人服務端玩家座標和維度，相容中文客戶端等不同命令輸出，不再依賴英文 NBT 輸出正則。

其他外掛的固定絕對資料路徑、原生 RCON、專用服務端日誌格式或程序重啟語義仍需適配。MCDR 外掛的相對配置與資料路徑按存檔隔離；自定義絕對路徑需要自行修改。


## 構建與自動釋出

構建需要 Python 3.10+、JDK 25（Gradle），NeoForge 1.21.x 還使用 JDK 21 工具鏈。

```text
python scripts/build_matrix.py --loader fabric --family 1.21.x
python scripts/build_matrix.py --loader fabric --family 26.x
python scripts/build_matrix.py --loader neoforge --family 1.21.x
python scripts/build_matrix.py --loader neoforge --family 26.x
```

產物位於 `dist/`，每次成功構建獨立歸檔到 `mod-builds/<時間戳>/` 並記錄 SHA-256。

釋出結構參考 [RankBoard](https://github.com/halfkite/rankboard)。釋出 GitHub Release 後，Fabric 與 NeoForge 獨立工作流構建兩個系列並上傳 GitHub、CurseForge 專案 `1723660`。金鑰使用倉庫 Secret `CURSEFORGE_TOKEN`，不寫入原始碼；支援手動重新發布已有 Release，詳見[釋出流程](docs/发布流程.md)。

## 許可證

本專案程式碼採用 [GNU Lesser General Public License v3.0](LICENSE)，與 [MCDReforged](https://github.com/MCDReforged/MCDReforged) 使用的許可證一致。Copyright (C) 2026 MCDR Singleplayer contributors。

設定 `MCDR_BRIDGE_TEST_PREINSTALLED=1` 可在自動啟動測試中預裝官方 PB、CB 與 candy_tools，驗證跳過安裝推薦的分支；不設定則驗證首次點選下載安裝。測試仍只使用 Gradle 的隔離遊戲目錄。
