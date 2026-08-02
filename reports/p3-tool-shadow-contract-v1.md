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
- runner 在发送评测请求前验证已安装模型包含 `tools` capability；
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
| P3 workflow + dataset + shadow 专项 | `34 passed` |
| 完整 Python 回归 | `182 passed, 5 skipped` |
| 非集成 CI 回归 | `182 passed, 5 deselected` |
| V1 catalog 校验 | 9 Source / 5 Medication / 3 Context / 4 Fact，`valid` |
| 前端生产构建 | 通过 |
| 公开仓库审计 | 通过，单文件上限 5 MiB |
| `git diff --check` | 通过 |

5 个 skip 是需要显式 Neo4j 环境的隔离集成项，本批没有把它们记为通过。

## 真实 Ollama 状态

原有 `deepseek-r1:1.5b` 不支持 tools，因此真实评测改用 `qwen3:1.7b`，模型 digest 为
`8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7`。

| Split | Prompt | Tool name | Whole call | P50 / P95 | Executed |
|---|---|---:|---:|---:|---:|
| dev，40 条 | v3 | 1.000 | 0.950 | 685 / 860 ms | 0 |
| locked test，20 条 | v3 | 0.950 | 0.850 | 681 / 842 ms | 0 |

v1 dev 的 whole-call exact match 只有 `0.275`；显式阶段映射后的 v2 为 `0.900`，最终
v3 为 `0.950`。三版开发结果均保留，避免只展示成功版本。

锁定测试只运行一次并保留 3 项失败：两项参数复制丢失标点，一项注入导致模型跳过解析、
错选 `query_safety_graph`。这项错误直接阻止模型进入正式控制流，v3 不再调整。

## 停止条件

当前模型不得进入正式工具执行路径。locked 注入失败已经触发停止条件；即使平均指标较高，
也不能抵消单项控制流错误。后续必须建立“模型只选工具名、服务端构造参数”的新版本，
继续满足非法工具执行率为 0、无证据医学陈述率为 0、失败可确定性回退，并通过独立的受控
执行实验；否则继续保持 shadow-only。
