# V1 来源对齐记录

更新时间：2026-07-25

## 状态定义

- `legacy_unreviewed`：旧仓库主张，尚未核对精确来源；
- `source_aligned`：项目记录的措辞和适用条件已与指定公开来源逐项对齐；
- `clinically_reviewed`：具备资质的医生或药师完成审核。

本轮新增数据全部是 `source_aligned`，不是 `clinically_reviewed`。

## V1 alpha.3 覆盖范围

当前只对齐三个场景：

1. 泰诺与感康共享对乙酰氨基酚，并应用“不要同时使用多个含对乙酰氨基酚产品”的风险规则；
2. 布洛芬与低剂量阿司匹林用于心血管保护时存在带条件的药效相互作用；
3. 明确报告既往服用阿司匹林或其他 NSAID 后出现哮喘、荨麻疹或过敏样反应时，布洛芬片标签明确要求不应使用。

其他旧图谱事实继续保持 `legacy_unreviewed`，Safety Engine 不读取它们。

alpha.3 没有增加风险事实，只增加“对乙酰氨基酚”的成分药品记录：

- 国家卫健委《国家基本药物目录（2018年版）》印刷页 13 对齐
  “对乙酰氨基酚 / Paracetamol”；
- FDA Acetaminophen 页面说明美国以外通常称为 `paracetamol`；
- 正式别名为 `paracetamol`、`acetaminophen`；
- “扑热息痛”尚未通过本批来源门，不进入正式别名表。

详细审计见
[`p2-source-alignment-alpha3.md`](../reports/p2-source-alignment-alpha3.md)。

## 来源链

### 泰诺 + 感康重复成分

- 上海市药监局公开目录第3页序号29：泰诺对应酚麻美敏片；
- 国家药监局转载用药提示第17行：酚麻美敏含对乙酰氨基酚等成分；
- 内蒙古政府采购合同第7页序号1：感康对应复方氨酚烷胺片；
- 烟台市政府 OTC 目录第17行：复方氨酚烷胺片含对乙酰氨基酚等成分；
- FDA Acetaminophen 页面 Safe Use 部分：不要同时使用多个含对乙酰氨基酚的产品。

### 布洛芬 + 阿司匹林

- FDA Science Paper 明确把结论限定为布洛芬与用于心血管保护的低剂量阿司匹林；
- 旧图谱将其写成一般性的 RED 相互作用，适用范围过宽；
- 新事实增加 `required_context`，缺少用途信息时 Safety Engine 必须要求澄清。

### 布洛芬 + 明确的阿司匹林/NSAID 反应史

- DailyMed 的 Ibuprofen Tablets, USP 600 mg 在用标签，Set ID `8df77ead-27eb-4f6f-95a9-f68d3e9cfa71`，更新时间 2024-07-18；
- 定位为 `CONTRAINDICATIONS` 和 `PRECAUTIONS—Preexisting asthma`；
- 规则只接受受控上下文“服用阿司匹林或其他 NSAID 后出现哮喘、荨麻疹或过敏反应”；
- 单独的“哮喘”保持未解析，不能触发禁忌；
- 旧图谱中的布洛芬高血压、胃溃疡和儿童禁忌没有迁移，原因记录在 `reports/contraindication-source-audit-v1.md`。

## 工程审核记录

- 审核者 ID：`project-source-audit-2026-07-20`；
- 审核内容：URL 可访问、发布机构、页面/行定位、记录措辞与条件；
- 未完成：临床分级、临床适用性和全量药品覆盖；
- severity 是项目风险沟通策略，不宣称来自监管来源的标准等级。
