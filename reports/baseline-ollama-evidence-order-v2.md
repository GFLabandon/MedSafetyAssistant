# Real Ollama Evidence-Planning Baseline: v2

执行日期：2026-07-20

- 数据集：`eval/explanation_model_dev_v1.jsonl`
- 数据版本：`v1.0.0-alpha.2`
- Prompt：`evidence-order-v2`
- 模型：`deepseek-r1:1.5b`
- 模型 digest：`e0979632db5a88d1a53884cb2a941772d10ff5d055aabaa6801c4e36f3a6c2d7`
- 参数：temperature 0、seed 42、num_predict 256、think false
- 结构化输出：每次依据 Evidence Packet 构建动态 JSON Schema
- 代码提交：`17e013a215c2882e641aa097da4b0f5b589627fe`
- 运行时工作树：clean
- 重复次数：3
- 模型请求：15

## 指标

| 指标 | v1 | v2 |
|---|---:|---:|
| Valid plan rate | 0.600 | 1.000 |
| Fallback rate | 0.400 | 0.000 |
| Valid plan consistency rate | 0.600 | 1.000 |
| Pipeline pass rate | 1.000 | 1.000 |
| Fact reference coverage | 1.000 | 1.000 |
| Unsupported claim rate | 0.000 | 0.000 |
| Planner latency P50 | 1374.098 ms | 1085.918 ms |
| Planner latency P95 | 1794.486 ms | 1511.546 ms |

P50 比 v1 降低 20.97%，P95 降低 15.77%。该开发运行没有证明 schema 必然降低时延，只说明本次固定环境的 v2 没有出现时延回退。

## 修复机制

v2 没有放松服务端 fact_id 校验，而是在模型生成前增加第二层约束：

- `conclusion_status` 由 JSON Schema `const` 固定；
- fact_id 只能从当前 Evidence Packet 的动态 `enum` 中选择；
- `minItems` 和 `maxItems` 固定为事实数；
- `uniqueItems: true` 禁止重复；
- `additionalProperties: false` 禁止夹带自由文本；
- prompt 明确 fact_id 是不可规范化的 opaque identifier。

v1 中稳定出现的连字符转下划线错误在 v2 的 6 个对应重跑中全部消失。15 次原始模型输出见 `reports/raw/ollama-evidence-order-v2-plans.jsonl`。

## 解释边界

这是同一小型开发探针上的 prompt/schema 迭代结果，不是独立测试集、临床质量或泛化能力证明。下一阶段必须冻结不同事实分组的测试集，不能继续用该开发集调参后宣称泛化提升。
