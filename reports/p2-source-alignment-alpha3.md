# P2 alpha.3 来源对齐审计

日期：2026-07-25
候选：`P2-A01`、`P2-F02`

## 结论

| 候选 | 来源门 | 模型门 | 决定 |
|---|---|---|---|
| `P2-A01` 对乙酰氨基酚英文别名 | 通过 | 通过 | 进入 alpha.3 |
| `P2-F02` 泰诺与驾驶/机械操作 | 通过 | 未通过 | 暂缓，不创建事实 |

本批没有把 legacy 主张直接升级为正式事实。

## P2-A01：通过

来源链：

1. 国家卫生健康委员会《国家基本药物目录（2018年版）》：
   - URL：`https://www.nhc.gov.cn/ewebeditor/uploadfile/2018/10/20181025195256627.pdf`
   - 原始 PDF SHA-256：
     `f4d8085d55ad24f2dc7c5f55b338d4890680d52b2bae27c44a72c82a298ebe9e`
   - 定位：PDF 第 27 页、目录印刷页 13，列出“对乙酰氨基酚 / Paracetamol”。
2. FDA `Acetaminophen` 页面：
   - URL：`https://www.fda.gov/drugs/safe-use-over-counter-pain-relievers-and-fever-reducers/acetaminophen`
   - 定位：`What is Acetaminophen?`，说明美国以外通常称为 `paracetamol`。

因此 alpha.3 新增成分药品“对乙酰氨基酚”，只接受 `paracetamol` 与
`acetaminophen`。`扑热息痛` 没有纳入，避免由常识替代本批来源证据。

## P2-F02：来源通过，模型门暂缓

找到上海强生制药有限公司泰诺酚麻美敏片官方说明书：

- URL：
  `https://www.xian-janssen.com.cn/sites/default/files/PDF/8_tai_nuo_20210319_fen_ma_mei_min_pian_shuo_ming_shu_.pdf`
- 原始 PDF SHA-256：
  `e41e047abc6810d87068298254da2a461cf92b690a5e236a9792bce7412d4045`
- 说明书修订日期：2021-03-19；
- 定位：PDF 第 3 页 `[注意事项]` 第 9 项，明确服药期间不得驾驶机、车、船，或从事
  高空、机械作业及操作精密仪器；
- PDF 第 2 页列出“可能引起嗜睡”，第 6 页再次说明马来酸氯苯那敏可能引起嗜睡。

当前 `FactRecord` 和 Neo4j P2 图要求事实主体必须是 `SafetyIngredient`。该说明书支持
的是“泰诺产品在用药期间的活动限制”，不能无损改写成“氯苯那敏成分禁忌”。因此：

- 不新增 `CONTRAINDICATED_IN`；
- 不把警示改写为成分级禁忌；
- 不外推到感康；
- 后续先设计 product-subject fact 与 `ACTIVITY_RESTRICTION` 类型，再用独立工程 PR
  和数据 PR 完成。

## 验收边界

- alpha.3 只扩充实体解析覆盖，不扩充医学风险事实；
- 新增 4 条开发样例包含两个别名正例、一个单药边界和一个未审核别名负例；
- 数据版本、校验和、数据卡、Safety Engine 基线及 JSON/Neo4j 等价测试必须一起更新。

## 自动化结果

- 普通 pytest：`141 passed, 3 skipped`；
- 隔离 Neo4j 5.26.28：`3 passed, 141 deselected`；
- 两次导入计数一致：8 Source、5 Medication、11 MedicationAlias、10 Ingredient、
  2 Context、8 ContextAlias、3 Fact；
- `paracetamol + 泰诺` 的完整 `EvidencePacket` 与 JSON Repository 一致；
- 绑定数据提交 `06b60eabc184396a460a870e65fbdbe56670619c` 的
  [`neo4j-query-plan-v1-alpha3.json`](neo4j-query-plan-v1-alpha3.json) 证明六条注册
  只读查询继续命中索引，八个 `Safety*` 索引均为 `ONLINE`，且没有计划通知；
- 测试结束后专用容器和网络已移除。
