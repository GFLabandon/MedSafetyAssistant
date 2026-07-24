# Source-Aligned Safety Engine Baseline

执行日期：2026-07-20
数据版本：`v1.0.0-alpha.2`
数据集：`eval/safety_engine_dev.jsonl`
样例数：9

## 数据范围

- 7 条来源记录；
- 4 条药品/成分记录；
- 2 条受控上下文；
- 3 条来源对齐事实；
- 所有事实均为 `source_aligned`，不是 `clinically_reviewed`。

## 指标

| 指标 | 结果 |
|---|---:|
| Conclusion accuracy | 1.000 |
| Fact-set exact match | 1.000 |
| Medication-set exact match | 1.000 |
| Context-set exact match | 1.000 |
| Whole-case exact match | 1.000 |

失败样例：0。

## 覆盖行为

- 泰诺 + 感康：命中来源对齐的对乙酰氨基酚重复成分事实；
- 布洛芬 + 阿司匹林，无用途信息：返回 `insufficient_information`；
- 布洛芬 + 用于心血管保护的阿司匹林：命中带条件的相互作用事实；
- 布洛芬 + 明确的阿司匹林/NSAID 过敏样反应史：命中禁忌事实；
- 布洛芬 + 普通哮喘：不扩大推断反应史，返回 `out_of_scope`；
- 单一已收录药品：返回 `no_known_risk_in_scope`，并明确“不代表安全”；
- 未收录药品：返回 `out_of_scope`；
- 中英文别名及大小写可规范化解析。

## 真实 Neo4j 验收

使用隔离的 Neo4j 5.26.28 和 tmpfs 数据目录连续导入两次：节点及关系计数保持不变。JSON 与 Neo4j Repository 在七类场景中的完整 `EvidencePacket` 一致。测试完成后容器与网络已自动移除。

## 解释边界

这是 3 条来源对齐事实、9 条开发样例上的确定性回归结果。开发样例与规则共同迭代，不是锁定测试集，不能用于宣称临床准确率、泛化能力或真实用户效果。项目没有医生或药师临床审核签名。
