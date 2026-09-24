import React, { useState } from 'react';
import { submitQueryFeedback } from '../api/client.js';

export default function FeedbackPanel({ feedbackId }) {
  const [reason, setReason] = useState('');
  const [choosingReason, setChoosingReason] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState('');

  if (!feedbackId) return null;

  async function submit(rating, selectedReason = null) {
    setSubmitting(true);
    setError('');
    try {
      await submitQueryFeedback(feedbackId, rating, selectedReason);
      setDone(true);
    } catch (err) {
      setError(err.message || '反馈提交失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="feedback-panel">
      <h3>这次结果有帮助吗？</h3>
      <p className="contract-note">只记录本次评价和原因类别，不保存你的问题正文。</p>
      {done ? <p role="status">感谢反馈，已记录。</p> : (
        <>
          <div className="feedback-actions">
            <button type="button" disabled={submitting} onClick={() => submit('useful')}>有帮助</button>
            <button type="button" disabled={submitting} onClick={() => setChoosingReason(true)}>需改进</button>
          </div>
          {choosingReason ? (
            <div className="feedback-actions">
              <select value={reason} onChange={(event) => setReason(event.target.value)} aria-label="需改进原因">
                <option value="">选择原因</option>
                <option value="missing_evidence">证据不足</option>
                <option value="wrong_entity">药品识别不准</option>
                <option value="unclear_explanation">说明不清楚</option>
                <option value="other">其他</option>
              </select>
              <button type="button" disabled={!reason || submitting} onClick={() => submit('not_useful', reason)}>提交反馈</button>
            </div>
          ) : null}
        </>
      )}
      {error ? <p className="error" role="alert">{error}</p> : null}
    </section>
  );
}
