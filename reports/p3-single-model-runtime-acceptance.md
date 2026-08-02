# P3 Single-model Runtime Acceptance

- 日期：2026-08-02
- 实现提交：`4b975bc7974ae2a7677cd6e1b026b4dc9a5a0005`
- 当前 Ollama 模型：`qwen3:4b-instruct`
- 模型 digest：`0edcdef34593`
- 本地 vectorizer：`local-char-ngram-hashing-v1`，512 维

## 结论

本批把本地运行依赖收敛为一个 Ollama 模型。`qwen3:4b-instruct` 同时用于证据解释、
服务端绑定的工具名提议和可选 Redis 候选 rerank；会话候选召回改为确定性的本地字符
n-gram feature hashing，因此不再需要第二个 embedding 模型或 `/api/embed`。

这没有扩大模型权限：LLM 仍不能创建医学事实、工具参数、Cypher 或 Evidence Packet。
本地 hashing 向量只证明药名与相近措辞的词法召回可工作，不代表通用语义检索质量。

## 本地模型清单与清理

清理前存在四个模型标签：

- `qwen3:4b-instruct`，2.5 GB；
- `qwen3:4b` thinking，2.5 GB；
- `qwen3:1.7b`，1.4 GB；
- `deepseek-r1:1.5b`，1.1 GB。

删除后三个冗余模型后，`ollama list` 只保留 `qwen3:4b-instruct`，约释放 5.0 GB。本地删除
可通过对应 `ollama pull` 恢复；仓库中的历史 A/B、locked test 和失败报告没有删除或改写。

## Redis 真实依赖验收

使用仓库 `docker-compose.local.yml` 只启动 Redis，并显式创建两个不同 session：

- 每条记录保存 `vectorizer_id=local-char-ngram-hashing-v1` 和 `vector_dimensions=512`；
- 所有验收记录具有正 TTL；
- session A 的查询不会返回 session B 的内容；
- “泰诺和感康还能一起吃吗”召回首项为“泰诺和感康能一起吃吗”，余弦相似度 `0.3592`；
- 两个验收 session 最后均通过 `clear_session` 清理。

这是小规模功能验收，不是 Recall@K、nDCG 或通用语义 embedding 基准。

## Ollama 冷启动完整链路

先执行 `ollama stop qwen3:4b-instruct` 强制卸载，再从
`/api/v1/workflows/safety/agent-query` 对“泰诺和感康能一起吃吗”运行完整链路。三个阶段：

| 阶段 | 模型工具名提议耗时 | 结果 |
|---|---:|---|
| `resolve_medications` | `4446.809 ms` | accepted |
| `query_safety_graph` | `740.517 ms` | accepted |
| `render_evidence_explanation` | `767.624 ms` | accepted |

最终返回 `fact-duplicate-acetaminophen-001`，`generation_mode=llm_planned`，没有触发工具名
回退。为覆盖 8 GB 开发机冷加载，工具 planner 使用独立、有限的 15 秒超时；证据解释的
5 秒超时保持不变。

## 自动化验收

- `conda run -n medsafety python -m pytest -q`：`201 passed, 5 skipped`；
- `npm run build`：Vite 生产构建通过；
- `shasum -a 256 -c data/v1/checksums.sha256`：5/5 通过；
- `python scripts/validate_v1_data.py --data-dir data/v1`：catalog 校验通过；
- 健康检查只要求一个去重后的 Ollama 模型，并公开 Redis vectorizer ID 与维度；
- 本地 `.env` 仍被 `.gitignore` 排除，未进入提交。

第一次直接运行 `conda run -n medsafety pytest ...` 因入口脚本没有仓库根目录的 import path
而收集失败；改用项目标准的 `python -m pytest` 后专项 11 项和完整回归均通过。该失败是
命令入口差异，不是测试或实现失败。

## 仍然不是

- 学习得到的语义 embedding 或向量数据库性能证明；
- 独立锁定的会话检索质量评测；
- 允许模型自由构造工具调用或医学结论的 Agent；
- 临床系统、生产高并发系统或可用性 SLO。
