# P2 第一批：事实节点知识图谱验收

日期：2026-07-25
分支：`codex/p2-knowledge-graph`
基线：`main@0e360c0`

## 变更范围

- `8785eb4`：公开仓库忽略规则、敏感/生成文件审计和 CI 门禁；
- `cb76204`：事实节点图模型、关系遍历、事务内完整性审计和 Docker 集成测试。

本批没有修改 `data/v1/`、冻结评测集、医学事实、来源内容或 Ollama prompt。

## 图模型结果

现有 `v1.0.0-alpha.2` 被重建为：

| 类型 | 数量 |
|---|---:|
| `SafetySource` | 7 |
| `SafetyMedication` | 4 |
| `SafetyIngredient` | 10 |
| `SafetyContext` | 2 |
| `SafetyFact` | 3 |
| `SafetyKnowledgeSnapshot` | 1 |
| `HAS_ACTIVE_INGREDIENT` | 11 |
| `SUPPORTED_BY` | 11 |
| `SUBJECT` | 3 |
| `OBJECT` | 3 |
| `APPLIES_IN` | 2 |
| `BELONGS_TO` | 3 |

相互作用事实的适用条件现在也通过 `APPLIES_IN` 表达，因此该关系由 P1 的 1 条增加为
2 条；医学事实本身没有增加。

## 自动化验收

| 检查 | 结果 | 边界 |
|---|---|---|
| 全量普通 pytest | `126 passed, 2 skipped` | 2 项需显式启动隔离 Neo4j |
| 真实 Neo4j 集成 | `2 passed, 126 deselected` | Neo4j 5.26.28，隔离端口 17687 |
| JSON/Neo4j 等价 | 7 类用例完全一致 | 比较完整 `EvidencePacket` |
| 重复导入 | 两次节点与关系计数一致 | 可重建投影，不代表生产迁移 |
| 损坏检测 | 删除 1 条 `SUBJECT` 后审计失败 | 报告缺边与孤立事实 |
| V1 校验和 | 5/5 通过 | 权威数据与评测样例未修改 |
| catalog 校验 | 7 Source、4 Medication、2 Context、3 Fact | 新增端点可建图校验 |
| 前端构建 | Vite 7.3.6 通过 | 26 modules transformed |
| 浏览器契约 | 4/4 通过 | API fixture，不是真实浏览器端到端依赖 |
| 公开仓库审计 | 通过 | 131 个已跟踪文件，单文件上限 5 MiB |
| GitHub Actions | 3/3 通过 | Repository、Backend、Frontend |
| `git diff --check` | 通过 | 无空白错误 |

真实 Neo4j 验收使用 `docker-compose.integration.yml` 创建专用容器和网络，测试完成后
均已自动移除。它没有读取或修改用户其他容器、卷或本机 Neo4j 安装。

## 已验证的失败边界

- 未知 predicate 或无法映射为成分/上下文的事实在 catalog 加载阶段被拒绝；
- 导入后的节点、关系、来源引用、适用条件或数据版本与 JSON 不一致时，重建事务失败；
- 已有投影可以用 `python scripts/import_v1_to_neo4j.py --audit-only` 只读复核；
- Repository 只沿 `SUBJECT`/`OBJECT` 关系匹配风险，并要求事实属于当前快照；
- Neo4j 不可用、快照缺失、记录损坏和混合版本仍映射为
  `knowledge_unavailable`，不会成为“未发现风险”。

## 尚未完成

- 当前仍只有 3 条 `source_aligned` 事实，没有临床审核签名；
- 尚未记录 `EXPLAIN/PROFILE` 查询计划或扩充知识内容；
- 内容扩充必须另行完成来源审核、数据冻结和评测，不能直接迁移 legacy 关系。
