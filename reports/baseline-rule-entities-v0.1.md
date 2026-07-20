# Current Rule Entity Baseline

执行日期：2026-07-20
代码基线：`ee0ca68`
数据集：`eval/dev_cases.jsonl` (`dev-v0.1`)
运行器：`rule_entities`
样例数：18

## 运行边界

本报告只评测当前 `exact_entity_extraction` 的实体集合输出。Docker、Neo4j、Redis 和 Ollama 在执行时均不可用，因此本报告不评测图谱检索、医学正确性、回答依据一致性或端到端安全。

所有样例的医学标签状态均为 `legacy_unreviewed`。

## 指标

| 指标 | 结果 |
|---|---:|
| Entity micro precision | 0.966 |
| Entity micro recall | 0.875 |
| Entity micro F1 | 0.918 |
| Drug exact match | 0.778 |
| Condition exact match | 0.944 |
| Whole-case exact match | 0.722 |

计数：

- Drug: TP 18 / FP 0 / FN 4；
- Condition: TP 10 / FP 1 / FN 0；
- 失败样例：5/18。

## 失败样例

### `dev_fenbid_alias`

- 问题：芬必得能和阿司匹林一起吃吗？
- 期望药品：布洛芬缓释胶囊、阿司匹林肠溶片；
- 实际药品：阿司匹林肠溶片；
- 原因：`DRUG_ALIAS_MAP` 定义了芬必得，但 `exact_entity_extraction` 没有使用它。

### `dev_english_ibuprofen`

- 问题：ibuprofen 和阿司匹林可以一起吃吗？
- 缺失实体：布洛芬缓释胶囊；
- 原因：英文别名没有进入实际抽取路径。

### `dev_paracetamol_alcohol`

- 问题：paracetamol 喝酒后能吃吗？
- 缺失实体：对乙酰氨基酚；
- 原因：英文成分别名没有进入实际抽取路径。

### `dev_disinfectant_false_positive`

- 问题：我用酒精消毒后可以吃泰诺吗？
- 错误状态：饮酒状态；
- 原因：当前规则只做子串匹配，无法区分外用酒精与饮酒。

### `dev_followup_history`

- 问题：那这个药还能继续吃吗？
- 历史药品：布洛芬缓释胶囊；
- 实际药品：空；
- 原因：规则运行器只接收本轮文本，不读取结构化会话历史。

## 结论

当前规则抽取对显式中文实体表现较好，但别名映射实际未接入、子串规则缺少语境、历史追问没有结构化解析。下一阶段应先修正统一规范化入口并为追问建立显式会话实体状态，不能只增加更多关键词。
