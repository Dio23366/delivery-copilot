# Delivery Copilot - Agent MVP Scope

## 1. Document Status

- Status: Historical Scope Freeze with Current As-built Overlay
- Public source of truth: checked-out source, migrations, evidence documents, and validators
- Runtime LangGraph dependency: `langgraph==1.2.10`
- Current implementation boundary: validated foundation with no production Runner takeover

This document preserves the original Sprint 3A-0 scope as a historical design contract and adds the current as-built status. Sections that describe a frozen target are retained to explain design intent; the as-built statements in this section and Sections 12-13 describe what the repository can honestly claim now.

The current repository implements the controlled single-agent workflow, Agent persistence, tool selection and guarded execution, bounded continuation, Human Clarification, analysis persistence, final review, and resume behavior. It also contains a runtime-tested LangGraph orchestration foundation with typed state, graph topology, adapters, a single-step Driver, checkpoint identity classification, a Coordinator foundation, and Runner constructor injection.

The production Runner remains the owner of the existing business execution path. Full production takeover by LangGraph, a persistent production Checkpointer, automated DB/Checkpoint reconciliation, and multi-agent collaboration are outside this portfolio scope.

## 2. MVP Objective

The Agent MVP upgrades the existing fixed Grounded RAG pipeline into a controlled, stateful, and auditable single-agent issue investigation workflow.

The MVP must demonstrate that an agent can:

1. triage an Issue;
2. select among approved read-only tools;
3. use tool results to decide the next step;
4. evaluate whether evidence is sufficient;
5. request human clarification when evidence is insufficient;
6. generate the existing six-field grounded analysis when evidence is sufficient;
7. persist the Agent Run, Steps, and Tool Calls;
8. continue into the existing Human Review workflow.

The MVP extends the existing product. It does not replace or rewrite the accepted Grounded RAG v1.0 implementation.

## 3. Primary Acceptance Scenario

The first and only required MVP scenario is:

**Issue #17 - API Authentication Investigation Agent**

The scenario concerns an enterprise API authentication failure and uses the existing Delivery Copilot business context and knowledge evidence.

The Agent MVP is not intended to be a general-purpose autonomous agent platform.

## 4. Target Workflow

The frozen target workflow was:

```text
START
-> Load Issue
-> AI Triage
-> Triage Confirmation
-> Route
-> Select Tool
-> Execute Tool
-> Evaluate Evidence
   |- evidence insufficient -> select another tool
   |- clarification required -> Human Clarification interrupt
   `- evidence sufficient -> Generate Analysis
-> Persist Analysis
-> Human Review
-> Persist Final Agent State
-> END
```

The final graph must contain real conditional routing. It must not be implemented as a fixed sequence disguised as an agent.

## 5. In-Scope Capabilities

### 5.1 AI Triage

The Agent will generate a triage suggestion containing:

- `issue_type`
- `subtype`
- `severity`
- `confidence`
- `reason`

The suggestion must be validated before use.

The Agent must not silently overwrite Issue fields entered or confirmed by a user.

### 5.2 Read-only Tool Layer

The first version contains four approved read-only tools:

1. `load_issue_context`
2. `search_knowledge`
3. `get_analysis_history`
4. `calculate_delivery_risk`

`load_issue_context` is a mandatory deterministic starting tool.

After context is loaded, the Agent must be capable of selecting among at least these three tools:

- `search_knowledge`
- `get_analysis_history`
- `calculate_delivery_risk`

The Agent is not required to call all three tools during every run.

### 5.3 Dynamic Routing

Tool selection after context loading must not be a completely fixed hard-coded order.

At least one Tool Result must influence the next node or tool choice.

The graph must support at least these outcomes:

- continue investigation;
- request human clarification;
- generate grounded analysis;
- terminate safely after failure or limit exhaustion.

### 5.4 Evidence Sufficiency

The Agent must explicitly evaluate whether collected evidence is sufficient for final analysis.

Evidence sufficiency is an Agent routing decision. It is not the same as model answer accuracy.

Similarity remains a retrieval relevance signal:

```text
similarity_score = 1 - cosine_distance
```

Similarity must not be represented as the probability that an analysis is correct.

### 5.5 Final Analysis

The Agent must reuse the existing six-field analysis contract:

- `issue_summary`
- `possible_root_cause`
- `recommended_actions`
- `customer_update_draft`
- `risk_level`
- `project_impact`

The MVP must not introduce an incompatible replacement for the accepted structured output.

### 5.6 Human Control

The MVP includes:

- confirmation of AI triage suggestions;
- Human Clarification when required information is missing;
- the existing final Human Review workflow;
- support for resuming an interrupted Agent Run.

The initial four tools are read-only and do not require per-call approval.

Any future write-capable tool must require explicit Human Approval before execution.

### 5.7 Auditability and Recovery

The Agent workflow must persist enough information to support:

- Agent Run status;
- current node;
- Step history;
- Tool Call arguments and results;
- retries;
- errors;
- approval or clarification state;
- final outcome;
- interruption and resume.

## 6. Tool Contract Requirements

Every Agent tool must define:

- `name`
- `description`
- `input_schema`
- `output_schema`
- `timeout`
- `retry_policy`
- `read_only`
- `requires_approval`

Tool inputs and outputs must be validated with Pydantic models.

Tool implementations must return controlled, serializable results rather than leaking raw provider objects or database sessions into Agent State.

The first four tools have:

```text
read_only = true
requires_approval = false
```

This does not permit future write tools to bypass approval.

## 7. Architecture Boundary

LangGraph is used only as the Agent orchestration layer.

The frozen architecture boundary was:

```text
FastAPI Agent API
-> Agent Application Service
-> LangGraph StateGraph
-> Agent Nodes and Tool Registry
-> Existing Delivery Copilot Services
```

The implementation must reuse existing capabilities where appropriate:

- FastAPI application;
- SQLAlchemy database access;
- Issue, Project, and Customer models;
- context building;
- knowledge retrieval;
- LLM provider abstraction;
- rule-based fallback;
- six-field structured output;
- `AIAnalysisLog`;
- existing Human Review.

The implementation must not place orchestration responsibilities inside:

- FastAPI route handlers;
- SQLAlchemy models;
- the LLM Provider;
- the Knowledge Search Service;
- individual Tool implementations.

The current `/api/ai/issues/{issue_id}/summarize` Grounded RAG path must remain available and unchanged during the Agent Foundation phase.

## 8. Dependency Boundary

The project runtime baseline is Python `3.11.9` in Docker.

The checked-in backend requirements pin `langgraph==1.2.10`. The dependency is installed in the accepted development runtime and has been exercised by state-contract, topology, adapter, Driver, checkpoint-identity, Coordinator, and Runner-injection validators.

This runtime validation establishes the orchestration foundation only. It does not establish a production Checkpointer deployment, distributed execution, automatic DB/Checkpoint reconciliation, or production Runner takeover.

## 9. Persistence Objects — Historical Plan and Current As-built State

Sprint 3A-0 reserved three persistence concepts:

- `agent_runs`
- `agent_steps`
- `agent_tool_calls`

They are now implemented as separate SQLAlchemy/Alembic persistence objects with lifecycle constraints, relationships, indexes, JSON state, terminal-consistency rules, and audit records.

The Agent tables remain separate from `AIAnalysisLog`. A completed Agent Run may reference the final `AIAnalysisLog` generated by that run.

Detailed current columns, constraints, relationships, and migration coverage are documented in `DATABASE_SCHEMA.md`.

## 10. Safety and Execution Limits

The implementation must have finite, configurable limits for:

- `max_steps`
- `max_tool_calls`
- `max_retries`
- node timeout
- tool timeout

Exact default values are not assigned by this scope document. They must be frozen before orchestration implementation.

A Run must terminate safely when a limit is reached.

Failures must be persisted without exposing credentials, API keys, provider endpoints, or unnecessary raw internal data.

## 11. Explicit Non-goals

The Agent MVP does not include:

- automatic modification of Issue records;
- automatic sending of customer messages;
- write-capable Agent tools;
- multi-agent collaboration;
- Agent long-term memory;
- Slack integration;
- Jira integration;
- CRM integration;
- model fine-tuning;
- authentication or RBAC;
- multi-tenant organization support;
- public cloud production deployment;
- Kubernetes;
- Redis;
- Kafka;
- a complete production observability platform;
- a general-purpose autonomous agent platform.

## 12. MVP Completion Criteria

The Agent Workflow can be described as implemented only after all of the following are verified:

- AI automatically proposes Issue classification;
- AI can select among at least three tools;
- tool selection is not a completely fixed order;
- the graph contains at least one conditional branch;
- a Tool Result affects the next step;
- Agent Run state is persisted;
- every executed Step has an audit record;
- every Tool Call has an audit record;
- the Agent can fail safely or retry;
- finite `max_steps` and `max_tool_calls` limits are enforced;
- at least one node supports Human Clarification or Approval;
- an interrupted Run can resume;
- at least one Agent task evaluation case exists;
- the final result enters the existing Human Review workflow.

### As-built Acceptance Status

The completion criteria above have been exercised through committed validators, PostgreSQL/API acceptance, resume and final-review flows, bounded execution checks, and the final LangGraph constructor-injection post-commit audit.

The accepted LangGraph foundation is an incremental migration seam around the existing production Runner, not evidence of production-scale orchestration takeover.

## 13. Portfolio Claim Boundary

The accepted portfolio may claim:

> Implemented and validated a controlled single-agent Issue investigation workflow with persisted Run/Step/ToolCall audit records, guarded read-only tools, bounded resume behavior, Human Clarification, final Human Review, and a LangGraph orchestration foundation.

The LangGraph claim is limited to the verified foundation: typed state, graph topology, adapters, a single-step Driver, checkpoint identity classification, Coordinator foundation, and Runner constructor injection.

It must not claim full LangGraph takeover of the production Runner, deployment of a persistent production Checkpointer, automatic reconciliation of DB/Checkpoint inconsistency, or enterprise Agent Platform status.

Claims must remain limited to the verified single-agent Issue investigation workflow and the accepted local portfolio evidence.

The project must not claim:

- production deployment;
- production SLA;
- formal business ROI;
- formal model accuracy;
- multi-agent implementation;
- fully autonomous enterprise actions.

## 14. Scope Change Control

This document is the frozen Sprint 3A-0 MVP boundary.

Any change that adds tools, write actions, integrations, infrastructure, or additional business scenarios must:

1. be proposed explicitly;
2. state why the current MVP cannot meet the objective without it;
3. identify architecture and acceptance impact;
4. update the scope version before implementation.

The Agent State, node definitions, conditional edges, interrupt points, and persistence mapping will be defined separately in:

```text
docs/agent/agent-state-and-graph.md
```
