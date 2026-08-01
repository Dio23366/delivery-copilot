from __future__ import annotations

from app.ai.issue_summarizer import IssueContext, summarize_issue as summarize_issue_rule_based
from app.ai.providers.base import BaseIssueAnalysisProvider
from app.ai.schemas import IssueAnalysisContext, IssueAnalysisResult


class RuleBasedIssueAnalysisProvider(BaseIssueAnalysisProvider):
    name = 'rule_based_fallback'

    def __init__(self) -> None:
        self.last_provider_name = self.name
        self.last_model_name = None

    def analyze_issue(self, context: IssueAnalysisContext) -> IssueAnalysisResult:
        issue = context.issue
        project = context.project or {}
        customer = context.customer or {}
        rule_context = IssueContext(
            issue_id=int(issue['id']),
            issue_title=str(issue.get('title') or ''),
            issue_description=issue.get('description') if isinstance(issue.get('description'), str) else None,
            issue_type=issue.get('issue_type') if isinstance(issue.get('issue_type'), str) else None,
            severity=str(issue.get('severity') or 'medium'),
            status=str(issue.get('status') or 'open'),
            owner=issue.get('owner') if isinstance(issue.get('owner'), str) else None,
            project_name=project.get('name') if isinstance(project.get('name'), str) else None,
            project_status=project.get('status') if isinstance(project.get('status'), str) else None,
            delivery_stage=project.get('delivery_stage') if isinstance(project.get('delivery_stage'), str) else None,
            risk_level=project.get('risk_level') if isinstance(project.get('risk_level'), str) else None,
            health=project.get('health') if isinstance(project.get('health'), str) else None,
            customer_name=customer.get('name') if isinstance(customer.get('name'), str) else None,
            customer_industry=customer.get('industry') if isinstance(customer.get('industry'), str) else None,
            customer_contact=None,
        )
        result = summarize_issue_rule_based(rule_context)
        self.last_provider_name = self.name
        self.last_model_name = None
        return IssueAnalysisResult(
            issue_summary=result['issue_summary'],
            possible_root_cause=result['possible_root_cause'],
            recommended_actions=list(result['recommended_actions']),
            customer_update_draft=result['customer_update_draft'],
            risk_level=result['risk_level'],
            project_impact=result['project_impact'],
        )
