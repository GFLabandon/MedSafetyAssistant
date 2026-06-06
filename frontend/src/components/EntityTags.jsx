import React from 'react';

function TagGroup({ title, values }) {
  const items = values || [];
  return (
    <div className="entity-group">
      <strong>{title}</strong>
      <div className="tag-row">
        {items.length === 0 ? (
          <span className="tag">未识别</span>
        ) : (
          items.map((item) => (
            <span className="tag" key={item}>
              {item}
            </span>
          ))
        )}
      </div>
    </div>
  );
}

export default function EntityTags({ drugs, conditions }) {
  return (
    <div className="entity-tags">
      <TagGroup title="药品实体" values={drugs} />
      <TagGroup title="状态实体" values={conditions} />
    </div>
  );
}
