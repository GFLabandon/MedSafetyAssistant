# V1 alpha.2 数据卡

冻结日期：2026-07-20
数据版本：`v1.0.0-alpha.2`

## 用途与范围

该快照只用于 MedSafetyAssistant 的工程验证和来源可追溯性演示。它覆盖 4 条药品/成分记录、2 个受控上下文和 3 条风险事实：对乙酰氨基酚重复成分、布洛芬与用于心血管保护的阿司匹林之间的条件性相互作用，以及严格限定反应史下的布洛芬禁忌。

它不适合评估真实世界总体用药安全，不得用于诊断、治疗、停药、换药或剂量决策。

## 来源与审核状态

- 7 条来源记录均包含可访问 URL、访问日期和项目内来源复核记录；
- 4 条药品/成分记录和 3 条事实均为 `source_aligned`；
- 项目没有医生或药师签名，任何记录都不是 `clinically_reviewed`；
- `reviewed` 表示项目工程流程已检查字段与来源定位，不表示临床审核。

详细来源与迁移边界见 [`SOURCE_ALIGNMENT.md`](SOURCE_ALIGNMENT.md) 和 [`../reports/contraindication-source-audit-v1.md`](../reports/contraindication-source-audit-v1.md)。

## 评测边界

`eval/safety_engine_dev.jsonl` 含 9 条开发样例，与规则共同迭代，只用于回归。当前 1.000 的确定性指标不是锁定测试集结果、模型泛化结果或临床准确率。基线见 [`../reports/baseline-safety-engine-v1-alpha.2.md`](../reports/baseline-safety-engine-v1-alpha.2.md)。

## 完整性校验

从仓库根目录执行：

```bash
shasum -a 256 -c data/v1/checksums.sha256

/opt/homebrew/Caskroom/miniconda/base/envs/medsafety/bin/python \
  scripts/validate_v1_data.py
```

`checksums.sha256` 同时冻结 4 个权威 JSON 文件和对应开发集。任何内容变更都必须提升数据版本、重新生成基线并更新本数据卡；不能只改校验和。

## 已知限制

- 覆盖药品、剂型、上下文和风险类型极少；
- 不包含剂量、年龄、孕产、肝肾功能等个体化判断；
- 来源可能更新，当前快照不会自动同步；
- 来源对齐不能替代临床专家复核；
- 空匹配只能表达“当前范围内未命中”，不能表达“安全”。
