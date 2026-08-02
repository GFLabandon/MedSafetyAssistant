# P3 Server-bound Tool Decision Acceptance

- 日期：2026-08-02
- 代码基线：`43391c541a2e38483931df2ab24d7692c71ab311`
- 数据集：`eval/tool_shadow_v1.jsonl` 的 40 条 `dev` 样例
- 数据集 SHA-256：`e037caf4a9aa3e2db33c2fb1fbc3cca6ca854a1e47bd16cc5a008cf25f8a3229`

## 结论

本批将上一阶段的“模型复制完整工具参数”收窄为“模型只提议工具名，服务端绑定全部
参数”。模型看不到用户问题、artifact ID、Evidence Packet 或 Cypher；名称不匹配、未知
工具、无工具调用和请求故障都会记录并回退到阶段确定的调用。

默认生成与工具模型选择 `qwen3:4b-instruct`。它在同一 40 条开发集上达到 raw tool-name
accuracy `1.000`；`qwen3:1.7b` 为 `0.875`，5 次错选全部由服务端拦截。两者的
server-bound call accuracy 都是 `1.000`，该指标只证明参数绑定与确定性回退正确，不能
替代模型准确率。

## 同条件模型 A/B

固定参数：temperature `0`、seed `42`、num_predict `48`、每条 1 次；两个正式报告均在
干净工作树上生成，绑定同一代码提交。

| 模型 | Digest 前缀 | Raw name | Bound call | Fallback | P50 / P95 |
|---|---|---:|---:|---:|---:|
| `qwen3:1.7b` | `8f68893c685c` | `0.875` | `1.000` | `0.125` | `417 / 507ms` |
| `qwen3:4b-instruct` | `0edcdef34593` | `1.000` | `1.000` | `0.000` | `749 / 856ms` |

正式机器可读结果：

- [`baseline-server-bound-tool-qwen3-1.7b-dev-v1.json`](baseline-server-bound-tool-qwen3-1.7b-dev-v1.json)
- [`baseline-server-bound-tool-qwen3-4b-instruct-dev-v1.json`](baseline-server-bound-tool-qwen3-4b-instruct-dev-v1.json)
- [`server-bound-tool-qwen3-1.7b-dev-v1-records.json`](raw/server-bound-tool-qwen3-1.7b-dev-v1-records.json)
- [`server-bound-tool-qwen3-4b-instruct-dev-v1-records.json`](raw/server-bound-tool-qwen3-4b-instruct-dev-v1-records.json)

普通 `qwen3:4b` thinking 标签也做了探索运行：40 次都在输出推理文本后以长度限制结束，
没有产生工具调用，因此没有因为参数量更大而进入默认配置。该探索结果没有作为正式对照
报告保留；最终选型只依据上表两个可复现报告和 capability 检查。

## 真实完整链路

使用新默认配置运行：

```text
用户问题
-> qwen3:4b-instruct name-only proposal x3
-> 服务端工具名校验与参数绑定
-> typed registry + server-held artifacts
-> Safety Engine Evidence Packet
-> qwen3:4b-instruct evidence-order plan
-> 服务端解释护栏
```

重复成分样例的三个模型工具名均被接受，执行路径为
`resolve_medications -> query_safety_graph -> render_evidence_explanation`，返回
`fact-duplicate-acetaminophen-001`，解释模式为 `llm_planned`。

此外，现有 5 个 explanation model 开发探针运行 3 次，共 15 次真实请求：valid plan、
结论保持、事实引用覆盖、来源可追溯和 pipeline pass 均为 `1.000`，unsupported claim 与
fallback 均为 `0`；P50/P95 为 `1557/2089ms`。这是共同迭代过的开发集结果，不是独立
泛化或医学准确率证明。

## 自动化验收

- Python：`197 passed, 5 skipped`；
- 新增 server-bound decision、workflow、evaluation 与 embedding provenance 契约；
- 前端生产构建通过；
- `data/v1` 5/5 校验和通过，catalog 仍为 9 Source、5 Medication、3 Context、4 Fact；
- 逐例记录不保存问题、参数值、模型正文或医学 artifact，只保存参数键和决策状态；
- 本地 `.env` 仍由 `.gitignore` 排除。

## 模型迁移边界

生成模型和工具模型已经从 DeepSeek 切换为 `qwen3:4b-instruct`。DeepSeek 暂时只保留为
embedding 模型，因为 Qwen3 生成模型的 Ollama capability 不包含 embedding，而专用 Qwen
embedding 尚未完成本机下载与验证。此时删除 DeepSeek 会破坏 Redis 历史检索，因此本批
明确不删除。

Redis 新记录保存 `embedding_model` 与 `embedding_dimensions`。未知旧记录、模型不一致或
维度不一致的向量不会参与相似度计算，并按 24 小时默认会话 TTL 自然过期；后续验证专用
embedding 模型后即可无破坏切换。

## 仍然不是

- 开放式 ReAct 或多 Agent；
- 允许模型创建工具、参数、Cypher、Evidence Packet 或医学事实；
- 独立锁定的模型泛化评测；
- 临床系统或生产高并发系统。
