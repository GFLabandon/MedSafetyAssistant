# P2 来源审核候选清单

日期：2026-07-25
状态：候选与已准入记录

## 1. 用途

本清单把“值得调查的覆盖缺口”和“已经进入正式知识库的医学事实”严格分开。表中内容只
是来源审核任务，不代表项目认可相应主张。任何候选项在完成来源、措辞、适用条件和评测
审核前，都不得写入 `data/v1/facts.json`，也不得出现在用户可见的安全结论中。

状态定义：

- `candidate_alias`：只调查实体或别名映射，不新增风险结论；
- `candidate_fact`：值得进行来源核验的事实假设；
- `accepted`：来源与当前模型均通过，已进入指定数据版本；
- `model_blocked`：来源通过，但当前模型不能无损表达；
- `hold`：范围或措辞歧义较大，暂不进入来源对齐；
- `reject_as_stated`：现有 legacy 表述不能按原样迁移。

## 2. 候选优先级

| ID | Legacy inventory | 待审核主题 | 状态 | 为什么优先或暂停 | 进入 V1 前必须补齐 |
|---|---|---|---|---|---|
| `P2-A01` | 无 | 对乙酰氨基酚的中英文通用名映射 | `accepted` | alpha.3 新增 `paracetamol`、`acetaminophen`；未增加风险事实 | 国家卫健委目录印刷页13 + FDA名称映射；13条开发回归 |
| `P2-F01` | `legacy-contraindicated_in-i_pseudo-c_hbp` | 含伪麻黄碱产品与特定高血压条件 | `candidate_fact` | 成分已存在于泰诺记录，可扩展现有产品的上下文判断 | 产品级权威标签；区分禁忌、警示和咨询措辞；明确血压条件；severity 依据 |
| `P2-F02` | `legacy-contraindicated_in-i_chlor-c_drive` | 泰诺与驾驶/机械操作 | `accepted` | alpha.4 以泰诺产品为主体新增活动限制，没有改写为成分禁忌 | 官方说明书PDF第1/3/8页 + product-subject模型 + 17条开发回归 |
| `P2-F03` | `legacy-contraindicated_in-i_acet-c_alc` | 对乙酰氨基酚与酒精相关条件 | `hold` | “饮酒状态”缺少频率、数量和适用范围，原条件过宽 | 权威标签原文、可执行但不过度推断的上下文、结论类型与 severity 依据 |
| `P2-F04` | `legacy-contraindicated_in-i_ibu-c_stomach` | 布洛芬与特定胃肠道病史或症状 | `hold` | legacy 的“胃溃疡”不足以表达标签中的具体范围 | 产品级来源、当前/既往状态区分、症状边界、年龄和剂型限制 |
| `P2-R01` | `legacy-contraindicated_in-i_ceph-c_alc` | “头孢菌素 + 饮酒状态”类级结论 | `reject_as_stated` | 当前 V1 没有对应产品记录，且 legacy 只有宽泛类别和来源名称 | 必须拆到具体活性成分/产品和可定位来源后重新立项 |
| `P2-R02` | `legacy-contraindicated_in-i_pseudo-c_preg` | 伪麻黄碱与妊娠期的现有合并表述 | `reject_as_stated` | legacy 把多个来源标签和结论等级合并，无法逐条追溯 | 重新定义产品、孕期阶段、来源、结论措辞和审核责任 |
| `P2-R03` | `legacy-interacts_with-i_asp-i_ibu` | 阿司匹林到布洛芬的反向重复关系 | `reject_as_stated` | V1 已有严格限定的布洛芬—阿司匹林事实；不能因方向不同重复计数 | 只有发现不同适用条件、机制或结论且有独立来源时才新建事实 |

## 3. 单条候选的准入门

一条候选只有同时满足以下条件，才可以进入新的版本化数据快照：

1. 确定具体药品、活性成分、剂型和适用上下文，禁止用模糊类别代替；
2. 注册可访问的权威来源 URL、发布者、版本或发布日期、访问日期；
3. 保存可重复定位的章节、表格、警示或说明书条目；
4. 将项目结论限制为来源实际支持的范围，不把“警示/咨询”改写成“禁忌”；
5. 由项目审核者记录 `reviewed_by` 与 `reviewed_at`；临床审核仍是独立状态；
6. 增加正例、缺失上下文、相邻但不满足条件、未知实体和来源不可用样例；
7. 提升数据版本，更新校验和、数据卡、Safety Engine 基线和 JSON/Neo4j 等价测试；
8. 在 Draft PR 中单独展示医学内容差异，不与无关工程重构混合审核。

## 4. 下一轮来源工作停止条件

`P2-A01` 已进入 alpha.3，`P2-F02` 已在产品主体模型通过后进入 alpha.4。下一轮来源
调查最多选择一个候选；如果来源措辞无法映射为项目结论类型，就记录失败原因并停止，
不用 legacy 来源名称或二手文章补齐缺口。

本清单引用的 legacy ID 来自
[`legacy-fact-source-inventory.md`](../reports/legacy-fact-source-inventory.md)；该清单本身
没有提升任何 legacy 事实的审核状态。

本轮来源、校验和与建模决定见
[`p2-source-alignment-alpha3.md`](../reports/p2-source-alignment-alpha3.md) 和
[`p2-tylenol-activity-alpha4.md`](../reports/p2-tylenol-activity-alpha4.md)。
