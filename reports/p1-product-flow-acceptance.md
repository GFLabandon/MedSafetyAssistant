# P1 正式产品链路验收

日期：2026-07-24

## 验收范围

P1 将自然语言输入接入正式 Safety Engine 和 Evidence Explanation，并补齐前端状态、
会话隔离、依赖 readiness、request trace 与浏览器契约测试。本阶段没有扩充医学事实，
也没有引入 Agent 或多智能体能力。

## 自动化结果

| 检查 | 结果 | 边界 |
|---|---:|---|
| Python 全量回归 | 115 passed，1 skipped | 跳过项需显式启动 Neo4j |
| V1 校验和与 catalog | 通过 | 数据仍为 `v1.0.0-alpha.2` |
| Vite 生产构建 | 通过 | Vite 7.3.6 |
| Playwright 浏览器契约 | 4/4 通过 | API fixture，不是全真实依赖浏览器测试 |
| npm audit | 0 vulnerability | 包含开发依赖 |

浏览器测试覆盖：

1. 已知重复成分风险及事实/来源展示；
2. 缺少阿司匹林用途时要求澄清；
3. 未知药品返回 `out_of_scope`；
4. 知识不可用不得显示为“范围内未命中风险”。

## 真实依赖同时在线 smoke test

临时环境：

- Redis `7.4-alpine`，本机映射端口 16379；
- Neo4j `5.26.28`，tmpfs 数据目录，本机 Bolt 端口 17687；
- Ollama `deepseek-r1:1.5b`；
- V1 catalog `v1.0.0-alpha.2`。

readiness 结果为 `status=ready`、`all_dependencies_ready=true`。最后一次探测耗时：

| 依赖 | 状态 | latency |
|---|---|---:|
| catalog | ready | 2.897 ms |
| Redis | ready | 13.516 ms |
| Neo4j | ready | 53.630 ms |
| Ollama | ready | 9.508 ms |

真实 `POST /api/v1/query` 使用 request ID `p1-live-smoke-001`：

- HTTP 200；
- `conclusion_status=risk_found`；
- `generation_mode=llm_planned`；
- 事实为 `fact-duplicate-acetaminophen-001`；
- 总耗时 3275.267 ms，其中证据解释 3274.474 ms。

该结果是单次本机开发 smoke test，不是负载测试、SLO 或生产性能结论。

## Redis 会话验收

真实 Redis 中分别写入 `acceptance-a` 和 `acceptance-b`：

- 每个会话生成用户、助手和对话对共 3 个键；
- 用户和助手键 TTL 均为 86400 秒；
- 清除 `acceptance-a` 删除 3 个键；
- `acceptance-a` 剩余 0 个键，`acceptance-b` 仍保留 3 个键；
- 验收后两个会话的测试键均已删除。

## 验收中发现并修复的问题

1. 首次 Neo4j 临时容器把 `/data` 限制为 512 MiB，事务日志预分配触发只读降级，
   `neo4j` 数据库离线。改为仓库既有不限额 tmpfs 策略后通过；失败容器已删除。
2. legacy embedding 适配器仍调用已被替代的 `/api/embeddings`，真实请求返回 404。
   已迁移到 Ollama 官方 [`POST /api/embed`](https://docs.ollama.com/api/embed)，使用
   `input` 和 `embeddings` 契约，并增加单元测试与 embedding 模型 readiness。
3. Playwright 未知药品测试最初因同一文本同时出现在历史、输入框和标签而发生 strict
   locator 冲突；页面行为正确，测试已收窄到未解析标签后 4/4 通过。

## 清理结果

- `medsafety-p1-redis` 与 `medsafety-p1-neo4j` 临时容器均已停止并自动移除；
- 没有删除用户已有容器或持久数据；
- Ollama 保持用户原有运行状态。
