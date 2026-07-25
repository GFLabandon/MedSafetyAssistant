# P3 Typed Tool Workflow 首批验收

日期：2026-07-25
代码基线：`68cb5d9d9caf1b7e7e893333b5e65519e9d4f1f5`
数据版本：`v1.0.0-alpha.4`

## 结论

首批 typed tool 执行层通过验收。项目现在具备固定工具注册表、严格输入/输出 schema、
服务端 artifact 引用、有限步数和结构化调用 trace。该结果证明确定性工具控制面的工程
契约，不表示已经完成模型 Function Calling 或通用 Agent。

## 已验证行为

- 四个工具均发布 `typed-tool-definition-v1` schema；
- 输入 schema 禁止未声明字段；
- `delete_database` 等未知工具不会执行；
- `cypher`、伪造 `tool_name` 等额外参数在 handler 前被拒绝；
- Safety Engine 只接受服务端 `InputResolution` artifact 的引用；
- 解释工具只接受服务端 `EvidencePacket` artifact 的引用；
- 不存在或类型不符的 artifact 返回 `invalid_artifact_reference`；
- handler 输出不满足预期 schema 时返回 `invalid_output`；
- 默认最大 4 步，当前成功路径执行 3 步；
- `max_steps=2` 时在第三个工具前停止；
- trace 只包含参数键，不包含问题、药名或 Evidence Packet；
- 提示注入文本不能改变注册工具路径或最终事实 ID；
- API 失败响应不包含 traceback、handler 异常或 artifact 内容。

## 自动化证据

- 完整 pytest：`160 passed, 5 skipped`；
- typed workflow 专项：12 项；
- OpenAPI：新增工具目录与查询端点均成功生成；
- catalog：9 Source、5 Medication、3 Context、4 Fact，状态 `valid`；
- 冻结文件校验和：5/5；
- 公开仓库审计：153 个已跟踪文件通过，单文件上限 5 MiB；
- `git diff --check`：通过。

以上检查在干净的代码提交 `68cb5d9` 上执行。机器可读摘要见
[`p3-typed-tool-workflow-v1.json`](p3-typed-tool-workflow-v1.json)。

## 边界

当前工作流由确定性 controller 驱动。Ollama 仍只参与 Evidence Packet 内事实排序，
没有选择工具、构造参数或控制循环。专项测试也不是模型质量或医学准确率评测。

下一批应先建立 50—80 条冻结的工具选择与恶意调用开发/测试样例，再接入只观察、不执行的
Ollama shadow planner。未通过评测前不允许模型控制真实工具执行。
