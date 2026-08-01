from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app.ai.issue_summarizer import IssueContext
from app.services.agent_triage_service import (
    CONTROLLED_SUBTYPES,
    AgentTriageExhaustedError,
    AgentTriageService,
)


SERVICE_PATH = Path(
    "app/services/agent_triage_service.py"
)


def context(
    *,
    title: str,
    description: str = "",
    issue_type: str | None = None,
    severity: str = "medium",
) -> IssueContext:
    return IssueContext(
        issue_id=101,
        issue_title=title,
        issue_description=description,
        issue_type=issue_type,
        severity=severity,
        status="open",
        owner="Agent Owner",
        project_name="Agent Project",
        project_status="active",
        delivery_stage="Implementation",
        risk_level="medium",
        health="at_risk",
        customer_name="Agent Customer",
        customer_industry="Technology",
        customer_contact="agent@example.com",
    )


def test_preserves_existing_type_and_specific_subtype() -> None:
    outcome = AgentTriageService().triage(
        context(
            title="API timeout during sync",
            issue_type="API",
            severity="high",
        )
    )

    assert outcome.result.issue_type == "API"
    assert outcome.result.subtype == "timeout"
    assert outcome.result.severity == "high"
    assert outcome.result.confidence == 0.95
    assert outcome.attempt == 1
    assert "preserved" in outcome.result.reason
    assert "severity 'high' was preserved" in (
        outcome.result.reason
    )


def test_existing_type_uses_generic_subtype() -> None:
    outcome = AgentTriageService().triage(
        context(
            title="General customer data concern",
            issue_type="Data",
        )
    )

    assert outcome.result.issue_type == "Data"
    assert outcome.result.subtype == "quality"
    assert outcome.result.confidence == 0.75


def test_infers_type_and_specific_subtype() -> None:
    outcome = AgentTriageService().triage(
        context(
            title="Deployment pipeline blocked",
            issue_type=None,
            severity="critical",
        )
    )

    assert outcome.result.issue_type == "Deployment"
    assert outcome.result.subtype == "pipeline"
    assert outcome.result.severity == "critical"
    assert outcome.result.confidence == 0.85
    assert "inferred" in outcome.result.reason


def test_inferred_type_uses_generic_subtype() -> None:
    outcome = AgentTriageService().triage(
        context(
            title="Integration problem reported",
            issue_type="",
        )
    )

    assert outcome.result.issue_type == "Integration"
    assert outcome.result.subtype == "connectivity"
    assert outcome.result.confidence == 0.60


def test_retry_then_success_with_injected_generator() -> None:
    attempts: list[int] = []

    def generator(
        issue_context: IssueContext,
        attempt: int,
    ) -> Mapping[str, Any]:
        del issue_context
        attempts.append(attempt)

        if attempt == 1:
            return {
                "issue_type": "API",
                "subtype": "quality",
                "severity": "medium",
                "confidence": 0.95,
                "reason": "First candidate mismatches.",
            }

        return {
            "issue_type": "API",
            "subtype": "authentication",
            "severity": "medium",
            "confidence": 0.95,
            "reason": "Second candidate is valid.",
        }

    service = AgentTriageService(
        candidate_generator=generator
    )
    outcome = service.triage(
        context(
            title="API authentication failure",
            issue_type="API",
        )
    )

    assert attempts == [1, 2]
    assert outcome.attempt == 2
    assert outcome.result.subtype == "authentication"


def test_unclassifiable_exhausts_finite_attempts() -> None:
    service = AgentTriageService()

    try:
        service.triage(
            context(
                title="Customer reported a concern",
                description="No technical details",
                issue_type=None,
            )
        )
    except AgentTriageExhaustedError as exc:
        assert exc.code == "triage_unclassifiable"
        assert exc.attempts == 3
        assert exc.max_retries == 2
    else:
        raise AssertionError(
            "Expected triage exhaustion"
        )


def test_invalid_severity_exhausts_finite_attempts() -> None:
    service = AgentTriageService()

    try:
        service.triage(
            context(
                title="API timeout",
                issue_type="API",
                severity="urgent",
            )
        )
    except AgentTriageExhaustedError as exc:
        assert exc.code == "triage_validation_failed"
        assert exc.attempts == 3
        assert exc.max_retries == 2
    else:
        raise AssertionError(
            "Expected invalid severity exhaustion"
        )


def test_state_update_contract() -> None:
    outcome = AgentTriageService().triage(
        context(
            title="Customer API authentication failure",
            issue_type="API",
            severity="critical",
        )
    )

    state_update = outcome.to_state_update()

    assert set(state_update) == {
        "triage_suggestion",
        "triage_attempt",
        "max_retries",
    }
    assert state_update["triage_attempt"] == 1
    assert state_update["max_retries"] == 2
    assert state_update["triage_suggestion"] == {
        "issue_type": "API",
        "subtype": "authentication",
        "severity": "critical",
        "confidence": 0.95,
        "reason": outcome.result.reason,
    }


def test_all_subtypes_are_unique_and_controlled() -> None:
    all_subtypes = [
        subtype
        for values in CONTROLLED_SUBTYPES.values()
        for subtype in values
    ]

    assert len(CONTROLLED_SUBTYPES) == 5
    assert len(all_subtypes) == 32
    assert len(all_subtypes) == len(set(all_subtypes))


def test_service_source_is_pure_and_db_free() -> None:
    source = SERVICE_PATH.read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    called_attributes: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(
                alias.name
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported_modules.add(node.module)
        elif (
            isinstance(node, ast.Call)
            and isinstance(
                node.func,
                ast.Attribute,
            )
        ):
            called_attributes.add(
                node.func.attr
            )

    forbidden_import_prefixes = (
        "sqlalchemy",
        "app.models",
        "app.db",
        "app.database",
    )

    for module in imported_modules:
        assert not module.startswith(
            forbidden_import_prefixes
        )

    assert not {
        "add",
        "delete",
        "commit",
        "rollback",
        "flush",
        "execute",
        "query",
    }.intersection(called_attributes)


TESTS: tuple[Callable[[], None], ...] = (
    test_preserves_existing_type_and_specific_subtype,
    test_existing_type_uses_generic_subtype,
    test_infers_type_and_specific_subtype,
    test_inferred_type_uses_generic_subtype,
    test_retry_then_success_with_injected_generator,
    test_unclassifiable_exhausts_finite_attempts,
    test_invalid_severity_exhausts_finite_attempts,
    test_state_update_contract,
    test_all_subtypes_are_unique_and_controlled,
    test_service_source_is_pure_and_db_free,
)


def main() -> None:
    for test in TESTS:
        test()
        print(f"passed={test.__name__}")

    print(f"validator_test_count={len(TESTS)}")
    print("controlled_issue_type_count=5")
    print("controlled_subtype_count=32")
    print("default_max_retries=2")
    print("default_max_attempts=3")
    print("service_database_dependency_count=0")
    print(
        "agent_triage_service_stub_validation=passed"
    )


if __name__ == "__main__":
    main()
