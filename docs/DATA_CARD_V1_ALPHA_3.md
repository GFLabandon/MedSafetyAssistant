# V1 alpha.3 数据卡

冻结日期：2026-07-25
数据版本：`v1.0.0-alpha.3`

## 用途与范围

该快照继续只用于 MedSafetyAssistant 的工程验证和来源可追溯性演示。风险覆盖仍是 3 条
来源对齐事实；alpha.3 只增加一条对乙酰氨基酚成分药品记录，使
`paracetamol`、`acetaminophen` 可以确定性解析为“对乙酰氨基酚”。

它不适合评估真实世界总体用药安全，不得用于诊断、治疗、停药、换药或剂量决策。

## 相对 alpha.2 的变化

- 来源从 7 条增加到 8 条，新增国家卫健委《国家基本药物目录（2018年版）》；
- 药品/成分记录从 4 条增加到 5 条；
- 增加 `medication-acetaminophen-substance`；
- 通过国家卫健委目录印刷页 13 与 FDA Acetaminophen 页面建立
  “对乙酰氨基酚 ↔ paracetamol ↔ acetaminophen”来源链；
- `扑热息痛` 没有在本批来源链中取得同等级精确定位，继续保持未收录；
- 上下文仍为 2 个，风险事实仍为 3 条，没有增加或改变医学结论。

## 来源与审核状态

- 8 条来源记录均包含可访问 URL、访问日期和项目内来源复核记录；
- 5 条药品/成分记录和 3 条事实均为 `source_aligned`；
- 项目没有医生或药师签名，任何记录都不是 `clinically_reviewed`；
- `reviewed` 表示项目工程流程已检查字段与来源定位，不表示临床审核。

国家卫健委原始 PDF 的 SHA-256 为
`f4d8085d55ad24f2dc7c5f55b338d4890680d52b2bae27c44a72c82a298ebe9e`。名称映射位于
PDF 第 27 页、目录印刷页 13；FDA 页面 `What is Acetaminophen?` 段落负责连接
`acetaminophen` 与 `paracetamol`。

## 评测边界

`eval/safety_engine_dev.jsonl` 含 13 条开发样例，其中 4 条是 alpha.3 新增别名正例、
单药边界和未审核别名负例。当前 1.000 的确定性指标是共同迭代后的开发回归，不是锁定
测试集结果、模型泛化结果或临床准确率。

基线见
[`baseline-safety-engine-v1-alpha.3.md`](../reports/baseline-safety-engine-v1-alpha.3.md)。

## 完整性校验

```bash
shasum -a 256 -c data/v1/checksums.sha256
python scripts/validate_v1_data.py
```

`checksums.sha256` 同时冻结 4 个权威 JSON 文件和对应开发集。任何内容变更都必须提升
数据版本、重新生成基线并更新数据卡；不能只改校验和。

## 已知限制

- `paracetamol` 和 `acetaminophen` 只解析到成分药品记录，不推断剂量、剂型或品牌；
- `扑热息痛` 仍不在正式别名表中；
- 泰诺驾驶/机械操作警示已找到产品级说明书，但当前事实模型不能表达产品作为主体，
  因此没有进入 alpha.3；
- 来源可能更新，当前快照不会自动同步；
- 来源对齐不能替代临床专家复核；
- 空匹配只能表达“当前范围内未命中”，不能表达“安全”。
