# P2 第二批：查询计划与事实溯源验收

日期：2026-07-25
分支：`codex/p2-knowledge-graph`
实现提交：`60dbfdf685409045d6ddfacba2e70a6954d94ce8`
数据版本：`v1.0.0-alpha.2`

## 变更范围

- 将药品和上下文别名投影为带唯一约束的别名节点；
- 为六条核心只读查询建立统一 EXPLAIN/PROFILE 采集器；
- 新增严格 `fact-provenance-v1` 契约和只读事实溯源 API；
- 增加来源审核候选队列，但不修改正式事实、来源、评测集或 Ollama prompt。

## 真实 Neo4j 结果

使用官方 `Neo4j/5.26.28`、隔离端口 `17687` 和 tmpfs 数据目录完成导入与 PROFILE。

| 查询 | 入口索引 | query type | DB hits |
|---|---|---:|---:|
| `resolve_medication` | `SafetyMedicationAlias.normalized_name` | `r` | 22 |
| `resolve_context` | `SafetyContextAlias.normalized_name` | `r` | 18 |
| `duplicate_fact` | `SafetyIngredient.name` | `r` | 44 |
| `interaction_facts` | `SafetyIngredient.name` | `r` | 50 |
| `contraindication_facts` | `SafetyIngredient.name` | `r` | 56 |
| `fact_provenance` | `SafetyFact.fact_id` | `r` | 82 |

六条查询均命中索引，八个 `Safety*` 索引均为 `ONLINE`，没有
`FeatureDeprecationWarning`。完整算子、索引详情、采集时间、代码 SHA 和通知列表保存在
[`neo4j-query-plan-v1.json`](neo4j-query-plan-v1.json)。

这些 DB hits 和单次耗时只用于发现标签扫描、错误索引和版本退化。当前图只有 3 条事实，
不能据此声称高并发、低延迟或规模化性能。

## 事实溯源 API

`GET /api/v1/knowledge/facts/{fact_id}` 返回：

- 原始 `FactRecord`；
- `SUBJECT` 与 `OBJECT` 端点；
- `APPLIES_IN` 上下文；
- 完整 `SUPPORTED_BY` 来源记录；
- `BELONGS_TO` 快照和数据版本。

服务端重新验证边与事实属性的一致性。缺失来源、错误端点、上下文不一致或混合版本均
映射为 503 `knowledge_unavailable`；不存在的 ID 返回 404 `fact_not_found`。接口没有
JSON fallback，因此可以真实暴露 Neo4j 投影问题。

## 自动化验收

| 检查 | 结果 | 边界 |
|---|---:|---|
| 全量普通 pytest | `134 passed, 3 skipped` | 3 项需显式启动隔离 Neo4j |
| 真实 Neo4j 集成 | `3 passed, 134 deselected` | 导入、Repository、API handler、损坏审计和 PROFILE |
| V1 catalog | 7 Source、4 Medication、2 Context、3 Fact | 正式数据未修改 |
| 公开仓库审计 | 通过 | 137 个已跟踪文件，单文件上限 5 MiB |
| 前端生产构建 | 通过 | Vite 7.3.6，26 modules transformed |
| 浏览器契约 | 4/4 通过 | API fixture；不包装为真实依赖端到端 |
| 前端生产依赖审计 | 0 vulnerability | `npm audit --omit=dev` |
| `git diff --check` | 通过 | 无空白错误 |

集成测试结束后，专用容器和网络均已移除；没有访问或修改其他 Neo4j 实例。

## 内容扩充边界

本批只建立
[`P2_SOURCE_CANDIDATES.md`](../docs/P2_SOURCE_CANDIDATES.md)。候选记录不是医学事实，
不会被 Safety Engine 或 Neo4j 正式投影读取。下一批来源工作应优先利用现有药品记录，
最多选择两项调查，并在无法取得产品级、可定位权威来源时停止。
