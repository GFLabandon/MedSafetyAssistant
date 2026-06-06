const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export async function submitMedicationQuery(question, sessionId = 'shared') {
  const response = await fetch(`${API_BASE_URL}/api/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: sessionId }),
  });

  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || data.detail || '查询失败');
  }

  return data;
}

export function parseSsePayload(line) {
  if (!line.startsWith('data: ')) {
    return null;
  }

  return JSON.parse(line.slice(6));
}

export async function streamMedicationQuery(question, callbacks = {}, sessionId = 'shared') {
  const response = await fetch(`${API_BASE_URL}/api/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, session_id: sessionId }),
  });

  if (!response.ok || !response.body) {
    throw new Error('流式查询启动失败');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() || '';

    for (const part of parts) {
      const payload = parseSsePayload(part.trim());
      if (!payload) {
        continue;
      }

      if (payload.type === 'meta') {
        callbacks.onMeta?.(payload);
      } else if (payload.type === 'token') {
        callbacks.onToken?.(payload.content || '');
      } else if (payload.type === 'done') {
        callbacks.onDone?.(payload);
      } else if (payload.type === 'error') {
        throw new Error(payload.error || '流式查询失败');
      }
    }
  }
}
