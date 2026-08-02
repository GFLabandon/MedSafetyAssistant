# P3 Structured Session Context Acceptance

- 日期：2026-08-02
- 实现提交：`2ba6272161a889008c5cc24d581875285ab5e4eb`
- 新增 routing 基线提交：`bb419057d7c366d7e718ca53adeffd9c7a0406a1`
- 模型：`qwen3:4b-instruct`
- 模型 digest：`0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`

## 结论

本批为 typed workflow 增加一个服务端约束的 `retrieve_session_context` 工具，使显式
session 内的明确追问可以复用上一轮 catalog 实体，同时保持医学事实、工具参数和 Redis
内容不受模型控制。

V1 不读取 legacy 问答文本。独立 Redis key 只保存药品/上下文 ID、数据版本、上一轮结论
状态和 schema 版本；模型 prompt、公开 trace 和结构化日志均不包含 session ID、问题、药名
或 artifact 内容。

## 契约与失败语义

- `session_id` 可省略；省略时 read/write 均为 `disabled`；
- Redis 未配置或故障时为 `unavailable`，安全查询继续无状态执行；
- 没有历史记录为 `empty`；数据版本不一致为 `stale`，不释放旧实体；
- 只有明确追问代词且当前问题没有显式药品时才应用 context；
- 当前轮明确药品不会与历史药品静默合并；
- 只有成功解析且存在当前数据版本时才写回；写失败不改变医学结论；
- `DELETE /api/sessions/{session_id}` 同时清理 legacy 与 V1 session namespace。

这仍不是认证或用户账户隔离：拿到合法 session ID 的调用方可以引用该 namespace。因此
当前能力只适用于本地演示和受控开发，不应称为生产隐私边界。

## 真实 Redis 双会话验收

只启动 `docker-compose.local.yml` 的 Redis 服务，建立两个明确 session：

- session A 首轮为泰诺 + 感康，追问后恢复 `[泰诺, 感康]` 并返回
  `fact-duplicate-acetaminophen-001`；
- session B 首轮为布洛芬，追问后只恢复 `[布洛芬]`，不读取 A 的药品或事实；
- 两个 key TTL 均为正；
- Redis hash 字段仅为 `schema_version`、`medication_ids`、`context_ids`、
  `data_version`、`prior_conclusion_status`；
- raw question/answer 不存在；
- `clear_session` 各删除一个 V1 key，验收后无残留 acceptance key。

## 真实 Ollama 两轮 Agent 验收

同一个显式 session 连续运行：

1. `泰诺和感康能一起吃吗？`
2. `刚才的药还能一起吃吗？`

首轮 session 状态为 `empty -> stored`，第二轮为 `available -> stored` 且
`context_applied=true`。两轮共 8 次 name-only 工具提议全部接受：

| 轮次 | 工具 | Planner latency |
|---|---|---:|
| 1 | `retrieve_session_context` | 5883.303 ms |
| 1 | `resolve_medications` | 732.316 ms |
| 1 | `query_safety_graph` | 744.605 ms |
| 1 | `render_evidence_explanation` | 763.583 ms |
| 2 | `retrieve_session_context` | 1949.162 ms |
| 2 | `resolve_medications` | 723.832 ms |
| 2 | `query_safety_graph` | 746.935 ms |
| 2 | `render_evidence_explanation` | 776.228 ms |

第二轮解析为 `[泰诺, 感康]`，返回
`fact-duplicate-acetaminophen-001`，`generation_mode=llm_planned`。首个请求包含模型冷加载
成本；该单次开发机延迟不代表稳定性能或 SLO。

## 模型路由开发集

新增 `eval/session_tool_routing_dev_v1.jsonl`：12 条 dev 样例，SHA-256 为
`8b9a7722308bcbe7dd38df9481f835842090835332c041b01846a373489e7c59`。

- session-routing 12 条：raw name `1.000`、bound call `1.000`、fallback `0`，P50/P95
  `646/772 ms`；
- 原有 40 条 dev 在 prompt v2 回归：raw name `1.000`、bound call `1.000`、fallback `0`，
  P50/P95 `688/752 ms`；
- 两组都是开发集，不是新的 locked test；原 20 条 locked test 不重复运行或重新包装。

机器可读报告：

- [`baseline-server-bound-session-tool-qwen3-4b-instruct-dev-v1.json`](baseline-server-bound-session-tool-qwen3-4b-instruct-dev-v1.json)
- [`baseline-server-bound-tool-qwen3-4b-instruct-dev-v2.json`](baseline-server-bound-tool-qwen3-4b-instruct-dev-v2.json)

## 自动化验收

- `conda run -n medsafety python -m pytest -q`：`211 passed, 5 skipped`；
- 新增 Redis adapter、数据版本隔离、损坏记录、两轮追问、新药不合并、模型隐私投影、
  request trace/log redaction 和 session 清理测试；
- V1 数据 5/5 校验和与 catalog 校验保持通过；
- 前端生产构建和公开仓库审计保持通过。

## 仍然不是

- 登录用户、ACL 或不可猜测 session 所构成的生产认证；
- 任意自然语言指代消解或长期个性化记忆；
- 允许模型读取 Redis、构造 session key 或写入自由文本的 Agent；
- 独立锁定的模型泛化评测、临床系统或生产 SLO。
