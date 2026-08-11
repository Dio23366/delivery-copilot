# Delivery Copilot Agent Demo — Runtime Acceptance

## 1. Acceptance Scope

This report records the local runtime acceptance of the operator-facing,
bounded single-agent Issue investigation workflow on 2026-08-10.

The accepted boundary is the existing custom production Runner exposed through
the Agent Investigation UI. It does not claim full LangGraph Runner takeover,
multi-agent orchestration, autonomous write actions, production RBAC, or a
production SLA.

## 2. Environment

- Windows host with Docker Desktop
- Docker Engine 29.6.1
- Docker Compose 5.3.0
- PostgreSQL / pgvector container healthy
- FastAPI backend health endpoint returned `status=ok`
- Node.js 24.18.0 and npm 11.16.0
- Frontend production build: passed

Runtime database identifiers and timestamps are local demo evidence and are not
portable repository fixtures.

## 3. Accepted Scenarios

| Scenario | Runtime evidence |
| --- | --- |
| Start and triage | Run persisted 3 Steps and interrupted at `await_triage_confirmation` |
| Triage resume | Human confirmation resumed the same Run without duplication |
| Tool audit | 3 approved read-only Tool calls were persisted and rendered in the timeline |
| Evidence guardrail | An authentication chunk with similarity `0.6089` was below the Agent threshold `0.65` |
| Clarification | Run interrupted at `waiting_for_clarification` with a focused API-timeout question |
| Clarification resume | A simulated endpoint, timeout, timestamp, and correlation ID were persisted as human evidence |
| Generation filter | Below-threshold knowledge remained auditable but was excluded from the Prompt and Citation Snapshot |
| Final Review | Run reached `await_final_review` at Step 20 with `Retrieval: no_results` |
| Completion | Final Human Review produced `finalize_run` at Step 21; 3 Tool calls and 0 retries |
| Normal cancellation | A Run waiting for triage was cancelled while its prior audit Steps remained visible |
| Recovery cancellation | An active Run with a failed latest Step was safely terminalized while preserving the failed Step |
| UI redaction | Retrieval query, chunk text, source URI, and secret-like fields rendered as hidden or redacted |

## 4. Defects Found and Closed During Acceptance

### 4.1 Browser state exposure

Tool results initially exposed retrieval query text, knowledge chunks, and
source URI. Recursive UI redaction now applies to Tool arguments, Tool results,
Step snapshots, and controlled Agent state.

### 4.2 Weak evidence accepted as sufficient

The original `0.60` boundary accepted an unrelated authentication chunk scored
at approximately `0.6089`. The Agent demo now uses a conservative `0.65`
guardrail. This value favors precision for a delivery workflow and remains a
calibration baseline rather than a production universal.

### 4.3 Clarification could not read persisted context

Production Run state stores Issue data under `issue_context`, while the
Clarification service initially expected flat fields. It now reads the
persisted nested contract and retains backwards compatibility for older flat
callers. API timeout receives a timeout-specific question instead of a generic
authentication question.

### 4.4 Failed Run could not be cancelled

A failed Step with an active outer Run previously created a recovery deadlock.
Recovery cancellation now preserves the failed Step and its error payload while
terminalizing the outer Run. It still refuses a failed Step that incorrectly
contains an active Tool call.

### 4.5 Step budget excluded the valid clarification path

`max_steps=16` could not cover three Tool calls plus one Human Clarification
round. The frozen demo default is now `20`; `max_tool_calls` remains `3`.
Final Human Review adds the terminal Step 21 outside the bounded investigation
loop.

### 4.6 Weak evidence still entered generation

Evidence evaluation and generation initially used different effective
boundaries. Generation now reuses the same `0.65` guardrail. Weak chunks remain
in immutable Tool audit data but are excluded from the generation Prompt and
Citation Snapshot. When none remain, the generated Analysis records
`retrieval_status=no_results`.

### 4.7 Review form state carried across Runs

The frontend now resets decision, note, and edited output whenever the linked
`analysis_log_id` changes.

## 5. Validation Results

```text
Agent UI validation: PASS
Grounded UI regression: PASS
Frontend build: PASS
Backend health: PASS
Normal final-review path: PASS
Normal cancellation path: PASS
Recovery cancellation path: PASS
Clarification path: PASS
Below-threshold generation filter: PASS
Final completion path: PASS
```

## 6. Honest Portfolio Claim

> Delivery Copilot implements an operator-visible, bounded single-agent Issue
> investigation workflow with persisted Run/Step/ToolCall audit records,
> guarded read-only tools, conservative evidence routing, Human Clarification,
> resumable execution, structured Analysis generation, and final Human Review.

This runtime acceptance does not establish a production-grade autonomous Agent
platform, multi-agent collaboration, full LangGraph Runner takeover, or
production accuracy without a representative evaluation dataset.
