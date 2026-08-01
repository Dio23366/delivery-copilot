import type { ReactNode } from 'react';

interface PageStatusProps {
  loading: boolean;
  error: string | null;
  empty?: boolean;
  emptyMessage?: string;
  children: ReactNode;
}

export function PageStatus({
  loading,
  error,
  empty = false,
  emptyMessage = '暂无数据',
  children,
}: PageStatusProps) {
  if (loading) {
    return <p className="page-status">加载中...</p>;
  }

  if (error) {
    return <p className="page-status page-error">加载失败：{error}</p>;
  }

  if (empty) {
    return <p className="page-status">{emptyMessage}</p>;
  }

  return <>{children}</>;
}
