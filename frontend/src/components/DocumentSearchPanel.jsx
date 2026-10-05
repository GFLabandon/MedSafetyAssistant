import React, { useState } from 'react';
import { searchProjectDocuments } from '../api/client.js';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export default function DocumentSearchPanel() {
  const [query, setQuery] = useState('');
  const [method, setMethod] = useState('lexical');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    if (query.trim().length < 2 || loading) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      setResult(await searchProjectDocuments(query.trim(), method));
    } catch (err) {
      setError(err.message || '文档检索失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel">
      <h2>项目文档检索实验区</h2>
      <p className="contract-note">检索项目自编文档的原文片段，用于比较检索方法；这些片段不是医学来源，也不参与上方风险判断。</p>
      <form className="fact-search-form" onSubmit={submit}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="例如：知识不可用时如何处理" aria-label="检索项目文档" />
        <select value={method} onChange={(event) => setMethod(event.target.value)} aria-label="文档检索方法">
          <option value="lexical">词法重叠</option>
          <option value="hashing_vector">本地哈希向量</option>
        </select>
        <button className="primary-button" type="submit" disabled={loading || query.trim().length < 2}>{loading ? '检索中...' : '检索文档'}</button>
      </form>
      {error ? <p className="error">{error}</p> : null}
      {result ? (
        <div aria-live="polite">
          <p className="contract-note">方法：{result.method} · 命中 {result.hits.length} 个片段</p>
          {result.hits.length === 0 ? <p>当前项目文档中没有匹配片段。</p> : null}
          <ul className="source-list">
            {result.hits.map((hit) => (
              <li key={hit.chunk_id}>
                <strong>{hit.title} / {hit.heading}</strong>
                <p>{hit.text}</p>
                <a href={`${API_BASE_URL}/api/v1/documents/${hit.document_id}`} target="_blank" rel="noopener noreferrer">打开完整项目文档</a>
                <code>{hit.chunk_id}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
