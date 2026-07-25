# P2 alpha.4 泰诺活动限制来源审计

日期：2026-07-25
候选：`P2-F02`
数据版本：`v1.0.0-alpha.4`

## 准入结论

`P2-F02` 已同时通过来源门、模型门和防外推测试，进入 alpha.4。正式事实主体是具体产品
“泰诺”，predicate 为 `ACTIVITY_RESTRICTION`；没有把说明书警示改写为氯苯那敏成分
禁忌，也没有外推到感康。

## 来源复核

来源：上海强生制药有限公司《泰诺®酚麻美敏片说明书》，由西安杨森官方网站提供。

- URL：
  `https://www.xian-janssen.com.cn/sites/default/files/PDF/8_tai_nuo_20210319_fen_ma_mei_min_pian_shuo_ming_shu_.pdf`
- 2026-07-25 重新下载的原始 PDF SHA-256：
  `e41e047abc6810d87068298254da2a461cf92b690a5e236a9792bce7412d4045`
- 文件：8 页 PDF；
- PDF 第 1 页 `[药品名称]`：通用名称酚麻美敏片，商品名称泰诺；
- PDF 第 3 页 `[注意事项]` 第 9 项：服药期间的驾驶、高空、机械和精密仪器活动限制；
- PDF 第 8 页：国药准字 `H20010115`，说明书修订日期 2021-03-19。

仓库不复制或提交原始 PDF，只保存 URL、释义、定位和哈希。

## 正式数据

- SourceRecord：`source-xian-janssen-tylenol-label-2021`
- Context：
  `context-driving-or-hazardous-operation`
- Fact：
  `fact-activity-restriction-tyno-driving-machinery-001`
- Subject：`泰诺`，`subject_kind=medication`
- Object：`驾驶或从事高空、机械及精密仪器作业`，`object_kind=context`
- Severity：`ORANGE`

ORANGE 仅表示项目界面应清楚提示避免该活动；它不是说明书或监管机构提供的临床严重度
等级，也不表示用户必须停药。

## 防外推验收

- `泰诺 + 开车`：命中正式产品事实；
- `酚麻美敏片 + 操作精密仪器`：通过产品别名命中同一事实；
- `感康 + 驾驶`：不继承泰诺产品说明书，返回范围内未命中；
- `氯苯那敏 + 驾驶`：不升级为成分事实，药品保持范围外；
- `泰诺` 未提供活动上下文：不主动触发该条件事实。

## 自动化边界

- 17 条开发样例全部精确匹配；
- 普通 pytest：`148 passed, 5 skipped`；
- 隔离 Neo4j 5.26.28：`5 passed`；
- 两次导入计数一致：9 Source、5 Medication、15 MedicationAlias、10 Ingredient、
  3 Context、15 ContextAlias、4 Fact；
- JSON 与 Neo4j 对泰诺正例、感康负例和氯苯那敏范围外用例返回相同
  `EvidencePacket`；
- `fact-provenance-v2` 返回泰诺稳定 medication ID、活动上下文、官方来源和 alpha.4
  快照；
- 绑定数据提交 `52ab9c8bce0e233e7743501b63bbf2672ed5689f` 的
  [`neo4j-query-plan-v1-alpha4.json`](neo4j-query-plan-v1-alpha4.json) 证明七条只读查询
  均命中索引，八个 `Safety*` 索引均为 `ONLINE`，且没有计划通知；
- 开发集与规则共同迭代，不是锁定测试或临床准确率；
- PROFILE 的 DB hits 和耗时只用于小图查询形状诊断，不是性能或可扩展性基准；
- 测试结束后专用容器、网络和 tmpfs 数据已移除。
