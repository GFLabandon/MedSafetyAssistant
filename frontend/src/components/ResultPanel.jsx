import React from 'react';
import DrugInfoCard from './DrugInfoCard.jsx';
import EntityTags from './EntityTags.jsx';
import RiskCard from './RiskCard.jsx';
import RouteBadge from './RouteBadge.jsx';

export default function ResultPanel({ result }) {
  if (!result) {
    return null;
  }

  const risks = result.risks || [];
  const drugInfos = result.drug_infos || [];

  return (
    <div className="panel result-panel">
      <div className="result-heading">
        <h2>分析结果</h2>
        <RouteBadge route={result.route} />
      </div>

      <h3>识别对象</h3>
      <EntityTags drugs={result.final_drugs || []} conditions={result.final_conditions || []} />

      <h3>风险扫描</h3>
      {risks.length === 0 ? (
        <div className="safe-state">当前知识图谱未发现已知禁忌。请注意这不等于绝对安全。</div>
      ) : (
        risks.map((risk, index) => <RiskCard key={`${risk.type}-${risk.drug}-${index}`} risk={risk} />)
      )}

      <h3>回答</h3>
      <div className="answer">{result.response_text || '正在生成回答...'}</div>

      {drugInfos.length > 0 ? (
        <>
          <h3>药品档案</h3>
          {drugInfos.map((info) => <DrugInfoCard key={info.drug} info={info} />)}
        </>
      ) : null}

      {result.conversation_saved ? <p className="save-status">对话已保存到历史记忆。</p> : null}
      {result.save_error ? <p className="save-status save-error">保存历史失败：{result.save_error}</p> : null}
    </div>
  );
}
