# P2 产品级事实模型验收

日期：2026-07-25
工程提交：`80f1bcfd467e53490de189d06aba847998bdd3ba`
正式数据版本：`v1.0.0-alpha.3`（未修改）

## 完成范围

- `FactRecord` 增加向后兼容的 `subject_kind`、`object_kind`；
- 新增严格的
  `ACTIVITY_RESTRICTION: Medication(product) → Context(activity)` 事实形状；
- JSON 与 Neo4j Repository 增加按稳定 medication ID 查询产品活动限制的方法；
- Safety Engine 只在活动上下文被显式解析时查询产品级限制；
- Neo4j 导入器、完整性审计和事实溯源允许 Medication 主体；
- 溯源响应升级为 `fact-provenance-v2`；
- 查询计划注册表从 6 条增加到 7 条。

本批没有修改 `data/v1/`、校验和或评测集，没有创建泰诺正式活动限制事实。测试使用
`example.invalid` 来源和明确标记的 test-only 事实，避免测试夹具被误解为正式医学内容。

## 自动化验收

| 检查 | 结果 | 边界 |
|---|---:|---|
| 普通 pytest | `145 passed, 5 skipped` | 5 项需要显式启动隔离 Neo4j |
| 隔离 Neo4j 5.26.28 | `5 passed` | tmpfs 数据目录，结束后已删除 |
| alpha.3 校验和 | 5/5 通过 | 正式数据没有变化 |
| catalog 校验 | 8 Source、5 Medication、2 Context、3 Fact | 仍为 alpha.3 |
| PROFILE 查询 | 7/7 使用索引 | 小型图诊断，不是性能基准 |
| Safety 索引 | 8/8 `ONLINE` | 隔离 Neo4j |
| PROFILE 通知 | 0 | 仅注册只读查询 |

机器可读 PROFILE 证据：
[`neo4j-query-plan-product-facts-v1.json`](neo4j-query-plan-product-facts-v1.json)。

## 真实图谱场景

隔离集成测试额外构造一条只存在于内存的测试事实：

```text
SafetyFact(test-only)
  -[:SUBJECT]-> SafetyMedication(泰诺)
  -[:OBJECT]-> SafetyContext(驾驶或操作机械)
  -[:APPLIES_IN]-> SafetyContext(驾驶或操作机械)
```

验收结果：

- JSON 与 Neo4j Safety Engine 返回完全相同的 `EvidencePacket`；
- `fact-provenance-v2` 返回
  `kind=medication`、`identifier=medication-tyno-cold-tablet-cn`、`name=泰诺`；
- 把 `SUBJECT` 人为改连到 `SafetyIngredient` 后，审计报告
  `subject_property_mismatches=1`；
- 原有 3 条 Ingredient 主体事实仍可无改 JSON 重建和查询。

## 停止条件

产品级工程模型已通过，可以进入独立数据批。下一批仍必须：

- 使用已核验的泰诺官方产品说明书，而不是 legacy 来源名称；
- 新增 activity context、SourceRecord 和正式事实时提升数据版本并重算校验和；
- 不把产品限制改写为氯苯那敏成分禁忌；
- 不外推到感康；
- 增加正例、未询问活动时的边界和相似产品负例后再更新开发基线。
