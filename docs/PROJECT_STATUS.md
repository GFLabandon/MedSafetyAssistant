# MedSafetyAssistant 项目状态

更新时间：2026-07-24
当前阶段：P0——公开入口与自动化质量门
状态：本地质量门通过；远程结果以面向 `main` 的 PR checks 为准

## 当前目标

将已经完成的 Evidence Packet、Safety Engine、Neo4j Repository 和真实模型失败证据
整理为招聘者可以从默认 GitHub 入口直接验证的 AI 应用项目。当前阶段不改变医学数据、
不扩展 Agent，也不把 legacy React 页面描述为 V1 正式链路。

## P0 公开可见性进展

- [x] 新增 `.github/workflows/quality.yml`，在 PR 和 `main` push 上运行仓库差异、
  V1 校验和、catalog 校验、离线 pytest 和前端生产构建；
- [x] README 首屏改为项目问题、核心架构、真实指标、解释边界和三条 V1 API 演示；
- [x] README 删除“推荐更大模型”等无评测依据的表述，并明确当前不是 ReAct、MCP、
  多 Agent、临床系统或生产高并发系统；
- [x] 明确 V1 API 是正式可验证入口，React 仍是使用共享 session 的 legacy 链路；
- [x] 本地复验 V1 校验和、catalog、全量 pytest 和 Vite build；

远程验收门：当前分支必须通过面向 `main` 的 PR 暴露完整差异，并在 GitHub Actions
全绿后才能合并默认分支。

P0 没有修改 `data/v1/`、评测集、报告或业务逻辑。

## 已验证基线

| 检查 | 结果 | 命令或依据 |
|---|---|---|
| Git 状态 | 开始任务前 `main` 与 `origin/main` 一致；仅计划书为未跟踪新文件 | `git status --short --branch` |
| Python 初始基线 | 25 passed，1 warning | 第一批任务开始前 |
| Python 当前回归 | 85 passed，1 integration skipped，0 warning | `/opt/homebrew/Caskroom/miniconda/base/envs/medsafety/bin/python -m pytest -q` |
| pytest 收集 | Redis 手工连接脚本已排除，不再产生返回值 warning | 测试输出 |
| 前端构建 | 通过，Vite 生成生产 bundle | `npm run build` |
| V1 冻结文件 | 5/5 SHA-256 通过 | `shasum -a 256 -c data/v1/checksums.sha256` |
| V1 catalog | 7 Source、4 Medication、2 Context、3 Fact，状态有效 | `scripts/validate_v1_data.py` |
| 前端生产依赖审计 | 0 vulnerability | `npm audit --omit=dev`，2026-07-24 |
| Ollama | 已运行 | `deepseek-r1:1.5b`，digest `e0979632…c2d7`，15 次 v2 请求完成 |
| Docker/Redis | Docker 28.0.4 已运行；Redis 未启动 | `docker info` 与容器清单 |
| Neo4j 集成 | 1 passed，61 deselected；测试后临时实例已移除 | Neo4j 5.26.28，隔离端口 17687，`pytest -m integration` |

本阶段已经真实运行 Ollama 解释规划，但没有同时运行 Neo4j、Redis 和 legacy 全链路，因此结果只能称为 V1 Evidence Packet 解释层开发基线，不能称为端到端系统质量结果。

## 当前数据快照

依据 `data_layer/medical_graph.cypher.txt` 的创建语句：

- 18 个 Drug；
- 18 个 Ingredient；
- 14 个 Condition；
- 22 条 CONTRAINDICATED_IN；
- 9 条 INTERACTS_WITH。

当前关系中的 `source` 只是自由文本来源标签。它们尚未逐条核验，也普遍缺少 URL、版本定位、访问日期和审核记录。因此全部视为 `legacy_unreviewed`，不能称为临床审核数据。

## 本阶段交付物

- [x] 总体升级计划；
- [x] 项目状态文档；
- [x] 安全边界文档；
- [x] 评测协议；
- [x] 来源、事实、证据包、结论状态和评测样例契约；
- [x] 现有图谱事实和来源完整性清单；
- [x] 18 条小型开发集；
- [x] 离线基线评测脚本和报告；
- [x] 新增契约与评测测试；
- [x] 全量回归和前端构建复验。

## 第一份离线基线

当前规则实体抽取在 18 条 `dev-v0.1` 样例上的结果：

- entity micro precision：0.966；
- entity micro recall：0.875；
- entity micro F1：0.918；
- whole-case exact match：0.722；
- 失败样例：5/18。

失败集中在未接入的中英文别名、`酒精消毒`子串误判和历史追问解析。该结果只评价实体工程行为，不是医学准确率。

## 已知 P0 风险

1. V1 事实只有 `source_aligned` 状态，没有医生或药师临床审核签名。
2. V1 仅覆盖 3 条事实，不能外推到未收录药品、剂量或人群。
3. legacy `/api/query` 仍使用默认共享会话和自由文本生成，不具备 V1 护栏。
4. 当前真实模型数据集已经用于 v1/v2 调优，不能再作为独立测试集。
5. 健康检查和完整依赖故障注入仍未完成。
6. 尚无 Neo4j、Redis、Ollama 同时在线的端到端基线。

## 下一验收门

进入 Safety Engine 重构前必须满足：

- 开发集和评测 schema 可自动校验；
- 现有风险关系都有稳定的 legacy inventory ID；
- 来源缺口被显式列出；
- 当前规则实体抽取已有真实基线；
- 新增测试和原有测试全部通过；
- 未对现有医学内容作未经核验的修改。

## V1 alpha.1 进展

- 已独立清理 19 个被 Git 跟踪的 `.pyc` 和 `2.1.0`；
- 建立 6 条可定位来源记录、4 条药品/成分记录和 2 条风险事实；
- 新事实均为 `source_aligned`，未声称 `clinically_reviewed`；
- Safety Engine 与旧 Cypher 隔离，只消费 `data/v1/`；
- 泰诺 + 感康可以返回完整的商品名、成分规则与 FDA 风险来源链；
- 布洛芬 + 阿司匹林会先检查“阿司匹林用于心血管保护”的适用条件；
- 7 条 source-aligned 开发样例确定性回归通过；该结果不是临床准确率。
- API 全局异常和 SSE 错误不再向客户端返回 traceback 或内部异常文本。
- Redis 手工连接脚本不再被 pytest 误收集。

## V1 alpha.2 进展

- 新增只读 `KnowledgeRepository` 边界，Safety Engine 不再依赖 JSON catalog 的具体实现；
- `KnowledgeCatalog` 继续作为权威 JSON 实现，现有 API 行为保持不变；
- 新增 `Neo4jKnowledgeRepository`，只读取 `reviewed` 且来源对齐的 V1 记录；
- 新增参数化、基于唯一约束和 `MERGE` 的 Neo4j 导入器；重复导入不会创建重复节点或关系；
- Neo4j 使用独立 `Safety*` 标签作为可重建查询投影，不读取或改写旧版未审核图谱；
- 导入脚本在依赖不可用时返回稳定退出码，不向终端输出驱动 traceback；
- 离线假驱动测试覆盖重复导入、参数化写入、严格契约重建和 Safety Engine 适配；
- 使用官方 Neo4j 5.26.28 镜像和 tmpfs 数据目录完成真实集成测试，测试后容器与网络已移除；
- 对同一 catalog 连续导入两次，节点与关系计数保持一致：7 Source、4 Medication、10 Ingredient、2 Context、3 Fact、1 Snapshot、11 条成分关系、11 条来源关系和 1 条上下文关系；
- JSON 与 Neo4j Repository 在七类场景中返回完全一致的 `EvidencePacket`。
- Neo4j 连接失败、快照缺失、记录损坏或数据版本不一致会转换为受控的 Repository 不可用错误；
- Safety Engine 将上述错误映射为 `knowledge_unavailable`，返回 `data_version: null`，不泄露内部异常，也不会错误返回 `no_known_risk_in_scope`；
- API 契约测试已覆盖该状态的 JSON 序列化。
- 完成 22 条 legacy 禁忌关系的重新筛查，旧记录继续保持 `legacy_unreviewed`；
- 新增 1 条 DailyMed 布洛芬片标签来源、1 条严格限定的禁忌事实和 2 个受控临床上下文，数据版本升级为 `v1.0.0-alpha.2`；
- Safety Engine 只在用户明确报告阿司匹林/NSAID 相关哮喘、荨麻疹或过敏样反应时命中禁忌；普通“哮喘”返回 `out_of_scope`；
- Neo4j 投影新增 2 个 `SafetyContext` 节点和 1 条 `APPLIES_IN` 关系；两次真实导入计数一致；
- 9 条 source-aligned 开发样例确定性回归全部匹配；该结果不是临床准确率。

alpha.2 的数据卡、校验和与可复现基线现已冻结；本阶段继续禁止扩张医学覆盖面，以免生成护栏和评测目标同时漂移。

## V1 第 3 周：约束生成第一阶段

- 新增 alpha.2 数据卡和 SHA-256 清单，冻结 4 个权威 JSON 文件与 9 条开发样例；
- 新增严格 `ExplanationPlan` 和 `SafetyExplanation` 契约，额外字段一律拒绝；
- Ollama 只看到结论状态、fact_id、风险类型和严重度，只能返回完整 fact_id 排序；
- 用户可见陈述、严重度说明、来源 ID 和定位全部从 Evidence Fact 确定性复制；
- 未知 ID、漏引、重复引用、结论篡改、额外医学字段和依赖故障均安全回退，且不向 API 暴露异常文本；
- 非风险状态不调用 LLM；风险状态可通过 `use_llm_plan: false` 强制走确定性路径；
- 新增 `POST /api/v1/safety/explain`，原确定性检查接口保持不变；
- 建立 9 条脚本化对抗集和可复现 runner，保存报告记录数据集 SHA-256、代码 commit、工作树状态、数据与 prompt 版本；
- 9/9 场景通过，结论保持、fact_id 引用覆盖、抽取式陈述和来源可追溯均为 1.000，无证据陈述率为 0.000；
- 上述脚本化结果只证明服务端护栏，不是实际模型或临床质量报告。

## 真实 Ollama 开发基线

- 固定模型 digest、temperature 0、seed 42、num_predict 256、think false，并保存 3 轮原始计划；
- v1 的 15 次请求中 6 次把 fact_id 连字符改为下划线，有效计划率 0.600、回退率 0.400；
- 所有无效 ID 均被服务端拒绝，21/21 case run 仍安全通过，无证据陈述率 0；
- v2 使用动态 JSON Schema 固定状态、ID enum、数量、唯一性及额外字段限制；
- v2 在相同探针和模型上 15/15 合法，有效计划率和三轮一致性均为 1.000，P50/P95 为 1085.918/1511.546 ms；
- v1/v2 均属于同一开发集上的调优证据，不能宣称模型泛化或临床准确率。

该验收门已通过独立的非医学 opaque-ID contract test 完成；医学内容层仍缺少按 fact_id 分组的独立测试集。

## 锁定 opaque-ID 测试与安全修复

- 在 v2 完成后冻结 12 条非医学合成测试，覆盖未见 ID、相似字符、大小写、Unicode、UUID 和 2/3/4 事实排序；
- 3 次重复共 36 次模型请求，有效计划率 0.833、逐字符引用率 0.900、精确严重度顺序率 0.667；
- Ollama structured output 在两个相似 ID 场景中稳定返回重复 ID，说明 `uniqueItems` 不能替代服务端校验；
- 两个多事实场景稳定违反严重度顺序，说明模型不能独立承担风险优先级策略；
- 服务端新增 `FATAL > RED > ORANGE > INFO` 顺序不变量，违规计划与未知、遗漏、重复 ID 一样确定性回退；
- `explanation_guardrails-v2` 的 10 个脚本化场景全部通过，历史 v1 数据和报告未被覆盖。

下一验收门：开始实体抽取边界重构，先定义歧义药名、未知实体、提示注入与必须澄清状态的版本化契约；不再扩展当前解释排序 prompt。
