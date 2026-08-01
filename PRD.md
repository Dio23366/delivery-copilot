# Delivery Copilot — As-built Product Requirements and Scope

## 1. Document Status

This document describes the implemented portfolio state of Delivery Copilot.

It is an **as-built specification**, not a promise that every idea from the original product vision is implemented. Historical planning remains in:

- `docs/product/prd-v0.1-original-vision.md`
- `docs/product/prd-change-summary.md`

The current source of truth is the code, database migrations, accepted validators, and the public-facing architecture documents.

## 2. Product Summary

Delivery Copilot is an AI-assisted enterprise delivery and issue-management platform.

It combines:

- customer, project, requirement, and issue tracking;
- dashboard risk metrics;
- persisted Grounded RAG issue analysis;
- knowledge-document ingestion, chunking, embeddings, and scoped retrieval;
- structured AI output and immutable citation snapshots;
- human review and AI evaluation metrics;
- a persisted, bounded single-agent investigation workflow;
- a validated LangGraph orchestration foundation.

The product is designed for delivery, implementation, support, solutions, and forward-deployed engineering workflows where operational context, evidence, and human accountability matter more than free-form chat.

## 3. Product Goals

The implemented product aims to:

1. centralize the core delivery entities and their current state;
2. surface operational risk through deterministic metrics;
3. generate reviewable issue analysis grounded in managed knowledge;
4. preserve provider, prompt, retrieval, citation, and review evidence;
5. degrade safely when retrieval or model providers fail;
6. support a resumable and auditable Agent MVP with explicit human boundaries;
7. demonstrate an incremental LangGraph migration seam without overstating production adoption.

## 4. Target Users

Primary users:

- Delivery Manager
- Implementation Engineer
- Solutions Engineer
- Forward Deployed Engineer
- Technical Product Manager
- Support or escalation engineer

The portfolio runtime does not implement login, user accounts, or role-based access control. User roles are product context, not enforced authorization identities.

## 5. Implemented Product Surface

### 5.1 Operational records

The application implements list, create, and controlled status/update operations for:

- Customers
- Projects
- Requirements
- Issues

Implemented relationships:

```text
Customer
└── Project
    ├── Requirement
    └── Issue
        ├── AI Analysis History
        └── Agent Run
```

### 5.2 Dashboard

The dashboard returns and displays:

- active customers;
- active projects;
- open issues;
- critical issues;
- overdue requirements;
- projects at risk.

### 5.3 Knowledge base

The knowledge subsystem implements:

- global, customer, and project document scopes;
- document creation and listing;
- deterministic chunk creation;
- single-chunk embedding;
- document-level batch embedding;
- 1536-dimensional vector persistence;
- scoped Top-K similarity search;
- document readiness and archive states.

### 5.4 Grounded RAG analysis

For a persisted Issue, the application can:

1. load Issue, Project, and Customer context;
2. build a retrieval query;
3. resolve permitted knowledge scope;
4. generate a query embedding;
5. retrieve relevant chunks through pgvector;
6. treat retrieved text as untrusted evidence;
7. build a grounded prompt;
8. call the configured LLM provider;
9. validate a six-field structured result;
10. fall back to a rule-based provider when required;
11. persist analysis metadata and citation snapshots;
12. expose the result for human review.

The six-field output contract is:

- `issue_summary`
- `possible_root_cause`
- `recommended_actions`
- `customer_update_draft`
- `risk_level`
- `project_impact`

### 5.5 Human review

Each persisted analysis starts with `feedback_status = pending`.

A reviewer may finalize it as:

- `accepted`
- `rejected`
- `edited_and_accepted`

`edited_and_accepted` requires a nonblank `edited_output`.

The original AI-generated content remains separate from the human-edited output. A finalized analysis cannot be finalized a second time.

### 5.6 AI evaluation

The AI Evaluation view aggregates:

- total analyses;
- pending and reviewed counts;
- positive outcome rate;
- direct acceptance rate;
- edit-and-accept rate;
- rejection rate;
- provider/model breakdown;
- prompt-version breakdown.

These are workflow review metrics. They are not a formal model-accuracy benchmark.

## 6. Agent MVP

### 6.1 Implemented lifecycle

The persisted Agent MVP supports:

- run creation and active-run reuse for one Issue;
- Issue context loading;
- validated triage suggestions;
- triage confirmation wait;
- deterministic investigation routing;
- bounded read-only tool selection and execution;
- evidence evaluation;
- clarification wait and resume;
- analysis generation;
- atomic analysis persistence;
- final-review wait;
- finalization through the existing analysis feedback endpoint;
- cancellation;
- terminal limit handling;
- Run, Step, and Tool Call audit records.

### 6.2 Approved tools

The Agent tool registry includes:

- `load_issue_context`
- `search_knowledge`
- `get_analysis_history`
- `calculate_delivery_risk`

The first tool is deterministic context loading. The investigation loop may select among the remaining three according to confirmed triage, prior results, clarification, and configured limits.

The initial tools are read-only and do not own database commits.

### 6.3 Run statuses

Implemented Agent Run statuses:

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

Human rejection of an analysis still closes an auditable workflow as `completed`; it is not a technical failure.

### 6.4 Safety boundaries

The Agent MVP is bounded by persisted counters and service-owned transition rules.

Important boundaries include:

- finite steps, tool calls, retries, and timeouts;
- schema validation for triage and tool input/output;
- no arbitrary tool execution;
- no write tools in the initial registry;
- explicit waiting states for human input;
- transaction ownership in orchestration and persistence services;
- lock ordering through the persistence layer;
- no SQLAlchemy Session, ORM object, provider client, credential, or exception object in serialized Agent state.

## 7. LangGraph Foundation

The repository includes a validated LangGraph orchestration foundation:

- typed Agent state;
- compiled graph topology;
- node and routing adapters;
- read-only adapters;
- an `execute_tool` runtime adapter;
- a single-step Driver;
- checkpoint identity classification;
- `AgentGraphStepCoordinator`;
- constructor injection into `AgentRunnerService`.

This is an incremental migration seam.

The current production business path remains owned by `AgentRunnerService`. The Runner stores the injected Coordinator but does not invoke it.

The portfolio does **not** claim:

- full production Runner takeover by LangGraph;
- a persistent production Checkpointer deployment;
- automatic database/checkpoint reconciliation;
- distributed workers;
- multi-agent orchestration;
- autonomous enterprise write actions.

## 8. Implemented API Workflows

### 8.1 Operational workflow

```text
Create or review Customer
→ create Project
→ create Requirements and Issues
→ update operational statuses
→ inspect Dashboard metrics
```

### 8.2 Grounded analysis workflow

```text
Issue
→ POST persisted analysis
→ retrieval and provider execution
→ AIAnalysisLog + citation snapshot
→ analysis history
→ human feedback
→ evaluation metrics
```

### 8.3 Agent workflow

```text
POST Agent Run
→ run to triage wait
→ resume with triage confirmation
→ bounded investigation
→ optional clarification wait/resume
→ persist analysis
→ final-review wait
→ PATCH analysis feedback
→ completed Agent Run
```

## 9. Persistence Requirements

The PostgreSQL schema is managed through Alembic revisions `0001` through `0007`.

The current as-built database contains ten application tables:

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

PostgreSQL uses JSONB for structured Agent state and pgvector for 1536-dimensional embeddings. SQLite-compatible variants are used by isolated validators where appropriate; the accepted runtime database is PostgreSQL.

## 10. Frontend Requirements

The React frontend implements routes for:

- Dashboard
- Customers
- Projects
- Requirements
- Issues
- AI Copilot
- AI Evaluation

The Issues page is the main AI workflow surface. It supports:

- issue creation and status updates;
- persisted issue analysis;
- provider and model display;
- retrieval-status and grounded badges;
- citation metadata;
- structured analysis fields;
- history browsing;
- accept, reject, and edit-and-accept feedback.

The current frontend does not expose a dedicated Agent lifecycle UI or knowledge-administration UI.

## 11. Provider and Failure Behavior

LLM and embedding configuration are independent.

The analysis workflow records:

- provider;
- model name;
- prompt version;
- retrieval status;
- retrieval query;
- citation snapshot;
- retrieval error code.

Handled outcomes include:

- successful grounded retrieval;
- no retrieval results;
- retrieval failure;
- embedding configuration or provider failure;
- LLM timeout;
- malformed provider output;
- rule-based fallback;
- persistence rollback;
- duplicate human finalization.

Provider failure must not silently appear as a successful LLM result.

## 12. Auditability and Trust

Historical citation snapshots are stored with the analysis record and are not rewritten when knowledge documents are later archived or changed.

Retrieved text is untrusted reference data. It does not override system instructions or application contracts.

The public frontend intentionally avoids exposing raw provider secrets and does not display the internal retrieval query or full raw chunk text.

## 13. Accepted Evidence Boundary

The portfolio contains accepted evidence for:

- real PostgreSQL and API end-to-end execution;
- Grounded RAG analysis and citation persistence;
- human-review transitions;
- provider fallback and timeout behavior;
- Agent persistence and lifecycle APIs;
- bounded resume and investigation execution;
- guarded tool execution;
- clarification and final-review waits;
- analysis persistence;
- LangGraph foundation and Runner constructor injection.

These demonstrate implementation and engineering acceptance. They do not establish production SLA, business ROI, security certification, or formal model accuracy.

## 14. Explicitly Not Implemented

The current product does not include:

- authentication, authorization, or RBAC;
- user administration;
- comments or activity feeds;
- a report/export module;
- a project-detail route;
- a dedicated Agent frontend;
- a dedicated knowledge-management frontend;
- public cloud deployment;
- CI/CD;
- distributed task workers;
- production observability or alerting;
- formal benchmark datasets;
- multi-agent behavior.

Legacy mock AI endpoints remain for simple demonstrations, but they are not the persisted Grounded RAG workflow.

## 15. Release Position

Delivery Copilot is a local, evidence-driven portfolio implementation.

The honest public claim is:

> Delivery Copilot implements an enterprise delivery workflow with persisted Grounded RAG analysis, citation snapshots, human review, evaluation metrics, and a bounded single-agent investigation MVP, together with a validated LangGraph orchestration foundation that has not replaced the production Runner.
