# Delivery Copilot - Agent MVP Scope

## 1. Document Status

- Status: Current As-built Scope with Historical Design Notes
- Public source of truth: checked-out source, migrations, evidence documents, and validators
- Runtime LangGraph dependency: `langgraph==1.2.10`
- Current runtime authority: `AgentRunnerService` + orchestration/persistence services
- LangGraph status: validated migration foundation; no production Runner takeover

This document replaces the previous “historical scope freeze with overlay” presentation with a clearer current-state-first view. Historical design terms are retained only where they explain how the implementation evolved.

The current repository implements a persisted, bounded single-agent Issue investigation workflow with Human Gates, three approved dynamic read-only Tools, evidence evaluation, clarification, resume, structured Analysis generation, final Human Review, and a complete Run / Step / ToolCall audit trail.

The repository also includes a validated LangGraph foundation with typed state, graph topology, adapters, single-step Driver, checkpoint identity classification, `AgentGraphStepCoordinator`, and constructor injection into `AgentRunnerService`. The current Runner stores the Coordinator but does not invoke it.

## 2. MVP Objective

The Agent MVP extends the accepted fixed Grounded RAG issue-analysis flow into a controlled, stateful, auditable investigation workflow.

The MVP demonstrates that the system can:

1. load the selected Issue context deterministically;
2. generate a validated triage suggestion;
3. pause for Human Triage Confirmation;
4. select among approved read-only investigation Tools;
5. persist each Tool call and result;
6. evaluate whether the collected evidence is sufficient;
7. request Human Clarification when required information is missing;
8. resume the same persisted Run;
9. generate the existing six-field structured Analysis;
10. persist the Analysis and wait for final Human Review;
11. preserve an auditable execution timeline through completion, cancellation, failure, or limit exhaustion.

The MVP is not a general-purpose autonomous Agent platform.

## 3. Primary Accepted Scenario

The accepted runtime scenario is an enterprise API-authentication / API-timeout investigation flow exercised locally against the real Docker Compose backend.

The accepted clarification-path evidence includes:

- Triage Human Gate and same-Run resume;
- 3 approved read-only Tool calls;
- a knowledge chunk scored at approximately `0.6089` rejected by the Agent `0.65` guardrail;
- a focused Human Clarification question;
- final generation with `Retrieval: no_results` when no usable chunk remained;
- 20 Steps to Final Review;
- Step 21 for final completion;
- 0 retries;
- normal cancellation and failed-Step recovery cancellation;
- browser redaction of sensitive Agent state and Tool snapshots.

The detailed evidence is in `docs/agent/agent-demo-acceptance.md`.

## 4. Current Runtime Workflow

```text
POST Agent Run
→ lock Issue / reuse active Run if present
→ create persisted AgentRun
→ load Issue context
→ triage
→ waiting_for_triage_confirmation
→ human confirm/correct
→ route investigation
→ select approved Tool
→ execute Tool
→ persist AgentToolCall
→ evaluate evidence
   ├─ another useful Tool → select Tool again
   ├─ insufficient + human information needed → waiting_for_clarification
   └─ ready for analysis → generate Analysis
→ persist AIAnalysisLog
→ waiting_for_final_review
→ Human Review
→ completed
```

The backend owns the state machine. The frontend only submits human input and renders persisted state.

## 5. In-Scope Capabilities

### 5.1 Deterministic context loading

Issue context is a mandatory precondition. The Runner uses `AgentIssueContextService` to load the business context before dynamic investigation.

Historical design documents used the name `load_issue_context` as a Tool concept. In the current implementation it is **not** part of the dynamic approved Tool Registry.

### 5.2 AI triage

The triage contract contains:

- `issue_type`
- `subtype`
- `severity`
- `confidence`
- `reason`

The triage output is validated and treated as a suggestion. It does not silently overwrite user-entered Issue fields.

### 5.3 Dynamic read-only Tool layer

The current approved dynamic Tool Registry contains exactly three Tools:

1. `search_knowledge`
2. `get_analysis_history`
3. `calculate_delivery_risk`

All three are:

```text
read_only = true
requires_approval = false
```

Their configured timeout boundaries are stored in the Tool definitions. The Agent may select different Tools based on triage, prior Tool results, clarification state, and remaining execution budget.

### 5.4 Guarded Tool execution

Tool execution is mediated by registry, contract, policy, dispatch, executor, result-state, and replay-aware services rather than arbitrary model-controlled function calls.

The runtime must reject:

- unregistered Tool names;
- invalid Tool arguments;
- incompatible Run/Step state;
- duplicate or conflicting persisted Tool-call identity;
- execution beyond the Tool-call budget;
- unsupported write behavior.

### 5.5 Evidence sufficiency

Evidence evaluation is an explicit routing stage.

The accepted demo baseline uses:

```text
similarity threshold = 0.65
```

Below-threshold knowledge remains auditable but is excluded from generation and Citation Snapshots.

Similarity is a retrieval relevance signal, not a probability that the final Analysis is correct.

### 5.6 Human Clarification

When approved Tool evidence is exhausted or insufficient, the Agent can persist a focused clarification question and enter `waiting_for_clarification`.

A nonblank human response resumes the same Run instead of creating a new investigation.

### 5.7 Structured Analysis

The Agent reuses the existing six-field contract:

- `issue_summary`
- `possible_root_cause`
- `recommended_actions`
- `customer_update_draft`
- `risk_level`
- `project_impact`

The Agent does not introduce an incompatible second Analysis format.

### 5.8 Final Human Review

The generated Analysis is persisted to `AIAnalysisLog` and linked to the Agent Run. Final Review reuses the existing Analysis feedback workflow:

- `accepted`
- `rejected`
- `edited_and_accepted`

A rejected Analysis still represents a completed, auditable business workflow.

### 5.9 Auditability and recovery

The runtime persists enough state to reconstruct the execution path:

- Run status and current node;
- ordered Steps;
- nested Tool Calls;
- arguments/results;
- counters and limits;
- controlled errors;
- waiting state;
- clarification state;
- linked Analysis;
- final outcome.

This makes the Agent suitable for step-level badcase analysis rather than only final-answer inspection.

## 6. Persistence Objects

The implemented Agent persistence layer uses:

- `agent_runs`
- `agent_steps`
- `agent_tool_calls`

These remain separate from `AIAnalysisLog`.

Critical state transitions use row locks so the workflow can enforce current-state assumptions before mutation. Tool-call replay logic validates persisted identity and counters before reuse or new reservation.

The public schema is documented in `DATABASE_SCHEMA.md`.

## 7. Concurrency and Idempotency Boundary

The API locks the selected Issue before deciding whether an active Run already exists. If a current active Run exists, the create endpoint returns that Run instead of intentionally creating a duplicate active workflow.

Resume uses persisted waiting state and validates that exactly one supported human input type is supplied.

Replay-aware Tool execution can reuse a prior successful persisted Tool result when its identity is valid, rather than blindly re-executing the same Tool call.

The runtime must not silently restart a Run from the beginning when a persisted waiting state exists.

## 8. Bounded Execution

The current Runner enforces finite execution through:

- `max_steps`;
- `max_tool_calls`;
- bounded transitions per call;
- Tool timeout;
- explicit waiting states;
- terminal states;
- state/node consistency checks;
- loop-stall detection.

The accepted clarification scenario uses a frozen default `max_steps=20` for the bounded investigation and `max_tool_calls=3`; final Human Review adds the terminal Step 21 outside that bounded investigation loop.

Limit exhaustion becomes an explicit `limit_exceeded` outcome rather than an infinite loop.

## 9. Failure and Cancellation Boundary

The Agent workflow distinguishes:

- missing resources;
- invalid state transition;
- Tool failure/timeout;
- bounded-loop conflict;
- cancellation;
- recovery cancellation after a failed Step;
- limit exhaustion;
- persistence failure.

Cancellation must preserve already-persisted audit evidence.

A failed Step must not leave an invalid active ToolCall behind when recovery cancellation is attempted.

## 10. Architecture Boundary

The current runtime architecture is:

```text
FastAPI Agent API
→ AgentRunnerService
→ AgentOrchestrationService / AgentPersistenceService
→ focused Agent services
→ approved Tool adapters
→ existing Delivery Copilot business / RAG services
→ PostgreSQL
```

The current production Runner remains responsible for the business state machine.

The LangGraph foundation is connected only through a validated constructor-injection seam:

```text
AgentRunnerService
  -. injected but not invoked .-> AgentGraphStepCoordinator
      → AgentGraphSingleStepDriver
      → compiled LangGraph
```

This is an incremental migration boundary, not a claim that LangGraph already owns production execution.

## 11. LangGraph Foundation Scope

Implemented and validated:

- typed Agent state;
- frozen node names;
- graph topology;
- conditional routing;
- read-only adapters;
- `execute_tool` adapter;
- single-step Driver;
- strict checkpoint config;
- checkpoint identity classification;
- `AgentGraphStepCoordinator`;
- Runner constructor injection.

Not implemented as production runtime:

- full Runner takeover;
- persistent production Checkpointer;
- automated DB/Checkpoint reconciliation;
- distributed graph workers;
- autonomous multi-agent execution.

## 12. Human and UI Safety Boundary

The Agent Investigation UI is operator-facing and backend-driven.

The browser must not expose controlled sensitive fields such as:

- retrieval query;
- full chunk text;
- source URI;
- credentials;
- provider endpoints;
- secret-like state values.

The UI does not own Agent transitions locally.

## 13. Explicit Non-goals

The Agent MVP does not include:

- automatic Issue mutation;
- automatic customer-message sending;
- write-capable Agent Tools;
- arbitrary Tool registration;
- multi-agent collaboration;
- Agent long-term memory;
- Slack / Jira / CRM integration;
- authentication or RBAC;
- multi-tenant organization isolation;
- public cloud production deployment;
- Kubernetes / Redis / Kafka architecture;
- production observability platform;
- production SLA or production-scale concurrency claim.

## 14. Completion and Portfolio Claim Boundary

The accepted implementation supports a truthful claim of:

> A persisted, bounded single-agent Issue investigation workflow with deterministic context loading, validated triage, Human Gates, three approved read-only investigation Tools, evidence evaluation, clarification/resume, structured Analysis generation, Human Review, cancellation, and Run / Step / ToolCall auditability.

It also supports a separate claim of:

> A validated LangGraph orchestration foundation and migration seam with typed state, graph topology, adapters, a single-step Driver, checkpoint identity handling, and a Coordinator injected into the current Runner.

It does **not** support claims of full LangGraph production orchestration, production autonomous Agent infrastructure, production Checkpoint/DB recovery, production RBAC, or production SLA.
