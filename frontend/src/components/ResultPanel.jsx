import React from 'react';

const STATUS_CONTENT = {
  risk_found: {
    title: '发现已收录风险',
    description: '当前数据版本命中了来源对齐的风险事实。',
    tone: 'risk',
  },
  no_known_risk_in_scope: {
    title: '当前范围内未命中风险',
    description: '这不代表药品或组合安全，请继续核对说明书并咨询专业人员。',
    tone: 'neutral',
  },
  insufficient_information: {
    title: '需要补充信息',
    description: '现有信息不足，系统没有作出完整风险判断。',
    tone: 'warning',
  },
  out_of_scope: {
    title: '超出当前覆盖范围',
    description: '药品或问题不在当前来源对齐目录中，系统没有生成开放域结论。',
    tone: 'warning',
  },
  knowledge_unavailable: {
    title: '知识服务不可用',
    description: '本次没有进行风险判断，请稍后重试。',
    tone: 'error',
  },
};

function TagList({ label, values, emptyText }) {
  return (
    <div>
      <span className="field-label">{label}</span>
      <div className="tag-row">
        {values.length > 0
          ? values.map((value) => <span className="tag" key={value}>{value}</span>)
          : <span className="empty-inline">{emptyText}</span>}
      </div>
    </div>
  );
}

function EvidenceClaim({ claim }) {
  return (
    <article className={`evidence-claim severity-${claim.severity.toLowerCase()}`}>
      <div className="claim-heading">
        <strong>{claim.risk_type}</strong>
        <span className="severity-badge">{claim.severity}</span>
      </div>
      <p>{claim.statement}</p>
      <dl className="evidence-details">
        <div>
          <dt>事实 ID</dt>
          <dd><code>{claim.fact_id}</code></dd>
        </div>
        <div>
          <dt>严重度依据</dt>
          <dd>{claim.severity_rationale}</dd>
        </div>
        <div>
          <dt>来源 ID</dt>
          <dd>{claim.source_ids.map((sourceId) => <code key={sourceId}>{sourceId}</code>)}</dd>
        </div>
        <div>
          <dt>来源定位</dt>
          <dd>{claim.source_locator}</dd>
        </div>
      </dl>
    </article>
  );
}

export default function ResultPanel({ result }) {
  if (!result) {
    return null;
  }

  const resolution = result.resolution || {};
  const explanation = result.explanation || {};
  const status = STATUS_CONTENT[explanation.conclusion_status] || STATUS_CONTENT.knowledge_unavailable;
  const medications = resolution.medications || [];
  const contexts = resolution.contexts || [];
  const unresolved = resolution.unresolved_mentions || [];
  const claims = explanation.claims || [];
  const limitations = explanation.limitations || [];
  const safetyFlags = resolution.safety_flags || [];

  return (
    <div className="panel result-panel">
      <section className={`status-card status-${status.tone}`}>
        <div>
          <span className="eyebrow">结论状态</span>
          <h2>{status.title}</h2>
          <p>{explanation.summary || status.description}</p>
        </div>
        <code>{explanation.conclusion_status}</code>
      </section>

      {resolution.clarification_question ? (
        <section className="clarification-card">
          <strong>需要你确认</strong>
          <p>{resolution.clarification_question}</p>
        </section>
      ) : null}

      <section>
        <h3>输入解析</h3>
        <div className="entity-grid">
          <TagList label="已识别药品" values={medications} emptyText="无" />
          <TagList label="已识别上下文" values={contexts} emptyText="无" />
        </div>
        {unresolved.length > 0 ? (
          <TagList label="未解析内容" values={unresolved} emptyText="无" />
        ) : null}
        <p className="contract-note">
          解析契约：<code>{resolution.schema_version}</code> · 状态：<code>{resolution.status}</code>
        </p>
        {safetyFlags.includes('instruction_like_text_ignored') ? (
          <p className="safety-flag">检测到指令式文本；系统已忽略该指令，只解析受控药品和上下文。</p>
        ) : null}
      </section>

      <section>
        <h3>证据与风险</h3>
        {claims.length > 0
          ? claims.map((claim) => <EvidenceClaim claim={claim} key={claim.fact_id} />)
          : <div className="empty-evidence">本次响应没有风险事实。请结合上方结论状态理解，不能据此推断安全。</div>}
      </section>

      {limitations.length > 0 ? (
        <section>
          <h3>限制说明</h3>
          <ul className="limitation-list">
            {limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
          </ul>
        </section>
      ) : null}

      <section className="result-metadata">
        <span>数据版本：<code>{explanation.data_version || 'unavailable'}</code></span>
        <span>生成模式：<code>{explanation.generation_mode}</code></span>
        <span>Prompt：<code>{explanation.prompt_version}</code></span>
        {explanation.fallback_reason ? (
          <span>回退原因：<code>{explanation.fallback_reason}</code></span>
        ) : null}
      </section>
    </div>
  );
}
