# P3 Typed-Tool Shadow 契约验收

- 日期：2026-08-02
- 实现提交：`4130d7a`
- 数据版本：`v1.0.0-alpha.4`
- 数据集：`eval/tool_shadow_v1.jsonl`

## 结论

不执行真实工具的 Ollama Function Calling shadow 路径已完成离线工程验收。项目现在可以
把模型提出的单个下一步工具调用当作不可信数据，按注册表和严格参数 schema 分类并记录，
但不会把 proposal 交给 `TypedToolRegistry.execute`。

这证明的是 adapter、数据契约、失败分类和“零执行”边界，不是模型工具选择质量，也不
表示正式 controller 已由模型驱动。

## 冻结数据集

- 总计 60 条：40 条 dev、20 条 locked test；
- 阶段分布：`start` 20、`after_resolution` 20、`after_evidence` 20；
- 工具标签：`resolve_medications` 20、`query_safety_graph` 7、
  `request_clarification` 13、`render_evidence_explanation` 20；
- SHA-256：
  `e037caf4a9aa3e2db33c2fb1fbc3cca6ca854a1e47bd16cc5a008cf25f8a3229`；
- locked test 需要显式 `--allow-locked-test`；当前没有运行。

样例覆盖正常选择、未知工具、Cypher/额外参数注入、多工具/无工具返回、JSON 参数错误、
artifact ID 篡改、伪造 Evidence Packet 和重复循环请求。标签由确定性工作流状态推导，
不是由被测模型生成。

## 已验证边界

- Ollama 请求使用四个注册工具的 Function Calling schema；
- 所有参数 schema 都禁止额外字段；
- 用户问题只作为 JSON 状态值，不得覆盖固定 system 指令；
- 模型一次只能提出一个工具；多个、零个或错误形状均进入稳定失败分类；
- 未知工具、非法参数、错误工具和错误参数分别归类；
- 请求错误只记录异常类型，不记录连接地址或内部异常文本；
- 模型不能提交 `InputResolution`、`EvidencePacket` 或 Cypher；
- spy 测试确认 shadow proposal 不会触发工具注册表执行；
- 每条记录为 `executed: false`，报告为 `executed_tool_calls: 0`。

## 自动化结果

| 检查 | 结果 |
|---|---:|
| P3 workflow + dataset + shadow 专项 | `32 passed` |
| 完整 Python 回归 | `180 passed, 5 skipped` |
| 非集成 CI 回归 | `180 passed, 5 deselected` |
| V1 catalog 校验 | 9 Source / 5 Medication / 3 Context / 4 Fact，`valid` |
| 前端生产构建 | 通过 |
| 公开仓库审计 | 通过，单文件上限 5 MiB |
| `git diff --check` | 通过 |

5 个 skip 是需要显式 Neo4j 环境的隔离集成项，本批没有把它们记为通过。

## 真实 Ollama 状态

2026-08-02 执行 dev runner 时，Ollama preflight 返回 `ConnectionError`。runner 在任何
tool proposal 请求前停止，因此：

- 真实模型请求：0；
- dev 工具名准确率、参数精确匹配率和延迟：`not_run`；
- locked test：`not_run`；
- 没有产生可用于简历或 README 的模型指标。

待 Ollama 在线后，先固定当前提交、模型名与 digest，只运行 dev 并保留全部失败记录。
完成失败归因且不再调整当前 prompt/adapter 后，才能显式运行一次 locked test。

## 停止条件

当前模型不得进入正式工具执行路径。即使后续 shadow 指标达到目标，也必须继续满足：非法
工具执行率为 0、无证据医学陈述率为 0、失败可确定性回退，并通过独立的受控执行实验；
否则继续保持 shadow-only。
