# mcdr-singleplayer

[![License](https://img.shields.io/github/license/halfkite/mcdr-singleplayer)](LICENSE)
[![CurseForge 下載量](https://img.shields.io/curseforge/dt/1723660?logo=curseforge&label=CurseForge&color=f16436)](https://www.curseforge.com/projects/1723660)
[![Minecraft 版本](https://cf.way2muchnoise.eu/versions/For%20MC_1723660_all.svg)](https://www.curseforge.com/projects/1723660)
[![GitHub 下載量](https://img.shields.io/github/downloads/halfkite/mcdr-singleplayer/total?logo=github)](https://github.com/halfkite/mcdr-singleplayer/releases)

[简体中文](README.md) | **繁體中文** | [English](README_en.md)

[問題回報](https://github.com/halfkite/mcdr-singleplayer/issues) | [MCDReforged](https://mcdreforged.com/zh-CN/) | [Prime Backup](https://mcdreforged.com/zh-CN/plugin/prime_backup) | [Chunk Backup](https://mcdreforged.com/zh-CN/plugin/chunk_backup)

MCDR 是用來控制 Minecraft 伺服器的 Python 工具，詳見 [MCDReforged](https://mcdreforged.com/zh-CN/)。<br>

**本模組仍處於初步測試階段。使用備份外掛前，請務必先以其他方式完整備份存檔！！！！！**<br>
**本模組仍處於初步測試階段。使用備份外掛前，請務必先以其他方式完整備份存檔！！！！！**<br>
**本模組仍處於初步測試階段。使用備份外掛前，請務必先以其他方式完整備份存檔！！！！！**<br>

## 需求與版本支援

支援 Minecraft 1.21–26.3 的 Fabric 與 NeoForge 版本。

| 載入器／依賴 | 要求 |
| --- | --- |
| [Fabric Loader](https://fabricmc.net/use/installer/) | 0.19.5 或更新版本；另需安裝與 Minecraft 版本相符的 [Fabric API](https://modrinth.com/mod/fabric-api) |
| [NeoForge](https://neoforged.net/) | 安裝與 Minecraft 版本相符的 NeoForge |
| [MCDR](https://mcdreforged.com/zh-CN/) | 安裝 Python 後，模組會自動安裝 MCDR |
| Python | Python 3.10 或更新版本及 pip |

模組不會自動下載或安裝 Python。若未偵測到 Python，進入單人世界後會顯示安裝提示。安裝並偵測到 Python 後，模組會繼續準備 MCDR。

## 安裝與首次啟動

將對應載入器與 Minecraft 版本系列的 JAR 放入**客戶端遊戲執行個體**的 `mods/` 資料夾，接著啟動遊戲並進入單人存檔。Fabric 也需要安裝 Fabric API。

- [自動啟動、存檔設定與設定匯入](docs/自动启动与存档配置.md)
- [手動安裝說明](docs/安装说明.md)
- [Prime Backup 相容性](docs/PrimeBackup适配.md)
- [Chunk Backup 相容性](docs/ChunkBackup适配.md)

MCDR 啟動後，聊天欄會說明主玩家擁有 MCDR 四級權限，並提供可選的備份外掛。可依提示安裝 Prime Backup 或 Chunk Backup。安裝 Prime Backup 後，可選擇是否啟用備份、每 4 小時自動備份，以及套用建議的自動清理設定。

## 功能

- 將遊戲聊天、玩家加入與離開、世界啟動與關閉事件轉發給 MCDR 外掛，並轉送指令及其回覆
- 將已載入 MCDR 外掛的根指令、別名、子指令、參數與建議註冊為客戶端 `/!!` 指令；外掛載入、卸載或重新載入時同步更新
- 依存檔資料夾名稱隔離外掛設定、外掛資料與備份；切換存檔時啟動對應的 MCDR 執行環境
- 為 Prime Backup 與 Chunk Backup 提供單人遊戲相容支援；顯示回檔進度，並在回檔完成前禁止開啟目標存檔
- 支援簡體中文、繁體中文與英文，介面語言會跟隨客戶端設定

## 資料目錄

模組與 MCDR 共用檔案位於遊戲執行個體的 `mcdr-singleplayer/` 目錄；每個存檔的資料位於 `date/<存檔資料夾名稱>/`。

```text
mcdr-singleplayer/
├─ mcdr-singleplayer-config.yml  本模組設定，含欄位註解
├─ config.yml                    共用 MCDR 設定
├─ permission.yml                共用玩家權限
├─ plugins/                      共用 MCDR 外掛
├─ date/
│  └─ <存檔資料夾名稱>/
│     ├─ config/<外掛 ID>/       外掛設定及部分外掛資料
│     ├─ pb_files/               Prime Backup 資料與備份
│     └─ cb_files/               Chunk Backup 區域備份
├─ log/                          安裝器、控制器與 MCDR 日誌
└─ runtime/                      Python、MCDR 與橋接執行環境
```

永久刪除存檔後，如需一併刪除其外掛資料，可移除對應的 `mcdr-singleplayer/date/<存檔資料夾名稱>/` 目錄。使用固定絕對路徑的第三方外掛可能需要另外調整設定。

## 授權條款

本專案採用 [GNU Lesser General Public License v3.0](LICENSE)。
