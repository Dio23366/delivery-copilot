import { useEffect, useMemo, useState } from 'react';

import { api } from '../api/client';
import type { AIAnalysisHistoryItem, Issue, IssueAnalysisResult, IssueCreatePayload, Project } from '../api/types';
import { PageStatus } from '../components/PageStatus';
import { useApi } from '../hooks/useApi';

const ISSUE_TYPES = ['API', 'Data', 'Deployment', 'Configuration', 'Integration'];
const SEVERITIES = ['low', 'medium', 'high', 'critical'];
const STATUSES = ['open', 'investigating', 'waiting_on_customer', 'waiting_on_engineering', 'resolved'];
const OWNERS = ['Engineering Team', 'Delivery Manager', 'Customer Success'];

type FeedbackAction = '' | 'accepted' | 'rejected' | 'edited_and_accepted';

export function Issues() {
  const issuesApi = useApi(api.getIssues);
  const projectsApi = useApi(api.getProjects);
  const issues = issuesApi.data ?? [];
  const projects = projectsApi.data ?? [];

  const [showForm, setShowForm] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [analysisLoadingId, setAnalysisLoadingId] = useState<number | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [rowErrorId, setRowErrorId] = useState<number | null>(null);
  const [historyOpenId, setHistoryOpenId] = useState<number | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [analysisHistory, setAnalysisHistory] = useState<AIAnalysisHistoryItem[]>([]);
  const [currentAnalysis, setCurrentAnalysis] = useState<IssueAnalysisResult | null>(null);
  const [feedbackSubmittingId, setFeedbackSubmittingId] = useState<number | null>(null);
  const [feedbackAction, setFeedbackAction] = useState<FeedbackAction>('');
  const [feedbackNote, setFeedbackNote] = useState('');
  const [editedOutput, setEditedOutput] = useState('');
  const [form, setForm] = useState<IssueCreatePayload>({
    title: '',
    description: '',
    issue_type: 'API',
    severity: 'medium',
    status: 'open',
    owner: 'Engineering Team',
    project_id: 0,
  });

  useEffect(() => {
    if (projects.length > 0 && form.project_id === 0) {
      setForm((prev) => ({ ...prev, project_id: projects[0].id }));
    }
  }, [projects, form.project_id]);

  useEffect(() => {
    setFeedbackAction('');
    setFeedbackNote('');
    setEditedOutput('');
  }, [currentAnalysis?.analysis_id]);

  const projectOptions = useMemo(() => projects, [projects]);

  function renderRecommendedActions(actions?: string[] | null) {
    if (!Array.isArray(actions) || actions.length === 0) {
      return <p>-</p>;
    }
    return (
      <ul>
        {actions.map((action, index) => (
          <li key={`${action}-${index}`}>{action}</li>
        ))}
      </ul>
    );
  }

  function renderCustomerUpdateDraft(draft?: string | null) {
    if (!draft || !draft.trim()) {
      return <p>-</p>;
    }
    return <p style={{ whiteSpace: 'pre-wrap' }}>{draft}</p>;
  }

  function formatSimilarityScore(value: unknown) {
    return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(4) : '-';
  }

  function getGroundingPresentation(analysis: Pick<IssueAnalysisResult, 'knowledge_grounded' | 'retrieval_status'>) {
    if (analysis.knowledge_grounded === true) {
      return { label: 'Grounded with Knowledge', className: 'grounding-badge grounding-badge-grounded' };
    }
    if (analysis.retrieval_status === 'succeeded') {
      return { label: 'Knowledge Retrieved · Not Grounded', className: 'grounding-badge grounding-badge-retrieved' };
    }
    if (analysis.retrieval_status === 'no_results') {
      return { label: 'No Knowledge Match', className: 'grounding-badge grounding-badge-empty' };
    }
    if (analysis.retrieval_status === 'failed') {
      return { label: 'Retrieval Failed', className: 'grounding-badge grounding-badge-failed' };
    }
    return { label: 'Retrieval Not Attempted', className: 'grounding-badge grounding-badge-neutral' };
  }

  function renderGroundingEvidence(analysis: IssueAnalysisResult | AIAnalysisHistoryItem) {
    const presentation = getGroundingPresentation(analysis);
    const citations = Array.isArray(analysis.knowledge_citations) ? analysis.knowledge_citations : [];

    return (
      <div className="grounding-panel">
        <div className="grounding-header">
          <div className="grounding-status">
            <span className={presentation.className}>{presentation.label}</span>
            <span className="grounding-meta">Retrieval status: {analysis.retrieval_status}</span>
          </div>
          <div className="grounding-meta">Prompt Version: {analysis.prompt_version ?? '-'}</div>
        </div>

        {analysis.retrieval_error_code ? <p className="grounding-error">Retrieval error code: {analysis.retrieval_error_code}</p> : null}

        <details className="grounding-details">
          <summary>Knowledge Citations ({citations.length})</summary>
          {citations.length === 0 ? (
            <p className="grounding-empty">No citations available.</p>
          ) : (
            <div className="citation-list">
              {citations.map((citation, index) => (
                <article key={`${citation.citation_id ?? 'K'}-${index}`} className="citation-card">
                  <div className="citation-card-header">
                    <span className="citation-id">{citation.citation_id ?? `K${index + 1}`}</span>
                    <span className="citation-title">{citation.document_title}</span>
                  </div>
                  <div className="citation-meta">Document ID: {citation.document_id}</div>
                  <div className="citation-meta">Doc Type: {citation.doc_type}</div>
                  <div className="citation-meta">Scope: {citation.scope_type}</div>
                  <div className="citation-meta">Source Kind: {citation.source_kind}</div>
                  {citation.source_name ? <div className="citation-meta">Source Name: {citation.source_name}</div> : null}
                  <div className="citation-meta">Similarity: {formatSimilarityScore(citation.similarity_score)}</div>
                </article>
              ))}
            </div>
          )}
        </details>
      </div>
    );
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);
    try {
      await api.createIssue({
        ...form,
        title: form.title.trim(),
        description: form.description?.trim() || null,
      });
      setSubmitSuccess('Issue 创建成功');
      setShowForm(false);
      setForm((prev) => ({
        ...prev,
        title: '',
        description: '',
        issue_type: 'API',
        severity: 'medium',
        status: 'open',
        owner: 'Engineering Team',
      }));
      await issuesApi.refetch();
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : '创建失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStatusChange(issue: Issue, nextStatus: string) {
    if (nextStatus === issue.status) {
      return;
    }
    setUpdatingId(issue.id);
    setRowErrorId(null);
    try {
      await api.updateIssueStatus(issue.id, nextStatus);
      setSubmitSuccess('Issue 状态更新成功');
      await issuesApi.refetch();
    } catch (err: unknown) {
      setRowErrorId(issue.id);
      setSubmitError(err instanceof Error ? err.message : '状态更新失败');
      await issuesApi.refetch();
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleAnalyze(issue: Issue) {
    setAnalysisLoadingId(issue.id);
    setAnalysisError(null);
    try {
      const result = await api.summarizeIssue(issue.id);
      setCurrentAnalysis(result);
      setFeedbackAction('');
      setFeedbackNote('');
      setEditedOutput('');
    } catch (err: unknown) {
      setAnalysisError(err instanceof Error ? err.message : 'AI 分析失败');
    } finally {
      setAnalysisLoadingId(null);
    }
  }

  async function loadHistory(issueId: number) {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const history = await api.getIssueAnalysisHistory(issueId);
      setAnalysisHistory(history);
      setHistoryOpenId(issueId);
    } catch (err: unknown) {
      setHistoryError(err instanceof Error ? err.message : '获取历史失败');
    } finally {
      setHistoryLoading(false);
    }
  }

  function openHistoryItem(item: AIAnalysisHistoryItem) {
    setCurrentAnalysis(item);
    setFeedbackAction('');
    setFeedbackNote('');
    setEditedOutput('');
  }

  async function submitFeedback(analysisId: number) {
    if (!feedbackAction) {
      setAnalysisError('请选择反馈操作');
      return;
    }
    setFeedbackSubmittingId(analysisId);
    setAnalysisError(null);
    try {
      await api.submitAnalysisFeedback(analysisId, {
        feedback_status: feedbackAction,
        feedback_note: feedbackNote || null,
        edited_output: feedbackAction === 'edited_and_accepted' ? editedOutput || null : null,
      });
      const refreshedHistory = currentAnalysis ? await api.getIssueAnalysisHistory(currentAnalysis.issue_id) : [];
      if (currentAnalysis) {
        setAnalysisHistory(refreshedHistory);
        const matched = refreshedHistory.find((item) => item.analysis_id === analysisId);
        if (matched) {
          setCurrentAnalysis(matched);
        }
      }
      if (historyOpenId) {
        const refreshed = await api.getIssueAnalysisHistory(historyOpenId);
        setAnalysisHistory(refreshed);
      }
      setFeedbackAction('');
      setFeedbackNote('');
      setEditedOutput('');
    } catch (err: unknown) {
      setAnalysisError(err instanceof Error ? err.message : '反馈提交失败');
    } finally {
      setFeedbackSubmittingId(null);
    }
  }

  return (
    <div>
      <h1>Issues</h1>
      <button type="button" onClick={() => setShowForm((value) => !value)}>
        {showForm ? '关闭表单' : 'Create Issue'}
      </button>
      {submitSuccess ? <p className="page-status">{submitSuccess}</p> : null}
      {submitError ? <p className="page-status page-error">{submitError}</p> : null}
      {analysisError ? <p className="page-status page-error">{analysisError}</p> : null}
      {showForm ? (
        <form onSubmit={handleSubmit} className="data-form">
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="title" required />
          <textarea value={form.description ?? ''} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="description" />
          <select value={form.issue_type ?? ''} onChange={(e) => setForm({ ...form, issue_type: e.target.value })}>
            {ISSUE_TYPES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
            {SEVERITIES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <select value={form.owner ?? ''} onChange={(e) => setForm({ ...form, owner: e.target.value })}>
            {OWNERS.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: Number(e.target.value) })} disabled={projectsApi.loading}>
            {projectOptions.map((project: Project) => (
              <option key={project.id} value={project.id}>{project.name}</option>
            ))}
          </select>
          {projectsApi.error ? <p className="page-error">{projectsApi.error}</p> : null}
          <div>
            <button type="submit" disabled={submitting || projectsApi.loading || projectOptions.length === 0}>
              {submitting ? '提交中...' : '提交'}
            </button>
            <button type="button" onClick={() => setShowForm(false)} disabled={submitting}>
              取消
            </button>
          </div>
        </form>
      ) : null}
      <PageStatus loading={issuesApi.loading} error={issuesApi.error} empty={issues.length === 0} emptyMessage="暂无问题数据">
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Title</th>
              <th>issue_type</th>
              <th>Severity</th>
              <th>Status</th>
              <th>Owner</th>
              <th>project_id</th>
              <th>AI</th>
            </tr>
          </thead>
          <tbody>
            {issues.map((issue) => (
              <tr key={issue.id}>
                <td>{issue.id}</td>
                <td>{issue?.title ?? '-'}</td>
                <td>{issue?.issue_type ?? '-'}</td>
                <td>{issue?.severity ?? '-'}</td>
                <td>
                  <select
                    value={issue.status}
                    disabled={updatingId === issue.id}
                    onChange={(e) => handleStatusChange(issue, e.target.value)}
                  >
                    {STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{issue?.owner ?? '-'}</td>
                <td>{issue?.project_id ?? '-'}</td>
                <td>
                  <button type="button" onClick={() => handleAnalyze(issue)} disabled={analysisLoadingId === issue.id}>
                    {analysisLoadingId === issue.id ? 'Analyzing...' : 'Analyze with AI'}
                  </button>
                  <button type="button" onClick={() => loadHistory(issue.id)} disabled={historyLoading && historyOpenId === issue.id}>
                    View Analysis History
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </PageStatus>

      {currentAnalysis ? (
        <div className="ai-grid" style={{ marginTop: '16px' }}>
          <div className="ai-card">
            <h3>AI Analysis #{currentAnalysis.analysis_id}</h3>
            <p><strong>Provider:</strong> {currentAnalysis.provider === 'llm' ? 'LLM' : 'Rule-based Fallback'}</p>
            <p><strong>Model:</strong> {currentAnalysis.model_name ?? '-'}</p>
            {renderGroundingEvidence(currentAnalysis)}
            <p><strong>Risk:</strong> {currentAnalysis.risk_level}</p>
            <p><strong>Summary:</strong> {currentAnalysis.issue_summary}</p>
            <p><strong>Root cause:</strong> {currentAnalysis.possible_root_cause}</p>
            <p><strong>Recommended Actions:</strong></p>
            {renderRecommendedActions(currentAnalysis.recommended_actions)}
            <p><strong>Project impact:</strong> {currentAnalysis.project_impact}</p>
            <p><strong>Customer Update Draft:</strong></p>
            {renderCustomerUpdateDraft(currentAnalysis.customer_update_draft)}
            <p><strong>Feedback:</strong> {currentAnalysis.feedback_status}</p>
            <details>
              <summary>展开反馈操作</summary>
              <div style={{ display: 'grid', gap: '8px', marginTop: '8px' }}>
                <select
                  value={feedbackAction}
                  onChange={(e) => {
                    const next = e.target.value as FeedbackAction;
                    setFeedbackAction(next);
                    if (next === 'edited_and_accepted' && !editedOutput.trim()) {
                      setEditedOutput(currentAnalysis.customer_update_draft);
                    }
                    if (next !== 'edited_and_accepted') {
                      setEditedOutput('');
                    }
                  }}
                >
                  <option value="">Select feedback action</option>
                  <option value="accepted">Accept</option>
                  <option value="rejected">Reject</option>
                  <option value="edited_and_accepted">Edit & Accept</option>
                </select>
                <textarea
                  value={feedbackNote}
                  onChange={(e) => setFeedbackNote(e.target.value)}
                  placeholder="feedback note"
                />
                {feedbackAction === 'edited_and_accepted' ? (
                  <textarea
                    value={editedOutput}
                    onChange={(e) => setEditedOutput(e.target.value)}
                    placeholder="edited output"
                  />
                ) : null}
                <div>
                  <button type="button" disabled={!feedbackAction || feedbackSubmittingId === currentAnalysis.analysis_id} onClick={() => submitFeedback(currentAnalysis.analysis_id)}>
                    {feedbackSubmittingId === currentAnalysis.analysis_id ? 'Submitting...' : 'Submit Feedback'}
                  </button>
                </div>
              </div>
            </details>
          </div>
        </div>
      ) : null}

      {historyOpenId ? (
        <div className="ai-card" style={{ marginTop: '16px' }}>
          <h3>Analysis History</h3>
          {historyError ? <p className="page-error">{historyError}</p> : null}
          {analysisHistory.length === 0 && !historyLoading ? <p className="page-status">暂无历史记录</p> : null}
          {analysisHistory.map((item) => (
            <div key={item.analysis_id} style={{ borderTop: '1px solid #eee', paddingTop: '12px', marginTop: '12px' }}>
              <button type="button" onClick={() => openHistoryItem(item)} style={{ marginBottom: '8px' }}>
                Open This Analysis
              </button>
              <p><strong>ID:</strong> {item.analysis_id}</p>
              <p><strong>Provider:</strong> {item.provider === 'llm' ? 'LLM' : 'Rule-based Fallback'}</p>
              <p><strong>Model:</strong> {item.model_name ?? '-'}</p>
              <p><strong>Created:</strong> {item.created_at}</p>
              {renderGroundingEvidence(item)}
              <p><strong>Risk:</strong> {item.risk_level}</p>
              <p><strong>Summary:</strong> {item.issue_summary}</p>
              <p><strong>Root cause:</strong> {item.possible_root_cause}</p>
              <p><strong>Recommended Actions:</strong></p>
              {renderRecommendedActions(item.recommended_actions)}
              <p><strong>Project impact:</strong> {item.project_impact}</p>
              <p><strong>Customer Update Draft:</strong></p>
              {renderCustomerUpdateDraft(item.customer_update_draft)}
              <p><strong>Feedback:</strong> {item.feedback_status}</p>
              <p><strong>Note:</strong> {item.feedback_note ?? '-'}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
