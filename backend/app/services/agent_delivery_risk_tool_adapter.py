from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.risk_analyzer import calculate_risk_level
from app.models import Issue, Project, Requirement
from app.schemas.agent_tools import (
    AgentDeliveryRiskInput,
    AgentDeliveryRiskOutput,
    AgentDeliveryRiskSignals,
)
from app.services.dashboard_service import (
    CLOSED_ISSUE_STATUSES,
    DELIVERED_REQUIREMENT_STATUSES,
)


BLOCKED_ISSUE_STATUSES = (
    "waiting_on_customer",
    "waiting_on_engineering",
)
COMPLETED_REQUIREMENT_STATUSES = tuple(
    DELIVERED_REQUIREMENT_STATUSES
)
EMPTY_REQUIREMENTS_COMPLETION_RATE = 1.0


class AgentDeliveryRiskSignalResolver:
    def resolve(
        self,
        issue_id: int,
        db: Session,
        *,
        as_of_date: date | None = None,
    ) -> AgentDeliveryRiskSignals:
        validated_input = AgentDeliveryRiskInput(
            issue_id=issue_id
        )
        issue = db.get(Issue, validated_input.issue_id)
        if issue is None:
            raise LookupError(
                f"Issue not found: {validated_input.issue_id}"
            )
        if issue.project_id is None:
            raise LookupError(
                f"Issue has no project: {validated_input.issue_id}"
            )

        project = db.get(Project, issue.project_id)
        if project is None:
            raise LookupError(
                f"Project not found for Issue: {issue.project_id}"
            )

        effective_date = as_of_date or date.today()
        project_id = project.id

        overdue_requirements = self._count(
            db,
            select(func.count())
            .select_from(Requirement)
            .where(
                Requirement.project_id == project_id,
                Requirement.due_date.is_not(None),
                Requirement.due_date < effective_date,
                Requirement.status.not_in(
                    COMPLETED_REQUIREMENT_STATUSES
                ),
            ),
        )
        blocked_issues = self._count(
            db,
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.project_id == project_id,
                Issue.status.in_(BLOCKED_ISSUE_STATUSES),
            ),
        )
        critical_issues = self._count(
            db,
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.project_id == project_id,
                Issue.severity == "critical",
                Issue.status.not_in(CLOSED_ISSUE_STATUSES),
            ),
        )
        total_requirements = self._count(
            db,
            select(func.count())
            .select_from(Requirement)
            .where(Requirement.project_id == project_id),
        )
        completed_requirements = self._count(
            db,
            select(func.count())
            .select_from(Requirement)
            .where(
                Requirement.project_id == project_id,
                Requirement.status.in_(
                    COMPLETED_REQUIREMENT_STATUSES
                ),
            ),
        )

        delivery_completion_rate = (
            EMPTY_REQUIREMENTS_COMPLETION_RATE
            if total_requirements == 0
            else completed_requirements / total_requirements
        )

        return AgentDeliveryRiskSignals(
            project_id=project_id,
            overdue_requirements=overdue_requirements,
            blocked_issues=blocked_issues,
            critical_issues=critical_issues,
            delivery_completion_rate=delivery_completion_rate,
        )

    @staticmethod
    def _count(db: Session, statement: object) -> int:
        value = db.scalar(statement)
        return int(value or 0)


class AgentDeliveryRiskToolAdapter:
    def __init__(
        self,
        resolver: AgentDeliveryRiskSignalResolver | None = None,
    ) -> None:
        self._resolver = (
            resolver or AgentDeliveryRiskSignalResolver()
        )

    def execute(
        self,
        issue_id: int,
        db: Session,
    ) -> AgentDeliveryRiskOutput:
        signals = self._resolver.resolve(issue_id, db)
        risk_level = calculate_risk_level(
            overdue_requirements=signals.overdue_requirements,
            blocked_issues=signals.blocked_issues,
            critical_issues=signals.critical_issues,
            delivery_completion_rate=(
                signals.delivery_completion_rate
            ),
        )

        return AgentDeliveryRiskOutput(
            **signals.model_dump(),
            risk_level=risk_level,
        )
