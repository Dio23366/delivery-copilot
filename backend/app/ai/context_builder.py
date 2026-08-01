from __future__ import annotations

from app.ai.schemas import IssueAnalysisContext, KnowledgeEvidence
from app.models import Customer, Issue, Project


def build_issue_analysis_context(
    issue: Issue,
    project: Project | None,
    customer: Customer | None,
    *,
    retrieval_query: str | None = None,
    knowledge_evidence: tuple[KnowledgeEvidence, ...] = (),
) -> IssueAnalysisContext:
    cleaned_retrieval_query = None
    if retrieval_query is not None:
        cleaned_retrieval_query = retrieval_query.strip() or None

    return IssueAnalysisContext(
        issue={
            'id': issue.id,
            'title': issue.title,
            'description': issue.description,
            'issue_type': issue.issue_type,
            'severity': issue.severity,
            'status': issue.status,
            'owner': issue.owner,
        },
        project=(
            {
                'id': project.id,
                'name': project.name,
                'status': project.status,
                'delivery_stage': project.delivery_stage,
                'risk_level': project.risk_level,
                'health': project.health,
            }
            if project
            else None
        ),
        customer=(
            {
                'id': customer.id,
                'name': customer.name,
                'industry': customer.industry,
            }
            if customer
            else None
        ),
        retrieval_query=cleaned_retrieval_query,
        knowledge_evidence=knowledge_evidence,
    )
