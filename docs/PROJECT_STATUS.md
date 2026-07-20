# MedSafetyAssistant 项目状态

更新时间：2026-07-20
当前阶段：V1 第 2 周——来源对齐、确定性 Safety Engine 与 Neo4j 查询投影
状态：V1 alpha.2 开发中；存储解耦与幂等导入已完成离线验证，真实 Neo4j 集成验收待运行

## 当前目标

将现有本地演示升级为一个范围明确、事实可追溯、结果可评测、故障可解释的 AI 应用。当前阶段不扩展 Agent 能力，先建立数据、证据和评测基础。

## 已验证基线

| 检查 | 结果 | 命令或依据 |
|---|---|---|
| Git 状态 | 开始任务前 `main` 与 `origin/main` 一致；仅计划书为未跟踪新文件 | `git status --short --branch` |
| Python 初始基线 | 25 passed，1 warning | 第一批任务开始前 |
| Python 当前回归 | 44 passed，0 warning | `/opt/homebrew/Caskroom/miniconda/base/envs/medsafety/bin/python -m pytest -q` |
| pytest 收集 | Redis 手工连接脚本已排除，不再产生返回值 warning | 测试输出 |
| 前端构建 | 通过，Vite 生成生产 bundle | `npm run build` |
| Ollama | 未运行 | `127.0.0.1:11434` 连接失败 |
| Docker/Redis | Docker daemon 未运行 | `docker ps` 连接失败 |
| Neo4j | 未发现本地 7687 监听 | 本地端口检查 |

外部依赖未运行，因此本阶段只发布离线、可复现的规则实体抽取基线。不得将依赖缺失时的全链路输出称为模型或系统质量结果。

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

1. 事实来源不可直接核查。
2. 空检索结果可能被误解为确认安全。
3. 默认共享会话 ID 存在上下文串线风险。
4. API 会向客户端返回 traceback。
5. 真实依赖状态没有被健康检查验证。
6. 缺少锁定测试集和端到端基线。

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
- 当前本机 Neo4j 未运行，因此不得将上述离线测试表述为真实数据库集成通过。

下一验收门：启动隔离的 Neo4j 5 测试实例，验证首次导入、二次导入计数不变、Repository 查询结果与 JSON catalog 一致，并将该过程加入可选集成测试。
