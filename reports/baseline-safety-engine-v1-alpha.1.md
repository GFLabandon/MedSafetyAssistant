# Source-Aligned Safety Engine Baseline

执行日期：2026-07-20
数据版本：`v1.0.0-alpha.1`
数据集：`eval/safety_engine_dev.jsonl`
样例数：7

## 指标

| 指标 | 结果 |
|---|---:|
| Conclusion accuracy | 1.000 |
| Fact-set exact match | 1.000 |
| Whole-case exact match | 1.000 |

失败样例：0。

## 覆盖行为

- 泰诺 + 感康：命中来源对齐的对乙酰氨基酚重复成分事实；
- 布洛芬 + 阿司匹林，无用途信息：返回 `insufficient_information`；
- 布洛芬 + 用于心血管保护的阿司匹林：命中带条件的相互作用事实；
- 单一已收录药品：返回 `no_known_risk_in_scope`，并明确“不代表安全”；
- 未收录药品：返回 `out_of_scope`；
- 英文别名大小写：可以规范化解析。

## 解释边界

这是两个来源对齐事实、7 条开发样例上的确定性回归结果。它不是锁定测试集结果，不测量开放域医学正确性，也没有经过医生或药师的临床审核。
