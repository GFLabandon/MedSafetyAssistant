# MedSafetyAssistant 评测协议

版本：0.1-draft
更新时间：2026-07-20

## 1. 目的

评测的目标不是证明系统“懂医学”，而是分别测量：

1. 是否正确识别问题中的药品和状态；
2. 是否检索到预期的审核事实；
3. 是否按确定性规则形成正确风险；
4. 是否在证据不足时拒绝给出确定性结论；
5. LLM 是否只解释证据而没有新增医学事实；
6. 外部依赖故障时是否安全降级；
7. 结果是否可以在固定环境中复现。

## 2. 数据分层

- `dev`：可用于调试和错误分析；
- `test`：在协议和标签冻结后锁定，只用于阶段验收；
- 同一事实的近义改写不得跨 dev/test；
- 当前第一批样例全部是 `legacy_unreviewed`，只能评测实体抽取等工程行为；
- 只有 `source_aligned` 或 `clinically_reviewed` 样例才能进入正式安全指标。

## 3. 样例结构

每条 JSONL 样例必须通过 `medsafety.contracts.EvaluationCase` 校验，包含：

- 稳定 `case_id`；
- split、category、question；
- 可选的历史对话；
- 期望药品和状态；
- 可选结论状态和必要 fact_id；
- 标签审核状态、tags 和说明。

当前 legacy 样例不得凭现有 Cypher 文本填入正式安全结论。医学标签必须在来源对齐后另行提交。

## 4. 运行器

第一阶段实现：

- `rule_entities`：离线调用当前 `exact_entity_extraction`，评测实体集合。

后续实现：

- `current_pipeline`：真实 Neo4j + Redis + Ollama 的当前全流程；
- `pure_llm`：无项目事实注入的模型基线；
- `prompt_llm`：仅固定安全 Prompt；
- `safety_engine`：不调用 LLM 的确定性事实与风险基线；
- `full_pipeline`：Evidence Packet + 受约束生成。

V1 已实现 `evidence-order-v1` 的第一层护栏测试：模型只规划 fact_id 顺序，服务端检查完整引用集合并确定性渲染。该测试覆盖未知 ID、漏引、重复引用、结论篡改、额外字段和 planner 故障；它是工程契约验证，不替代真实 Ollama 的重复运行评测。

脚本化基线保存在 `reports/baseline-explanation-guardrails-v1.{json,md}`。报告记录数据集 SHA-256、代码 commit、工作树状态、数据版本和 prompt 版本；保存结果还会由全量测试与当前 runner 指标比对。

真实 Ollama 开发基线保存在 `reports/baseline-ollama-evidence-order-v1.{json,md}` 和 v2 对应文件中，15 条原始计划分别保存在 `reports/raw/`。v1 暴露了 fact_id 字符替换问题，v2 用动态 JSON Schema 修复；两者使用同一数据集和模型 digest。该对比属于开发调优证据，不能作为独立测试集结果。

`current_pipeline`、`pure_llm`、`prompt_llm` 和 `full_pipeline` 必须记录模型名称、模型摘要、参数、prompt 版本和依赖健康状态。依赖不健康时不得生成正式报告。

## 5. 指标

### 5.1 实体指标

- micro Precision / Recall / F1；
- 药品集合 exact match；
- 状态集合 exact match；
- 每个失败样例的 false positive / false negative。

实体比较使用集合，避免当前实现中 set 转 list 的顺序影响结果。

### 5.2 安全指标

仅对已审核标签计算：

- expected fact_id 命中率；
- 风险 Precision / Recall；
- 严重风险 Recall；
- 结论状态准确率；
- 未收录/信息不足正确拒答率；
- 无证据医学事实率；
- 风险事实引用覆盖率。

### 5.3 工程指标

- 检索、首 token 和总耗时 P50/P95；
- 外部依赖分别故障时的降级通过率；
- 并行会话隔离通过率；
- SSE 事件契约通过率。

## 6. 对照与重复运行

正式报告至少比较纯 LLM、固定 Prompt LLM、Safety Engine 和完整流程。生成式运行在固定参数下至少重复 3 次，报告均值、最差值和失败样例，不只报告最佳结果。

## 7. 防止数据泄漏

- 先冻结测试事实分组，再生成措辞改写；
- 同一 fact_id 及其近义改写只属于一个 split；
- 不把 test 失败样例直接加入 Prompt；
- 发生测试集修订时递增数据版本并说明原因；
- 不使用被测 LLM 生成未经人工核对的标准答案。

`opaque-id-test-v1` 是独立于医学事实的锁定 contract test：它在 `evidence-order-v2` 完成后冻结，只验证未见 opaque ID 的字符保持、完整引用和严重度排序。首次运行后禁止据此调 prompt；它也不能替代按医学 fact_id 分组的临床内容测试集。

首次可审计运行结果保存在 `reports/baseline-ollama-opaque-id-test-v1.{json,md}` 和 `reports/raw/`：36 次请求中有效计划率 0.833、精确严重度顺序率 0.667。失败用于增加服务端严重度顺序不变量，但没有修改锁定数据或据此调 prompt；新的脚本化 `explanation-guardrails-v2` 验证所有不变量。

## 8. 报告要求

每份报告必须记录：

- git commit；
- 数据集版本和样例数；
- 数据/事实版本；
- runner、模型、参数和 prompt 版本；
- 环境与依赖健康状态；
- 汇总指标；
- 失败样例和错误分类；
- 已知限制。

当前仍无正式端到端基线：真实 Ollama 只评测了 V1 Evidence Packet 解释规划，Neo4j、Redis、实体抽取和 legacy 查询链路没有在同一次受控运行中验收。
