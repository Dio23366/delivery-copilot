# Delivery Copilot — As-built Page Design

## 1. Status

This document describes the React routes and interactions implemented in the current frontend.

- Status: As-built documentation refresh
- Runtime acceptance date: `2026-08-10`
- Source of truth: current public frontend/backend contracts and accepted runtime evidence

The application is a desktop-oriented portfolio interface using React, TypeScript, Vite, React Router, and a shared sidebar layout.

There is no Login page, authentication flow, Reports page, Project Detail route, or knowledge-administration UI. The implemented Agent lifecycle surface is a bounded operator demo driven by the backend `AgentRunnerService` state machine rather than a general autonomous-Agent workspace. The UI does not imply LangGraph production Runner takeover.

## 2. Application Shell

The shared shell contains:

- product name: `Delivery Copilot`;
- subtitle: `AI-powered enterprise delivery dashboard`;
- persistent sidebar navigation;
- main content outlet.

Implemented routes:

| Route | Page |
| --- | --- |
| `/dashboard` | Dashboard |
| `/customers` | Customers |
| `/projects` | Projects |
| `/requirements` | Requirements |
| `/issues` | Issues |
| `/ai-copilot` | AI Copilot |
| `/ai-evaluation` | AI Evaluation |
| `/agent-runs` | Agent Investigation |

`/` redirects to `/dashboard`.

All data-backed pages use shared loading, error, and empty-state behavior.

## 3. Dashboard

### Purpose

Provide a compact operational summary.

### Implemented content

Six metric cards:

- Active Customers
- Active Projects
- Open Issues
- Critical Issues
- Overdue Requirements
- Projects at Risk

### Interaction boundary

The current page is metric-only. It does not implement charts, date filters, drill-down panels, recent activity, or report export.

## 4. Customers

### Purpose

List Customer records and support basic lifecycle operations.

### Implemented content

Table fields:

- ID
- name
- industry
- contact
- status
- owner

### Implemented actions

- show or hide Create Customer form;
- create a Customer;
- update Customer status inline;
- refresh data after success or failure.

Allowed UI status values:

- `active`
- `inactive`
- `prospect`

There is no Customer Detail route, search, pagination, delete action, or role assignment.

## 5. Projects

### Purpose

List delivery Projects and manage their current delivery state.

### Implemented content

The table displays Project identity and operational fields including:

- ID
- name
- Customer ID
- status
- delivery stage
- risk level
- derived health

### Implemented actions

- load Customer options;
- create a Project for an existing Customer;
- update status;
- update delivery stage;
- update risk level and derived health.

There is no separate Project Detail route, milestone view, comment timeline, or project-level AI page.

## 6. Requirements

### Purpose

Track delivery commitments.

### Implemented content

The table displays:

- ID
- title
- priority
- status
- owner
- due date
- Project ID

### Implemented actions

- load Project options;
- create a Requirement;
- update status inline.

The page visually exposes current records but does not implement search, pagination, comments, requirement detail, bulk editing, or AI requirement review.

## 7. Issues

### Purpose

Manage delivery Issues and provide the primary persisted AI-analysis interface.

### Implemented issue operations

- list Issues;
- create an Issue for a Project;
- update Issue status;
- display issue type, severity, owner, and Project ID.

### Implemented analysis operations

Each Issue row provides:

- `Analyze with AI`;
- `View Analysis History`.

The current analysis card displays:

- analysis ID;
- provider;
- model;
- retrieval status;
- prompt version;
- grounded-state badge;
- retrieval error code when present;
- citation count and citation metadata;
- risk level;
- issue summary;
- possible root cause;
- recommended actions;
- project impact;
- customer update draft;
- feedback status.

### Grounding presentation

Implemented badges:

- `Grounded with Knowledge`
- `Knowledge Retrieved · Not Grounded`
- `No Knowledge Match`
- `Retrieval Failed`
- `Retrieval Not Attempted`

Citation cards show controlled metadata:

- citation ID;
- document title and ID;
- document type;
- scope;
- source kind and optional source name;
- similarity score.

The page intentionally does not show the internal retrieval query, raw provider credentials, or full raw chunk text.

### Human Review controls

Supported actions:

- Accept
- Reject
- Edit & Accept

The feedback form supports an optional note. Edit & Accept also displays an editable output field.

After submission, the page refreshes the persisted analysis history.

### Analysis History

The history panel lists persisted records and lets the reviewer reopen a historical analysis in the same detail card.

### Current limitations

- no dedicated Issue Detail route;
- no comments or resolution timeline;
- Agent Run controls live on the dedicated Agent Investigation page rather than inside each Issue row;
- no knowledge-administration controls;
- no advanced filters or pagination.

## 8. AI Copilot

### Purpose

Present a lightweight overview of the available AI tasks.

The current page is informational/static. It is not a free-form chat interface and does not invoke the persisted Agent lifecycle.

It must not be described as a complete interactive copilot workspace.

## 9. AI Evaluation

### Purpose

Show Human Review outcomes for persisted analyses.

### Overview cards

- Total Analyses
- Pending Reviews
- Reviewed Analyses
- Positive Outcome Rate
- Direct Acceptance Rate
- Edit & Accept Rate
- Rejection Rate

### Provider / Model breakdown

The table displays:

- provider;
- model;
- total;
- reviewed;
- pending;
- positive outcome;
- direct acceptance;
- edit and accept;
- rejection.

### Prompt Version breakdown

The table displays:

- prompt version;
- provider;
- model;
- total;
- reviewed;
- pending;
- direct acceptance;
- edit and accept;
- rejection.

Legacy records without a prompt version are labeled `Unversioned (legacy)`.

The page reports workflow review statistics, not formal model accuracy.

## 10. Agent Investigation

### Purpose

Expose the persisted, bounded single-Agent Issue investigation workflow to an operator without moving transition ownership into the browser.

### Run selection and control

The page supports:

- selecting an existing Issue;
- starting a new Run or reusing the Issue's active Run;
- viewing Run identity, status, current node, graph version, counters, waiting time, update time, and errors;
- manually refreshing the backend-owned Run;
- cancelling a cancellable Run, including the accepted recovery-cancellation path for an active Run whose latest Step already failed.

### Human Gates

The page renders the Human Gate required by the current Run state:

- **Confirm Triage** — review or correct issue type, subtype, severity, confidence, and reason, then resume;
- **Clarification Required** — answer one focused question when approved evidence is insufficient, then resume the same Run;
- **Final Review** — accept, reject, or edit and accept the linked persisted Analysis through the existing feedback workflow.

The original generated Analysis remains immutable. Human feedback and edited output are stored through the backend contract.

### Analysis and audit presentation

The page displays:

- the generated six-field Analysis when available;
- retrieval status, provider, model, and prompt version;
- the persisted Step timeline and nested Tool Calls;
- Tool version, timeout, approval requirement, status, and read-only boundary;
- controlled Step snapshots and final Agent state.

The browser recursively hides retrieval query text, knowledge chunk text, source URI, and secret-like fields from Tool arguments, Tool results, Step snapshots, and controlled Agent state. Below-threshold evidence may remain in immutable Tool audit data while being excluded from the generation Prompt and Citation Snapshot.

### Interaction boundary

The backend remains the source of truth for every transition. The page does not register arbitrary tools, execute autonomous write actions, infer state locally, replace the existing Issues analysis page, or claim multi-agent behavior.

## 11. Shared Interaction Patterns

Implemented shared patterns include:

- sidebar route navigation;
- metric cards;
- data tables;
- inline select controls;
- create forms;
- loading states;
- error states;
- empty states;
- success and failure messages;
- controlled AI evidence cards.
- persisted execution timelines;
- explicit Human Gates and resume actions;
- controlled state redaction.

The UI prioritizes functional evidence and workflow transparency over a complete design system.

## 12. Responsive and Accessibility Boundary

The current interface is optimized for a local desktop demonstration.

It includes semantic form controls, headings, buttons, tables, and basic disabled states, but it has not completed:

- formal accessibility auditing;
- keyboard-flow acceptance;
- mobile optimization;
- localization architecture;
- visual-regression testing;
- a production design-system review.

## 13. Future UI Scope

Possible future work includes:

- authentication and user identity;
- knowledge document administration;
- Customer and Project detail pages;
- issue comments and activity history;
- reporting and export;
- advanced filters and pagination;
- richer Agent filtering, comparison, and evaluation views;
- stronger responsive and accessibility support.

These are future possibilities, not implemented pages.
