from __future__ import annotations

import math
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.embeddings.base import BaseEmbeddingProvider
from app.embeddings.openai_provider import (
    EmbeddingConfigurationError,
    EmbeddingProviderError,
    OpenAIEmbeddingProvider,
)
from app.embeddings.schemas import (
    BatchEmbeddingFailure,
    BatchEmbeddingResult,
    EmbeddingResult,
)
from app.models import KnowledgeChunk, KnowledgeDocument


class EmbeddingService:
    def __init__(self, provider: BaseEmbeddingProvider | None = None) -> None:
        self.provider = provider if provider is not None else OpenAIEmbeddingProvider()

    def _validate_result(self, result: EmbeddingResult) -> None:
        if not isinstance(result.provider, str) or not result.provider.strip():
            raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        if not isinstance(result.model, str) or not result.model.strip():
            raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        if not isinstance(result.embedding, list):
            raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        if (
            not isinstance(result.dimension, int)
            or isinstance(result.dimension, bool)
            or result.dimension != 1536
        ):
            raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        if len(result.embedding) != 1536:
            raise HTTPException(status_code=422, detail='Invalid embedding provider result')
        for value in result.embedding:
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                raise HTTPException(status_code=422, detail='Invalid embedding provider result')

    def embed_chunk(
        self,
        chunk_id: int,
        db: Session,
        force: bool = False,
    ) -> KnowledgeChunk:
        chunk = db.query(KnowledgeChunk).filter(KnowledgeChunk.id == chunk_id).first()
        if chunk is None:
            raise HTTPException(status_code=404, detail='Chunk not found')
        if not chunk.chunk_text.strip():
            raise HTTPException(status_code=422, detail='chunk_text must not be blank')
        if chunk.embedding is not None and not force:
            raise HTTPException(status_code=409, detail='Embedding already exists')

        try:
            result = self.provider.embed_text(chunk.chunk_text)
            self._validate_result(result)
            chunk.embedding = result.embedding
            chunk.embedding_provider = result.provider
            chunk.embedding_model = result.model
            chunk.embedding_dimension = result.dimension
            chunk.embedded_at = datetime.utcnow()
            db.commit()
            db.refresh(chunk)
            return chunk
        except EmbeddingConfigurationError as exc:
            db.rollback()
            raise HTTPException(
                status_code=503,
                detail='Embedding provider is not configured',
            ) from exc
        except EmbeddingProviderError as exc:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail='Embedding provider failed',
            ) from exc
        except HTTPException:
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise HTTPException(status_code=500, detail='Failed to embed chunk')

    def embed_document(
        self,
        document_id: int,
        db: Session,
        force: bool = False,
    ) -> BatchEmbeddingResult:
        document_exists = (
            db.query(KnowledgeDocument.id)
            .filter(KnowledgeDocument.id == document_id)
            .first()
        )
        if document_exists is None:
            raise HTTPException(status_code=404, detail='Knowledge document not found')

        chunks = (
            db.query(KnowledgeChunk)
            .filter(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.chunk_index.asc(), KnowledgeChunk.id.asc())
            .all()
        )

        succeeded = 0
        skipped = 0
        failures: list[BatchEmbeddingFailure] = []

        for chunk in chunks:
            if chunk.embedding is not None and not force:
                skipped += 1
                continue

            try:
                self.embed_chunk(chunk.id, db, force=force)
                succeeded += 1
            except HTTPException as exc:
                failures.append(
                    BatchEmbeddingFailure(
                        chunk_id=chunk.id,
                        status_code=exc.status_code,
                        detail=str(exc.detail),
                    )
                )
            except Exception:
                db.rollback()
                failures.append(
                    BatchEmbeddingFailure(
                        chunk_id=chunk.id,
                        status_code=500,
                        detail='Failed to embed chunk',
                    )
                )

        failed = len(failures)

        if failed == 0:
            batch_status = 'completed'
        elif succeeded > 0:
            batch_status = 'partial_success'
        else:
            batch_status = 'failed'

        return BatchEmbeddingResult(
            document_id=document_id,
            total=len(chunks),
            succeeded=succeeded,
            skipped=skipped,
            failed=failed,
            status=batch_status,
            failures=failures,
        )


embedding_service = EmbeddingService()