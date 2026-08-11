import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type {
  AIFeedbackPayload,
  AgentRun,
  AgentRunStatus,
  AgentTriageResult,
  AIAnalysisHistoryItem,
  Issue,
} from '../api/types';
import { PageStatus } from '../components/PageStatus';
import { useApi } from '../hooks/useApi';

const ISSUE_TYPES: AgentTriageResult['issue_type'][] = [
  'API',
  'Data',
  'Deployment',
  'Configuration',
  'Integration',
];

const SEVERITIES: AgentTriageResult['severity'][] = ['low', 'medium', 'high', 'critical'];

const CONTROLLED_SUBTYPES: Record<AgentTriageResult['issue_type'], string[]> = {
  API: ['authentication', 'authorization', 'timeout', 'request_validation', 'response_error', 'rate_limit', 'api_dependency'],
  Data: ['schema_mapping', 'synchronization', 'migration', 'consistency', 'quality', 'missing_data', 'duplication'],
  Deployment: ['pipeline', 'build', 'release', 'environment', 'dependency', 'rollback'],
  Configuration: ['environment_variable', 'credential', 'permission', 'parameter', 'feature_flag', 'endpoint'],
  Integration: ['connectivity', 'protocol', 'third_party_dependency', 'webhook', 'messaging', 'compatibility'],
};

const TERMINAL_STATUSES: AgentRunStatus[] = ['completed', 'failed', 'cancelled', 'limit_exceeded'];

const CANCELLABLE_STATUSES: AgentRunStatus[] = [
  'running',
  'generating_analysis',
  'waiting_for_triage_confirmation',
  'waiting_for_clarification',
  'waiting_for_final_review',
];

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return '-';
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

const HIDDEN_UI_FIELDS = new Set(['retrieval_query', 'chunk_text', 'source_uri']);
const SECRET_FIELD_MARKERS = ['api_key', 'authorization', 'credential', 'password', 'secret', 'token'];

function redactForUi(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(redactForUi);
  }
  if (value === null || typeof value !== 'object') {
    return value;
  }

  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, item]) => {
      const normalizedKey = key.toLowerCase();
      if (HIDDEN_UI_FIELDS.has(normalizedKey)) {
        return [key, '[hidden from UI]'];
      }
      if (SECRET_FIELD_MARKERS.some((marker) => normalizedKey.includes(marker))) {
        return [key, '[redacted]'];
      }
      return [key, redactForUi(item)];
    }),
  );
}

function prettyJson(value: unknown): string {
  if (value === null || value === undefined) {
    return '-';
  }
  try {
    return JSON.stringify(redactForUi(value), null, 2);
  } catch {
    return String(value);
  }
}

function statusTone(status: AgentRunStatus): string {
  if (status === 'completed') return 'agent-status-success';
  if (status === 'failed' || status === 'limit_exceeded') return 'agent-status-error';
  if (status === 'cancelled') return 'agent-status-neutral';
  if (status.startsWith('waiting_')) return 'agent-status-waiting';
  return 'agent-status-running';
}

function emptyTriage(): AgentTriageResult {
  return {
    issue_type: 'API',
    subtype: '',
    severity: 'medium',
    confidence: 0.5,
    reason: '',
  };
}

function AgentTimeline({ run }: { run: AgentRun }) {
  if (run.steps.length === 0) {
    return <p className="agent-muted">No persisted steps yet.</p>;
  }

  return (
    <div className="agent-timeline">
      {run.steps.map((step) => (
        <article className="agent-step" key={step.id}>
          <div className="agent-step-heading">
            <div>
              <span className="agent-step-index">{step.step_index}</span>
              <strong>{step.node_name}</strong>
            </div>
            <span className="agent-chip">{step.step_status}</span>
          </div>
          <div className="agent-meta-grid">
            <span>Started: {formatDate(step.started_at)}</span>
            <span>Completed: {formatDate(step.completed_at)}</span>
          </div>
          {step.error_message ? <p className="page-error agent-inline-error">{step.error_message}</p> : null}
          {step.tool_calls.map((call) => (
            <details className="agent-tool" key={call.id}>
              <summary>
                {call.tool_name} · {call.call_status} · {call.read_only ? 'read-only' : 'write'}
              </summary>
              <div className="agent-tool-body">
                <p><strong>Version:</strong> {call.tool_version ?? '-'}</p>
                <p><strong>Timeout:</strong> {call.timeout_seconds}s</p>
                <p><strong>Requires approval:</strong> {call.requires_approval ? 'yes' : 'no'}</p>
                {call.error_message ? <p className="page-error agent-inline-error">{call.error_message}</p> : null}
                <details>
                  <summary>Arguments</summary>
                  <pre>{prettyJson(call.arguments)}</pre>
                </details>
                <details>
                  <summary>Result</summary>
                  <pre>{prettyJson(call.result)}</pre>
                </details>
              </div>
            </details>
          ))}
          <details className="agent-state-details">
            <summary>Step state snapshot</summary>
            <div className="agent-state-columns">
              <div>
                <h4>Input</h4>
                <pre>{prettyJson(step.input_state)}</pre>
              </div>
              <div>
                <h4>Output</h4>
                <pre>{prettyJson(step.output_state)}</pre>
              </div>
            </div>
          </details>
        </article>
      ))}
    </div>
  );
}

function GeneratedAnalysis({ run }: { run: AgentRun }) {
  const analysis = run.state.generated_analysis;
  if (!analysis) {
    return null;
  }

  return (
    <section className="ai-card">
      <h2>Generated Analysis</h2>
      <div className="agent-meta-grid">
        <span>Provider: {analysis.provider ?? '-'}</span>
        <span>Model: {analysis.model_name ?? '-'}</span>
        <span>Prompt: {analysis.prompt_version ?? '-'}</span>
        <span>Retrieval: {analysis.retrieval_status ?? '-'}</span>
      </div>
      <p><strong>Risk:</strong> {analysis.risk_level ?? '-'}</p>
      <p><strong>Summary:</strong> {analysis.issue_summary ?? '-'}</p>
      <p><strong>Possible root cause:</strong> {analysis.possible_root_cause ?? '-'}</p>
      <p><strong>Project impact:</strong> {analysis.project_impact ?? '-'}</p>
      <p><strong>Recommended actions:</strong></p>
      <ul>
        {(analysis.recommended_actions ?? []).map((item, index) => (
          <li key={`${item}-${index}`}>{item}</li>
        ))}
      </ul>
      <p><strong>Customer update draft:</strong></p>
      <p className="agent-prewrap">{analysis.customer_update_draft ?? '-'}</p>
    </section>
  );
}

export function AgentRuns() {
  const issuesApi = useApi(api.getIssues);
  const issues = issuesApi.data ?? [];
  const [selectedIssueId, setSelectedIssueId] = useState<number>(0);
  const [run, setRun] = useState<AgentRun | null>(null);
  const [triage, setTriage] = useState<AgentTriageResult>(emptyTriage());
  const [clarification, setClarification] = useState('');
  const [analysis, setAnalysis] = useState<AIAnalysisHistoryItem | null>(null);
  const [feedbackAction, setFeedbackAction] = useState<AIFeedbackPayload['feedback_status']>('accepted');
  const [feedbackNote, setFeedbackNote] = useState('');
  const [editedOutput, setEditedOutput] = useState('');
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  useEffect(() => {
    if (selectedIssueId === 0 && issues.length > 0) {
      setSelectedIssueId(issues[0].id);
    }
  }, [issues, selectedIssueId]);

  useEffect(() => {
    const suggestion = run?.state.triage_suggestion ?? run?.state.triage_result;
    if (suggestion) {
      setTriage({ ...suggestion });
    }
  }, [run]);

  useEffect(() => {
    setFeedbackAction('accepted');
    setFeedbackNote('');
    setEditedOutput('');
  }, [run?.analysis_log_id]);

  useEffect(() => {
    if (!run?.analysis_log_id) {
      setAnalysis(null);
      return;
    }
    let cancelled = false;
    void api.getIssueAnalysisHistory(run.issue_id).then((items) => {
      if (!cancelled) {
        setAnalysis(items.find((item) => item.analysis_id === run.analysis_log_id) ?? null);
      }
    }).catch((error: unknown) => {
      if (!cancelled) {
        setActionError(error instanceof Error ? error.message : 'Unable to load linked Analysis');
      }
    });
    return () => {
      cancelled = true;
    };
  }, [run?.analysis_log_id, run?.issue_id]);

  const selectedIssue = useMemo(
    () => issues.find((item) => item.id === selectedIssueId) ?? null,
    [issues, selectedIssueId],
  );

  async function execute(action: string, task: () => Promise<AgentRun>, message: string) {
    setBusyAction(action);
    setActionError(null);
    setActionMessage(null);
    try {
      const next = await task();
      setRun(next);
      setActionMessage(message);
      return next;
    } catch (error: unknown) {
      setActionError(error instanceof Error ? error.message : 'Agent operation failed');
      return null;
    } finally {
      setBusyAction(null);
    }
  }

  async function startRun() {
    if (!selectedIssueId) return;
    setAnalysis(null);
    await execute('start', () => api.createAgentRun(selectedIssueId), 'Agent Run started or active Run reused.');
  }

  async function refreshRun() {
    if (!run) return;
    await execute('refresh', () => api.getAgentRun(run.run_id), 'Agent Run refreshed.');
  }

  async function confirmTriage(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!run) return;
    await execute(
      'triage',
      () => api.resumeAgentRun(run.run_id, { triage_result: triage }),
      'Triage confirmed and investigation resumed.',
    );
  }

  async function submitClarification(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!run) return;
    const response = clarification.trim();
    if (!response) return;
    const next = await execute(
      'clarification',
      () => api.resumeAgentRun(run.run_id, { clarification_response: response }),
      'Clarification submitted and investigation resumed.',
    );
    if (next) setClarification('');
  }

  async function cancelRun() {
    if (!run) return;
    await execute('cancel', () => api.cancelAgentRun(run.run_id), 'Agent Run cancelled.');
  }

  async function submitFeedback(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!run?.analysis_log_id) return;
    setBusyAction('feedback');
    setActionError(null);
    setActionMessage(null);
    const payload: AIFeedbackPayload = {
      feedback_status: feedbackAction,
      feedback_note: feedbackNote.trim() || null,
    };
    if (feedbackAction === 'edited_and_accepted') {
      payload.edited_output = editedOutput.trim();
    }
    try {
      const saved = await api.submitAnalysisFeedback(run.analysis_log_id, payload);
      setAnalysis(saved);
      const refreshed = await api.getAgentRun(run.run_id);
      setRun(refreshed);
      setActionMessage('Final Human Review submitted and Agent Run refreshed.');
    } catch (error: unknown) {
      setActionError(error instanceof Error ? error.message : 'Unable to submit final review');
    } finally {
      setBusyAction(null);
    }
  }

  const isTerminal = run ? TERMINAL_STATUSES.includes(run.run_status) : false;
  const canCancel = run ? CANCELLABLE_STATUSES.includes(run.run_status) : false;

  return (
    <div>
      <div className="agent-page-heading">
        <div>
          <h1>Agent Investigation</h1>
          <p className="agent-muted">Operator view for the bounded, auditable single-Agent Issue workflow.</p>
        </div>
        {run ? <span className={`agent-status ${statusTone(run.run_status)}`}>{run.run_status}</span> : null}
      </div>

      <PageStatus loading={issuesApi.loading} error={issuesApi.error} empty={issues.length === 0} emptyMessage="No Issues available">
        <section className="ai-card agent-launcher">
          <label>
            <span>Issue</span>
            <select value={selectedIssueId} onChange={(event) => setSelectedIssueId(Number(event.target.value))} disabled={Boolean(run && !isTerminal)}>
              {issues.map((issue: Issue) => (
                <option key={issue.id} value={issue.id}>#{issue.id} · {issue.title}</option>
              ))}
            </select>
          </label>
          <button type="button" onClick={startRun} disabled={!selectedIssueId || busyAction !== null || Boolean(run && !isTerminal)}>
            {busyAction === 'start' ? 'Starting...' : 'Start / Reuse Agent Run'}
          </button>
          {selectedIssue ? <p className="agent-muted">{selectedIssue.description ?? 'No issue description'}</p> : null}
        </section>
      </PageStatus>

      {actionMessage ? <p className="page-status agent-success">{actionMessage}</p> : null}
      {actionError ? <p className="page-status page-error">{actionError}</p> : null}

      {run ? (
        <>
          <section className="agent-overview ai-card">
            <div className="agent-overview-header">
              <div>
                <h2>Run Control</h2>
                <p className="agent-run-id">{run.run_id}</p>
              </div>
              <div className="agent-actions">
                <button type="button" onClick={refreshRun} disabled={busyAction !== null}>Refresh</button>
                <button type="button" className="agent-danger-button" onClick={cancelRun} disabled={!canCancel || busyAction !== null}>Cancel Run</button>
              </div>
            </div>
            <div className="agent-stat-grid">
              <div><strong>{run.current_node}</strong><span>Current node</span></div>
              <div><strong>{run.step_count}</strong><span>Steps</span></div>
              <div><strong>{run.tool_call_count}</strong><span>Tool calls</span></div>
              <div><strong>{run.retry_count}</strong><span>Retries</span></div>
            </div>
            <div className="agent-meta-grid">
              <span>Graph: {run.graph_version}</span>
              <span>Resume node: {run.resume_node ?? '-'}</span>
              <span>Waiting since: {formatDate(run.waiting_since)}</span>
              <span>Updated: {formatDate(run.updated_at)}</span>
            </div>
            {run.error_message ? <p className="page-error agent-inline-error">{run.error_code ?? 'error'}: {run.error_message}</p> : null}
          </section>

          {run.run_status === 'waiting_for_triage_confirmation' ? (
            <section className="ai-card">
              <h2>Human Gate · Confirm Triage</h2>
              <p className="agent-muted">Review the deterministic suggestion before the Agent may investigate.</p>
              <form className="agent-form" onSubmit={confirmTriage}>
                <label><span>Issue type</span><select value={triage.issue_type} onChange={(event) => { const issueType = event.target.value as AgentTriageResult['issue_type']; setTriage({ ...triage, issue_type: issueType, subtype: CONTROLLED_SUBTYPES[issueType][0] }); }}>{ISSUE_TYPES.map((item) => <option key={item}>{item}</option>)}</select></label>
                <label><span>Subtype</span><select value={triage.subtype} required onChange={(event) => setTriage({ ...triage, subtype: event.target.value })}>{CONTROLLED_SUBTYPES[triage.issue_type].map((item) => <option key={item}>{item}</option>)}</select></label>
                <label><span>Severity</span><select value={triage.severity} onChange={(event) => setTriage({ ...triage, severity: event.target.value as AgentTriageResult['severity'] })}>{SEVERITIES.map((item) => <option key={item}>{item}</option>)}</select></label>
                <label><span>Confidence (0–1)</span><input type="number" min="0" max="1" step="0.01" value={triage.confidence} required onChange={(event) => setTriage({ ...triage, confidence: Number(event.target.value) })} /></label>
                <label className="agent-form-wide"><span>Reason</span><textarea value={triage.reason} maxLength={2000} required onChange={(event) => setTriage({ ...triage, reason: event.target.value })} /></label>
                <div className="agent-form-wide"><button type="submit" disabled={busyAction !== null}>{busyAction === 'triage' ? 'Resuming...' : 'Confirm & Resume'}</button></div>
              </form>
            </section>
          ) : null}

          {run.run_status === 'waiting_for_clarification' ? (
            <section className="ai-card">
              <h2>Human Gate · Clarification Required</h2>
              <p><strong>Question:</strong> {run.state.clarification_question ?? 'Additional business context is required.'}</p>
              <p><strong>Why:</strong> {run.state.evidence_reason ?? 'Current evidence is insufficient.'}</p>
              <form className="agent-form" onSubmit={submitClarification}>
                <label className="agent-form-wide"><span>Clarification response</span><textarea value={clarification} minLength={12} maxLength={4000} required onChange={(event) => setClarification(event.target.value)} /></label>
                <div className="agent-form-wide"><button type="submit" disabled={busyAction !== null}>{busyAction === 'clarification' ? 'Resuming...' : 'Submit & Resume'}</button></div>
              </form>
            </section>
          ) : null}

          <GeneratedAnalysis run={run} />

          {run.run_status === 'waiting_for_final_review' && analysis ? (
            <section className="ai-card">
              <h2>Human Gate · Final Review</h2>
              <p>Analysis #{analysis.analysis_id} is pending. The original generated output remains immutable.</p>
              <form className="agent-form" onSubmit={submitFeedback}>
                <label><span>Decision</span><select value={feedbackAction} onChange={(event) => setFeedbackAction(event.target.value as AIFeedbackPayload['feedback_status'])}><option value="accepted">Accept</option><option value="rejected">Reject</option><option value="edited_and_accepted">Edit & Accept</option></select></label>
                <label className="agent-form-wide"><span>Review note</span><textarea value={feedbackNote} onChange={(event) => setFeedbackNote(event.target.value)} /></label>
                {feedbackAction === 'edited_and_accepted' ? <label className="agent-form-wide"><span>Edited output</span><textarea value={editedOutput} required onChange={(event) => setEditedOutput(event.target.value)} /></label> : null}
                <div className="agent-form-wide"><button type="submit" disabled={busyAction !== null}>{busyAction === 'feedback' ? 'Submitting...' : 'Submit Final Review'}</button></div>
              </form>
            </section>
          ) : null}

          <section className="ai-card">
            <div className="agent-section-heading">
              <div><h2>Execution Timeline</h2><p className="agent-muted">Persisted Steps and nested Tool Calls; backend remains the source of truth.</p></div>
              <span className="agent-chip">{run.steps.length} steps</span>
            </div>
            <AgentTimeline run={run} />
          </section>

          <details className="ai-card agent-raw-state">
            <summary>Controlled Agent state · sensitive fields hidden</summary>
            <pre>{prettyJson(run.state)}</pre>
          </details>
        </>
      ) : null}
    </div>
  );
}
