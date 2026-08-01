from __future__ import annotations

import math

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.embeddings.base import BaseEmbeddingProvider
from app.embeddings.openai_provider import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    OpenAIEmbeddingProvider,
)
from app.embeddings.schemas import EmbeddingResult
from app.models import KnowledgeChunk, KnowledgeDocument
from app.schemas.knowledge import (
    KnowledgeSearchContext,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSearchResult,
    ScopeType,
)
from app.services.knowledge_search_context_resolver import (
    KnowledgeSearchContextResolver,
    knowledge_search_context_resolver,
)


class KnowledgeSearchService:
    def __init__(
        self,
        provider: BaseEmbeddingProvider | None = None,
        context_resolver: KnowledgeSearchContextResolver | None = None,
    ) -> None:
        self.provider = provider if provider is not None else OpenAIEmbeddingProvider()
        self.context_resolver = (
            context_resolver if context_resolver is not None else knowledge_search_context_resolver
        )

    def _validate_embedding_result(self, result: object) -> EmbeddingResult:
        if not isinstance(result, EmbeddingResult):
            raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        if not isinstance(result.provider, str) or not result.provider.strip():
            raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        if not isinstance(result.model, str) or not result.model.strip():
            raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        if not isinstance(result.embedding, list):
            raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        if not isinstance(result.dimension, int) or isinstance(result.dimension, bool) or result.dimension != 1536:
            raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        if len(result.embedding) != 1536:
            raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        for value in result.embedding:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        return result

    def _build_scope_filters(self, context: KnowledgeSearchContext):
        filters = [
            KnowledgeDocument.status == 'ready',
            KnowledgeChunk.embedding.is_not(None),
        ]

        scope_clauses = []
        for scope_type in context.resolved_scope_types:
            if scope_type == ScopeType.global_scope:
                scope_clauses.append(
                    and_(
                        KnowledgeDocument.scope_type == 'global',
                        KnowledgeDocument.customer_id.is_(None),
                        KnowledgeDocument.project_id.is_(None),
                    )
                )
            elif scope_type == ScopeType.customer:
                scope_clauses.append(
                    and_(
                        KnowledgeDocument.scope_type == 'customer',
                        KnowledgeDocument.customer_id == context.customer_id,
                        KnowledgeDocument.project_id.is_(None),
                    )
                )
            elif scope_type == ScopeType.project:
                scope_clauses.append(
                    and_(
                        KnowledgeDocument.scope_type == 'project',
                        KnowledgeDocument.project_id == context.project_id,
                        KnowledgeDocument.customer_id.is_(None),
                    )
                )

        if scope_clauses:
            filters.append(or_(*scope_clauses))

        return filters

    def _build_query(
        self,
        payload: KnowledgeSearchRequest,
        context: KnowledgeSearchContext,
        query_embedding: list[float],
        db: Session,
    ):
        cosine_distance_expr = KnowledgeChunk.embedding.cosine_distance(query_embedding)

        query = (
            db.query(
                KnowledgeChunk.id.label('chunk_id'),
                KnowledgeDocument.id.label('document_id'),
                KnowledgeDocument.title.label('document_title'),
                KnowledgeDocument.scope_type.label('scope_type'),
                KnowledgeDocument.customer_id.label('customer_id'),
                KnowledgeDocument.project_id.label('project_id'),
                KnowledgeDocument.doc_type.label('doc_type'),
                KnowledgeDocument.source_kind.label('source_kind'),
                KnowledgeDocument.source_name.label('source_name'),
                KnowledgeDocument.source_uri.label('source_uri'),
                KnowledgeChunk.chunk_index.label('chunk_index'),
                KnowledgeChunk.chunk_text.label('chunk_text'),
                cosine_distance_expr.label('distance'),
            )
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .filter(*self._build_scope_filters(context))
        )

        if payload.min_similarity is not None:
            query = query.filter(cosine_distance_expr <= (1 - payload.min_similarity))

        return query.order_by(
            cosine_distance_expr.asc(),
            KnowledgeDocument.id.asc(),
            KnowledgeChunk.chunk_index.asc(),
            KnowledgeChunk.id.asc(),
        ).limit(payload.top_k)

    def search(self, payload: KnowledgeSearchRequest, db: Session) -> KnowledgeSearchResponse:
        try:
            context = self.context_resolver.resolve(payload, db)
            embedding_result = self._validate_embedding_result(self.provider.embed_text(payload.query))
            query = self._build_query(payload, context, embedding_result.embedding, db)
            rows = query.all()

            results = [
                KnowledgeSearchResult(
                    rank=index + 1,
                    chunk_id=row.chunk_id,
                    document_id=row.document_id,
                    document_title=row.document_title,
                    scope_type=row.scope_type,
                    customer_id=row.customer_id,
                    project_id=row.project_id,
                    doc_type=row.doc_type,
                    source_kind=row.source_kind,
                    source_name=row.source_name,
                    source_uri=row.source_uri,
                    chunk_index=row.chunk_index,
                    chunk_text=row.chunk_text,
                    distance=float(row.distance),
                    similarity_score=1 - float(row.distance),
                )
                for index, row in enumerate(rows)
            ]

            return KnowledgeSearchResponse(
                query=payload.query,
                top_k=payload.top_k,
                min_similarity=payload.min_similarity,
                context=context,
                result_count=len(results),
                results=results,
            )
        except HTTPException:
            raise
        except EmbeddingConfigurationError:
            raise HTTPException(status_code=503, detail='Embedding provider is not configured')
        except EmbeddingProviderError:
            raise HTTPException(status_code=502, detail='Embedding provider failed')
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(status_code=500, detail='Knowledge search failed')
        except Exception:
            db.rollback()
            raise HTTPException(status_code=500, detail='Knowledge search failed')


knowledge_search_service = KnowledgeSearchService()
