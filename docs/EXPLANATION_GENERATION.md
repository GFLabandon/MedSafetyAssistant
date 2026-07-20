# Evidence Packet 约束生成

版本：`evidence-order-v1`
更新时间：2026-07-20

## 设计目标

V1 解释层将“风险判断”“LLM 可做的决定”和“用户可见医学陈述”分开：

1. Safety Engine 依据来源对齐事实生成 `EvidencePacket`；
2. Ollama 只接收结论状态及每条事实的 `fact_id`、风险类型和严重度；
3. 模型只能返回原结论状态和完整的 `fact_id` 排序；
4. 服务端验证无未知、遗漏或重复 ID 后，按计划排序；
5. 每条用户可见陈述都逐字取自对应 `EvidenceFact.reason`，来源和定位也由服务端复制。

因此，模型不能创建、改写或删除医学事实。该阶段的 AI 作用是结构化排序，不是开放式医学回答。

## 输出与回退契约

`POST /api/v1/safety/explain` 返回 `SafetyExplanation`：

- `conclusion_status`：与 Evidence Packet 完全一致；
- `summary`：由状态和事实数确定性生成；
- `claims[]`：包含 `fact_id`、原始证据陈述、来源 ID 和来源定位；
- `generation_mode`：`llm_planned`、`deterministic` 或 `deterministic_fallback`；
- `prompt_version`：固定为 `evidence-order-v1`；
- `fallback_reason`：只公开稳定错误码，不包含底层异常文本。

以下情况自动保留全部证据并切换到确定性排序：

- Ollama 不可用或超过 5 秒；
- 返回内容不是严格 JSON；
- 夹带建议、剂量或其他额外字段；
- 改写结论状态；
- 引用未知 fact_id；
- 漏引或重复引用。

非风险状态没有可排序事实，因此不会调用 LLM。请求可显式设置 `use_llm_plan: false`，用于完全离线和可重复的路径。

## Prompt 注入边界

V1 不把原始问题、未解析输入、事实正文、来源正文或历史会话交给排序模型。即使药品输入中含提示注入文本，也不能进入此 prompt。模型返回值随后还要通过 Pydantic 的 `extra="forbid"` 契约和事实集合一致性校验。

这只保护 V1 解释排序路径。旧 `/api/query` 仍是 legacy 自由生成接口，不应被描述为具备相同护栏。

## 验证命令

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/medsafety/bin/python \
  -m pytest test/test_explanation.py test/test_api.py -q

curl -X POST http://localhost:8000/api/v1/safety/explain \
  -H 'Content-Type: application/json' \
  -d '{"medications":["泰诺","感康"],"contexts":[],"use_llm_plan":false}'
```

当前自动测试使用脚本化 planner 覆盖有效排序、未知 ID、漏引、重复引用、结论篡改、额外医学字段和依赖异常。它证明服务端护栏行为，不等于真实模型质量评测。正式 Ollama 运行仍需记录模型摘要、固定参数并重复至少 3 次。
