import type {
  AIEvaluationMetricsResponse,
  AIFeedbackPayload,
  AIAnalysisHistoryItem,
  Customer,
  CustomerCreatePayload,
  CustomerStatusUpdatePayload,
  DashboardMetrics,
  Issue,
  IssueAnalysisResult,
  IssueCreatePayload,
  IssueStatusUpdatePayload,
  Project,
  ProjectCreatePayload,
  ProjectUpdatePayload,
  Requirement,
  RequirementCreatePayload,
  RequirementStatusUpdatePayload,
} from './types';

const API_BASE = '/api';

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    let message = `请求失败 (${response.status} ${response.statusText})`;
    try {
      const payload = (await response.json()) as { detail?: unknown; message?: unknown };
      const detail = payload.detail ?? payload.message;
      if (typeof detail === 'string') {
        message = detail;
      } else if (Array.isArray(detail)) {
        message = detail
          .map((item) =>
            typeof item === 'string' ? item : typeof item?.msg === 'string' ? item.msg : JSON.stringify(item),
          )
          .join(', ');
      }
    } catch {
      // ignore parse error and keep default message
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export const api = {
  getDashboardMetrics: () => fetchJson<DashboardMetrics>('/dashboard/metrics'),
  getCustomers: () => fetchJson<Customer[]>('/customers'),
  getProjects: () => fetchJson<Project[]>('/projects'),
  getRequirements: () => fetchJson<Requirement[]>('/requirements'),
  getIssues: () => fetchJson<Issue[]>('/issues'),
  createCustomer: (payload: CustomerCreatePayload) =>
    fetchJson<Customer>('/customers', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateCustomerStatus: (customerId: number, payload: CustomerStatusUpdatePayload) =>
    fetchJson<Customer>(`/customers/${customerId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  createRequirement: (payload: RequirementCreatePayload) =>
    fetchJson<Requirement>('/requirements', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  createIssue: (payload: IssueCreatePayload) =>
    fetchJson<Issue>('/issues', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateRequirementStatus: (requirementId: number, status: RequirementStatusUpdatePayload['status']) =>
    fetchJson<Requirement>(`/requirements/${requirementId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  updateIssueStatus: (issueId: number, status: IssueStatusUpdatePayload['status']) =>
    fetchJson<Issue>(`/issues/${issueId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  createProject: (payload: ProjectCreatePayload) =>
    fetchJson<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateProject: (projectId: number, payload: ProjectUpdatePayload) =>
    fetchJson<Project>(`/projects/${projectId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  summarizeIssue: (issueId: number) => fetchJson<IssueAnalysisResult>(`/ai/issues/${issueId}/summarize`, { method: 'POST' }),
  getIssueAnalysisHistory: (issueId: number) =>
    fetchJson<AIAnalysisHistoryItem[]>(`/ai/issues/${issueId}/analyses`),
  submitAnalysisFeedback: (analysisId: number, payload: AIFeedbackPayload) =>
    fetchJson<AIAnalysisHistoryItem>(`/ai/analyses/${analysisId}/feedback`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  getAIEvaluationMetrics: () => fetchJson<AIEvaluationMetricsResponse>('/ai/evaluation/metrics'),
};
