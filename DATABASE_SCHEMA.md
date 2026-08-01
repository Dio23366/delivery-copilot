# Delivery Copilot — As-built Database Schema

## 1. Status

The accepted runtime database is PostgreSQL.

Schema changes are managed by Alembic:

| Revision | Purpose |
| --- | --- |
| `0001_baseline_schema` | Customers, Projects, Requirements, Issues, AI analysis baseline |
| `0002_knowledge_base_schema` | Knowledge Documents and Chunks |
| `0003_embeddings` | pgvector and embedding metadata |
| `0004_grounded_rag_analysis` | Retrieval and citation snapshot fields |
| `0005_agent_persistence` | Agent Runs, Steps, and Tool Calls |
| `0006_agent_tool_cancel` | Tool-call cancellation support |
| `0007_agent_run_terminal` | terminal-state consistency constraints |

The current schema contains ten application tables.

## 2. Relationship Overview

```text
customers
└── projects
    ├── requirements
    └── issues
        ├── ai_analysis_logs
        └── agent_runs
            └── agent_steps
                └── agent_tool_calls

knowledge_documents
└── knowledge_chunks
```

`agent_runs.analysis_log_id` optionally and uniquely links a Run to its persisted final analysis.

## 3. `customers`

Purpose: enterprise customer account records.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | primary key |
| `name` | varchar(255) | required |
| `industry` | varchar(100) | optional |
| `contact` | varchar(255) | optional |
| `status` | varchar(50) | required |
| `owner` | varchar(255) | required |
| `created_at` | datetime | creation time |
| `updated_at` | datetime | update time |

Application-accepted statuses:

- `active`
- `inactive`
- `prospect`

One Customer may have many Projects.

## 4. `projects`

Purpose: delivery engagements belonging to Customers.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | primary key |
| `customer_id` | integer FK | optional database field; API create requires an existing Customer |
| `name` | varchar(255) | required |
| `status` | varchar(50) | required |
| `health` | varchar(50) | required |
| `risk_level` | varchar(50) | optional |
| `delivery_stage` | varchar(50) | optional |
| `created_at` | datetime | creation time |
| `updated_at` | datetime | update time |

Application project statuses:

- `planning`
- `active`
- `on_hold`
- `completed`
- `cancelled`

Delivery stages:

- `Discovery`
- `Implementation`
- `Testing`
- `Go-live`
- `Support`

Risk-to-health mapping:

```text
low → healthy
medium → at_risk
high → critical
```

## 5. `requirements`

Purpose: delivery requirements and commitments.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | primary key |
| `project_id` | integer FK | optional database field; API create requires an existing Project |
| `title` | varchar(255) | required |
| `status` | varchar(50) | required |
| `priority` | varchar(50) | required |
| `owner` | varchar(255) | optional |
| `due_date` | date | optional |
| `created_at` | datetime | creation time |
| `updated_at` | datetime | update time |

Application statuses:

- `draft`
- `approved`
- `in_progress`
- `blocked`
- `delivered`

## 6. `issues`

Purpose: blockers, escalations, incidents, and delivery risks.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | primary key |
| `project_id` | integer FK | optional database field; API create requires an existing Project |
| `title` | varchar(255) | required |
| `description` | text | optional |
| `issue_type` | varchar(100) | optional |
| `status` | varchar(50) | required |
| `severity` | varchar(50) | required |
| `owner` | varchar(255) | optional |
| `created_at` | datetime | creation time |
| `updated_at` | datetime | update time |

Application statuses:

- `open`
- `investigating`
- `waiting_on_customer`
- `waiting_on_engineering`
- `resolved`

One Issue may have many analysis history records. Agent Runs also reference an Issue.

## 7. `ai_analysis_logs`

Purpose: persisted structured AI output, retrieval metadata, citation snapshots, and Human Review.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | primary key |
| `issue_id` | integer FK | required; indexed |
| `analysis_type` | varchar(100) | default `issue_summarizer` |
| `provider` | varchar(50) | `llm` or `rule_based_fallback` |
| `model_name` | varchar(255) | optional |
| `prompt_version` | varchar(100) | optional |
| `issue_summary` | text | required |
| `possible_root_cause` | text | required |
| `recommended_actions_json` | text | serialized action list |
| `customer_update_draft` | text | required |
| `risk_level` | varchar(50) | required |
| `project_impact` | text | required |
| `feedback_status` | varchar(50) | default `pending` |
| `feedback_note` | text | optional |
| `edited_output` | text | optional, separate from original output |
| `retrieval_status` | varchar(50) | default `not_attempted` |
| `retrieval_query` | text | optional |
| `knowledge_citations_json` | text | immutable citation snapshot payload |
| `retrieval_error_code` | varchar(100) | optional |
| `created_at` | datetime | creation time |
| `updated_at` | datetime | update time |

Human Review values:

- `pending`
- `accepted`
- `rejected`
- `edited_and_accepted`

## 8. `knowledge_documents`

Purpose: managed source documents for scoped retrieval.

Important constraints:

- scope type must be `global`, `customer`, or `project`;
- global scope has no Customer or Project ID;
- customer scope requires only `customer_id`;
- project scope requires only `project_id`;
- document type, source kind, and status use controlled values.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | primary key |
| `scope_type` | varchar(20) | required |
| `customer_id` | integer FK | optional by scope |
| `project_id` | integer FK | optional by scope |
| `title` | varchar(255) | required |
| `doc_type` | varchar(50) | required |
| `source_kind` | varchar(50) | required |
| `source_uri` | text | optional |
| `source_name` | varchar(255) | optional |
| `content_text` | text | required |
| `content_hash` | varchar(64) | required |
| `version_label` | varchar(100) | optional |
| `status` | varchar(20) | `pending`, `ready`, `failed`, or `archived` |
| `error_message` | text | optional |
| `created_at` | datetime | required |
| `updated_at` | datetime | required |
| `ingested_at` | datetime | optional |
| `last_indexed_at` | datetime | optional |

Document types:

- `api_doc`
- `deployment_guide`
- `troubleshooting_guide`
- `solution_note`
- `product_guide`

Source kinds:

- `manual`
- `uploaded`
- `internal_wiki`
- `generated`

## 9. `knowledge_chunks`

Purpose: deterministic source chunks and persisted vector embeddings.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | primary key |
| `document_id` | integer FK | required; cascade delete |
| `chunk_index` | integer | nonnegative; unique per document |
| `chunk_text` | text | required |
| `chunk_title` | varchar(255) | optional |
| `section_path` | varchar(500) | optional |
| `page_number` | integer | optional |
| `token_count` | integer | optional, nonnegative |
| `char_count` | integer | optional, nonnegative |
| `source_span_start` | integer | optional, nonnegative |
| `source_span_end` | integer | optional, nonnegative |
| `metadata_json` | JSONB | optional |
| `embedding` | vector(1536) | optional |
| `embedding_provider` | varchar(50) | required when embedding exists |
| `embedding_model` | varchar(100) | required when embedding exists |
| `embedding_dimension` | integer | must equal 1536 when present |
| `embedded_at` | datetime | required when embedding exists |
| `created_at` | datetime | required |
| `updated_at` | datetime | required |

Embedding and all four embedding metadata fields must be present or absent together.

## 10. `agent_runs`

Purpose: one persisted, resumable Agent execution.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | primary key |
| `run_id` | varchar(36) | unique external identifier |
| `issue_id` | integer FK | required |
| `analysis_log_id` | integer FK | optional and unique |
| `graph_version` | varchar(100) | required |
| `current_node` | varchar(100) | required |
| `run_status` | varchar(50) | constrained lifecycle value |
| `step_count` | integer | nonnegative |
| `tool_call_count` | integer | nonnegative |
| `retry_count` | integer | nonnegative |
| `state_json` | JSONB | required serializable state |
| `waiting_since` | datetime | required only in waiting states |
| `resume_node` | varchar(100) | required only in waiting states |
| `error_code` | varchar(100) | controlled error metadata |
| `error_message` | text | controlled error metadata |
| `started_at` | datetime | required after execution starts |
| `completed_at` | datetime | required for terminal states |
| `created_at` | datetime | required |
| `updated_at` | datetime | required |

Allowed Run statuses:

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

Key constraints enforce:

- nonnegative counters;
- chronological completion;
- status/timestamp consistency;
- waiting fields only in waiting states;
- error presence for `failed` and `limit_exceeded`;
- error absence for `completed` and `cancelled`;
- unique `run_id`;
- at most one Run per `analysis_log_id`.

## 11. `agent_steps`

Purpose: ordered audit records for Agent nodes.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | primary key |
| `agent_run_id` | integer FK | required; cascade delete |
| `step_index` | integer | positive; unique per Run |
| `node_name` | varchar(100) | required |
| `step_status` | varchar(50) | lifecycle value |
| `input_state_json` | JSONB | optional controlled snapshot |
| `output_state_json` | JSONB | optional controlled snapshot |
| `error_code` | varchar(100) | optional |
| `error_message` | text | optional |
| `started_at` | datetime | required |
| `completed_at` | datetime | required for terminal Step states |

Allowed Step statuses:

- `running`
- `completed`
- `interrupted`
- `failed`
- `cancelled`

Constraints enforce positive ordering, timestamp consistency, and error metadata for failed Steps.

## 12. `agent_tool_calls`

Purpose: ordered audit records for guarded Agent tool attempts.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer | primary key |
| `agent_step_id` | integer FK | required; cascade delete |
| `tool_call_index` | integer | positive; unique per Step |
| `tool_name` | varchar(100) | required |
| `tool_version` | varchar(100) | optional |
| `call_status` | varchar(50) | lifecycle value |
| `arguments_json` | JSONB | required |
| `result_json` | JSONB | required for completed calls |
| `read_only` | boolean | required |
| `requires_approval` | boolean | required |
| `timeout_seconds` | integer | positive |
| `error_code` | varchar(100) | optional |
| `error_message` | text | optional |
| `started_at` | datetime | state-dependent |
| `completed_at` | datetime | state-dependent |
| `created_at` | datetime | required |
| `updated_at` | datetime | required |

Allowed Tool Call statuses:

- `created`
- `running`
- `completed`
- `failed`
- `timed_out`
- `cancelled`

Constraints enforce status/timestamp consistency, a result for completed calls, error metadata for failed/timed-out calls, and positive timeout values.

## 13. Transaction and Deletion Boundaries

- Agent orchestration services own commit, rollback, and refresh.
- Persistence services own row locks and atomic advancement.
- Graph nodes and tool adapters do not own database commits.
- Lock order is Run → Step → Tool Call; final review additionally coordinates the linked Analysis.
- Deleting an Agent Run cascades to Steps and Tool Calls.
- Deleting a Knowledge Document cascades to Chunks.
- Business relationships such as Issue → Analysis and Issue → Agent Run are not configured as broad destructive cascades.

## 14. Portability Boundary

PostgreSQL is the accepted runtime and provides:

- JSONB;
- pgvector;
- relational constraints;
- row locking used by lifecycle services.

Several model types have SQLite-compatible variants to support isolated stub validation. That compatibility must not be described as the accepted production database.

## 15. Not Present

The current schema does not contain:

- `users`
- `comments`
- `ai_insights`
- report tables
- authentication/session tables
- multi-agent tables
- checkpoint reconciliation tables

Those appeared in early planning material but are not part of the as-built schema.
