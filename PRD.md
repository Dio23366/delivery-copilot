# Delivery Copilot — As-built Product Requirements and Scope

## 1. Document Status

This is the current **as-built specification** for the public Delivery Copilot repository. It describes implemented behavior, accepted evidence, and explicit limits. It is not a future-state wishlist and does not imply production deployment.

The product currently contains:

- an enterprise delivery workflow;
- persisted Grounded RAG issue analysis;
- Human review and analysis history;
- a persisted, bounded single-agent investigation workflow;
- an operator-facing Agent Investigation UI;
- a validated LangGraph orchestration foundation that has not replaced the current Runner.

This documentation refresh clarifies the runtime authority boundary. It does not add runtime functionality.

## 2. Product Summary

Delivery Copilot helps enterprise delivery teams organize Customer, Project, Requirement, Issue, and knowledge context, then use AI to investigate delivery issues with evidence and human control.

The implemented AI product has two complementary execution paths:

1. **Persisted Grounded RAG analysis** for evidence-backed structured issue analysis.
2. **Bounded Agent investigation** for multi-step triage, controlled Tool use, evidence evaluation, optional clarification, resume, analysis generation, and final Human Review.

The product is designed around a simple principle: AI output is not treated as useful merely because a model generated it. Evidence, state, failure behavior, and Human review are part of the product contract.

## 3. Product Goals

The implemented product goals are to:

- centralize delivery context across Customer, Project, Requirement, and Issue records;
- reduce manual synthesis for issue investigation and customer communication;
- produce structured, reviewable AI analysis rather than free-form opaque text;
- ground factual analysis in retrievable Knowledge where evidence exists;
- preserve a Citation Snapshot so historical evidence is auditable;
- allow a bounded Agent to investigate with approved read-only tools;
- persist Agent execution so operators can inspect Run / Step / Tool Call history;
- interrupt for human input when evidence or business confirmation is required;
- fail or degrade safely when external AI dependencies are unavailable.

## 4. Target Users

Primary portfolio user types are:

- enterprise delivery / implementation engineers;
- project and delivery managers;
- technical account / solutions roles;
- operators who investigate blockers and prepare customer updates;
- AI Product / Technical Product stakeholders evaluating evidence-backed workflows.

This repository does not implement user accounts, tenancy, or role-based permission management.

## 5. Implemented Product Surface

### 5.1 Operational records

Implemented business entities include:

- Customer
- Project
- Requirement
- Issue
- Knowledge documents and chunks

The frontend supports basic create/list/update workflows for the operational entities that are present in the public implementation.

### 5.2 Dashboard

The Dashboard exposes operational metrics including active Customers, active Projects, open Issues, critical Issues, overdue Requirements, and Projects at risk.

The current Dashboard is intentionally compact and does not claim mature BI, forecasting, or executive reporting.

### 5.3 Knowledge base

The backend supports:

- manual Knowledge document ingestion;
- chunk persistence;
- single and batch embedding;
- safe retry / failed-chunk isolation;
- `text-embedding-v4`;
- 1536-dimensional embeddings;
- PostgreSQL + pgvector storage;
- global / Customer / Project retrieval scope;
- ready/archive lifecycle behavior.

A dedicated knowledge-administration frontend is not implemented.

### 5.4 Grounded RAG analysis

For an Issue, the persisted Grounded RAG workflow can:

1. load Issue / Project / Customer context;
2. build a deterministic retrieval query;
3. resolve permitted knowledge scope;
4. embed the query;
5. retrieve Top-K candidates through pgvector cosine similarity;
6. treat retrieved Knowledge as untrusted evidence;
7. build the `issue_summarizer_v4_grounded` prompt;
8. call the configured LLM provider;
9. validate a strict structured result;
10. use rule-based fallback when provider execution cannot be trusted;
11. persist provider, model, Prompt Version, retrieval status, and Citation Snapshot;
12. expose the Analysis for Human review.

The six-field structured contract is:

- `issue_summary`
- `possible_root_cause`
- `recommended_actions`
- `customer_update_draft`
- `risk_level`
- `project_impact`

### 5.5 Human review

Each persisted Analysis begins with `feedback_status = pending`.

A reviewer may finalize it as:

- `accepted`
- `rejected`
- `edited_and_accepted`

`edited_and_accepted` requires nonblank edited output. Original AI content remains separate from human-edited content, and a finalized Analysis cannot be finalized a second time.

### 5.6 AI evaluation

The AI Evaluation view aggregates workflow-review outcomes such as total Analyses, pending/reviewed counts, positive outcome rate, direct acceptance rate, edit-and-accept rate, rejection rate, provider/model breakdown, and Prompt Version breakdown.

These metrics describe Human review outcomes. They are not a formal model-accuracy benchmark.

## 6. Agent MVP

### 6.1 Implemented lifecycle

The current Agent runtime supports:

- active-Run reuse for one Issue;
- deterministic Issue context loading;
- validated triage suggestion;
- Triage Human Gate;
- bounded investigation routing;
- approved read-only Tool selection and execution;
- Tool result persistence and replay-aware reuse;
- explicit evidence evaluation;
- optional Human Clarification;
- same-Run resume from persisted waiting state;
- structured Analysis generation;
- AIAnalysisLog persistence;
- final-review waiting;
- Human Review closure;
- cancellation and recovery cancellation;
- terminal `failed`, `cancelled`, and `limit_exceeded` outcomes;
- persisted Run, Step, and Tool Call audit records.

### 6.2 Approved tools

The current dynamic Agent Tool Registry contains exactly three approved read-only Tools:

- `search_knowledge`
- `get_analysis_history`
- `calculate_delivery_risk`

The historical design used the capability name `load_issue_context` as a starting Tool concept. In the current implementation, context loading is deterministic and handled before dynamic Tool selection by the Runner/service path; it is not registered as a fourth dynamic Tool.

All current dynamic Tools are read-only and do not own arbitrary database commits.

### 6.3 Run statuses

Implemented Agent Run statuses include:

- `created`
- `running`
- `waiting_for_triage_confirmation`
- `waiting_for_clarification`
- `generating_analysis`
- `waiting_for_final_review`
- `completed`
- `failed`
- `cancelled`
- `limit_exceeded`

Human rejection still closes an auditable business workflow as `completed`; it is not a technical failure.

### 6.4 Safety boundaries

The Agent runtime is bounded by persisted counters, allowlisted Tools, state validation, and service-owned transitions.

Implemented boundaries include:

- finite `max_steps` and `max_tool_calls`;
- bounded transitions per Runner call;
- Tool timeouts;
- schema validation for triage and Tool contracts;
- no arbitrary Tool execution;
- no write Tools in the current registry;
- explicit waiting states for human input;
- loop-stall detection;
- state/node consistency checks;
- replay-aware Tool-call identity handling;
- transaction ownership in orchestration/persistence services;
- row locking for critical state transitions;
- no Session, ORM object, provider client, credential, raw HTTP response, or exception object in serialized Agent state.

## 7. LangGraph Foundation

The repository contains a validated LangGraph orchestration foundation:

- typed Agent state;
- compiled graph topology;
- graph nodes and conditional routing;
- read-only adapters;
- `execute_tool` adapter;
- single-step Driver;
- checkpoint identity classification;
- `AgentGraphStepCoordinator`;
- constructor injection into `AgentRunnerService`.

The current production business path remains owned by `AgentRunnerService`. **The Runner stores the injected Coordinator but does not invoke it.**

Therefore this repository does not claim:

- full production Runner takeover by LangGraph;
- persistent production Checkpointer deployment;
- automatic database/checkpoint reconciliation;
- distributed LangGraph workers;
- multi-agent orchestration.

The migration strategy is incremental: validate the seam first, then consider takeover only when the runtime and recovery model justify it.

## 8. Implemented API Workflows

### 8.1 Operational workflow

```text
Create / review Customer
→ create Project
→ create Requirements and Issues
→ update operational status
→ inspect Dashboard metrics
```

### 8.2 Grounded analysis workflow

```text
Issue
→ POST persisted analysis
→ retrieval + provider execution
→ AIAnalysisLog + Citation Snapshot
→ history
→ Human review
→ evaluation metrics
```

### 8.3 Agent workflow

```text
POST Agent Run
→ deterministic context load
→ triage wait
→ resume with triage confirmation
→ bounded investigation
→ optional clarification wait/resume
→ persist Analysis
→ final-review wait
→ PATCH Analysis feedback
→ completed Agent Run
```

The public Agent API includes create, read, resume, and cancel endpoints. Invalid state transitions are rejected rather than silently restarting the workflow.

## 9. Persistence Requirements

The accepted runtime uses PostgreSQL and Alembic migrations through `0007_agent_run_terminal`.

Application persistence includes:

- `customers`
- `projects`
- `requirements`
- `issues`
- `ai_analysis_logs`
- `knowledge_documents`
- `knowledge_chunks`
- `agent_runs`
- `agent_steps`
- `agent_tool_calls`

PostgreSQL JSONB stores controlled Agent state. pgvector stores 1536-dimensional embeddings.

Critical Agent persistence operations use row locks to coordinate current Run / Step / Tool Call / linked Analysis transitions. Agent creation locks the Issue row before active-Run reuse is decided.

Historical Citation Snapshots are immutable even when a Knowledge document is later archived.

## 10. Frontend Requirements

The React frontend implements:

- Dashboard
- Customers
- Projects
- Requirements
- Issues
- AI Copilot
- AI Evaluation
- Agent Investigation

The Issues page supports persisted Grounded RAG analysis, provider/model metadata, retrieval status, Grounded badge, citations, structured fields, history, and Human review.

The `/agent-runs` page supports:

- selecting an Issue and starting/reusing its active Agent Run;
- Run status, current node, counters, waiting state, errors, refresh, and cancellation;
- Triage confirmation / correction;
- Human Clarification;
- same-Run resume;
- generated Analysis and final Human Review;
- persisted Step timeline and nested Tool Calls;
- controlled Agent state display.

The frontend recursively hides retrieval queries, full chunk text, source URIs, credentials, provider endpoints, and secret-like values from Agent state / Tool snapshots rendered in the browser.

The frontend does not own Agent transitions; the backend is authoritative.

## 11. Provider and Failure Behavior

LLM and embedding configuration are independent.

The LLM provider supports an OpenAI-compatible endpoint and records provider/model behavior. Controlled fallback conditions include:

- missing API key;
- LLM timeout;
- HTTP error;
- request / connection error;
- invalid JSON;
- schema validation error;
- malformed response structure;
- unexpected provider exception.

When these occur, the system can use rule-based fallback rather than silently treating the failed provider call as a successful LLM result.

The system also distinguishes:

- no retrieval results;
- retrieval failure;
- embedding configuration/provider failure;
- Tool timeout/failure;
- invalid Agent state transition;
- duplicate finalization;
- persistence rollback.

The API includes controlled 404, 409, 422, and 500 outcomes for relevant request/state/persistence cases.

## 12. Auditability and Trust

The product persists generated output and Grounded Evidence separately.

A Citation Snapshot is tied to the historical Analysis record and is not rewritten when Knowledge lifecycle state changes.

Retrieved Knowledge Evidence is untrusted reference data and cannot override system/application contracts.

The Agent audit model preserves:

- Run identity and status;
- ordered Steps;
- nested Tool Calls;
- Tool arguments/results after controlled persistence;
- error codes/messages;
- Human waiting state;
- generated Analysis linkage;
- terminal outcome.

This enables failure analysis at the execution-step level rather than treating every bad result as a generic “prompt problem.”

## 13. Accepted Evidence Boundary

The portfolio contains accepted evidence for:

- real PostgreSQL and API end-to-end execution;
- Grounded RAG analysis and Citation Snapshot persistence;
- `text-embedding-v4` with 1536-dimensional embeddings;
- Human review transitions;
- provider fallback and timeout behavior;
- Agent persistence and lifecycle APIs;
- bounded investigation and resume;
- guarded read-only Tool execution;
- replay-aware Tool-call behavior;
- Human Clarification and Final Review waits;
- operator-facing Agent Investigation UI;
- persisted Step / Tool Call timeline;
- recursive browser redaction;
- conservative Agent evidence routing at the accepted demo boundary;
- normal and recovery cancellation;
- LangGraph state/topology/adapters/Driver/Coordinator validation;
- Runner constructor injection boundary.

The accepted Grounded RAG E2E evidence model is `gpt-5.5`; the configurable example default is `gpt-4.1-mini`.

**They do not establish production SLA, business ROI, security certification, or formal model accuracy.**

## 14. Explicitly Not Implemented

The current product does not include:

- Authentication, authorization, or RBAC;
- user administration or multi-tenant organization isolation;
- public cloud deployment;
- CI/CD;
- distributed task workers;
- production-scale load testing;
- production observability / alerting platform;
- formal benchmark datasets and calibrated model accuracy;
- a dedicated Knowledge-management frontend;
- arbitrary Tool registration;
- autonomous enterprise write actions;
- multi-agent behavior;
- Agent long-term memory;
- full production Runner takeover by LangGraph;
- persistent production Checkpointer deployment;
- automatic database/checkpoint reconciliation.

## 15. Release Position

Delivery Copilot is a local, evidence-driven engineering portfolio system.

The accurate public claim is:

> Delivery Copilot implements an enterprise delivery workflow with persisted Grounded RAG analysis, Citation Snapshots, Human review, and a bounded stateful single-agent investigation runtime with auditable Run / Step / Tool Call state. It also includes a validated LangGraph orchestration foundation and migration seam, but LangGraph has not replaced the current `AgentRunnerService` execution path.

The system is materially beyond a clickable UI prototype because it exercises real persistence, retrieval, external-provider failure behavior, state transitions, concurrency protection, interruption/resume, Tool audit, and Docker runtime dependencies. It is still a portfolio implementation rather than a production enterprise SaaS deployment.
