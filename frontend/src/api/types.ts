export interface DashboardMetrics {
  active_customers: number;
  active_projects: number;
  open_issues: number;
  critical_issues: number;
  overdue_requirements: number;
  projects_at_risk: number;
}

export interface Customer {
  id: number;
  name: string;
  industry?: string | null;
  status: string;
  owner?: string | null;
  contact?: string | null;
}

export interface Project {
  id: number;
  customer_id?: number | null;
  name: string;
  status: string;
  risk_level?: string | null;
  delivery_stage?: string | null;
  health?: string | null;
}

export interface Requirement {
  id: number;
  project_id?: number | null;
  title: string;
  status: string;
  priority: string;
  owner?: string | null;
  due_date?: string | null;
}

export interface Issue {
  id: number;
  project_id?: number | null;
  title: string;
  description?: string | null;
  issue_type?: string | null;
  status: string;
  severity: string;
  owner?: string | null;
}

export interface RequirementCreatePayload {
  title: string;
  priority: string;
  status: string;
  owner?: string | null;
  due_date?: string | null;
  project_id: number;
}

export interface IssueCreatePayload {
  title: string;
  description?: string | null;
  issue_type?: string | null;
  severity: string;
  status: string;
  owner?: string | null;
  project_id: number;
}

export interface RequirementStatusUpdatePayload {
  status: string;
}

export interface IssueStatusUpdatePayload {
  status: string;
}

export interface ProjectCreatePayload {
  name: string;
  customer_id: number;
  status: string;
  delivery_stage?: string | null;
  risk_level?: string | null;
}

export interface ProjectUpdatePayload {
  status?: string | null;
  delivery_stage?: string | null;
  risk_level?: string | null;
}

export interface CustomerCreatePayload {
  name: string;
  industry: string;
  contact?: string | null;
  status: string;
  owner: string;
}

export interface CustomerStatusUpdatePayload {
  status: 'active' | 'inactive' | 'prospect';
}

export type RetrievalStatus =
  | 'not_attempted'
  | 'succeeded'
  | 'no_results'
  | 'failed';

export interface KnowledgeCitation {
  citation_id: string;
  rank: number;
  chunk_id: number;
  document_id: number;
  document_title: string;
  scope_type: 'global' | 'customer' | 'project';
  customer_id?: number | null;
  project_id?: number | null;
  doc_type: string;
  source_kind: string;
  source_name?: string | null;
  source_uri?: string | null;
  chunk_index: number;
  distance?: number | null;
  similarity_score: number;
}

export interface GroundedAnalysisFields {
  prompt_version?: string | null;
  retrieval_status: RetrievalStatus;
  retrieval_query?: string | null;
  knowledge_citations: KnowledgeCitation[];
  retrieval_error_code?: string | null;
  knowledge_grounded: boolean;
}

export interface IssueAnalysisResult extends GroundedAnalysisFields {
  analysis_id: number;
  issue_id: number;
  analysis_type: string;
  issue_summary: string;
  possible_root_cause: string;
  recommended_actions: string[];
  customer_update_draft: string;
  risk_level: string;
  project_impact: string;
  feedback_status: string;
  feedback_note?: string | null;
  edited_output?: string | null;
  created_at: string;
  updated_at?: string | null;
  provider: 'llm' | 'rule_based_fallback';
  model_name?: string | null;
}

export interface AIAnalysisHistoryItem extends IssueAnalysisResult {}

export interface AIFeedbackPayload {
  feedback_status: 'pending' | 'accepted' | 'rejected' | 'edited_and_accepted';
  feedback_note?: string | null;
  edited_output?: string | null;
}

export interface AIEvaluationMetricGroup {
  provider: string;
  model_name: string | null;
  total_analyses: number;
  pending_reviews: number;
  reviewed_analyses: number;
  accepted: number;
  rejected: number;
  edited_and_accepted: number;
  review_completion_rate: number | null;
  positive_outcome_rate: number | null;
  direct_acceptance_rate: number | null;
  edit_and_accept_rate: number | null;
  rejection_rate: number | null;
}

export interface AIEvaluationPromptVersionGroup {
  prompt_version: string | null;
  provider: string;
  model_name: string | null;
  total_analyses: number;
  pending_reviews: number;
  reviewed_analyses: number;
  accepted: number;
  rejected: number;
  edited_and_accepted: number;
  review_completion_rate: number | null;
  positive_outcome_rate: number | null;
  direct_acceptance_rate: number | null;
  edit_and_accept_rate: number | null;
  rejection_rate: number | null;
}

export interface AIEvaluationMetricsResponse {
  total_analyses: number;
  pending_reviews: number;
  reviewed_analyses: number;
  accepted: number;
  rejected: number;
  edited_and_accepted: number;
  review_completion_rate: number | null;
  positive_outcome_rate: number | null;
  direct_acceptance_rate: number | null;
  edit_and_accept_rate: number | null;
  rejection_rate: number | null;
  provider_breakdown: AIEvaluationMetricGroup[];
  prompt_version_breakdown: AIEvaluationPromptVersionGroup[];
}

export type AgentRunStatus =
  | 'created'
  | 'running'
  | 'waiting_for_triage_confirmation'
  | 'waiting_for_clarification'
  | 'generating_analysis'
  | 'waiting_for_final_review'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'limit_exceeded';

export interface AgentTriageResult {
  issue_type: 'API' | 'Data' | 'Deployment' | 'Configuration' | 'Integration';
  subtype: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  confidence: number;
  reason: string;
}

export interface AgentGeneratedAnalysis {
  analysis_type?: string;
  provider?: 'llm' | 'rule_based_fallback';
  model_name?: string | null;
  prompt_version?: string | null;
  issue_summary?: string;
  possible_root_cause?: string;
  recommended_actions?: string[];
  customer_update_draft?: string;
  risk_level?: string;
  project_impact?: string;
  retrieval_status?: RetrievalStatus;
  retrieval_query?: string | null;
  knowledge_citations?: KnowledgeCitation[];
  retrieval_error_code?: string | null;
}

export interface AgentRunState extends Record<string, unknown> {
  triage_suggestion?: AgentTriageResult;
  triage_result?: AgentTriageResult;
  triage_confirmed?: boolean;
  evidence_sufficient?: boolean;
  evidence_reason?: string;
  clarification_question?: string;
  clarification_response?: string | null;
  generated_analysis?: AgentGeneratedAnalysis;
}

export interface AgentToolCall {
  id: number;
  tool_call_index: number;
  tool_name: string;
  tool_version?: string | null;
  call_status: string;
  arguments: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  read_only: boolean;
  requires_approval: boolean;
  timeout_seconds: number;
  error_code?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AgentStep {
  id: number;
  step_index: number;
  node_name: string;
  step_status: string;
  input_state?: Record<string, unknown> | null;
  output_state?: Record<string, unknown> | null;
  error_code?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  tool_calls: AgentToolCall[];
}

export interface AgentRun {
  id: number;
  run_id: string;
  issue_id: number;
  analysis_log_id?: number | null;
  graph_version: string;
  current_node: string;
  run_status: AgentRunStatus;
  step_count: number;
  tool_call_count: number;
  retry_count: number;
  state: AgentRunState;
  waiting_since?: string | null;
  resume_node?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  steps: AgentStep[];
}

export interface AgentRunResumePayload {
  triage_result?: AgentTriageResult;
  clarification_response?: string;
}
