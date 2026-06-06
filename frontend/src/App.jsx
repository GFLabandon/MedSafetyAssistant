import React, { useState } from 'react';
import QueryForm from './components/QueryForm.jsx';
import ResultPanel from './components/ResultPanel.jsx';
import { useMedicationQuery } from './hooks/useMedicationQuery.js';

export default function App() {
  const [history, setHistory] = useState([]);
  const [selectedQuestion, setSelectedQuestion] = useState('');
  const { result, loading, streaming, error, submit } = useMedicationQuery();
  const busy = loading || streaming;

  async function handleSubmit(question) {
    setSelectedQuestion(question);
    const data = await submit(question, { stream: true });
    if (data) {
      setHistory((items) => [question, ...items.filter((item) => item !== question)].slice(0, 8));
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h2>查询历史</h2>
        <div className="history-list">
          {history.length === 0 ? <div className="history-empty">暂无本地查询历史</div> : null}
          {history.map((item) => (
            <button className="history-item" type="button" key={item} onClick={() => setSelectedQuestion(item)}>
              {item}
            </button>
          ))}
        </div>
      </aside>
      <main className="main">
        <div className="content">
          <h1 className="title">家庭用药安全助手</h1>
          <p className="subtitle">家庭常见用药风险核查</p>
          <div className="disclaimer">
            法律声明：本系统为科研演示原型，数据覆盖有限。用药建议不具法律效力，禁止作为临床决策唯一依据。
          </div>
          <QueryForm key={selectedQuestion} initialQuestion={selectedQuestion} loading={busy} onSubmit={handleSubmit} />
          {error ? <div className="error">{error}</div> : null}
          <ResultPanel result={result} />
        </div>
      </main>
    </div>
  );
}
