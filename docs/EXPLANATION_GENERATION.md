# Evidence Packet 约束生成

当前 Ollama prompt：`evidence-order-v2`
更新时间：2026-07-20

## 设计目标

V1 解释层将“风险判断”“LLM 可做的决定”和“用户可见医学陈述”分开：

1. Safety Engine 依据来源对齐事实生成 `EvidencePacket`；
2. Ollama 只接收结论状态及每条事实的 `fact_id`、风险类型和严重度；
3. 服务端按本次 Evidence Packet 动态生成 JSON Schema，固定结论、合法 ID 集合、数量和唯一性；
4. 模型只能返回原结论状态和完整的 `fact_id` 排序；
5. 服务端再次验证无未知、遗漏或重复 ID 后，按计划排序；
6. 服务端验证计划满足 `FATAL > RED > ORANGE > INFO`，低严重度排在高严重度之前时确定性回退；
7. 每条用户可见陈述都逐字取自对应 `EvidenceFact.reason`，来源和定位也由服务端复制。

因此，模型不能创建、改写或删除医学事实。该阶段的 AI 作用是结构化排序，不是开放式医学回答。

## 输出与回退契约

`POST /api/v1/safety/explain` 返回 `SafetyExplanation`：

- `conclusion_status`：与 Evidence Packet 完全一致；
- `summary`：由状态和事实数确定性生成；
- `claims[]`：包含 `fact_id`、原始证据陈述、来源 ID 和来源定位；
- `generation_mode`：`llm_planned`、`deterministic` 或 `deterministic_fallback`；
- `prompt_version`：Ollama 路径当前为 `evidence-order-v2`；
- `fallback_reason`：只公开稳定错误码，不包含底层异常文本。

以下情况自动保留全部证据并切换到确定性排序：

- Ollama 不可用或超过 5 秒；
- 返回内容不是严格 JSON；
- 夹带建议、剂量或其他额外字段；
- 改写结论状态；
- 引用未知 fact_id；
- 漏引或重复引用。
- 严重度顺序违反 `FATAL > RED > ORANGE > INFO`。

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

自动测试使用脚本化 planner 覆盖有效排序、未知 ID、漏引、重复引用、结论篡改、额外医学字段和依赖异常。真实模型 runner 另行记录模型 digest、固定参数、三次重复、时延、失败分类和原始计划；两类评测不能互相替代。

## 真实模型迭代结果

在同一 7 条开发探针、同一 `deepseek-r1:1.5b` digest 和 3 次重复运行下：

- v1 使用普通 JSON mode，15 次计划中 6 次把 fact_id 连字符改为下划线，有效计划率 0.600；
- 服务端全部拒绝这些未知 ID 并安全回退，流水线通过率仍为 1.000；
- v2 增加动态 JSON Schema 和 opaque ID 约束后，15/15 计划合法且三轮完全一致；
- v2 无证据陈述率仍为 0，引用覆盖率仍为 1.000。

详见 `reports/baseline-ollama-evidence-order-v1.md` 和 `reports/baseline-ollama-evidence-order-v2.md`。这是开发集调优结果，不是独立测试集结论。
