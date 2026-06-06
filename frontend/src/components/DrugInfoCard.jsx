export default function DrugInfoCard({ info }) {
  return (
    <div className="drug-card">
      <strong>{info.drug}</strong>
      <div className="tag-row">
        <span className="tag">{info.category || '未分类'}</span>
        <span className="tag">成分：{info.ingredients || '未记录'}</span>
      </div>
      <p>{info.function || '暂无功能说明'}</p>
      <p>用法用量：{info.dosage || '请参考说明书'}</p>
    </div>
  );
}
