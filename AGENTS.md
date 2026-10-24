# 工作约定

本文件记录维护者对自动化改动的固定要求，改动前后都以此为准。

## 发布必须先获得同意

**发布必须经维护者明确同意后才能执行。** 本项目里「发布」包括：

- 创建或移动版本 tag（`git tag`、`git push --tags`、`git tag -f`）
- 创建或编辑 GitHub Release（`gh release create/edit`）
- 触发发布类工作流：`release.yml`、`release-neoforge.yml`、`publish-loader.yml`、
  `release-netdisk.yml`（用 `gh workflow run` 或推送 tag 间接触发）
- 上传到 CurseForge 或 123 网盘
- 为发布而提升版本号（`gradle.properties`、`compat/versions.json`、三个
  `mcdreforged.plugin.json`、`BUNDLED_VERSION`、`BRIDGE_VERSION`、`__init__.py`）

提发布前先说明：版本号、包含哪些改动、要跑哪些工作流，得到「发」的答复后再动手。

**无需同意的操作**：修改代码、写测试、本地构建、`pytest`、`gradlew test`、提交到本地
仓库、推送普通提交到 `main`（会触发 `build.yml` 的测试与构建，但不产出 Release）。

## 不动用户的游戏目录

- 不修改玩家的存档、`mcdr-singleplayer` 运行数据、启动器配置。
- 需要在实际实例里验证时，用 `.client-tests/shared/mc-home` 这套隔离运行时。
- 只有在维护者明确要求安装到某个实例时，才替换该实例 `mods` 里的模组 JAR。

## 改动必须自测

- Python：`.venv\Scripts\python.exe -m pytest -q`（全绿）
- Java：`.\fabric-bridge\gradlew.bat -p fabric-bridge --no-daemon test`（BUILD SUCCESSFUL）
- 发布前额外跑 `python scripts\check_release.py`，确认版本号各处一致

## 注释与文案

- 代码注释、文档、更新日志用中文；标识符与日志键名用英文。
- 用户可见文案同时补齐 `zh_cn`、`zh_tw`、`en_us` 三份，键数保持一致。
