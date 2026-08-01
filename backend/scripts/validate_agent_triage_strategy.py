from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path


STRATEGY_PATH = Path(
    "docs/agent/agent-triage-strategy.md"
)

JSON_BEGIN = (
    "<!-- TRIAGE_STRATEGY_JSON_BEGIN -->"
)
JSON_END = (
    "<!-- TRIAGE_STRATEGY_JSON_END -->"
)

EXPECTED_ISSUE_TYPES = [
    "API",
    "Data",
    "Deployment",
    "Configuration",
    "Integration",
]

EXPECTED_SEVERITIES = [
    "low",
    "medium",
    "high",
    "critical",
]

EXPECTED_SUBTYPES = {
    "API": [
        "authentication",
        "authorization",
        "timeout",
        "request_validation",
        "response_error",
        "rate_limit",
        "api_dependency",
    ],
    "Data": [
        "schema_mapping",
        "synchronization",
        "migration",
        "consistency",
        "quality",
        "missing_data",
        "duplication",
    ],
    "Deployment": [
        "pipeline",
        "build",
        "release",
        "environment",
        "dependency",
        "rollback",
    ],
    "Configuration": [
        "environment_variable",
        "credential",
        "permission",
        "parameter",
        "feature_flag",
        "endpoint",
    ],
    "Integration": [
        "connectivity",
        "protocol",
        "third_party_dependency",
        "webhook",
        "messaging",
        "compatibility",
    ],
}

EXPECTED_GENERIC_SUBTYPES = {
    "API": "api_dependency",
    "Data": "quality",
    "Deployment": "environment",
    "Configuration": "parameter",
    "Integration": "connectivity",
}

EXPECTED_CONFIDENCE_LEVELS = {
    "existing_type_specific_subtype": 0.95,
    "inferred_type_specific_subtype": 0.85,
    "existing_type_generic_subtype": 0.75,
    "inferred_type_generic_subtype": 0.6,
}


def load_strategy() -> tuple[str, dict[str, object]]:
    source = STRATEGY_PATH.read_text(
        encoding="utf-8"
    )

    if source.count(JSON_BEGIN) != 1:
        raise AssertionError(
            "Expected one JSON begin marker"
        )

    if source.count(JSON_END) != 1:
        raise AssertionError(
            "Expected one JSON end marker"
        )

    section = source.split(
        JSON_BEGIN,
        maxsplit=1,
    )[1].split(
        JSON_END,
        maxsplit=1,
    )[0]

    match = re.search(
        r"```json\s*(\{.*\})\s*```",
        section,
        flags=re.DOTALL,
    )

    if match is None:
        raise AssertionError(
            "Machine-readable JSON block missing"
        )

    config = json.loads(match.group(1))

    return source, config


SOURCE, CONFIG = load_strategy()


def test_version_and_generator() -> None:
    assert CONFIG["version"] == "agent_triage_v0.1"
    assert CONFIG["generator"] == "rule_based"
    assert (
        CONFIG["mutation_policy"]
        == "do_not_modify_issue"
    )


def test_issue_type_and_severity_contract() -> None:
    assert CONFIG["issue_types"] == EXPECTED_ISSUE_TYPES
    assert CONFIG["severities"] == EXPECTED_SEVERITIES
    assert (
        CONFIG["severity_policy"]
        == "preserve_valid_input"
    )


def test_controlled_subtype_vocabulary() -> None:
    assert CONFIG["subtypes"] == EXPECTED_SUBTYPES
    assert (
        CONFIG["generic_subtypes"]
        == EXPECTED_GENERIC_SUBTYPES
    )

    subtype_pattern = re.compile(
        r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$"
    )

    for issue_type, subtypes in EXPECTED_SUBTYPES.items():
        assert len(subtypes) == len(set(subtypes))
        assert subtypes

        for subtype in subtypes:
            assert subtype_pattern.fullmatch(subtype)

        assert (
            EXPECTED_GENERIC_SUBTYPES[issue_type]
            in subtypes
        )


def test_confidence_contract() -> None:
    assert (
        CONFIG["confidence_levels"]
        == EXPECTED_CONFIDENCE_LEVELS
    )

    values = set(
        CONFIG["confidence_levels"].values()
    )

    assert values == {
        0.95,
        0.85,
        0.75,
        0.6,
    }


def test_retry_contract() -> None:
    assert CONFIG["max_retries"] == 2
    assert CONFIG["max_attempts"] == 3
    assert (
        CONFIG["max_attempts"]
        == CONFIG["max_retries"] + 1
    )

    assert CONFIG["retryable_errors"] == [
        "triage_validation_failed",
        "triage_subtype_mismatch",
        "triage_unclassifiable",
    ]


def test_state_and_routing_contract() -> None:
    assert CONFIG["state_keys"] == {
        "result": "triage_suggestion",
        "attempt": "triage_attempt",
        "max_retries": "max_retries",
    }

    assert (
        CONFIG["success_next_node"]
        == "await_triage_confirmation"
    )
    assert (
        CONFIG["waiting_status"]
        == "waiting_for_triage_confirmation"
    )


def test_required_textual_commitments() -> None:
    required_text = (
        "Status: Frozen",
        "deterministic rule-based generation",
        "must not silently modify the persisted Issue",
        "maximum total attempts = 3",
        "perform no database mutation itself",
        "Runner integration is a separate subsequent unit",
    )

    for text in required_text:
        assert text in SOURCE


TESTS: tuple[Callable[[], None], ...] = (
    test_version_and_generator,
    test_issue_type_and_severity_contract,
    test_controlled_subtype_vocabulary,
    test_confidence_contract,
    test_retry_contract,
    test_state_and_routing_contract,
    test_required_textual_commitments,
)


def main() -> None:
    for test in TESTS:
        test()
        print(f"passed={test.__name__}")

    subtype_count = sum(
        len(values)
        for values in EXPECTED_SUBTYPES.values()
    )

    print(f"validator_test_count={len(TESTS)}")
    print(
        f"controlled_issue_type_count="
        f"{len(EXPECTED_ISSUE_TYPES)}"
    )
    print(
        f"controlled_severity_count="
        f"{len(EXPECTED_SEVERITIES)}"
    )
    print(
        f"controlled_subtype_count="
        f"{subtype_count}"
    )
    print("max_retries=2")
    print("max_attempts=3")
    print(
        "triage_strategy_validation=passed"
    )


if __name__ == "__main__":
    main()
