import React, { useState } from 'react';
import { searchReviewedFacts, searchReviewedSourceDocuments } from '../api/client.js';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export default function FactSearchPanel() {
  const [query, setQuery] = useState('');
  const [scope, setScope] = useState('facts');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (query.trim().length < 2 || loading) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      setResult(await (scope === 'facts' ? searchReviewedFacts(query.trim()) : searchReviewedSourceDocuments(query.trim())));
    } catch (err) {
      setError(err.message || '检索失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel">
      <h2>查找已审事实</h2>
      <p className="contract-note">可比较已审事实摘要和当前已核对的 FDA 来源章节；检索结果与上方风险判断相互独立，不代表用药建议。</p>
      <form className="fact-search-form" onSubmit={submit}>
        <select value={scope} onChange={(event) => { setScope(event.target.value); setResult(null); }} aria-label="检索范围">
          <option value="facts">事实摘要</option>
          <option value="sources">FDA 来源章节</option>
        </select>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="例如：布洛芬和阿司匹林" aria-label="检索已审事实" />
        <button className="primary-button" type="submit" disabled={loading || query.trim().length < 2}>{loading ? '检索中...' : '检索'}</button>
      </form>
      {error ? <p className="error">{error}</p> : null}
      {result ? (
        <div aria-live="polite">
          <p className="contract-note">{scope === 'facts' ? `数据版本：${result.data_version}` : 'FDA 来源章节快照'} · 命中 {result.hits.length} 条</p>
          {result.hits.length === 0 ? <p>当前检索范围内没有匹配项。</p> : null}
          <ul className="source-list">
            {scope === 'facts' ? result.hits.map((hit) => (
              <li key={hit.fact_id}>
                <strong>{hit.summary}</strong>
                <span>{hit.source_locator}</span>
                {hit.sources.map((source) => <a key={source.source_id} href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a>)}
                <code>{hit.fact_id}</code>
              </li>
            )) : result.hits.map((hit) => (
              <li key={hit.chunk_id}>
                <strong>{hit.title} / {hit.heading}</strong>
                <p>{hit.text}</p>
                <a href={hit.source_url} target="_blank" rel="noopener noreferrer">打开 FDA 原页面</a>
                <a href={`${API_BASE_URL}/api/v1/source-documents/${hit.document_id}`} target="_blank" rel="noopener noreferrer">打开本次抽取快照</a>
                <code>{hit.chunk_id}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
