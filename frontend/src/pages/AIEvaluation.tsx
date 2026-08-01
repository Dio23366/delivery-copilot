import { api } from '../api/client';
import type {
  AIEvaluationMetricGroup,
  AIEvaluationMetricsResponse,
  AIEvaluationPromptVersionGroup,
} from '../api/types';
import { PageStatus } from '../components/PageStatus';
import { useApi } from '../hooks/useApi';

function formatPercentage(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '-';
  }
  return `${(value * 100).toFixed(1)}%`;
}

function formatModelName(value: string | null | undefined): string {
  return value ?? '-';
}

function formatPromptVersion(value: string | null | undefined): string {
  if (value === null || value === undefined) {
    return 'Unversioned (legacy)';
  }
  return value;
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <div className="metric-value">{value}</div>
      <div className="metric-label">{label}</div>
    </div>
  );
}

function OverviewSection({ metrics }: { metrics: AIEvaluationMetricsResponse }) {
  return (
    <section>
      <h2>Human Review Overview</h2>
      <div className="metrics-grid">
        <MetricCard label="Total Analyses" value={metrics.total_analyses.toString()} />
        <MetricCard label="Pending Reviews" value={metrics.pending_reviews.toString()} />
        <MetricCard label="Reviewed Analyses" value={metrics.reviewed_analyses.toString()} />
        <MetricCard label="Positive Outcome Rate" value={formatPercentage(metrics.positive_outcome_rate)} />
        <MetricCard label="Direct Acceptance Rate" value={formatPercentage(metrics.direct_acceptance_rate)} />
        <MetricCard label="Edit & Accept Rate" value={formatPercentage(metrics.edit_and_accept_rate)} />
        <MetricCard label="Rejection Rate" value={formatPercentage(metrics.rejection_rate)} />
      </div>
    </section>
  );
}

function ProviderBreakdownSection({ rows }: { rows: AIEvaluationMetricGroup[] }) {
  return (
    <section>
      <h2>Provider / Model Breakdown</h2>
      {rows.length === 0 ? (
        <p className="page-status">暂无 provider breakdown 数据</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Model</th>
              <th>Total</th>
              <th>Reviewed</th>
              <th>Pending</th>
              <th>Positive Outcome</th>
              <th>Direct Accept</th>
              <th>Edit &amp; Accept</th>
              <th>Reject</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.provider}-${row.model_name ?? 'null'}`}>
                <td>{row.provider}</td>
                <td>{formatModelName(row.model_name)}</td>
                <td>{row.total_analyses}</td>
                <td>{row.reviewed_analyses}</td>
                <td>{row.pending_reviews}</td>
                <td>{formatPercentage(row.positive_outcome_rate)}</td>
                <td>{formatPercentage(row.direct_acceptance_rate)}</td>
                <td>{formatPercentage(row.edit_and_accept_rate)}</td>
                <td>{formatPercentage(row.rejection_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function PromptVersionBreakdownSection({ rows }: { rows: AIEvaluationPromptVersionGroup[] }) {
  return (
    <section>
      <h2>Prompt Version Breakdown</h2>
      {rows.length === 0 ? (
        <p className="page-status">暂无 prompt version breakdown 数据</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Prompt Version</th>
              <th>Provider</th>
              <th>Model</th>
              <th>Total</th>
              <th>Reviewed</th>
              <th>Pending</th>
              <th>Direct Accept</th>
              <th>Edit &amp; Accept</th>
              <th>Reject</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.prompt_version ?? 'null'}-${row.provider}-${row.model_name ?? 'null'}`}>
                <td>{formatPromptVersion(row.prompt_version)}</td>
                <td>{row.provider}</td>
                <td>{formatModelName(row.model_name)}</td>
                <td>{row.total_analyses}</td>
                <td>{row.reviewed_analyses}</td>
                <td>{row.pending_reviews}</td>
                <td>{formatPercentage(row.direct_acceptance_rate)}</td>
                <td>{formatPercentage(row.edit_and_accept_rate)}</td>
                <td>{formatPercentage(row.rejection_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export function AIEvaluation() {
  const { data, loading, error } = useApi(api.getAIEvaluationMetrics);
  const metrics = data ?? null;
  const providerBreakdown = metrics?.provider_breakdown ?? [];
  const promptVersionBreakdown = metrics?.prompt_version_breakdown ?? [];

  return (
    <div>
      <h1>AI Evaluation</h1>
      <PageStatus loading={loading} error={error} empty={!metrics} emptyMessage="暂无 AI Evaluation 数据">
        {metrics ? (
          <div style={{ display: 'grid', gap: '24px' }}>
            <OverviewSection metrics={metrics} />
            <ProviderBreakdownSection rows={providerBreakdown} />
            <PromptVersionBreakdownSection rows={promptVersionBreakdown} />
          </div>
        ) : null}
      </PageStatus>
    </div>
  );
}
