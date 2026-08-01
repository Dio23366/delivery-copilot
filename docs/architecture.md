# Delivery Copilot — As-built Architecture

## 1. Purpose and Scope
This document describes the system that has already been implemented, run, and accepted in the current repository state.
Delivery Copilot is an AI-powered enterprise delivery and issue management platform.
It is not a generic chatbot.
It is not a simple CRUD demo.
The architecture focuses on grounded issue analysis, a persisted single-agent workflow, evidence and execution auditability, human review, and an incrementally validated LangGraph orchestration foundation.

## 2. Product Workflow
The implemented business workflow is:

Customer
→ Project
→ Requirement / Issue
→ AI-assisted Issue Analysis
→ Grounded Evidence
→ Human Review
→ Analysis History

Customer, Project, Requirement, and Issue provide the operational context for delivery work.
Issue is the entry point for Grounded RAG analysis.
Human Review is the final business closure step.

### Agent MVP and validated LangGraph foundation

The accepted Agent MVP adds persisted `AgentRun`, `AgentStep`, and `AgentToolCall` records; deterministic triage and tool selection; guarded read-only tool execution; bounded continuation; Human Clarification; analysis persistence; final-review waiting; and resume behavior.

```mermaid
flowchart LR
  API[FastAPI Agent API] --> R[AgentRunnerService]
  R --> S[Existing business and persistence services]
  R -. constructor injection only .-> C[AgentGraphStepCoordinator]
  C --> D[AgentGraphSingleStepDriver]
  D --> G[Compiled LangGraph]
  G --> N[Nodes, routing, and adapters]
  S --> PG[(PostgreSQL AgentRun / Step / ToolCall)]
```

The solid Runner-to-service path remains the current production business path. The dashed Runner-to-Coordinator edge is a validated migration seam: the Coordinator is injectable, but the production Runner does not yet call it.

The LangGraph foundation includes typed state, compiled topology, read-only adapters, an `execute_tool` adapter, a single-step Driver, checkpoint identity classification, and matched-checkpoint-only coordination. Persistent production checkpoint storage, bootstrap/reconciliation behavior, and full production takeover are documented roadmap items rather than completed claims.

## 3. System Context Diagram

```mermaid
flowchart LR
  FE[React + TypeScript Frontend] --> API[FastAPI API Layer]
  API --> CS[Customer Service]
  API --> PS[Project Service]
  API --> RS[Requirement Service]
  API --> IS[Issue Service]
  API --> GAS[Grounded Analysis Service]
  API --> HS[Analysis History]
  API --> HF[Human Feedback]

  GAS --> KI[Knowledge Ingestion]
  KI --> EP[Embedding Provider]
  GAS --> PG[(PostgreSQL)]
  KI --> PG
  CS --> PG
  PS --> PG
  RS --> PG
  IS --> PG
  HS --> PG
  HF --> PG
  GAS --> PGV[(pgvector)]
  GAS --> LLM[LLM Provider]
  LLM -. failure .-> RBF[Rule-based Fallback]
  HF --> API
```

Frontend only accesses the backend through REST API calls.
Embedding Provider and LLM Provider are configured independently.
PostgreSQL stores business data, knowledge data, analysis logs, and citation snapshots.
pgvector handles similarity retrieval.
LLM failure degrades to rule-based fallback.
Human feedback is written back to the Analysis Log.

## 4. Grounded RAG Request Sequence

```mermaid
sequenceDiagram
  participant U as User
  participant FE as Frontend
  participant API as FastAPI API
  participant S as Grounded Analysis Service
  participant Q as Retrieval Query Builder
  participant E as Embedding Provider
  participant K as Knowledge Search
  participant P as Prompt Builder
  participant L as LLM Provider
  participant DB as PostgreSQL

  U->>FE: requests issue analysis
  FE->>API: POST /api/ai/issues/{issue_id}/summarize
  API->>DB: load Issue, Project, Customer
  API->>S: analyze_and_store(issue_id)
  S->>Q: create deterministic retrieval query
  Q-->>S: retrieval query
  S->>E: embed query text
  E-->>S: query embedding
  S->>K: scoped pgvector cosine retrieval
  K-->>S: ready-document matches
  S->>P: build grounded prompt with untrusted evidence
  P-->>S: grounded prompt
  S->>L: send structured prompt
  L-->>S: six-field structured JSON
  S->>DB: persist retrieval metadata, citations, provider, model, Prompt Version
  API-->>FE: return stored Analysis record
  FE->>FE: render Grounded status and Citation Cards
  U->>FE: accepts, rejects, or edits and accepts
  FE->>API: PATCH feedback
  API->>DB: write human review result

  alt Retrieval no results
    K-->>S: empty result set
  else Retrieval failed
    K-->>S: retrieval error
  else LLM failed
    L-->>S: provider failure
    S->>L: rule-based fallback
  end
```

Only documents with `status=ready` are eligible.
The retrieval policy ensures archived documents are excluded from new retrieval.
The audit model ensures historical Citation Snapshots remain immutable.

## 5. Retrieval Scope Resolution
No context ID means global documents only.
A `customer_id` resolves to global plus matching customer documents.
A `project_id` resolves to global plus the project customer plus project documents.
An `issue_id` resolves Issue → Project → Customer, then uses the visible global/customer/project scopes.
Issue is a retrieval context, not a KnowledgeDocument scope.
Missing linked Project degrades according to the implemented runtime behavior.

Resolved scope types are ordered as global, customer, then project.
Archived, failed, and pending documents do not participate in ready retrieval.
`embedding IS NOT NULL` is part of the retrieval candidate filter.
The similarity order is ascending cosine distance.
`similarity_score = 1 - cosine_distance`.
Deterministic tie-breakers preserve repeatability.

## 6. Knowledge Ingestion and Embedding
The implemented ingestion pipeline supports manual knowledge document ingestion and text chunking.
`KnowledgeDocument` and `KnowledgeChunk` are persisted in PostgreSQL.
Single-chunk embedding and batch embedding backfill are implemented.
Existing embeddings are skipped by default and can be forced when needed.
Per-chunk failure isolation keeps one failed chunk from blocking the rest of the batch.
Safe retry is supported.
The embedding provider is `text-embedding-v4` with 1536 dimensions.
Provider metadata is stored alongside the embedding result.
Embeddings are stored in pgvector.
Embedding API Key and LLM API Key are separate runtime concerns.

## 7. Grounded Prompt and Structured Output
The grounded prompt version is `issue_summarizer_v4_grounded`.
Knowledge Evidence is limited to at most 5 items, and each item is length-limited before being inserted into the prompt.
Evidence is wrapped in an explicit untrusted boundary.
The prompt instructs the model not to follow role changes, tool calls, or output-format instructions that appear inside the evidence.

The structured output contract contains exactly six fields:

- `issue_summary`
- `possible_root_cause`
- `recommended_actions`
- `customer_update_draft`
- `risk_level`
- `project_impact`

LLM output must satisfy the structured JSON / Pydantic contract.
Prompt construction failure or provider failure can trigger rule-based fallback.
Fallback results still record provider and model metadata.

## 8. Persistence and Audit Model
`AIAnalysisLog` persists at least the following fields:

- `issue_id`
- `provider`
- `model_name`
- `prompt_version`
- the six structured output fields
- `retrieval_status`
- `retrieval_query`
- `knowledge_citations_json`
- `retrieval_error_code`
- `feedback_status`
- `feedback_note`
- `edited_output`
- timestamps

Generated text and Grounded Evidence are persisted separately.
Citation Snapshots are immutable historical evidence.
Knowledge document metadata cleanup does not rewrite old Analysis records.

Agent execution is persisted separately in `agent_runs`, `agent_steps`, and `agent_tool_calls`. Existing orchestration and persistence services own transactions, row locks, state advancement, and audit writes; LangGraph nodes and the single-step Driver do not own database sessions or commit boundaries.

Analysis #67 preserves the pre-cleanup Citation Snapshot.
Document #4 was archived after acceptance.
Analysis #68 contains only the clean business-facing Document #3 evidence path.

## 9. Human-in-the-loop State Machine

```mermaid
stateDiagram-v2
  [*] --> pending
  pending --> accepted: accept
  pending --> rejected: reject
  pending --> edited_and_accepted: edit and accept
  accepted --> [*]
  rejected --> [*]
  edited_and_accepted --> [*]
```

A finalized Analysis cannot be finalized twice.
A second feedback PATCH returns conflict.
`edited_and_accepted` requires nonblank `edited_output`.
Edited output is stored separately.
The original AI output remains unchanged.
`feedback_note` is optional and trimmed.

## 10. Frontend Evidence Layer
The frontend displays a Grounded Badge, Retrieval Status, Prompt Version, Citation Count, Document Title, Document ID, Doc Type, Scope, Source Kind, Source Name, and Similarity Score.
It does not display `retrieval_query`, `chunk_text`, `source_uri`, credentials, or provider endpoints.
Current Analysis and Analysis History use the same Evidence Renderer, which avoids field loss and presentation drift.

## 11. Failure Handling
The system explicitly handles missing Issue / Project / Customer records, invalid request schema, missing embedding configuration, embedding provider failure, no retrieval results, malformed retrieval response, LLM timeout, malformed LLM JSON, rule-based fallback, persistence transaction safety, duplicate feedback finalization, Agent step/tool-call limits, timeout and cancellation, idempotent resume, human waiting boundaries, and checkpoint identity mismatch classification.

HTTP request failure, `retrieval_status`, provider metadata, and persisted Analysis state are related but separate concerns.
The implementation records the failure mode it can safely persist without exposing secrets or raw provider internals.
The system does not claim full observability for every internal exception path.

## 12. Runtime and Deployment Topology

```mermaid
flowchart TD
  B[Browser] --> F[Vite development frontend]
  F --> A[FastAPI backend container]
  A --> P[(PostgreSQL + pgvector container)]
  A --> E[External Embedding endpoint]
  A --> L[External OpenAI-compatible LLM endpoint]
  A --> C[Docker Compose network]
  F --> C
  P --> C
```

The backend runs on port 8000.
The frontend development server runs on port 5173.
PostgreSQL is exposed on the configured local port.
Alembic applies schema revisions, and the accepted schema includes Grounded RAG plus Agent persistence and terminal-consistency migrations through `0007_agent_run_terminal`.
The deployment is a local Docker Compose runtime, not a public cloud deployment.

## 13. Verified Evidence

| Capability | Evidence |
| --- | --- |
| Real query embedding | text-embedding-v4 request completed |
| Vector dimensions | 1536 |
| Retrieval | pgvector Top-K cosine search |
| Final clean Analysis | #68 |
| LLM provider | llm |
| Model | gpt-5.5 |
| Prompt version | issue_summarizer_v4_grounded |
| Retrieval status | succeeded |
| Citation count | 1 |
| Citation document | Document #3 |
| Historical snapshot | Analysis #67 preserved |
| Archived test knowledge | Document #4 excluded from new retrieval |
| Frontend build | TypeScript and Vite production build passed |
| Human review | accepted / rejected / edited_and_accepted tested |
| Accepted E2E evidence model | `gpt-5.5` |
| Configurable example default | `gpt-4.1-mini` in `.env.example` and `compose.yaml` |
| Agent MVP evidence | Persisted lifecycle, bounded execution, tool, clarification, analysis, and final-review validators |
| LangGraph foundation | State, topology, adapters, Driver, Coordinator, and Runner injection validated |
| Runner injection boundary | `AgentRunnerService` stores the Coordinator but does not invoke it |
| Public validation | Checked-in documentation and Agent/LangGraph validators |

- [Portfolio README](../README.md)
- [Grounded RAG acceptance report](grounded-rag-acceptance.md)
- [Analysis #67 evidence snapshot](evidence/grounded-rag-analysis-67.json)
- [Final Grounded Analysis screenshot](screenshots/analysis-68-grounded-rag.png)

## 14. Security and Trust Boundaries
Knowledge Evidence is treated as untrusted data.
Credentials are environment configuration, not persisted in public documentation.
Retrieval query and raw chunk text are not exposed in the UI.
No authentication or RBAC is implemented.
This is a local portfolio runtime, not a production multi-tenant deployment.
Provider calls leave the local Docker environment and reach configured external endpoints.

## 15. Known Limitations
Authentication and RBAC are not implemented.
No public cloud deployment is included.
No CI/CD pipeline is included.
Grounded RAG has been accepted on one primary real business scenario.
No dedicated Grounded RAG evaluation dashboard exists.
Runtime demo records are local database state.
The frontend is functional but not a mature design system.
The architecture has not been load-tested for production-scale concurrency.
The validated LangGraph foundation has not taken over the production Runner execution path.
Persistent production checkpoint storage and automated DB/Checkpoint reconciliation are not included.
