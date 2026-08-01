from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

from app.schemas.agent import (
    ALLOWED_AGENT_TRIAGE_ISSUE_TYPES,
    ALLOWED_AGENT_TRIAGE_SEVERITIES,
    AgentTriageResult,
)


VALID_PAYLOAD = {
    "issue_type": "API",
    "subtype": "Authentication",
    "severity": "high",
    "confidence": 0.85,
    "reason": (
        "The issue description indicates an "
        "authentication-related API failure."
    ),
}


def assert_validation_error(
    payload: dict[str, object],
    field_name: str,
) -> None:
    try:
        AgentTriageResult.model_validate(
            payload
        )
    except ValidationError as exc:
        locations = {
            tuple(error["loc"])
            for error in exc.errors()
        }

        assert (
            (field_name,) in locations
        ), (
            f"Expected validation error for "
            f"{field_name}, got {locations}"
        )
        return

    raise AssertionError(
        f"Expected validation error for "
        f"{field_name}"
    )


def test_valid_full_payload() -> None:
    result = AgentTriageResult.model_validate(
        VALID_PAYLOAD
    )

    assert result.issue_type == "API"
    assert result.subtype == "Authentication"
    assert result.severity == "high"
    assert result.confidence == 0.85
    assert result.reason


def test_confidence_zero_is_valid() -> None:
    payload = {
        **VALID_PAYLOAD,
        "confidence": 0.0,
    }

    result = AgentTriageResult.model_validate(
        payload
    )

    assert result.confidence == 0.0


def test_confidence_one_is_valid() -> None:
    payload = {
        **VALID_PAYLOAD,
        "confidence": 1.0,
    }

    result = AgentTriageResult.model_validate(
        payload
    )

    assert result.confidence == 1.0


def test_string_fields_are_trimmed() -> None:
    payload = {
        **VALID_PAYLOAD,
        "issue_type": " API ",
        "subtype": " Authentication ",
        "severity": " high ",
        "reason": " Controlled reason ",
    }

    result = AgentTriageResult.model_validate(
        payload
    )

    assert result.issue_type == "API"
    assert result.subtype == "Authentication"
    assert result.severity == "high"
    assert result.reason == "Controlled reason"


def test_unknown_issue_type_is_rejected() -> None:
    payload = {
        **VALID_PAYLOAD,
        "issue_type": "Network",
    }

    assert_validation_error(
        payload,
        "issue_type",
    )


def test_blank_subtype_is_rejected() -> None:
    payload = {
        **VALID_PAYLOAD,
        "subtype": "   ",
    }

    assert_validation_error(
        payload,
        "subtype",
    )


def test_unknown_severity_is_rejected() -> None:
    payload = {
        **VALID_PAYLOAD,
        "severity": "urgent",
    }

    assert_validation_error(
        payload,
        "severity",
    )


def test_confidence_below_zero_is_rejected() -> None:
    payload = {
        **VALID_PAYLOAD,
        "confidence": -0.01,
    }

    assert_validation_error(
        payload,
        "confidence",
    )


def test_confidence_above_one_is_rejected() -> None:
    payload = {
        **VALID_PAYLOAD,
        "confidence": 1.01,
    }

    assert_validation_error(
        payload,
        "confidence",
    )


def test_blank_reason_is_rejected() -> None:
    payload = {
        **VALID_PAYLOAD,
        "reason": "   ",
    }

    assert_validation_error(
        payload,
        "reason",
    )


def test_extra_field_is_rejected() -> None:
    payload = {
        **VALID_PAYLOAD,
        "owner": "Agent",
    }

    assert_validation_error(
        payload,
        "owner",
    )


TESTS: tuple[
    Callable[[], None],
    ...,
] = (
    test_valid_full_payload,
    test_confidence_zero_is_valid,
    test_confidence_one_is_valid,
    test_string_fields_are_trimmed,
    test_unknown_issue_type_is_rejected,
    test_blank_subtype_is_rejected,
    test_unknown_severity_is_rejected,
    test_confidence_below_zero_is_rejected,
    test_confidence_above_one_is_rejected,
    test_blank_reason_is_rejected,
    test_extra_field_is_rejected,
)


def main() -> None:
    for test in TESTS:
        test()
        print(f"passed={test.__name__}")

    expected_fields = {
        "issue_type",
        "subtype",
        "severity",
        "confidence",
        "reason",
    }

    assert (
        set(AgentTriageResult.model_fields)
        == expected_fields
    )

    assert (
        AgentTriageResult.model_config.get(
            "extra"
        )
        == "forbid"
    )

    print(
        f"validator_test_count={len(TESTS)}"
    )
    print(
        "contract_field_count="
        f"{len(expected_fields)}"
    )
    print(
        "allowed_issue_types="
        + ",".join(
            sorted(
                ALLOWED_AGENT_TRIAGE_ISSUE_TYPES
            )
        )
    )
    print(
        "allowed_severities="
        + ",".join(
            sorted(
                ALLOWED_AGENT_TRIAGE_SEVERITIES
            )
        )
    )
    print("extra_behavior=forbid")
    print(
        "agent_triage_schema_validation=passed"
    )


if __name__ == "__main__":
    main()
