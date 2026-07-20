# V1 禁忌症来源审计

审计日期：2026-07-20
审计范围：`data_layer/medical_graph.cypher.txt` 中 22 条 legacy `CONTRAINDICATED_IN` 关系
结论：保留 22 条 legacy 关系为 `legacy_unreviewed`；本轮只新增 1 条重新建模、可定位的来源对齐事实

## 审计原则

1. 旧图谱的来源名称不能直接升级为正式引用；必须重新找到 URL、版本和稳定章节定位。
2. “禁忌”“避免使用”“谨慎使用”“咨询医生”是不同强度，不能互换。
3. 用户没有明确报告疾病、用药目的或既往反应时，系统不作推断。
4. 来源对齐只表示项目释义与指定来源一致，不代表临床审核。
5. 项目 severity 是产品沟通等级，不声称是来源中的医学分级。

## 选中的最小事实

| 字段 | 内容 |
|---|---|
| Fact ID | `fact-contraindication-ibuprofen-nsaid-allergic-reaction-001` |
| 药物成分 | 布洛芬 |
| 明确上下文 | 既往服用阿司匹林或其他 NSAID 后出现哮喘、荨麻疹或其他过敏样反应 |
| 来源 | [DailyMed: Ibuprofen Tablets, USP 600 mg](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=8df77ead-27eb-4f6f-95a9-f68d3e9cfa71) |
| 版本 | Set ID `8df77ead-27eb-4f6f-95a9-f68d3e9cfa71`；Updated 2024-07-18 |
| 定位 | `CONTRAINDICATIONS`；`PRECAUTIONS—Preexisting asthma` |
| 项目结论 | 命中该明确既往反应时返回 `risk_found`；普通哮喘不触发 |
| 项目等级 | `RED`：停止自行判断并核对具体产品说明书、联系医生或药师 |
| 审核状态 | `source_aligned`，不是 `clinically_reviewed` |

DailyMed 页面把该产品标为处方药标签和 ANDA 营销状态。其禁忌章节明确排除已知布洛芬超敏者，并说明既往在服用阿司匹林或其他 NSAID 后出现哮喘、荨麻疹或过敏样反应者不应使用；标签同时指出这类患者中报告过严重、极少数致命的类过敏反应。

[DailyMed 的来源说明](https://dailymed.nlm.nih.gov/dailymed/about-dailymed.cfm)指出，NLM 提供企业提交给 FDA、当前在用的标签，但 NLM 不在发布前审核 SPL 内容，且在用标签可能与 Drugs@FDA 的最新批准标签存在差异。因此本项目保留具体产品、Set ID 和更新时间，不把该记录扩写成对所有剂型的临床结论。

## 明确没有迁移的旧主张

| Legacy 主张 | 审计决定 | 理由 |
|---|---|---|
| 布洛芬 + 高血压 = `CONTRAINDICATED_IN/RED` | 不迁移 | 同一标签的 `WARNINGS—Hypertension` 要求谨慎使用并监测血压，没有把一般高血压列为禁忌。 |
| 布洛芬 + 胃溃疡 = `CONTRAINDICATED_IN/RED` | 不迁移 | 标签强调既往溃疡/消化道出血会显著增加风险并要求极度谨慎，但该版本没有把一般胃溃疡史列入禁忌章节。 |
| 布洛芬 + 所有儿童 = `CONTRAINDICATED_IN/RED`，并归因于瑞氏综合征 | 拒绝迁移 | 旧记录把适用年龄、剂型和风险归因混在一起，现有来源标签不能支持该宽泛结论。 |
| 布洛芬 + 普通哮喘 = 禁忌 | 拒绝迁移 | 标签区分普通既往哮喘与阿司匹林敏感型哮喘；只有明确的阿司匹林/NSAID 相关反应史进入本轮规则。 |
| 其余 18 条 legacy 禁忌 | 延后 | 仍缺少具体产品、URL、版本、章节定位或足以支持“禁忌”强度的原文。 |

## 工程边界

- 该事实只由明确的结构化 context 触发，不使用 LLM 猜测过敏史。
- 别名 `阿司匹林过敏`、`NSAID过敏` 等映射到同一个受控 context；单独输入 `哮喘` 必须保持未解析。
- 输出证据同时包含药品来源和禁忌事实来源。
- 当 context 未收录、知识库不可用或数据版本不一致时，不允许回退成“未发现风险”。
