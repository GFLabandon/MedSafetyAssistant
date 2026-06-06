import { useState } from 'react';

export default function QueryForm({ initialQuestion, loading, onSubmit }) {
  const [question, setQuestion] = useState(initialQuestion || '');

  function submit() {
    const trimmed = question.trim();
    if (!trimmed || loading) {
      return;
    }
    onSubmit(trimmed);
  }

  function handleKeyDown(event) {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      submit();
    }
  }

  return (
    <div className="panel query-form">
      <textarea
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="请输入用药问题，例如：我有高血压，能吃泰诺吗？"
      />
      <div className="actions">
        <button className="primary-button" type="button" disabled={loading || !question.trim()} onClick={submit}>
          {loading ? '分析中...' : '开始分析'}
        </button>
      </div>
    </div>
  );
}
