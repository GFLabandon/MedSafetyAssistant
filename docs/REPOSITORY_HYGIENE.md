# 仓库卫生待办清单

盘点日期：2026-07-20
状态：已完成

## 已被 Git 跟踪的待清理文件

- `2.1.0`；
- 根目录 `__pycache__/` 下 3 个 `.pyc`；
- `logic_layer/__pycache__/` 下 16 个 `.pyc`。

这些文件不是源代码或必要运行资产，且已被 `.gitignore` 覆盖。删除后可通过 Git 历史恢复，不会删除本地 `.env`、数据库、模型、用户数据或依赖目录。

## 暂不处理

- `.env`：未被 Git 跟踪，本轮不读取、不删除；
- `frontend/node_modules/` 和 `frontend/dist/`：未被 Git 跟踪，本轮不删除；
- `.idea/`、`.DS_Store`：本地忽略文件，本轮不删除；
- `docs/superpowers/`：已从公开仓库移除；正式项目计划和状态保留在 `docs/` 根目录；
- `app.py`：保留 Streamlit 原型；
- 两份 Cypher 数据文件：在来源清点和迁移完成前保留。

## 拟执行动作

用户确认后，已单独执行以下卫生变更：

1. 从 Git 索引和工作区移除上述已跟踪缓存及 `2.1.0`；
2. 运行测试与前端构建；
3. 确认未删除任何未跟踪用户文件；
4. 不与功能修改合并提交。

最终精确复核为 19 个 `.pyc` 和 1 个 `2.1.0`，共 20 个文件。初始文档将 `logic_layer/__pycache__/` 误计为 14 个，执行删除前已重新列出全部 Git 跟踪路径并修正数量。

## 公开仓库清理（2026-07-24）

- [x] 移除 Codex 本地说明文件 `.codex`；
- [x] 移除包含旧 Agent 指令和过时路线的 `docs/superpowers/`；
- [x] 移除指向已废弃 `redisearch-new` 容器的旧 Redis Compose、启动脚本和连接测试；
- [x] 将公开文档中的本机绝对 Python 路径改为通用 `python` 命令；
- [x] 保留 `PROJECT_PLAN`、`PROJECT_STATUS`、`SOURCE_ALIGNMENT`、`SAFETY_BOUNDARY`、
  `EVALUATION` 和数据卡等可复现、与项目交付直接相关的文档。
