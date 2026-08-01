from __future__ import annotations

import json
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.ai.context_builder import build_issue_analysis_context
from app.ai.grounded_retrieval_service import grounded_retrieval_service
from app.ai.prompt_builder import ISSUE_SUMMARIZER_PROMPT_VERSION
from app.ai.providers.llm import LLMIssueAnalysisProvider
from app.ai.providers.rule_based import RuleBasedIssueAnalysisProvider
from app.ai.schemas import ProviderAnalysisResult
from app.models import AIAnalysisLog, Customer, Issue, Project


class IssueAnalysisService:
    def __init__(self, llm_provider=None, grounded_retrieval_service=None) -> None:
        self.llm_provider = llm_provider if llm_provider is not None else LLMIssueAnalysisProvider()
        self.grounded_retrieval_service = (
            grounded_retrieval_service if grounded_retrieval_service is not None else globals()['grounded_retrieval_service']
        )
        self.rule_based_provider = RuleBasedIssueAnalysisProvider()

    def analyze_and_store(self, issue_id: int, db: Session) -> AIAnalysisLog:
        issue = db.query(Issue).filter(Issue.id == issue_id).first()
        if issue is None:
            raise LookupError('Issue 不存在')

        project = db.query(Project).filter(Project.id == issue.project_id).first() if issue.project_id else None
        customer = (
            db.query(Customer).filter(Customer.id == project.customer_id).first()
            if project and project.customer_id
            else None
        )

        retrieval_outcome = self.grounded_retrieval_service.retrieve(issue, project, customer, db)
        context = build_issue_analysis_context(
            issue,
            project,
            customer,
            retrieval_query=retrieval_outcome.retrieval_query,
            knowledge_evidence=retrieval_outcome.knowledge_evidence,
        )
        result = self.llm_provider.analyze_issue(context)
        provider_name = self.llm_provider.last_provider_name
        model_name = self.llm_provider.last_model_name if provider_name == 'llm' else None
        prompt_version = ISSUE_SUMMARIZER_PROMPT_VERSION

        log = AIAnalysisLog(
            issue_id=issue.id,
            analysis_type='issue_summarizer',
            provider=provider_name,
            model_name=model_name,
            prompt_version=prompt_version,
            issue_summary=result.issue_summary,
            possible_root_cause=result.possible_root_cause,
            recommended_actions_json=json.dumps(result.recommended_actions, ensure_ascii=False),
            customer_update_draft=result.customer_update_draft,
            risk_level=result.risk_level,
            project_impact=result.project_impact,
            feedback_status='pending',
            feedback_note=None,
            edited_output=None,
            retrieval_status=retrieval_outcome.retrieval_status,
            retrieval_query=retrieval_outcome.retrieval_query,
            knowledge_citations_json=json.dumps(
                [asdict(citation) for citation in retrieval_outcome.knowledge_citations],
                ensure_ascii=False,
            ),
            retrieval_error_code=retrieval_outcome.retrieval_error_code,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    def get_issue_history(self, issue_id: int, db: Session) -> list[AIAnalysisLog]:
        issue = db.query(Issue).filter(Issue.id == issue_id).first()
        if issue is None:
            raise LookupError('Issue 不存在')
        return (
            db.query(AIAnalysisLog)
            .filter(AIAnalysisLog.issue_id == issue_id)
            .order_by(AIAnalysisLog.created_at.desc(), AIAnalysisLog.id.desc())
            .all()
        )


analysis_service = IssueAnalysisService()
