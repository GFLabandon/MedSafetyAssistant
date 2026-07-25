# Source-Aligned Safety Engine Baseline

执行日期：2026-07-25
数据版本：`v1.0.0-alpha.4`
数据集：`eval/safety_engine_dev.jsonl`
样例数：17

## 数据范围

- 9 条来源记录；
- 5 条药品/成分记录；
- 3 条受控上下文；
- 4 条来源对齐事实；
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

## alpha.4 新增覆盖

- `泰诺 + 开车`：命中泰诺产品级活动限制事实；
- `酚麻美敏片 + 操作精密仪器`：经产品别名与 activity context 命中同一事实；
- `感康 + 驾驶`：返回 `no_known_risk_in_scope`，不按共享成分外推泰诺说明书；
- `氯苯那敏 + 驾驶`：药品保持 `out_of_scope`，不把产品限制改写为成分事实。

原 13 条 alpha.3 开发样例保持通过。新增的 ORANGE 是项目风险沟通级别，不是说明书中的
临床分级，也不表示用户必须停药。

## 解释边界

这是 4 条来源对齐事实、17 条开发样例上的确定性回归结果。开发样例与规则、上下文数据
共同迭代，不是锁定测试集，不能用于宣称临床准确率、泛化能力或真实用户效果。项目没有
医生或药师临床审核签名。
