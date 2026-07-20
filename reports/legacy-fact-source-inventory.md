# Legacy Fact and Source Inventory

生成日期：2026-07-20
输入：`data_layer/medical_graph.cypher.txt`
处理方式：只读解析，未修改现有事实

## 汇总

- 解析到具名 Drug/Ingredient/Condition 节点：50；
- 禁忌关系：22；
- 相互作用关系：9；
- 风险关系总数：31；
- 同时具备可核查 URL 和精确定位的关系：0/31；
- 审核状态：全部 `legacy_unreviewed`。

来源名称不等于可验证引用。当前每一行都缺少来源注册 ID、URL、精确章节/说明书条目、访问日期和审核记录。

## 风险事实

| Inventory ID | Type | Subject | Object | Severity | Current source label | Missing metadata |
|---|---|---|---|---|---|---|
| `legacy-contraindicated_in-i_ceph-c_alc` | CONTRAINDICATED_IN | 头孢菌素 | 饮酒状态 | FATAL | 《中国药典 2020 版》《临床用药须知》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_acet-c_alc` | CONTRAINDICATED_IN | 对乙酰氨基酚 | 饮酒状态 | FATAL | 《药物不良反应杂志》2022 年版 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_asp-c_alc` | CONTRAINDICATED_IN | 阿司匹林 | 饮酒状态 | FATAL | FDA 用药安全警告 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_pseudo-c_hbp` | CONTRAINDICATED_IN | 伪麻黄碱 | 高血压 | RED | 《中国高血压防治指南 2023 版》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_ibu-c_hbp` | CONTRAINDICATED_IN | 布洛芬 | 高血压 | RED | 《高血压患者用药指导规范》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_pseudo-c_preg` | CONTRAINDICATED_IN | 伪麻黄碱 | 妊娠期 | RED | FDA 妊娠药物分级 D 类 & 中国药典 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_chlor-c_preg` | CONTRAINDICATED_IN | 氯苯那敏 | 妊娠期 | ORANGE | 《妊娠期和哺乳期用药指南》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_zhimahuang-c_preg` | CONTRAINDICATED_IN | 炙麻黄 | 妊娠期 | ORANGE | 《中药妊娠禁忌用药规范》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_ceph-c_preg` | CONTRAINDICATED_IN | 头孢菌素 | 妊娠期 | ORANGE | 《临床妇产科用药指南》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_amox-c_lact` | CONTRAINDICATED_IN | 阿莫西林 | 哺乳期 | ORANGE | 《哺乳期用药安全手册》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_lora-c_lact` | CONTRAINDICATED_IN | 氯雷他定 | 哺乳期 | ORANGE | 药品说明书 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_ibu-c_child` | CONTRAINDICATED_IN | 布洛芬 | 儿童 | RED | 《中国儿科用药指南 2024 版》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_chlor-c_child` | CONTRAINDICATED_IN | 氯苯那敏 | 儿童 | RED | 《儿科药物治疗学》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_asp-c_child` | CONTRAINDICATED_IN | 阿司匹林 | 儿童 | RED | WHO 儿童用药安全指南 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_chlor-c_drive` | CONTRAINDICATED_IN | 氯苯那敏 | 驾驶/高空作业 | ORANGE | 药品说明书 & 道路交通安全法 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_cetirizine-c_drive` | CONTRAINDICATED_IN | 西替利嗪 | 驾驶/高空作业 | ORANGE | 药品说明书 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_ibu-c_stomach` | CONTRAINDICATED_IN | 布洛芬 | 胃溃疡 | RED | 《消化性溃疡诊疗规范》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_asp-c_stomach` | CONTRAINDICATED_IN | 阿司匹林 | 胃溃疡 | RED | 《胃肠病学杂志》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_acet-c_liver` | CONTRAINDICATED_IN | 对乙酰氨基酚 | 肝功能不全 | RED | 《肝功能不全患者用药指导》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_ibu-c_kidney` | CONTRAINDICATED_IN | 布洛芬 | 肾功能不全 | RED | 《肾功能不全患者用药规范》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_amox-c_allergy_penicillin` | CONTRAINDICATED_IN | 阿莫西林 | 青霉素过敏 | FATAL | 《青霉素类药物临床应用指导原则》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-contraindicated_in-i_ceph-c_allergy_ceph` | CONTRAINDICATED_IN | 头孢菌素 | 头孢过敏 | FATAL | 《头孢菌素类抗生素临床应用指南》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-interacts_with-i_acet-i_ibu` | INTERACTS_WITH | 对乙酰氨基酚 | 布洛芬 | ORANGE | 《临床药物相互作用指导原则》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-interacts_with-i_ibu-i_asp` | INTERACTS_WITH | 布洛芬 | 阿司匹林 | RED | MCDEX 药物临床信息参考 & FDA 警告 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-interacts_with-i_lora-i_chlor` | INTERACTS_WITH | 氯雷他定 | 氯苯那敏 | ORANGE | 药品说明书 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-interacts_with-i_cetirizine-i_chlor` | INTERACTS_WITH | 西替利嗪 | 氯苯那敏 | ORANGE | 《抗过敏药物临床应用规范》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-interacts_with-i_pseudo-i_nife` | INTERACTS_WITH | 伪麻黄碱 | 硝苯地平 | RED | 《临床药物治疗学》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-interacts_with-i_pseudo-i_lisinopril` | INTERACTS_WITH | 伪麻黄碱 | 赖诺普利 | RED | 《高血压合并感冒用药指导》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-interacts_with-i_ceph-i_amox` | INTERACTS_WITH | 头孢菌素 | 阿莫西林 | ORANGE | 《抗生素临床合理应用指南》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-interacts_with-i_rox-i_amox` | INTERACTS_WITH | 罗红霉素 | 阿莫西林 | ORANGE | 《大环内酯类抗生素临床应用规范》 | source_id, URL, locator, accessed_at, reviewer |
| `legacy-interacts_with-i_asp-i_ibu` | INTERACTS_WITH | 阿司匹林 | 布洛芬 | RED | 《抗血小板治疗专家共识》 | source_id, URL, locator, accessed_at, reviewer |

## 数据问题

1. 所有 31 条关系都缺少可直接核查的来源定位。
2. `布洛芬 → 阿司匹林` 与 `阿司匹林 → 布洛芬` 各存在一条无向相互作用关系，语义可能重复，迁移时必须去重或说明二者差异。
3. 当前 severity 是自由文本，尚未通过来源对齐证明等级划分合理。
4. 现有关系描述的是仓库当前主张，不代表本报告认可其医学正确性。

事实只有在措辞、适用范围、severity 和来源定位核对后，才可从 `legacy_unreviewed` 提升为 `source_aligned`；临床审核是独立状态。
