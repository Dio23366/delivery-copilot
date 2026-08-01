from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session, joinedload

from app.ai.issue_summarizer import IssueContext
from app.models.issue import Issue
from app.models.project import Project


class AgentIssueContextService:
    def load_issue_context(
        self,
        db: Session,
        *,
        issue_id: int,
    ) -> IssueContext:
        issue = (
            db.query(Issue)
            .options(
                joinedload(Issue.project).joinedload(
                    Project.customer
                )
            )
            .filter(Issue.id == issue_id)
            .first()
        )

        if issue is None:
            raise LookupError(
                f"Issue not found: {issue_id}"
            )

        return self.build_issue_context(issue)

    @staticmethod
    def build_issue_context(
        issue: Issue,
    ) -> IssueContext:
        project = issue.project
        customer = (
            project.customer
            if project is not None
            else None
        )

        return IssueContext(
            issue_id=issue.id,
            issue_title=issue.title,
            issue_description=issue.description,
            issue_type=issue.issue_type,
            severity=issue.severity,
            status=issue.status,
            owner=issue.owner,
            project_name=(
                project.name
                if project is not None
                else None
            ),
            project_status=(
                project.status
                if project is not None
                else None
            ),
            delivery_stage=(
                project.delivery_stage
                if project is not None
                else None
            ),
            risk_level=(
                project.risk_level
                if project is not None
                else None
            ),
            health=(
                project.health
                if project is not None
                else None
            ),
            customer_name=(
                customer.name
                if customer is not None
                else None
            ),
            customer_industry=(
                customer.industry
                if customer is not None
                else None
            ),
            customer_contact=(
                customer.contact
                if customer is not None
                else None
            ),
        )

    @staticmethod
    def serialize_issue_context(
        context: IssueContext,
    ) -> dict[str, object]:
        return dict(asdict(context))
