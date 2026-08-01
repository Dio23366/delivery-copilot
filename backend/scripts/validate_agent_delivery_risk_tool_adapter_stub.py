from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sys
from typing import Callable, TypeVar

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.models import Customer, Issue, Project, Requirement
from app.models.base import Base
from app.schemas.agent_tools import (
    AgentDeliveryRiskOutput,
    AgentDeliveryRiskSignals,
)
from app.services.agent_delivery_risk_tool_adapter import (
    BLOCKED_ISSUE_STATUSES,
    COMPLETED_REQUIREMENT_STATUSES,
    EMPTY_REQUIREMENTS_COMPLETION_RATE,
    AgentDeliveryRiskSignalResolver,
    AgentDeliveryRiskToolAdapter,
)
from app.services.agent_tool_registry import (
    approved_agent_tool_registry,
)
from app.services.dashboard_service import (
    CLOSED_ISSUE_STATUSES,
    DELIVERED_REQUIREMENT_STATUSES,
)


T = TypeVar("T")
AS_OF_DATE = date(2026, 7, 27)


def expect_raises(
    exception_type: type[T],
    callback: Callable[[], object],
) -> T:
    try:
        callback()
    except exception_type as exc:
        return exc
    raise AssertionError(
        f"Expected {exception_type.__name__} to be raised"
    )


def build_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Customer.__table__,
            Project.__table__,
            Requirement.__table__,
            Issue.__table__,
        ],
    )
    return Session(engine)


def seed_data(db: Session) -> None:
    projects = (
        Project(
            id=101,
            name="Primary Delivery",
            status="active",
            health="at_risk",
            risk_level="medium",
            delivery_stage="Testing",
        ),
        Project(
            id=202,
            name="Unrelated Delivery",
            status="active",
            health="critical",
            risk_level="high",
            delivery_stage="Go-live",
        ),
        Project(
            id=303,
            name="Empty Scope",
            status="planning",
            health="healthy",
            risk_level="low",
            delivery_stage="Discovery",
        ),
    )
    db.add_all(projects)

    db.add_all(
        (
            Issue(
                id=1001,
                project_id=101,
                title="Target critical issue",
                status="open",
                severity="critical",
            ),
            Issue(
                id=1002,
                project_id=101,
                title="Waiting on customer",
                status="waiting_on_customer",
                severity="medium",
            ),
            Issue(
                id=1003,
                project_id=101,
                title="Waiting on engineering",
                status="waiting_on_engineering",
                severity="critical",
            ),
            Issue(
                id=1004,
                project_id=101,
                title="Investigating critical issue",
                status="investigating",
                severity="critical",
            ),
            Issue(
                id=1005,
                project_id=101,
                title="Resolved critical issue",
                status="resolved",
                severity="critical",
            ),
            Issue(
                id=2001,
                project_id=202,
                title="Other project blocker",
                status="waiting_on_customer",
                severity="critical",
            ),
            Issue(
                id=3001,
                project_id=303,
                title="Issue without requirements",
                status="open",
                severity="low",
            ),
            Issue(
                id=4001,
                project_id=None,
                title="Unscoped issue",
                status="open",
                severity="low",
            ),
            Issue(
                id=4002,
                project_id=999,
                title="Orphan project issue",
                status="open",
                severity="low",
            ),
        )
    )

    db.add_all(
        (
            Requirement(
                id=1101,
                project_id=101,
                title="Overdue active",
                status="in_progress",
                priority="high",
                due_date=AS_OF_DATE - timedelta(days=1),
            ),
            Requirement(
                id=1102,
                project_id=101,
                title="Delivered overdue date",
                status="delivered",
                priority="medium",
                due_date=AS_OF_DATE - timedelta(days=5),
            ),
            Requirement(
                id=1103,
                project_id=101,
                title="Legacy rejected terminal",
                status="rejected",
                priority="low",
                due_date=AS_OF_DATE - timedelta(days=3),
            ),
            Requirement(
                id=1104,
                project_id=101,
                title="Future blocked",
                status="blocked",
                priority="critical",
                due_date=AS_OF_DATE + timedelta(days=2),
            ),
            Requirement(
                id=1105,
                project_id=101,
                title="Approved no due date",
                status="approved",
                priority="medium",
                due_date=None,
            ),
            Requirement(
                id=2201,
                project_id=202,
                title="Other project overdue",
                status="blocked",
                priority="critical",
                due_date=AS_OF_DATE - timedelta(days=30),
            ),
        )
    )
    db.commit()


def test_semantics_are_frozen() -> None:
    assert BLOCKED_ISSUE_STATUSES == (
        "waiting_on_customer",
        "waiting_on_engineering",
    )
    assert COMPLETED_REQUIREMENT_STATUSES == (
        DELIVERED_REQUIREMENT_STATUSES
    )
    assert COMPLETED_REQUIREMENT_STATUSES == (
        "delivered",
        "rejected",
    )
    assert CLOSED_ISSUE_STATUSES == (
        "resolved",
        "closed",
    )
    assert EMPTY_REQUIREMENTS_COMPLETION_RATE == 1.0
    print("PASS: delivery-risk semantics are frozen")


def test_project_scoped_signal_resolution(db: Session) -> None:
    resolver = AgentDeliveryRiskSignalResolver()
    signals = resolver.resolve(
        1001,
        db,
        as_of_date=AS_OF_DATE,
    )

    assert signals == AgentDeliveryRiskSignals(
        project_id=101,
        overdue_requirements=1,
        blocked_issues=2,
        critical_issues=3,
        delivery_completion_rate=0.4,
    )
    print("PASS: project-scoped delivery signals")


def test_resolved_and_terminal_rows_are_excluded(
    db: Session,
) -> None:
    signals = AgentDeliveryRiskSignalResolver().resolve(
        1001,
        db,
        as_of_date=AS_OF_DATE,
    )
    assert signals.overdue_requirements == 1
    assert signals.critical_issues == 3
    assert signals.delivery_completion_rate == 2 / 5
    print("PASS: terminal rows are excluded or completed")


def test_other_projects_do_not_leak(db: Session) -> None:
    signals = AgentDeliveryRiskSignalResolver().resolve(
        1001,
        db,
        as_of_date=AS_OF_DATE,
    )
    assert signals.overdue_requirements != 2
    assert signals.blocked_issues != 3
    assert signals.critical_issues != 4
    print("PASS: unrelated project rows do not leak")


def test_zero_requirement_project_is_neutral(
    db: Session,
) -> None:
    signals = AgentDeliveryRiskSignalResolver().resolve(
        3001,
        db,
        as_of_date=AS_OF_DATE,
    )
    assert signals.delivery_completion_rate == 1.0
    assert signals.overdue_requirements == 0

    output = AgentDeliveryRiskToolAdapter().execute(
        3001,
        db,
    )
    assert output.risk_level == "low"
    print("PASS: zero requirements use neutral completion")


def test_adapter_returns_valid_high_risk_output(
    db: Session,
) -> None:
    output = AgentDeliveryRiskToolAdapter().execute(
        1001,
        db,
    )
    assert isinstance(output, AgentDeliveryRiskOutput)
    assert output.project_id == 101
    assert output.overdue_requirements == 1
    assert output.blocked_issues == 2
    assert output.critical_issues == 3
    assert output.delivery_completion_rate == 0.4
    assert output.risk_level == "high"
    print("PASS: adapter returns controlled high-risk output")


def test_missing_issue_is_rejected(db: Session) -> None:
    error = expect_raises(
        LookupError,
        lambda: AgentDeliveryRiskSignalResolver().resolve(
            999999,
            db,
            as_of_date=AS_OF_DATE,
        ),
    )
    assert "Issue not found" in str(error)
    print("PASS: missing Issue is rejected")


def test_issue_without_project_is_rejected(
    db: Session,
) -> None:
    error = expect_raises(
        LookupError,
        lambda: AgentDeliveryRiskSignalResolver().resolve(
            4001,
            db,
            as_of_date=AS_OF_DATE,
        ),
    )
    assert "Issue has no project" in str(error)
    print("PASS: Issue without Project is rejected")


def test_missing_project_is_rejected(db: Session) -> None:
    error = expect_raises(
        LookupError,
        lambda: AgentDeliveryRiskSignalResolver().resolve(
            4002,
            db,
            as_of_date=AS_OF_DATE,
        ),
    )
    assert "Project not found" in str(error)
    print("PASS: missing Project is rejected")


def test_invalid_issue_id_is_rejected(db: Session) -> None:
    expect_raises(
        ValidationError,
        lambda: AgentDeliveryRiskToolAdapter().execute(
            0,
            db,
        ),
    )
    print("PASS: invalid issue_id is rejected")


def test_registry_target_matches_adapter() -> None:
    definition = approved_agent_tool_registry.get(
        "calculate_delivery_risk"
    )
    assert (
        definition.adapter_target
        == "AgentDeliveryRiskToolAdapter.execute"
    )
    assert definition.argument_fields == ("issue_id",)
    assert definition.result_fields == (
        "project_id",
        "overdue_requirements",
        "blocked_issues",
        "critical_issues",
        "delivery_completion_rate",
        "risk_level",
    )
    print("PASS: Registry target matches Adapter")


def test_service_source_is_read_only() -> None:
    source_path = (
        BACKEND_ROOT
        / "app"
        / "services"
        / "agent_delivery_risk_tool_adapter.py"
    )
    source = source_path.read_text(encoding="utf-8")

    forbidden_tokens = (
        "db.add(",
        "db.delete(",
        "db.commit(",
        "db.rollback(",
        "db.flush(",
        "db.refresh(",
        ".with_for_update(",
    )
    found = [
        token
        for token in forbidden_tokens
        if token in source
    ]
    assert not found, found
    assert "select(func.count())" in source
    assert "AgentDeliveryRiskOutput(" in source
    print("PASS: service source is read-only")


def main() -> None:
    test_semantics_are_frozen()

    db = build_session()
    try:
        seed_data(db)
        test_project_scoped_signal_resolution(db)
        test_resolved_and_terminal_rows_are_excluded(db)
        test_other_projects_do_not_leak(db)
        test_zero_requirement_project_is_neutral(db)
        test_adapter_returns_valid_high_risk_output(db)
        test_missing_issue_is_rejected(db)
        test_issue_without_project_is_rejected(db)
        test_missing_project_is_rejected(db)
        test_invalid_issue_id_is_rejected(db)
        test_registry_target_matches_adapter()
        test_service_source_is_read_only()
    finally:
        db.close()

    print(
        "Agent Delivery Risk Tool Adapter assertions "
        "passed (12/12)"
    )


if __name__ == "__main__":
    main()
