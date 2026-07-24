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
