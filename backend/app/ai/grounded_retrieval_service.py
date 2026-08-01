from __future__ import annotations

import math

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.ai.retrieval_query_builder import build_issue_retrieval_query
from app.ai.schemas import (
    GroundedRetrievalOutcome,
    KnowledgeCitationSnapshot,
    KnowledgeEvidence,
)
from app.embeddings.schemas import EmbeddingResult
from app.models import Customer, Issue, Project
from app.schemas.knowledge import KnowledgeSearchRequest
from app.services.knowledge_search_service import knowledge_search_service


class GroundedRetrievalService:
    def __init__(
        self,
        knowledge_search_service=None,
    ) -> None:
        self.knowledge_search_service = knowledge_search_service or globals()['knowledge_search_service']

    def _string_value(self, value: object) -> str:
        if hasattr(value, 'value') and isinstance(getattr(value, 'value'), str):
            return getattr(value, 'value')
        if isinstance(value, str):
            return value
        return str(value)

    def _validate_result_structure(self, payload: KnowledgeSearchRequest, result) -> bool:
        if result.result_count != len(result.results):
            return False
        if result.result_count > payload.top_k:
            return False
        for index, item in enumerate(result.results, start=1):
            if item.rank != index:
                return False
            if not isinstance(item.chunk_text, str) or not item.chunk_text.strip():
                return False
            for metric in (item.distance, item.similarity_score):
                if not isinstance(metric, (int, float)) or isinstance(metric, bool) or not math.isfinite(float(metric)):
                    return False
            if abs((1 - float(item.distance)) - float(item.similarity_score)) > 1e-7:
                return False
        return True

    def _map_http_error(self, exc: HTTPException) -> str:
        status_code = exc.status_code
        if status_code == 404:
            return 'retrieval_context_not_found'
        if status_code == 422:
            return 'invalid_retrieval_response'
        if status_code == 502:
            return 'embedding_provider_failed'
        if status_code == 503:
            return 'embedding_provider_not_configured'
        if status_code == 500:
            return 'retrieval_internal_error'
        return 'retrieval_http_error'

    def retrieve(
        self,
        issue: Issue,
        project: Project | None,
        customer: Customer | None,
        db: Session,
    ) -> GroundedRetrievalOutcome:
        retrieval_query = build_issue_retrieval_query(issue, project, customer)
        payload = KnowledgeSearchRequest(query=retrieval_query, issue_id=issue.id, top_k=5)

        try:
            response = self.knowledge_search_service.search(payload, db)
        except HTTPException as exc:
            return GroundedRetrievalOutcome(
                retrieval_status='failed',
                retrieval_query=retrieval_query,
                knowledge_evidence=(),
                knowledge_citations=(),
                retrieval_error_code=self._map_http_error(exc),
            )
        except Exception:
            return GroundedRetrievalOutcome(
                retrieval_status='failed',
                retrieval_query=retrieval_query,
                knowledge_evidence=(),
                knowledge_citations=(),
                retrieval_error_code='retrieval_unexpected_error',
            )

        if not self._validate_result_structure(payload, response):
            return GroundedRetrievalOutcome(
                retrieval_status='failed',
                retrieval_query=retrieval_query,
                knowledge_evidence=(),
                knowledge_citations=(),
                retrieval_error_code='invalid_retrieval_response',
            )

        if response.result_count == 0:
            return GroundedRetrievalOutcome(
                retrieval_status='no_results',
                retrieval_query=retrieval_query,
                knowledge_evidence=(),
                knowledge_citations=(),
                retrieval_error_code=None,
            )

        evidence_items: list[KnowledgeEvidence] = []
        citation_items: list[KnowledgeCitationSnapshot] = []
        for index, item in enumerate(response.results, start=1):
            citation_id = f'K{index}'
            scope_type = self._string_value(item.scope_type)
            doc_type = self._string_value(item.doc_type)
            source_kind = self._string_value(item.source_kind)
            evidence = KnowledgeEvidence(
                citation_id=citation_id,
                rank=item.rank,
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                document_title=item.document_title,
                scope_type=scope_type,
                doc_type=doc_type,
                source_kind=source_kind,
                source_name=item.source_name,
                source_uri=item.source_uri,
                chunk_index=item.chunk_index,
                chunk_text=item.chunk_text,
                distance=float(item.distance),
                similarity_score=float(item.similarity_score),
            )
            evidence_items.append(evidence)
            citation_items.append(
                KnowledgeCitationSnapshot(
                    citation_id=citation_id,
                    rank=item.rank,
                    chunk_id=item.chunk_id,
                    document_id=item.document_id,
                    document_title=item.document_title,
                    scope_type=scope_type,
                    doc_type=doc_type,
                    source_kind=source_kind,
                    source_name=item.source_name,
                    source_uri=item.source_uri,
                    chunk_index=item.chunk_index,
                    chunk_text=item.chunk_text,
                    similarity_score=float(item.similarity_score),
                )
            )

        return GroundedRetrievalOutcome(
            retrieval_status='succeeded',
            retrieval_query=retrieval_query,
            knowledge_evidence=tuple(evidence_items),
            knowledge_citations=tuple(citation_items),
            retrieval_error_code=None,
        )


grounded_retrieval_service = GroundedRetrievalService()
