# Locked Opaque Fact-ID Planner Test

执行日期：2026-07-20

- 数据集：`eval/opaque_id_test_v1.jsonl`
- SHA-256：`ced2daf4cabbc4cb4c1d0238b35e352a485515a9764207d89fdc2c4035d99f5a`
- 数据集版本：`opaque-id-test-v1`
- Prompt：`evidence-order-v2`
- 模型：`deepseek-r1:1.5b`
- 模型 digest：`e0979632db5a88d1a53884cb2a941772d10ff5d055aabaa6801c4e36f3a6c2d7`
- 代码提交：`2f40fbda211f79aba6569acbc9d96a1b14283f6f`
- 运行时工作树：clean
- 12 条锁定用例，3 次重复，36 次模型请求

首次相同命令已完成，但执行通道没有捕获 stdout。本报告来自数据集、prompt 和参数均未修改的重复采集；没有依据首次运行结果调参。

## 指标

| 指标 | 结果 |
|---|---:|
| Valid plan rate | 0.833 |
| Exact severity order rate | 0.667 |
| Character-exact reference rate | 0.900 |
| Raw plan consistency rate | 1.000 |
| Planner latency P50 | 946.787 ms |
| Planner latency P95 | 1489.869 ms |

## 失败分析

### JSON Schema 未保证 ID 唯一性

两个相似 ID 场景各连续失败 3 次：

- 连字符与下划线仅一字符不同的 ID 被模型复制成两个相同的连字符 ID；
- 只在大小写上不同的 ID 被模型复制成两个相同的小写 ID。

这说明当前 Ollama structured output 接受了违反 `uniqueItems: true` 的结果。服务端完整集合与重复 ID 校验仍能拒绝它们，因此 JSON Schema 不能替代应用层验证。

### 严重度排序不可靠

两个多事实场景各连续 3 次返回完整、合法的 ID 集合，但没有遵守 `FATAL > RED > ORANGE > INFO`。现有生产校验只检查集合完整性，尚未验证顺序策略，这是本次测试发现的服务端缺口。

全部 36 条原始计划见 `reports/raw/ollama-opaque-id-test-v1-plans.jsonl`。

## 解释边界

这是冻结的合成 contract test，只评价 opaque ID 复制和严重度排序，不包含医学事实，不衡量临床质量。该 v1 测试结果必须保留；后续安全修复不能把它覆盖为通过结果。
