import { useCallback, useEffect, useRef, useState } from 'react';

interface UseApiResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<T | null>;
}

export function useApi<T>(fetcher: () => Promise<T>): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const cancelledRef = useRef(false);
  const fetcherRef = useRef(fetcher);

  useEffect(() => {
    fetcherRef.current = fetcher;
  }, [fetcher]);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await fetcherRef.current();
      if (cancelledRef.current) {
        return null;
      }
      setData(result);
      return result;
    } catch (err: unknown) {
      if (!cancelledRef.current) {
        setError(err instanceof Error ? err.message : '未知错误');
      }
      return null;
    } finally {
      if (!cancelledRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    cancelledRef.current = false;
    void run();

    return () => {
      cancelledRef.current = true;
    };
  }, [run]);

  return { data, loading, error, refetch: run };
}
