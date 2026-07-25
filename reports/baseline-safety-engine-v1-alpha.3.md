# Source-Aligned Safety Engine Baseline

执行日期：2026-07-25
数据版本：`v1.0.0-alpha.3`
数据集：`eval/safety_engine_dev.jsonl`
样例数：13

## 数据范围

- 8 条来源记录；
- 5 条药品/成分记录；
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

## alpha.3 新增覆盖

- `paracetamol + 泰诺`：解析为“对乙酰氨基酚 + 泰诺”并命中既有重复成分事实；
- `acetaminophen + 感康`：解析为“对乙酰氨基酚 + 感康”并命中同一事实；
- 单独输入 `paracetamol`：返回 `no_known_risk_in_scope` 并保留“不代表安全”限制；
- 输入未通过来源门的“扑热息痛”：返回 `out_of_scope`。

原 9 条 alpha.2 开发样例保持通过。风险事实数量、结论措辞和严重度均未变化。

## 解释边界

这是 3 条来源对齐事实、13 条开发样例上的确定性回归结果。开发样例与规则、别名数据共同
迭代，不是锁定测试集，不能用于宣称临床准确率、泛化能力或真实用户效果。项目没有医生
或药师临床审核签名。
