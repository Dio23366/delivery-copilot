# Delivery Copilot Agent Demo UI — Frozen Scope

## 1. Goal

Expose the existing bounded single-agent Issue investigation workflow as an
operator-facing demo. The UI must make the Agent's state, controlled decisions,
tool use, evidence boundary, human interrupts, and final review visible without
changing the accepted backend orchestration behavior.

## 2. In Scope

- select an existing Issue and start or reuse its active Agent Run;
- show Run identity, status, current node, counters, waiting state, and errors;
- show the persisted Step timeline and nested Tool Calls;
- redact retrieval query text, knowledge chunk text, source URI, and secret-like
  fields from all state and Tool result snapshots rendered in the browser;
- show and allow confirmation or correction of the triage suggestion;
- show the clarification question and submit one human clarification response;
- resume the bounded investigation after triage confirmation or clarification;
- show evidence sufficiency and the generated Analysis summary from Agent state;
- link the final-review state to the existing Analysis Human Review flow;
- refresh Run state manually and cancel a cancellable Run;
- preserve the backend as the source of truth for every transition.

## 3. Non-goals

- no multi-agent collaboration;
- no autonomous write tools or customer-facing actions;
- no arbitrary tool registration or free-form tool execution;
- no change to the deterministic triage or tool-selection policy;
- no LangGraph takeover of `AgentRunnerService`;
- no persistent production Checkpointer or DB/Checkpoint reconciliation;
- no authentication, RBAC, distributed workers, or production SLA claim;
- no replacement of the existing Grounded RAG Analysis page.

## 4. Frozen Interaction Contract

The frontend uses only the existing endpoints:

- `POST /api/agent/runs`
- `GET /api/agent/runs/{run_id}`
- `POST /api/agent/runs/{run_id}/resume`
- `POST /api/agent/runs/{run_id}/cancel`
- `GET /api/ai/issues/{issue_id}/analyses`
- `PATCH /api/ai/analyses/{analysis_id}/feedback`

The UI must not infer or persist Agent state locally. It submits human input and
renders the Run returned by the backend.

## 5. Acceptance Scenarios

### A. Triage confirmation

1. User selects an Issue and starts a Run.
2. The backend reaches `waiting_for_triage_confirmation`.
3. UI renders the structured triage suggestion.
4. User confirms or corrects it and resumes.
5. UI renders the returned Run and the appended persisted Steps.

### B. Human clarification

1. Knowledge below the conservative demo similarity guardrail (`0.65`) is not
   counted as usable grounded evidence.
2. Below-threshold chunks remain in the Tool audit record but are excluded from
   the generation Prompt and Citation Snapshot; generation reports
   `retrieval_status=no_results` when no usable chunk remains.
3. The Run reaches `waiting_for_clarification` when approved Tool evidence is
   exhausted and remains insufficient.
4. Clarification reads the Run's persisted `issue_context` and produces a
   focused question for the detected problem signal (including API timeout).
5. UI renders `clarification_question` and `evidence_reason`.
6. User submits a nonblank clarification response.
7. The backend resumes from the persisted boundary without duplicating the Run.
8. The frozen default `max_steps=20` covers one Clarification round after the
   full three-call Tool budget while keeping both limits finite.

### C. Final review and audit

1. The Run reaches `waiting_for_final_review` with an `analysis_log_id`.
2. UI renders the generated Analysis and loads the persisted Analysis record.
3. User accepts, rejects, or edits and accepts through the existing feedback API.
4. The linked Agent Run becomes terminal according to the existing backend rule.
5. The full Run / Step / ToolCall timeline remains visible.
6. When a different Analysis is loaded, the review form resets to `Accept`
   with blank review note and edited output; decisions from a prior Run are not
   carried forward.

### D. Controlled termination

1. User can cancel a waiting or cancellable active Run.
2. An active Run whose latest Step has already failed can be recovery-cancelled;
   the failed Step and its error payload remain unchanged for audit, while the
   outer Run becomes terminal.
3. Failed, cancelled, completed, and limit-exceeded Runs render as terminal.
4. Backend error codes and messages are visible without exposing credentials or
   internal provider objects.

## 6. Honest Portfolio Claim After Acceptance

> Delivery Copilot implements an operator-visible, bounded single-agent Issue
> investigation workflow with persisted Run/Step/ToolCall audit records,
> guarded read-only tools, Human Clarification, resumable execution, grounded
> Analysis generation, and final Human Review.

This acceptance does not establish a production-grade autonomous Agent platform,
multi-agent orchestration, or full LangGraph Runner takeover.
