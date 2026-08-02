# Evaluation Dataset

当前数据版本：`dev-v0.1`
标签状态：`legacy_unreviewed`

`dev_cases.jsonl` 包含 18 条用于评测当前实体抽取行为的开发样例。它覆盖显式药名、中文别名、英文别名、未知实体、子串误报和历史追问。

这些样例只提供实体层工程标签，没有正式医学结论或风险 fact_id。不得用它计算或宣传医学准确率。

运行离线基线：

```bash
python scripts/evaluate.py \
  --dataset eval/dev_cases.jsonl \
  --runner rule_entities \
  --format markdown
```

校验规则由 `medsafety.contracts.EvaluationCase` 定义。正式 test split 将在来源对齐并按 fact_id 分组后建立，防止同一事实的改写跨 split 泄漏。

`safety_engine_dev.jsonl` 是独立的 `source_aligned` 小型开发集，覆盖 V1 alpha.4 的
4 条事实、来源对齐别名和产品活动限制边界。运行：

```bash
python scripts/evaluate.py \
  --dataset eval/safety_engine_dev.jsonl \
  --runner safety_engine \
  --data-dir data/v1 \
  --format markdown
```

该开发集用于确定性回归，不是锁定测试集，也不代表临床准确率。

`tool_shadow_v1.jsonl` 冻结 60 条不执行真实工具的 typed-tool 选择样例：40 条开发集和
20 条锁定测试集。模型只能提出下一工具调用，评测器永远不会执行该 proposal。
`tool_shadow_v1.sha256` 冻结 JSONL 的逐字节内容。开发阶段只允许运行 `dev`；prompt 和
adapter 固定后才运行一次 `test`，并保留失败，不得针对锁定结果继续调优。

开发集真实 Ollama shadow 运行命令：

```bash
python scripts/evaluate_tool_shadow.py \
  --dataset eval/tool_shadow_v1.jsonl \
  --split dev \
  --model qwen3:4b-instruct \
  --format markdown \
  --output reports/baseline-ollama-tool-shadow-dev-v1.md \
  --records-output reports/raw/ollama-tool-shadow-dev-v1-records.json
```

锁定集还要求显式传入 `--allow-locked-test`，以避免在 prompt/adapter 开发中误用。该
runner 只记录并严格验证模型 proposal，不会把它传给工具注册表，也不会因模型选择而
访问 Neo4j、Redis 或 Safety Engine。

`server-bound-tool-name-v1` 是 locked shadow 失败后的独立收窄方案。模型只接收最小
路由状态并提议工具名；参数由服务端从可信状态构造。当前只允许在既有 `dev` split 做
模型 A/B，不把已经运行过的 locked split 重新包装成新测试集：

```bash
python scripts/evaluate_server_bound_tools.py \
  --dataset eval/tool_shadow_v1.jsonl \
  --split dev \
  --model qwen3:4b-instruct \
  --format markdown
```

报告同时给出原始工具名准确率、确定性回退率和服务端绑定调用正确率；最后一项不能替代
模型质量指标。runner 不执行任何工具，也不保存问题文本或参数值。

`explanation_guardrails_v1.jsonl` 包含 9 个脚本化 planner 场景，验证有效重排、未知/遗漏/重复 fact_id、结论篡改、额外医学字段、错误形状、依赖故障和显式禁用 LLM。运行：

```bash
python scripts/evaluate.py \
  --dataset eval/explanation_guardrails_v1.jsonl \
  --runner explanation_guardrails \
  --data-dir data/v1 \
  --format markdown
```

这是服务端护栏的对抗性回归集，不调用真实模型，也不表示模型或临床质量。

`explanation_guardrails_v2.jsonl` 在 v1 基础上增加严重度逆序攻击，并把合法计划改为 `RED` 先于 `ORANGE`。当前代码回归使用 v2；v1 与其报告作为新增严重度规则之前的历史基线保留。

`explanation_model_dev_v1.jsonl` 是真实 Ollama 开发探针。它包含 5 个实际模型规划场景和 2 个必须跳过模型的非风险场景。下面命令只用于复现历史基线，需要临时重新拉取现已删除的旧模型；当前单模型验收请使用 `qwen3:4b-instruct`：

```bash
python scripts/evaluate.py \
  --dataset eval/explanation_model_dev_v1.jsonl \
  --runner ollama_explanation \
  --model deepseek-r1:1.5b \
  --repetitions 3 \
  --timeout-seconds 120 \
  --format json
```

该数据集已经用于 `evidence-order-v1` 到 v2 的迭代，只能作为开发集；后续不能把它改称独立测试集。

`opaque_id_test_v1.jsonl` 是在 v2 prompt/schema 完成后冻结的合成 contract test，SHA-256 为 `ced2daf4cabbc4cb4c1d0238b35e352a485515a9764207d89fdc2c4035d99f5a`。它只测试未见 fact_id 的逐字符复制、完整集合、严重度排序和三轮一致性，不包含医学事实。下面仍保留首次历史运行所用模型，复现时需要临时重新拉取：

```bash
python scripts/evaluate.py \
  --dataset eval/opaque_id_test_v1.jsonl \
  --runner ollama_opaque_ids \
  --model deepseek-r1:1.5b \
  --repetitions 3 \
  --timeout-seconds 120 \
  --format json
```

首次真实运行后，无论结果是否通过，都不得再用该版本调 prompt。任何内容或期望顺序修改必须创建新的数据集版本，并保留 v1 原始报告。
