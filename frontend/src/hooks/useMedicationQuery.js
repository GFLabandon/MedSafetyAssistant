import { useCallback, useState } from 'react';
import { submitMedicationQuery } from '../api/client.js';

export function useMedicationQuery() {
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
      const data = await submitMedicationQuery(question);
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
