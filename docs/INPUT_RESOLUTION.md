# V1 自然语言输入边界

更新时间：2026-07-24
契约版本：`entity-resolution-v1`

## 目标

自然语言入口只负责把用户文本解析为 V1 catalog 中已经存在的药品与上下文，然后交给
确定性 Safety Engine。解析器不调用 LLM，不生成新药名，不把未知输入当作“未发现风险”。

正式入口：

```http
POST /api/v1/query
Content-Type: application/json

{
  "question": "泰诺和感康能一起吃吗？",
  "use_llm_plan": false
}
```

## 状态

| 解析状态 | 行为 |
|---|---|
| `resolved` | 调用 Safety Engine；若缺少事实适用条件，再转为 `needs_clarification` |
| `ambiguous` | 返回具体澄清问题，不执行医学风险判断 |
| `unknown` | 返回 `out_of_scope`，不生成开放域回答 |
| `needs_clarification` | 要求重新写出药品或补充必要上下文 |
| `rejected_input` | 对超长文本或不允许的控制字符拒绝解析 |

## 安全规则

- 药品和上下文只来自 `data/v1/` 的 canonical name、alias 或受测上下文规则。
- 英文别名使用大小写无关且带字母数字边界的匹配，避免在更长单词内误命中。
- “感冒药”“止痛药”等类别词视为歧义，不能映射到某个具体药品。
- “这个药”“它”等跨轮指代不会读取共享历史，而是要求用户重新写出药品。
- “忽略之前规则”“system prompt”等指令式文本只产生
  `instruction_like_text_ignored` 标记，不影响工具、数据源或 Safety Engine。
- 单个问题最长 500 个字符；不允许的控制字符会被拒绝。

## 当前限制

- 解析器是确定性、小范围实现，不代表通用医疗 NER。
- 上下文推断只覆盖当前三条来源对齐事实所需的明确表达。
- 正式 V1 当前无状态，不做跨轮共指。
- 新增药品别名或上下文规则必须先更新 catalog、测试和数据版本边界，不能只改 prompt。
