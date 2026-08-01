from __future__ import annotations

from typing import Protocol

from sqlalchemy.orm import Session

from app.ai.grounded_retrieval_service import (
    grounded_retrieval_service,
)
from app.ai.schemas import (
    GroundedRetrievalOutcome,
    KnowledgeCitationSnapshot,
    KnowledgeEvidence,
)
from app.models import Customer, Issue, Project
from app.schemas.agent_tools import (
    AgentKnowledgeCitation,
    AgentKnowledgeEvidence,
    AgentSearchKnowledgeInput,
    AgentSearchKnowledgeOutput,
)


class GroundedRetrievalPort(Protocol):
    def retrieve(
        self,
        issue: Issue,
        project: Project | None,
        customer: Customer | None,
        db: Session,
    ) -> GroundedRetrievalOutcome:
        ...


class AgentSearchKnowledgeToolAdapter:
    def __init__(
        self,
        retrieval_service: GroundedRetrievalPort | None = None,
    ) -> None:
        self._retrieval_service = (
            retrieval_service or grounded_retrieval_service
        )

    def execute(
        self,
        issue_id: int,
        db: Session,
    ) -> AgentSearchKnowledgeOutput:
        validated_input = AgentSearchKnowledgeInput(
            issue_id=issue_id
        )
        issue = db.get(Issue, validated_input.issue_id)
        if issue is None:
            raise LookupError(
                f"Issue not found: {validated_input.issue_id}"
            )

        project = (
            db.get(Project, issue.project_id)
            if issue.project_id is not None
            else None
        )
        customer = (
            db.get(Customer, project.customer_id)
            if (
                project is not None
                and project.customer_id is not None
            )
            else None
        )

        outcome = self._retrieval_service.retrieve(
            issue,
            project,
            customer,
            db,
        )

        return AgentSearchKnowledgeOutput(
            retrieval_status=outcome.retrieval_status,
            retrieval_query=outcome.retrieval_query,
            knowledge_evidence=tuple(
                self._to_agent_evidence(item)
                for item in outcome.knowledge_evidence
            ),
            knowledge_citations=tuple(
                self._to_agent_citation(item)
                for item in outcome.knowledge_citations
            ),
            retrieval_error_code=(
                outcome.retrieval_error_code
            ),
        )

    @staticmethod
    def _to_agent_evidence(
        item: KnowledgeEvidence,
    ) -> AgentKnowledgeEvidence:
        return AgentKnowledgeEvidence(
            citation_id=item.citation_id,
            rank=item.rank,
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            document_title=item.document_title,
            scope_type=item.scope_type,
            doc_type=item.doc_type,
            source_kind=item.source_kind,
            source_name=item.source_name,
            source_uri=item.source_uri,
            chunk_index=item.chunk_index,
            chunk_text=item.chunk_text,
            distance=item.distance,
            similarity_score=item.similarity_score,
        )

    @staticmethod
    def _to_agent_citation(
        item: KnowledgeCitationSnapshot,
    ) -> AgentKnowledgeCitation:
        return AgentKnowledgeCitation(
            citation_id=item.citation_id,
            rank=item.rank,
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            document_title=item.document_title,
            scope_type=item.scope_type,
            doc_type=item.doc_type,
            source_kind=item.source_kind,
            source_name=item.source_name,
            source_uri=item.source_uri,
            chunk_index=item.chunk_index,
            chunk_text=item.chunk_text,
            similarity_score=item.similarity_score,
        )


agent_search_knowledge_tool_adapter = (
    AgentSearchKnowledgeToolAdapter()
)
