import React from 'react';

const ROUTE_LABELS = {
  query_kg: '知识图谱检索',
  search_history: '历史对话检索',
  both: '混合检索',
};

export default function RouteBadge({ route }) {
  const safeRoute = route || 'both';
  return (
    <span className={`route-badge route-${safeRoute}`}>
      {ROUTE_LABELS[safeRoute] || safeRoute}
    </span>
  );
}
