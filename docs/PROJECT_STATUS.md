# MedSafetyAssistant 项目状态

更新时间：2026-08-02
当前阶段：P3——受约束 typed tool workflow
状态：P3 确定性控制面已合并；工具选择数据集和不执行 proposal 的 shadow runner 已完成离线验收

## 当前目标

在不扩大 LLM 医学权限的前提下，把实体解析、Safety Engine、澄清和证据解释封装为
严格 typed tools，建立注册、参数校验、服务端 artifact、步数上限和 trace 边界。模型
工具选择必须先经过独立 shadow 评测，不能直接获得任意执行权。

## P3 typed tool workflow 首批

- [x] 新增四个版本化工具定义和严格输入/输出 schema；
- [x] 新增固定注册表，拒绝未知工具、额外参数和非法输出；
- [x] 工具间使用单请求服务端 artifact `call_id`，不接受调用方构造的领域对象；
- [x] 默认最多 4 步，当前正常与澄清路径均固定执行 3 步；
- [x] 新增 `tool-workflow-trace-v1`，只记录参数键，不记录参数值；
- [x] 新增工具 schema 与 typed workflow 两个 API；
- [x] 同步调用在线程池执行，不直接阻塞 FastAPI 事件循环；
- [x] 12 项专项契约覆盖未知工具、参数注入、artifact 伪造、非法输出、提示注入和步数上限；
- [x] 冻结 60 条模型工具选择与恶意调用样例：40 条 dev、20 条 locked test；
- [x] 接入只记录、不执行的 Ollama Function Calling shadow planner；
- [x] proposal 经过注册工具与严格参数 schema 校验，未知工具、额外参数、错误 artifact
  引用和多工具调用均归类但不执行；
- [x] locked test 需要显式 `--allow-locked-test`，避免开发期间误用；
- [x] 模型预检同时验证已安装状态和 `tools` capability，避免向不兼容模型重复请求；
- [x] P3 相关契约 `34 passed`，完整回归 `182 passed, 5 skipped`；
- [ ] 真实 Ollama dev baseline：原有 `deepseek-r1:1.5b` 不支持 tools，兼容模型尚待运行；
- [ ] 真实 Ollama locked test：尚未运行，必须在 prompt/adapter 固定后只运行一次。

规格见 [`P3_TYPED_TOOL_WORKFLOW.md`](P3_TYPED_TOOL_WORKFLOW.md)，首批与 shadow 验收分别见
[`p3-typed-tool-workflow-acceptance.md`](../reports/p3-typed-tool-workflow-acceptance.md) 和
[`p3-tool-shadow-contract-v1.md`](../reports/p3-tool-shadow-contract-v1.md)。

## P2 alpha.4 泰诺活动限制

- [x] 重新下载官方说明书并复核 SHA-256、页数、产品身份、警示与修订日期；
- [x] 新增 1 条官方来源、1 个 activity context 和 1 条产品级正式事实；
- [x] 泰诺药品记录增加官方产品说明书来源；
- [x] 正式 catalog 为 9 Source、5 Medication、3 Context、4 Fact；
- [x] 开发集从 13 条扩展到 17 条，包含 2 个正例与 2 个防外推负例；
- [x] 自然语言查询可解析“泰诺 + 开车”，但不把事实外推到感康或氯苯那敏；
- [x] 校验和、alpha.4 数据卡和 Safety Engine 基线已更新；
- [x] 隔离 Neo4j 的 5 项集成、产品事实 API 溯源和 JSON 等价通过；
- [x] 生成绑定 alpha.4 数据提交的七查询 PROFILE 证据；
- [x] PR #6 已按依赖顺序合并到默认 `main`。

来源审计见
[`p2-tylenol-activity-alpha4.md`](../reports/p2-tylenol-activity-alpha4.md)，数据边界见
[`DATA_CARD_V1_ALPHA_4.md`](DATA_CARD_V1_ALPHA_4.md)。

## P2 产品级事实模型

- [x] `FactRecord` 增加向后兼容的 `subject_kind/object_kind`；
- [x] 新增 `Medication(product) → Context(activity)` 的 `ACTIVITY_RESTRICTION` 形状；
- [x] catalog 拒绝 substance 主体、未知端点和 predicate/risk/端点类型不一致；
- [x] JSON 与 Neo4j Repository 均按稳定 medication ID 查询产品活动限制；
- [x] `fact-provenance-v2` 可返回 Medication 主体的 ID、规范名和完整来源链；
- [x] 完整性审计可识别产品事实被错误连接到 Ingredient 的损坏；
- [x] 隔离 Neo4j 5.26.28 的 5 项真实集成测试通过；
- [x] alpha.3 的 JSON、校验和、3 条正式事实和 13 条开发集保持不变；
- [x] 生成绑定提交的七条查询 PROFILE 证据；
- [x] 推送独立 stacked Draft PR #5，Quality Gate 全绿。

规格见 [`P2_PRODUCT_FACT_MODEL.md`](P2_PRODUCT_FACT_MODEL.md)。该批测试夹具未进入
`data/v1/`，随后已由 alpha.4 正式事实替换。验收见
[`p2-product-fact-model-acceptance.md`](../reports/p2-product-fact-model-acceptance.md)。

## P2 alpha.3 来源对齐

- [x] 国家卫健委《国家基本药物目录（2018年版）》原始 PDF 可访问并保存 SHA-256；
- [x] 用目录印刷页 13 与 FDA 页面建立
  “对乙酰氨基酚 ↔ paracetamol ↔ acetaminophen”来源链；
- [x] 新增成分药品记录，正式来源变为 8 条、药品/成分记录变为 5 条；
- [x] 新增 4 条别名正例、单药边界和未审核别名负例，13/13 开发回归通过；
- [x] 泰诺官方说明书的驾驶/机械操作警示已核验到 PDF 第 3 页；
- [x] 因当前事实主体只能是 Ingredient，产品级警示暂不写成成分禁忌，也不外推到感康；
- [x] 在隔离 Neo4j 5.26.28 上复核 alpha.3 导入、别名索引和 JSON 等价；
- [x] 生成绑定 alpha.3 数据提交的 PROFILE 证据，六条只读查询均命中索引；
- [x] 推送独立 stacked Draft PR #4，Quality Gate 全绿。

来源决定见
[`p2-source-alignment-alpha3.md`](../reports/p2-source-alignment-alpha3.md)，数据冻结边界见
[`DATA_CARD_V1_ALPHA_3.md`](DATA_CARD_V1_ALPHA_3.md)。

## P2 第二批范围

- [x] 将药品和上下文规范名/别名建模为带唯一约束的别名节点；
- [x] 六条核心只读查询统一采集 EXPLAIN/PROFILE、索引、DB hits 和通知；
- [x] 六条真实 PROFILE 查询全部命中索引，八个 `Safety*` 索引均为 `ONLINE`；
- [x] 新增 `fact-provenance-v1`，严格验证事实属性与图关系；
- [x] 新增 `GET /api/v1/knowledge/facts/{fact_id}`，区分成功、未知和知识不可用；
- [x] 真实 Neo4j 验证全部 3 条正式事实可还原来源、上下文和快照；
- [x] 建立来源审核候选清单，没有升级或新增医学事实；
- [x] 生成绑定代码 SHA 与 Neo4j 版本的机器可读查询计划证据。

验收报告见
[`p2-query-and-provenance-acceptance.md`](../reports/p2-query-and-provenance-acceptance.md)，
内容候选与停止条件见 [`P2_SOURCE_CANDIDATES.md`](P2_SOURCE_CANDIDATES.md)。

## P2 第一批范围

- [x] P1 PR #2 合并至默认 `main`，删除已合并的本地和远程 P1 分支；
- [x] 从最新 `main` 建立独立 `codex/p2-knowledge-graph` 分支；
- [x] 冻结事实节点图模型、端点类型和迁移验收门；
- [x] 公开仓库忽略规则改为明确路径，并增加凭据、构建物和超大文件 CI 审计；
- [x] 实现事实主体、客体、上下文、来源与快照关系；
- [x] Repository 风险查询全部改为真实边遍历；
- [x] 导入事务内完成计数、孤立事实、版本和属性—关系一致性检查；
- [x] 在 Docker Neo4j 上验证重复导入、JSON 等价性和人为损坏检测。

完整规格见 [`KNOWLEDGE_GRAPH_P2.md`](KNOWLEDGE_GRAPH_P2.md)。
本批本地证据见
[`p2-graph-model-acceptance.md`](../reports/p2-graph-model-acceptance.md)。

## P1 完成项

- [x] 新增版本化 `entity-resolution-v1` 契约，显式区分 `resolved`、`ambiguous`、
  `unknown`、`needs_clarification` 和 `rejected_input`；
- [x] 新增只消费 `data/v1/` catalog 的确定性实体解析器，覆盖中英文别名、上下文规则、
  模糊药名、未知药名、跨轮代词和指令式文本标记；
- [x] 新增 `POST /api/v1/query`，串联实体解析、Safety Engine 与 Evidence Explanation；
- [x] 缺少阿司匹林用途等事实适用条件时返回澄清问题，而不是给出“无风险”；
- [x] React 从 legacy 自由回答链路切换到正式 V1，展示五种结论状态、事实 ID、来源、
  定位、数据版本、生成模式和确定性回退原因；
- [x] FastAPI legacy 请求默认生成独立 UUID，Streamlit 为每个浏览器会话生成独立 UUID，
  Redis 历史方法不再提供 `"shared"` 默认值；
- [x] 新增输入边界、API 序列化和默认会话唯一性测试；
- [x] Redis 会话键使用独立 UUID turn ID，默认 TTL 为 86400 秒；增加单会话清除接口、
  session ID 字符约束和并行隔离测试；
- [x] 将过时 `/api/embeddings` 适配器迁移到 Ollama 官方 `/api/embed` 契约，并支持
  单次批量 embedding；
- [x] 新增 `/api/live` 与真实 `/api/ready`；catalog 为必需依赖，Redis、Neo4j、
  Ollama 为可选能力，探测并发且有 1.5 秒默认超时；
- [x] 新增 `X-Request-ID`、结构化请求日志和 `request-trace-v1`，记录实体解析、
  Safety Engine 与证据解释三阶段状态和耗时；
- [x] Playwright 浏览器契约测试覆盖风险、澄清、未知和知识不可用四条路径，并接入 CI；
- [x] Vite 升级到 7.3.6，完整 npm audit 为 0 vulnerability；
- [x] 本地全量回归 `115 passed, 1 skipped`，Vite 生产构建和 4 项浏览器 E2E 通过；
- [x] 临时 Redis、Neo4j 与本机 Ollama 同时在线时 readiness 全部为 ready，真实 V1
  请求返回 `risk_found`、正确事实 ID、`llm_planned` 和完整 trace；
- [x] 临时容器与测试 Redis 键已清理。

## Neo4j 兼容链路修复（P2 暂停期间）

- [x] legacy `/api/query`、`/api/query/stream` 与 Streamlit 在 Neo4j 驱动或会话失败时
  返回稳定的 `knowledge_unavailable`，不再把空风险列表交给 LLM 生成疑似安全结论；
- [x] Neo4j 连接超时、数据库名进入统一配置，导入脚本默认使用 `NEO4J_DATABASE`；
- [x] 导入器在同一写事务内重建专用 `Safety*` 投影，旧事实不会在成功导入后残留，失败时
  清理会随事务回滚；
- [x] 新增 `docker-compose.local.yml`，默认映射 `7474/7687` 与 `6379`，健康检查使用
  Neo4j 镜像内绝对路径；隔离 Compose 健康检查同步修正；
- [x] 临时真实验证：Neo4j/Redis 健康、catalog 导入、旧 `SafetyFact` 清理和
  `泰诺 + 感康 -> fact-duplicate-acetaminophen-001` 均通过；验证栈已清理，现有
  `distracted_benz` 未修改。

仍保留的边界：

- 正式 V1 保持无状态，跨轮代词要求用户重新写出药品名称；
- legacy Redis 会话没有认证、用户账户绑定或生产级并发/SLO；
- Playwright 使用 API fixture 验证前端契约；真实依赖 smoke test 验证 API，两者不包装
  为生产环境浏览器全链路；
- readiness 证明单次连接可用，不代表持续可用性。

## P0 公开可见性进展

- [x] 新增 `.github/workflows/quality.yml`，在 PR 和 `main` push 上运行仓库差异、
  V1 校验和、catalog 校验、离线 pytest 和前端生产构建；
- [x] README 首屏改为项目问题、核心架构、真实指标、解释边界和三条 V1 API 演示；
- [x] README 删除“推荐更大模型”等无评测依据的表述，并明确当前不是 ReAct、MCP、
  多 Agent、临床系统或生产高并发系统；
- [x] 明确 V1 API 是正式可验证入口，React 已切换到 V1 evidence flow；legacy API 仅保留兼容；
- [x] 本地复验 V1 校验和、catalog、全量 pytest 和 Vite build；

远程验收门：当前分支必须通过面向 `main` 的 PR 暴露完整差异，并在 GitHub Actions
全绿后才能合并默认分支。

P0 没有修改 `data/v1/`、评测集或评测报告；本节之后的 Neo4j 兼容修复是独立的
P2 暂停期变更。

## 已验证基线

| 检查 | 结果 | 命令或依据 |
|---|---|---|
| Git 状态 | shadow 实现提交 `4130d7a`，文档验收批次在当前分支继续 | `git log --oneline` |
| Python 初始基线 | 25 passed，1 warning | 第一批任务开始前 |
| Python 当前回归 | 182 passed，5 integration skipped，0 warning | `python -m pytest -q`（使用 `medsafety` 环境） |
| pytest 收集 | Redis 手工连接脚本已排除，不再产生返回值 warning | 测试输出 |
| 前端构建 | 通过，Vite 生成生产 bundle | `npm run build` |
| 浏览器契约 E2E | 4/4 通过 | `npm run test:e2e` |
| 前端完整依赖审计 | 0 vulnerability | `npm audit`，Vite 7.3.6 |
| V1 冻结文件 | 5/5 SHA-256 通过 | `shasum -a 256 -c data/v1/checksums.sha256` |
| V1 catalog | 9 Source、5 Medication、3 Context、4 Fact，状态有效 | `scripts/validate_v1_data.py` |
| 前端生产依赖审计 | 0 vulnerability | `npm audit --omit=dev`，2026-07-24 |
| Ollama | 已运行 | `deepseek-r1:1.5b`，digest `e0979632…c2d7`，15 次 v2 请求完成 |
| Ollama tool shadow | 未运行 | `deepseek-r1:1.5b` capabilities 不含 `tools`，在任何模型请求前停止；locked test 未触碰 |
| Docker/Redis | Docker 28.0.4 已运行；Redis 未启动 | `docker info` 与容器清单 |
| Neo4j 集成 | 3 passed，141 deselected；测试后临时实例已移除 | Neo4j 5.26.28，隔离端口 17687，`pytest -m integration` |

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
2. V1 仅覆盖 4 条事实，不能外推到未收录药品、剂量或人群。
3. legacy `/api/query` 仍是自由文本生成，不具备 V1 护栏；默认共享会话已移除。
4. 当前真实模型数据集已经用于 v1/v2 调优，不能再作为独立测试集。
5. 健康检查和完整依赖故障注入仍未完成。
6. P1 已有单机同时在线 API smoke baseline，但尚无负载、持续可用性或生产 SLO。

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

该验收门、P1 可靠性验收和 P2 事实图验收均已完成。当前进入 P3：先冻结工具选择与
恶意调用评测集，再接入不执行真实工具的 Function Calling shadow planner；继续禁止
模型创建医学事实、提交 Evidence Packet 或生成 Cypher。
