# FDA Safe Use 章节入库记录

- 原始页面：[FDA Acetaminophen](https://www.fda.gov/drugs/safe-use-over-counter-pain-relievers-and-fever-reducers/acetaminophen#safeuse)，页面标示内容日期 2025-08-14；2026-09-24 抓取并人工核对章节标题和重复产品提示。
- 复用依据：[FDA Website Policies](https://www.fda.gov/about-fda/about-website/website-policies)说明，除另有标注外，FDA 网站文字属于公有领域，并建议复制时注明日期和原链接。本仓库仅保留目标章节，不使用 FDA 标志，也不暗示 FDA 认可本项目。
- 原始 HTML SHA-256：`8d8d45ffed175e90ac99edcf98548e78b0939e5002d39a9df40cf44c4a97d76f`。本仓库不提交完整 HTML；可用 `scripts/extract_fda_safe_use.py` 对该快照重建目标章节。
- 抽取文件：[Safe Use 章节快照](../data/source_documents/fda_acetaminophen_safe_use_2026-09-24.txt)，SHA-256：`e0993c1dc983761f281c148b887dab3c3007b8e718cf1662e219296e0d7b0f`。入库清单：[source_document_corpus_v1.json](../data/source_document_corpus_v1.json)。
- 关联关系：`source-fda-acetaminophen-2025` → `fact-duplicate-acetaminophen-001`。该关联仅表示已审事实引用该来源；章节内其他建议没有自动成为项目风险事实。检索结果在独立区域展示，不进入 Safety Engine 或正式解释器。

开发检索集 `eval/source_document_search_dev_v1.jsonl` 含 3 条应命中片段及 1 条未知输入；运行 `python -m evaluation.source_document_search`，本次 top-1 或空结果为 **4/4**。集合与当前索引共同迭代，不能宣称泛化检索质量。

当前只纳入 **1 个来源章节**，还没有外部来源的锁定测试集。FDA 页面会更新；校验和只能证明本地快照未变，不能证明原页面今天仍相同。后续更新应重新抓取、审阅、记录新校验和，并评估是否需要新数据版本。
