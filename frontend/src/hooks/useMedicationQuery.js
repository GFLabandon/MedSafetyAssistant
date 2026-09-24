import { useCallback, useRef, useState } from 'react';
import { submitSessionMedicationQuery } from '../api/client.js';

export function useMedicationQuery() {
  const sessionId = useRef(globalThis.crypto?.randomUUID?.() || null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = useCallback(async (question) => {
    if (loading) {
      return null;
    }

    setError('');
    setResult(null);
    setLoading(true);

    try {
      const data = await submitSessionMedicationQuery(question, sessionId.current);
      setResult(data);
      return data;
    } catch (err) {
      setError(err.message || '查询失败');
      return null;
    } finally {
      setLoading(false);
    }
  }, [loading]);

  return {
    result,
    loading,
    error,
    submit,
  };
}
