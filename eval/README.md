# Evaluation Dataset

当前数据版本：`dev-v0.1`
标签状态：`legacy_unreviewed`

`dev_cases.jsonl` 包含 18 条用于评测当前实体抽取行为的开发样例。它覆盖显式药名、中文别名、英文别名、未知实体、子串误报和历史追问。

这些样例只提供实体层工程标签，没有正式医学结论或风险 fact_id。不得用它计算或宣传医学准确率。

运行离线基线：

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/medsafety/bin/python scripts/evaluate.py \
  --dataset eval/dev_cases.jsonl \
  --runner rule_entities \
  --format markdown
```

校验规则由 `medsafety.contracts.EvaluationCase` 定义。正式 test split 将在来源对齐并按 fact_id 分组后建立，防止同一事实的改写跨 split 泄漏。

`safety_engine_dev.jsonl` 是独立的 `source_aligned` 小型开发集，覆盖 V1 alpha.2 的 3 条事实。运行：

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/medsafety/bin/python scripts/evaluate.py \
  --dataset eval/safety_engine_dev.jsonl \
  --runner safety_engine \
  --data-dir data/v1 \
  --format markdown
```

该开发集用于确定性回归，不是锁定测试集，也不代表临床准确率。

`explanation_guardrails_v1.jsonl` 包含 9 个脚本化 planner 场景，验证有效重排、未知/遗漏/重复 fact_id、结论篡改、额外医学字段、错误形状、依赖故障和显式禁用 LLM。运行：

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/medsafety/bin/python scripts/evaluate.py \
  --dataset eval/explanation_guardrails_v1.jsonl \
  --runner explanation_guardrails \
  --data-dir data/v1 \
  --format markdown
```

这是服务端护栏的对抗性回归集，不调用真实模型，也不表示模型或临床质量。

`explanation_model_dev_v1.jsonl` 是真实 Ollama 开发探针。它包含 5 个实际模型规划场景和 2 个必须跳过模型的非风险场景，运行 3 次会产生 15 次模型请求：

```bash
/opt/homebrew/Caskroom/miniconda/base/envs/medsafety/bin/python scripts/evaluate.py \
  --dataset eval/explanation_model_dev_v1.jsonl \
  --runner ollama_explanation \
  --model deepseek-r1:1.5b \
  --repetitions 3 \
  --timeout-seconds 120 \
  --format json
```

该数据集已经用于 `evidence-order-v1` 到 v2 的迭代，只能作为开发集；后续不能把它改称独立测试集。
