# Agent Triage Strategy v0.1

## 1. Status

- Status: Frozen
- Scope: Agent MVP first executable slice
- Strategy version: `agent_triage_v0.1`
- Initial implementation mode: deterministic rule-based generation

This document freezes the behavior required before implementing
`AgentTriageService` and the `triage_issue` Runner node.

## 2. Input and output boundary

Input:

- the existing 15-field `IssueContext`;
- controlled serializable Agent State;
- no ORM model, Session, credential, or provider object in Agent State.

Output:

- one validated `AgentTriageResult`;
- fields: `issue_type`, `subtype`, `severity`, `confidence`, `reason`;
- validation must occur before routing.

The generator must not silently modify the persisted Issue.

## 3. Issue Type policy

The only allowed Issue Type values are:

- `API`
- `Data`
- `Deployment`
- `Configuration`
- `Integration`

Selection order:

1. Preserve the current Issue Type when it is valid.
2. If the current Issue Type is missing or invalid, infer it from controlled
   category signals in the title and description.
3. If no controlled category can be identified, the attempt is
   `triage_unclassifiable`.
4. The generator must not invent a sixth Issue Type.

## 4. Controlled subtype vocabulary

All subtype values use lowercase `snake_case`.

### API

- `authentication`
- `authorization`
- `timeout`
- `request_validation`
- `response_error`
- `rate_limit`
- `api_dependency`

Generic API fallback: `api_dependency`.

### Data

- `schema_mapping`
- `synchronization`
- `migration`
- `consistency`
- `quality`
- `missing_data`
- `duplication`

Generic Data fallback: `quality`.

### Deployment

- `pipeline`
- `build`
- `release`
- `environment`
- `dependency`
- `rollback`

Generic Deployment fallback: `environment`.

### Configuration

- `environment_variable`
- `credential`
- `permission`
- `parameter`
- `feature_flag`
- `endpoint`

Generic Configuration fallback: `parameter`.

### Integration

- `connectivity`
- `protocol`
- `third_party_dependency`
- `webhook`
- `messaging`
- `compatibility`

Generic Integration fallback: `connectivity`.

A subtype must belong to the selected Issue Type.

## 5. Severity policy

Agent Triage v0.1 preserves the current valid Issue severity:

- `low`
- `medium`
- `high`
- `critical`

The first implementation must not automatically escalate or downgrade
severity based only on keywords.

An invalid or missing severity produces an invalid triage attempt and must
not be replaced with an arbitrary default.

Human confirmation may later accept or correct the suggestion.

## 6. Confidence policy

Confidence has controlled meanings:

- `0.95`: valid existing Issue Type and a high-specificity subtype signal;
- `0.85`: Issue Type inferred from controlled category and subtype signals;
- `0.75`: valid existing Issue Type with only the category's generic subtype;
- `0.60`: inferred Issue Type with only the category's generic subtype.

No other confidence value is emitted by the rule-based v0.1 generator.

Confidence describes classification evidence. It does not indicate delivery
impact, urgency, or probability of successful remediation.

## 7. Reason policy

`reason` must:

- be nonblank;
- be no longer than the `AgentTriageResult` schema limit;
- identify the controlled signal or fallback used;
- mention whether Issue Type was preserved or inferred;
- mention that severity was preserved;
- avoid secrets, credentials, raw tokens, provider endpoints, and internal
  exception dumps.

## 8. Retry policy

- `max_retries = 2`
- maximum total attempts = 3
- attempt 1 is the initial attempt;
- attempts 2 and 3 are retries.

Retryable failures:

- output fails `AgentTriageResult` validation;
- subtype does not belong to the selected Issue Type;
- classification is `triage_unclassifiable`.

Non-retryable failures:

- Issue does not exist;
- database access fails;
- Agent Run is not in the expected state;
- execution limits are already exhausted.

Retries must be finite and must not create duplicate Steps for one attempt.

## 9. State and routing policy

The successful result is serialized under:

```text
triage_suggestion
```

Attempt metadata is stored under:

```text
triage_attempt
max_retries
```

Successful routing:

```text
triage_issue
鈫?await_triage_confirmation
鈫?waiting_for_triage_confirmation
```

The suggestion is advisory. The persisted Issue fields remain unchanged until
an explicit human-confirmed business operation is implemented.

## 10. Provider boundary

The first executable slice uses a deterministic rule-based generator so that
Runner behavior, retries, state persistence, and human interruption can be
tested without network variability.

A future LLM implementation may replace the generator behind the same service
boundary, but it must obey this exact output contract, controlled vocabulary,
retry policy, and non-mutation rule.

## 11. Machine-readable frozen configuration

<!-- TRIAGE_STRATEGY_JSON_BEGIN -->
```json
{
  "version": "agent_triage_v0.1",
  "generator": "rule_based",
  "issue_types": [
    "API",
    "Data",
    "Deployment",
    "Configuration",
    "Integration"
  ],
  "severities": [
    "low",
    "medium",
    "high",
    "critical"
  ],
  "subtypes": {
    "API": [
      "authentication",
      "authorization",
      "timeout",
      "request_validation",
      "response_error",
      "rate_limit",
      "api_dependency"
    ],
    "Data": [
      "schema_mapping",
      "synchronization",
      "migration",
      "consistency",
      "quality",
      "missing_data",
      "duplication"
    ],
    "Deployment": [
      "pipeline",
      "build",
      "release",
      "environment",
      "dependency",
      "rollback"
    ],
    "Configuration": [
      "environment_variable",
      "credential",
      "permission",
      "parameter",
      "feature_flag",
      "endpoint"
    ],
    "Integration": [
      "connectivity",
      "protocol",
      "third_party_dependency",
      "webhook",
      "messaging",
      "compatibility"
    ]
  },
  "generic_subtypes": {
    "API": "api_dependency",
    "Data": "quality",
    "Deployment": "environment",
    "Configuration": "parameter",
    "Integration": "connectivity"
  },
  "confidence_levels": {
    "existing_type_specific_subtype": 0.95,
    "inferred_type_specific_subtype": 0.85,
    "existing_type_generic_subtype": 0.75,
    "inferred_type_generic_subtype": 0.6
  },
  "severity_policy": "preserve_valid_input",
  "max_retries": 2,
  "max_attempts": 3,
  "retryable_errors": [
    "triage_validation_failed",
    "triage_subtype_mismatch",
    "triage_unclassifiable"
  ],
  "state_keys": {
    "result": "triage_suggestion",
    "attempt": "triage_attempt",
    "max_retries": "max_retries"
  },
  "success_next_node": "await_triage_confirmation",
  "waiting_status": "waiting_for_triage_confirmation",
  "mutation_policy": "do_not_modify_issue"
}
```
<!-- TRIAGE_STRATEGY_JSON_END -->

## 12. Implementation boundary

The next implementation unit is `AgentTriageService`.

It must:

1. accept an `IssueContext`;
2. generate a controlled candidate;
3. validate the candidate with `AgentTriageResult`;
4. retry only within the frozen limits;
5. return the validated result and attempt metadata;
6. perform no database mutation itself.

Runner integration is a separate subsequent unit.
