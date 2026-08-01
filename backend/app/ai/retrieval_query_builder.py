from __future__ import annotations

from app.models import Customer, Issue, Project


def _clean_value(value: object | None) -> str:
    if value is None:
        return 'not provided'
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or 'not provided'
    cleaned = str(value).strip()
    return cleaned or 'not provided'


def build_issue_retrieval_query(
    issue: Issue,
    project: Project | None,
    customer: Customer | None,
) -> str:
    lines = [
        f"Issue title: {_clean_value(issue.title)}",
        f"Issue description: {_clean_value(issue.description)}",
        f"Issue type: {_clean_value(issue.issue_type)}",
        f"Severity: {_clean_value(issue.severity)}",
        f"Status: {_clean_value(issue.status)}",
        f"Project name: {_clean_value(project.name if project is not None else None)}",
        f"Delivery stage: {_clean_value(project.delivery_stage if project is not None else None)}",
        f"Customer industry: {_clean_value(customer.industry if customer is not None else None)}",
    ]
    return '\n'.join(lines).strip()
