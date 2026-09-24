const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export async function submitMedicationQuery(question, { useLlmPlan = true } = {}) {
  const response = await fetch(`${API_BASE_URL}/api/v1/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      use_llm_plan: useLlmPlan,
    }),
  });

  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => item.msg).join('；')
      : data.detail;
    throw new Error(data.error || detail || '查询失败');
  }

  return data;
}

export async function searchReviewedFacts(query) {
  const response = await fetch(`${API_BASE_URL}/api/v1/knowledge/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || data.detail || '检索失败');
  }
  return data;
}

export async function searchProjectDocuments(query, method = 'lexical') {
  const response = await fetch(`${API_BASE_URL}/api/v1/documents/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, method }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || data.detail || '文档检索失败');
  }
  return data;
}

export async function searchReviewedSourceDocuments(query) {
  const response = await fetch(`${API_BASE_URL}/api/v1/source-documents/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, method: 'lexical' }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || data.detail || '来源文档检索失败');
  }
  return data;
}

export async function submitQueryFeedback(feedbackId, rating, reason = null) {
  const response = await fetch(`${API_BASE_URL}/api/v1/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ feedback_id: feedbackId, rating, reason }),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || '反馈提交失败');
  }
  return data;
}
