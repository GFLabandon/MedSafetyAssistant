import { useCallback, useState } from 'react';
import { streamMedicationQuery, submitMedicationQuery } from '../api/client.js';

export function useMedicationQuery() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState('');

  const submit = useCallback(async (question, options = { stream: true }) => {
    if (loading || streaming) {
      return null;
    }

    setError('');
    setResult(null);

    if (options.stream) {
      setStreaming(true);
      let meta = null;
      let responseText = '';

      try {
        await streamMedicationQuery(question, {
          onMeta(payload) {
            meta = { ...payload };
            delete meta.type;
            setResult({ ...meta, response_text: '' });
          },
          onToken(content) {
            responseText += content;
            setResult((current) => ({
              ...(current || meta || {}),
              response_text: responseText,
            }));
          },
          onDone(payload) {
            setResult((current) => ({
              ...(current || meta || {}),
              response_text: responseText,
              conversation_saved: Boolean(payload.conversation_saved),
              save_error: payload.save_error || null,
            }));
          },
        });

        return { ...(meta || {}), response_text: responseText };
      } catch (err) {
        setError(err.message || '查询失败');
        return null;
      } finally {
        setStreaming(false);
      }
    }

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
  }, [loading, streaming]);

  return {
    result,
    loading,
    streaming,
    error,
    submit,
  };
}
