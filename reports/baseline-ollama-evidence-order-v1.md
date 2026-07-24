# Real Ollama Evidence-Planning Baseline: v1

执行日期：2026-07-20

- 数据集：`eval/explanation_model_dev_v1.jsonl`
- 数据版本：`v1.0.0-alpha.2`
- Prompt：`evidence-order-v1`
- 模型：`deepseek-r1:1.5b`
- 模型 digest：`e0979632db5a88d1a53884cb2a941772d10ff5d055aabaa6801c4e36f3a6c2d7`
- 参数：temperature 0、seed 42、num_predict 256、think false、format json
- 代码提交：`5e8103d12e50886592c52c17f0ad01af879b52f5`
- 运行时工作树：clean
- 重复次数：3
- 模型请求：15

## 指标

| 指标 | 结果 |
|---|---:|
| Valid plan rate | 0.600 |
| Fallback rate | 0.400 |
| Valid plan consistency rate | 0.600 |
| Pipeline pass rate | 1.000 |
| Conclusion preservation | 1.000 |
| Fact reference coverage | 1.000 |
| Extractive claim rate | 1.000 |
| Source traceability rate | 1.000 |
| Unsupported claim rate | 0.000 |
| Planner latency P50 | 1374.098 ms |
| Planner latency P95 | 1794.486 ms |

## 失败分析

6 次无效计划全部发生在对乙酰氨基酚重复成分事实。模型把合法 ID：

`fact-duplicate-acetaminophen-001`

稳定改写为：

`fact-duplicate_acetaminophen-001`

该错误在普通重复用药探针和包含未解析提示注入文本的隔离探针中各重复 3 次。原始用户文本没有进入模型 prompt，因此这不是提示注入成功，而是小模型复制 opaque identifier 时的字符替换错误。

服务端拒绝未知 ID 并确定性回退，所有 21 个 case run 仍保留完整 Evidence Packet，流水线安全失败数为 0。

15 条原始模型输出见 `reports/raw/ollama-evidence-order-v1-plans.jsonl`。

## 解释边界

这是小型开发探针上的真实本地模型结果，不是锁定测试集、临床质量或泛化能力结论。该数据集用于 prompt 和结构化输出约束迭代，因此后续 v2 结果必须保留 v1 基线，不得覆盖。
