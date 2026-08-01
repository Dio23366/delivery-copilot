# Delivery Copilot — As-built API Design

## 1. Status and Base Paths

This document lists the endpoints implemented by the current FastAPI application.

Application base:

```text
http://localhost:8000
```

API base:

```text
/api
```

Health check:

```text
GET /health
```

There is no `/api/v1` prefix in the implemented runtime.

## 2. Common Behavior

- Requests and responses use JSON unless no body is required.
- Pydantic validation errors use FastAPI's standard `422` response.
- Missing resources generally return `404`.
- Invalid lifecycle or duplicate-finalization operations generally return `409`.
- Create operations return `201` where declared; other successful operations return `200`.
- Unhandled persistence/provider failures are converted to controlled `500` responses.
- Authentication and RBAC are not implemented.
- Operational list endpoints currently return complete arrays without pagination.

## 3. Health

### `GET /health`

Response:

```json
{
  "status": "ok"
}
```

## 4. Dashboard

### `GET /api/dashboard/metrics`

Returns:

```json
{
  "active_customers": 0,
  "active_projects": 0,
  "open_issues": 0,
  "critical_issues": 0,
  "overdue_requirements": 0,
  "projects_at_risk": 0
}
```

## 5. Customers

### `GET /api/customers`

Returns all Customers ordered by ID.

### `POST /api/customers`

Creates a Customer.

Request:

```json
{
  "name": "Example Customer",
  "industry": "Technology",
  "contact": "ops@example.invalid",
  "status": "active",
  "owner": "Delivery Team"
}
```

Allowed status values:

- `active`
- `inactive`
- `prospect`

A duplicate normalized name returns `409`.

### `PATCH /api/customers/{customer_id}`

Updates only the Customer status.

Request:

```json
{
  "status": "inactive"
}
```

## 6. Projects

### `GET /api/projects`

Returns all Projects ordered by ID.

### `POST /api/projects`

Creates a Project for an existing Customer.

Request:

```json
{
  "name": "API Integration",
  "customer_id": 1,
  "status": "active",
  "delivery_stage": "Implementation",
  "risk_level": "medium"
}
```

Allowed project statuses:

- `planning`
- `active`
- `on_hold`
- `completed`
- `cancelled`

Allowed delivery stages:

- `Discovery`
- `Implementation`
- `Testing`
- `Go-live`
- `Support`

Allowed risk levels:

- `low`
- `medium`
- `high`

Project health is derived from risk:

```text
low → healthy
medium → at_risk
high → critical
```

### `PATCH /api/projects/{project_id}`

Updates one or more of:

- `status`
- `delivery_stage`
- `risk_level`

An empty update returns `400`.

## 7. Requirements

### `GET /api/requirements`

Returns all Requirements ordered by ID.

### `POST /api/requirements`

Creates a Requirement for an existing Project.

Request:

```json
{
  "title": "Confirm authentication flow",
  "priority": "high",
  "status": "in_progress",
  "owner": "Implementation Team",
  "due_date": "2026-08-15",
  "project_id": 1
}
```

### `PATCH /api/requirements/{requirement_id}/status`

Request:

```json
{
  "status": "delivered"
}
```

Allowed status values:

- `draft`
- `approved`
- `in_progress`
- `blocked`
- `delivered`

## 8. Issues

### `GET /api/issues`

Returns all Issues ordered by ID.

### `POST /api/issues`

Creates an Issue for an existing Project.

Request:

```json
{
  "title": "Customer API authentication failure",
  "description": "Production requests return 401.",
  "issue_type": "API",
  "severity": "critical",
  "status": "open",
  "owner": "Engineering Team",
  "project_id": 1
}
```

### `PATCH /api/issues/{issue_id}/status`

Request:

```json
{
  "status": "investigating"
}
```

Allowed status values:

- `open`
- `investigating`
- `waiting_on_customer`
- `waiting_on_engineering`
- `resolved`

## 9. Persisted AI Analysis

### `POST /api/ai/issues/{issue_id}/summarize`

Runs the persisted issue-analysis workflow.

The service loads Issue context, attempts scoped knowledge retrieval, calls the configured provider, validates the structured result, applies rule-based fallback when needed, and persists an `AIAnalysisLog`.

Representative response:

```json
{
  "analysis_id": 68,
  "issue_id": 17,
  "analysis_type": "issue_summarizer",
  "provider": "llm",
  "model_name": "gpt-5.5",
  "prompt_version": "issue_summarizer_v4_grounded",
  "issue_summary": "...",
  "possible_root_cause": "...",
  "recommended_actions": ["..."],
  "customer_update_draft": "...",
  "risk_level": "high",
  "project_impact": "...",
  "feedback_status": "pending",
  "feedback_note": null,
  "edited_output": null,
  "retrieval_status": "succeeded",
  "retrieval_query": "...",
  "knowledge_citations": [
    {
      "citation_id": "K1",
      "rank": 1,
      "chunk_id": 1,
      "document_id": 1,
      "document_title": "API Authentication Troubleshooting Guide",
      "scope_type": "global",
      "customer_id": null,
      "project_id": null,
      "doc_type": "troubleshooting_guide",
      "source_kind": "manual",
      "source_name": "Delivery Knowledge",
      "source_uri": null,
      "chunk_index": 0,
      "distance": 0.39,
      "similarity_score": 0.61
    }
  ],
  "retrieval_error_code": null,
  "knowledge_grounded": true,
  "created_at": "...",
  "updated_at": "..."
}
```

`knowledge_grounded` is true only when all of the following hold:

- provider is `llm`;
- retrieval status is `succeeded`;
- at least one citation exists;
- prompt version is `issue_summarizer_v4_grounded`.

### `GET /api/ai/issues/{issue_id}/analyses`

Returns persisted analysis history for one Issue.

### `PATCH /api/ai/analyses/{analysis_id}/feedback`

Finalizes Human Review.

Request examples:

```json
{
  "feedback_status": "accepted",
  "feedback_note": "Reviewed."
}
```

```json
{
  "feedback_status": "edited_and_accepted",
  "feedback_note": "Customer-safe wording applied.",
  "edited_output": "Updated customer communication."
}
```

Accepted schema values:

- `pending`
- `accepted`
- `rejected`
- `edited_and_accepted`

The UI and normal final-review workflow use the three final values. `edited_and_accepted` requires a nonblank edited output. A finalized analysis returns `409` on a second finalization.

For an Agent-linked analysis, this endpoint also atomically finalizes the waiting Agent Run. Agent-linked feedback must use a final status.

### `GET /api/ai/evaluation/metrics`

Returns overall, provider/model, and prompt-version review metrics.

## 10. Legacy Mock AI Endpoints

These endpoints return deterministic mock output and do not represent the persisted Grounded RAG workflow:

- `POST /api/ai/parse-requirement`
- `POST /api/ai/summarize-issue`
- `POST /api/ai/analyze-risk`
- `POST /api/ai/customer-update-draft`

They remain as lightweight compatibility/demo endpoints.

## 11. Knowledge Documents and Embeddings

### `POST /api/knowledge/documents`

Creates a document, validates its scope, computes a content hash, and creates deterministic chunks.

Core request fields:

- `scope_type`: `global`, `customer`, or `project`
- `customer_id`
- `project_id`
- `title`
- `doc_type`
- `source_kind`
- `source_uri`
- `source_name`
- `content_text`
- `version_label`

Scope identity rules:

```text
global   → customer_id = null, project_id = null
customer → customer_id required, project_id = null
project  → project_id required, customer_id = null
```

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

Statuses:

- `pending`
- `ready`
- `failed`
- `archived`

### `GET /api/knowledge/documents`

Optional filters:

- `scope_type`
- `customer_id`
- `project_id`
- `status`
- `doc_type`

### `GET /api/knowledge/documents/{document_id}`

Returns document detail including `content_text`.

### `GET /api/knowledge/documents/{document_id}/chunks`

Returns deterministic chunk records.

### `POST /api/knowledge/chunks/{chunk_id}/embedding?force=false`

Embeds one chunk.

A successful response includes:

- chunk and document IDs;
- provider;
- model;
- dimension;
- embedded timestamp;
- status.

### `POST /api/knowledge/documents/{document_id}/embeddings?force=false`

Runs batch embedding for every chunk and returns total, succeeded, skipped, failed, status, and per-chunk failures.

### `POST /api/knowledge/search`

Request:

```json
{
  "query": "401 authentication troubleshooting",
  "issue_id": 17,
  "top_k": 5,
  "min_similarity": 0.2
}
```

At most one of `customer_id`, `project_id`, or `issue_id` may be supplied.

`top_k` must be between 1 and 20.

Response includes:

- normalized query;
- resolved context and scope types;
- result count;
- ranked chunks;
- cosine distance;
- `similarity_score = 1 - distance`.

Similarity is a retrieval relevance signal, not answer confidence.

## 12. Agent Lifecycle API

### `POST /api/agent/runs`

Request:

```json
{
  "issue_id": 17
}
```

Behavior:

- locks and validates the Issue;
- returns the newest active Run if one already exists for that Issue;
- otherwise creates a Run and advances it to the triage-confirmation boundary.

The initial graph version is `agent_mvp_v0.1`.

### `GET /api/agent/runs/{run_id}`

Returns the complete persisted Run view, including:

- Run state and counters;
- waiting/resume fields;
- errors and timestamps;
- ordered Steps;
- ordered Tool Calls with validated arguments, controlled results, policy flags, timeouts, and errors.

### `POST /api/agent/runs/{run_id}/resume`

Exactly one resume input is required.

Triage-confirmation example:

```json
{
  "triage_result": {
    "issue_type": "API",
    "subtype": "Authentication",
    "severity": "critical",
    "confidence": 0.93,
    "reason": "The issue reports repeated production 401 responses."
  }
}
```

Clarification example:

```json
{
  "clarification_response": "The token issuer and audience were verified."
}
```

The endpoint resumes the waiting transaction and runs the bounded investigation loop until the next persistence or human boundary.

### `POST /api/agent/runs/{run_id}/cancel`

Cancels supported waiting or active Run states.

Unsupported terminal or incompatible states return `409`.

## 13. Agent Final Review Integration

There is no separate Agent final-review endpoint.

After the Agent persists an Analysis and enters `waiting_for_final_review`, the existing endpoint is used:

```text
PATCH /api/ai/analyses/{analysis_id}/feedback
```

The orchestration service locks and finalizes both the Analysis and linked Agent Run in one controlled transaction.

## 14. Endpoint Inventory

Implemented API routes:

```text
GET    /health

GET    /api/dashboard/metrics

GET    /api/customers
POST   /api/customers
PATCH  /api/customers/{customer_id}

GET    /api/projects
POST   /api/projects
PATCH  /api/projects/{project_id}

GET    /api/requirements
POST   /api/requirements
PATCH  /api/requirements/{requirement_id}/status

GET    /api/issues
POST   /api/issues
PATCH  /api/issues/{issue_id}/status

POST   /api/ai/parse-requirement
POST   /api/ai/summarize-issue
POST   /api/ai/analyze-risk
POST   /api/ai/customer-update-draft
POST   /api/ai/issues/{issue_id}/summarize
GET    /api/ai/issues/{issue_id}/analyses
GET    /api/ai/evaluation/metrics
PATCH  /api/ai/analyses/{analysis_id}/feedback

POST   /api/knowledge/documents
GET    /api/knowledge/documents
GET    /api/knowledge/documents/{document_id}
GET    /api/knowledge/documents/{document_id}/chunks
POST   /api/knowledge/chunks/{chunk_id}/embedding
POST   /api/knowledge/documents/{document_id}/embeddings
POST   /api/knowledge/search

POST   /api/agent/runs
GET    /api/agent/runs/{run_id}
POST   /api/agent/runs/{run_id}/resume
POST   /api/agent/runs/{run_id}/cancel
```

Not implemented:

- authentication endpoints;
- user endpoints;
- comment endpoints;
- report endpoints;
- pagination envelopes;
- public webhook or background-worker endpoints.
