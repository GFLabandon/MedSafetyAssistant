import React, { useState } from 'react';
import QueryForm from './components/QueryForm.jsx';
import ResultPanel from './components/ResultPanel.jsx';
import { useMedicationQuery } from './hooks/useMedicationQuery.js';

export default function App() {
  const [history, setHistory] = useState([]);
  const [selectedQuestion, setSelectedQuestion] = useState('');
  const { result, loading, error, submit } = useMedicationQuery();

  async function handleSubmit(question) {
    setSelectedQuestion(question);
    const data = await submit(question);
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
          <p className="subtitle">基于来源对齐证据的家庭常见用药风险核查</p>
          <div className="disclaimer">
            本系统是工程验证原型，仅覆盖少量来源对齐事实，不是医疗器械，也不能替代医生或药师。
          </div>
          <QueryForm key={selectedQuestion} initialQuestion={selectedQuestion} loading={loading} onSubmit={handleSubmit} />
          {error ? <div className="error">{error}</div> : null}
          <ResultPanel result={result} />
        </div>
      </main>
    </div>
  );
}
