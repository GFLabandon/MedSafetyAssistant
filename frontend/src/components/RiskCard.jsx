const TYPE_LABELS = {
  DUPLICATE_THERAPY: '重复成分',
  CONTRAINDICATION: '用药禁忌',
  INTERACTION: '药物相互作用',
};

export default function RiskCard({ risk }) {
  const fatal = risk.severity === 'FATAL';
  return (
    <div className={`risk-card ${fatal ? 'fatal' : ''}`}>
      <div className="risk-heading">
        <strong>{TYPE_LABELS[risk.type] || risk.type}</strong>
        <span className="tag">严重程度：{risk.severity || 'UNKNOWN'}</span>
      </div>
      <p>{risk.drug}{risk.condition ? ` + ${risk.condition}` : ''}</p>
      {risk.ingredient ? <p>重复成分：{risk.ingredient}</p> : null}
      <p>{risk.reason}</p>
    </div>
  );
}
