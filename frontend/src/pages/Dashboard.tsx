import { api } from '../api/client';
import type { DashboardMetrics } from '../api/types';
import { PageStatus } from '../components/PageStatus';
import { useApi } from '../hooks/useApi';

const METRIC_ITEMS: { key: keyof DashboardMetrics; label: string }[] = [
  { key: 'active_customers', label: 'Active Customers' },
  { key: 'active_projects', label: 'Active Projects' },
  { key: 'open_issues', label: 'Open Issues' },
  { key: 'critical_issues', label: 'Critical Issues' },
  { key: 'overdue_requirements', label: 'Overdue Requirements' },
  { key: 'projects_at_risk', label: 'Projects at Risk' },
];

export function Dashboard() {
  const { data, loading, error } = useApi(api.getDashboardMetrics);
  const metrics = data ?? null;

  return (
    <div>
      <h1>Dashboard</h1>
      <PageStatus loading={loading} error={error} empty={!metrics} emptyMessage="暂无仪表盘数据">
        <div className="metrics-grid">
          {METRIC_ITEMS.map((item) => (
            <div key={item.key} className="metric-card">
              <div className="metric-value">{metrics?.[item.key] ?? 0}</div>
              <div className="metric-label">{item.label}</div>
            </div>
          ))}
        </div>
      </PageStatus>
    </div>
  );
}
