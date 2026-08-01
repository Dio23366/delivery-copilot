# Delivery Copilot — As-built Page Design

## 1. Status

This document describes the React routes and interactions implemented in the current frontend.

The application is a desktop-oriented portfolio interface using React, TypeScript, Vite, React Router, and a shared sidebar layout.

There is no Login page, authentication flow, Reports page, Project Detail route, Agent lifecycle UI, or knowledge-administration UI.

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
- no Agent Run controls;
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

## 10. Shared Interaction Patterns

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

The UI prioritizes functional evidence and workflow transparency over a complete design system.

## 11. Responsive and Accessibility Boundary

The current interface is optimized for a local desktop demonstration.

It includes semantic form controls, headings, buttons, tables, and basic disabled states, but it has not completed:

- formal accessibility auditing;
- keyboard-flow acceptance;
- mobile optimization;
- localization architecture;
- visual-regression testing;
- a production design-system review.

## 12. Future UI Scope

Possible future work includes:

- authentication and user identity;
- Agent Run creation, resume, cancellation, and timeline views;
- knowledge document administration;
- Customer and Project detail pages;
- issue comments and activity history;
- reporting and export;
- advanced filters and pagination;
- stronger responsive and accessibility support.

These are future possibilities, not implemented pages.
